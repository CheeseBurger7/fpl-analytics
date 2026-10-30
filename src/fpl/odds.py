"""Import Premier League match odds from football-data.co.uk into DuckDB (``match_odds``).

One CSV per season (``mmz4281/2425/E0.csv``): result plus odds from several bookmakers, 380 matches
per season from 2016-17. Over/Under 2.5, Asian handicap and market-average columns exist from
2019-20 (missing columns load as NULL). The 2026-27 file grows weekly, so refresh it. Club names
are matched to ``hist_teams`` of the same season to fill the team ids; matches whose clubs cannot
be matched keep NULL ids and are logged.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from fpl.store import ODDS_COLUMNS, Store

log = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281/"
USER_AGENT = "fpl-analytics/0.1 (+personal research)"
DEFAULT_CACHE = Path("data/raw/footballdata")

# destination column -> football-data column
_ODDS_FIELDS = {
    "b365_h": "B365H", "b365_d": "B365D", "b365_a": "B365A",
    "ps_h": "PSH", "ps_d": "PSD", "ps_a": "PSA",
    "avg_h": "AvgH", "avg_d": "AvgD", "avg_a": "AvgA",
    "avg_over25": "Avg>2.5", "avg_under25": "Avg<2.5",
    "ah_line": "AHh", "avg_ah_h": "AvgAHH", "avg_ah_a": "AvgAHA",
    "psc_h": "PSCH", "psc_d": "PSCD", "psc_a": "PSCA",
    "avgc_h": "AvgCH", "avgc_d": "AvgCD", "avgc_a": "AvgCA",
}  # fmt: skip

# lower-case spelling -> shared key, for the clubs that football-data and vaastav spell differently
_ALIASES = {
    "man united": "man utd", "manchester united": "man utd", "manchester city": "man city",
    "tottenham": "spurs", "tottenham hotspur": "spurs", "sheffield united": "sheffield utd",
    "coventry": "coventry city", "hull": "hull city", "ipswich": "ipswich town",
    "leicester": "leicester city", "norwich": "norwich city", "cardiff": "cardiff city",
    "swansea": "swansea city", "stoke": "stoke city", "huddersfield": "huddersfield town",
    "wolverhampton wanderers": "wolves", "west bromwich albion": "west brom",
    "newcastle united": "newcastle", "leeds united": "leeds", "west ham united": "west ham",
    "brighton and hove albion": "brighton", "nottingham forest": "nott'm forest",
    "luton town": "luton", "afc bournemouth": "bournemouth",
}  # fmt: skip


def team_key(name: str) -> str:
    """Spelling-independent club key, e.g. 'Man United' and 'Man Utd' -> 'man utd'."""
    n = name.strip().lower()
    return _ALIASES.get(n, n)


def season_code(season: str) -> str:
    """'2024-25' -> '2425'."""
    return season[2:4] + season[5:7]


def _cell(value: str | None) -> float | None:
    if value is None or value.strip() in ("", "NA"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {value!r}")


def parse_odds_rows(
    season: str, rows: Iterable[dict[str, str]], team_ids: dict[str, int] | None = None
) -> list[tuple]:
    """CSV rows -> ``ODDS_COLUMNS`` tuples. ``team_ids`` maps ``team_key`` -> hist team id."""
    team_ids = team_ids or {}
    out = []
    for r in rows:
        home, away = (r.get("HomeTeam") or "").strip(), (r.get("AwayTeam") or "").strip()
        if not home or not away or not (r.get("Date") or "").strip():
            continue  # trailing blank lines
        hid, aid = team_ids.get(team_key(home)), team_ids.get(team_key(away))
        if team_ids and (hid is None or aid is None):
            log.warning("%s: %s v %s not matched to hist_teams", season, home, away)
        hg, ag = _cell(r.get("FTHG")), _cell(r.get("FTAG"))
        values: dict[str, Any] = {
            "season": season, "match_date": _date(r["Date"]), "home_team": home,
            "away_team": away, "home_team_id": hid, "away_team_id": aid,
            "home_goals": None if hg is None else int(hg),
            "away_goals": None if ag is None else int(ag),
            "raw": json.dumps(r, separators=(",", ":")),
        }  # fmt: skip
        for dest, src in _ODDS_FIELDS.items():
            values[dest] = _cell(r.get(src))
        out.append(tuple(values[c] for c in ODDS_COLUMNS))
    return out


def make_http() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL, headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True
    )


def fetch(http: httpx.Client, season: str, cache_dir: Path, *, refresh: bool = False) -> Path:
    """Download the season's E0.csv into the cache, once unless ``refresh``."""
    target = cache_dir / f"{season_code(season)}.csv"
    if target.exists() and not refresh:
        return target
    resp = http.get(f"{season_code(season)}/E0.csv")
    resp.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(resp.content)
    return target


def _hist_team_ids(store: Store, season: str) -> dict[str, int]:
    rows = store.con.execute(
        "SELECT name, team_id FROM hist_teams WHERE season = ?", [season]
    ).fetchall()
    return {team_key(n): i for n, i in rows if n}


def import_odds_season(
    http: httpx.Client,
    store: Store,
    season: str,
    *,
    cache_dir: Path = DEFAULT_CACHE,
    refresh: bool = False,
) -> int:
    """Download (or reuse cached) the season odds CSV, replace its rows; returns the match count."""
    path = fetch(http, season, cache_dir, refresh=refresh)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = parse_odds_rows(season, csv.DictReader(io.StringIO(text)), _hist_team_ids(store, season))
    store.replace_odds_season(season, rows)
    log.info("%s: %d matches with odds", season, len(rows))
    return len(rows)


def import_odds_seasons(
    http: httpx.Client,
    store: Store,
    seasons: Iterable[str],
    *,
    cache_dir: Path = DEFAULT_CACHE,
    refresh: bool = False,
    on_season: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    """Import each season; one that fails (e.g. 404) is logged and skipped."""
    done: dict[str, int] = {}
    for season in seasons:
        try:
            done[season] = import_odds_season(
                http, store, season, cache_dir=cache_dir, refresh=refresh
            )
        except httpx.HTTPError as exc:
            log.warning("%s skipped: %s", season, exc)
            continue
        if on_season:
            on_season(season, done[season])
    return done
