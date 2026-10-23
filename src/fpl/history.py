"""Import past seasons from the vaastav/Fantasy-Premier-League dataset into DuckDB.

Per season we read ``players_raw.csv`` (identity, team, position, cross-season ``code``) and
``gws/merged_gw.csv`` (one row per player per fixture) and ``teams.csv``. 2016-17 has no
``teams.csv`` and the repo-level ``master_team_list.csv`` stops at 2023-24, so that list is only a
fallback. CSV columns drift between seasons, so missing columns load as NULL and the whole row is
preserved in ``raw``. 2019-20 ``round`` runs to 47 (post-lockdown fixtures), not 38.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import httpx

from fpl.store import HIST_GW_COLUMNS, Store, _ts

log = logging.getLogger(__name__)

BASE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/"
USER_AGENT = "fpl-analytics/0.1 (+personal research)"
DEFAULT_CACHE = Path("data/raw/vaastav")
FIRST_SEASON = "2016-17"
MASTER_TEAMS = "master_team_list.csv"
TEAMS = "teams.csv"
PLAYERS = "players_raw.csv"
MERGED_GW = "gws/merged_gw.csv"

# destination column -> (csv column, cast); columns not listed here are handled explicitly.
_INT, _FLOAT = "int", "float"
_GW_FIELDS: dict[str, tuple[str, str]] = {
    "round": ("round", _INT), "opponent_team": ("opponent_team", _INT),
    "team_h_score": ("team_h_score", _INT), "team_a_score": ("team_a_score", _INT),
    "minutes": ("minutes", _INT), "starts": ("starts", _INT),
    "total_points": ("total_points", _INT), "goals_scored": ("goals_scored", _INT),
    "assists": ("assists", _INT), "clean_sheets": ("clean_sheets", _INT),
    "goals_conceded": ("goals_conceded", _INT), "own_goals": ("own_goals", _INT),
    "penalties_missed": ("penalties_missed", _INT), "penalties_saved": ("penalties_saved", _INT),
    "yellow_cards": ("yellow_cards", _INT), "red_cards": ("red_cards", _INT),
    "saves": ("saves", _INT), "bonus": ("bonus", _INT), "bps": ("bps", _INT),
    "influence": ("influence", _FLOAT), "creativity": ("creativity", _FLOAT),
    "threat": ("threat", _FLOAT), "ict_index": ("ict_index", _FLOAT),
    "expected_goals": ("expected_goals", _FLOAT),
    "expected_assists": ("expected_assists", _FLOAT),
    "expected_goal_involvements": ("expected_goal_involvements", _FLOAT),
    "expected_goals_conceded": ("expected_goals_conceded", _FLOAT),
    "xp": ("xP", _FLOAT), "value": ("value", _INT), "selected": ("selected", _INT),
    "transfers_in": ("transfers_in", _INT), "transfers_out": ("transfers_out", _INT),
    "transfers_balance": ("transfers_balance", _INT),
}  # fmt: skip


def _cell(value: str | None, kind: str | None = None) -> Any:
    """CSV cell -> typed value; '' and 'None' (pandas artefact in some seasons) become NULL."""
    if value is None or value.strip() in ("", "None", "nan"):
        return None
    if kind == _INT:
        return int(float(value))
    if kind == _FLOAT:
        return float(value)
    return value


def _bool(value: str | None) -> bool | None:
    v = _cell(value)
    return None if v is None else v.strip().lower() == "true"


def seasons_between(first: str, last: str) -> list[str]:
    """Inclusive list of season labels, e.g. ('2022-23', '2024-25') -> 3 labels."""
    start, end = int(first[:4]), int(last[:4])
    return [f"{y}-{(y + 1) % 100:02d}" for y in range(start, end + 1)]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
        return list(csv.DictReader(fh))


def fetch(
    http: httpx.Client, rel_path: str, cache_dir: Path, *, refresh: bool = False
) -> Path:
    """Download ``rel_path`` (relative to the dataset's data/ dir) into the cache, once."""
    target = cache_dir / rel_path
    if target.exists() and not refresh:
        return target
    resp = http.get(rel_path)
    resp.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(resp.content)
    return target


def make_http() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=60.0,
        follow_redirects=True,
    )


def parse_teams(season: str, rows: Iterable[dict[str, str]]) -> list[tuple]:
    return [(season, int(r["id"]), r["name"]) for r in rows]


def parse_master_teams(season: str, rows: Iterable[dict[str, str]]) -> list[tuple]:
    return [(season, int(r["team"]), r["team_name"]) for r in rows if r["season"] == season]


def _season_teams(
    http: httpx.Client, season: str, cache_dir: Path, *, refresh: bool
) -> list[tuple]:
    try:
        path = fetch(http, f"{season}/{TEAMS}", cache_dir, refresh=refresh)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        master = _read_csv(fetch(http, MASTER_TEAMS, cache_dir, refresh=refresh))
        return parse_master_teams(season, master)
    return parse_teams(season, _read_csv(path))


def parse_players(season: str, rows: Iterable[dict[str, str]]) -> list[tuple]:
    return [
        (
            season, int(r["id"]), _cell(r.get("code"), _INT), r.get("web_name"),
            r.get("first_name"), r.get("second_name"), _cell(r.get("team"), _INT),
            _cell(r.get("element_type"), _INT),
        )
        for r in rows
    ]  # fmt: skip


def parse_gw_rows(season: str, rows: Iterable[dict[str, str]]) -> list[tuple]:
    out = []
    for r in rows:
        element, fixture = _cell(r.get("element"), _INT), _cell(r.get("fixture"), _INT)
        if element is None or fixture is None:
            log.debug("%s: skipping row without element/fixture: %s", season, r.get("name"))
            continue
        values: dict[str, Any] = {
            "season": season,
            "element_id": element,
            "fixture_id": fixture,
            "was_home": _bool(r.get("was_home")),
            "kickoff_time": _ts(_cell(r.get("kickoff_time"))),
            "raw": json.dumps(r, separators=(",", ":")),
        }
        for dest, (src, kind) in _GW_FIELDS.items():
            values[dest] = _cell(r.get(src), kind)
        out.append(tuple(values[c] for c in HIST_GW_COLUMNS))
    return out


def import_season(
    http: httpx.Client,
    store: Store,
    season: str,
    *,
    cache_dir: Path = DEFAULT_CACHE,
    refresh: bool = False,
) -> int:
    """Download (or reuse cached) CSVs for ``season`` and replace its rows. Returns GW row count."""
    teams = _season_teams(http, season, cache_dir, refresh=refresh)
    players = _read_csv(fetch(http, f"{season}/{PLAYERS}", cache_dir, refresh=refresh))
    merged = _read_csv(fetch(http, f"{season}/{MERGED_GW}", cache_dir, refresh=refresh))
    gw_rows = parse_gw_rows(season, merged)
    store.replace_hist_season(season, teams, parse_players(season, players), gw_rows)
    log.info("%s: %d players, %d player-fixture rows", season, len(players), len(gw_rows))
    return len(gw_rows)


def import_seasons(
    http: httpx.Client,
    store: Store,
    seasons: Iterable[str],
    *,
    cache_dir: Path = DEFAULT_CACHE,
    refresh: bool = False,
    on_season: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    """Import each season; a season that fails (e.g. 404) is logged and skipped."""
    done: dict[str, int] = {}
    for season in seasons:
        try:
            done[season] = import_season(http, store, season, cache_dir=cache_dir, refresh=refresh)
        except httpx.HTTPError as exc:
            log.warning("%s skipped: %s", season, exc)
            continue
        if on_season:
            on_season(season, done[season])
    return done
