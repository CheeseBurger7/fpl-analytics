"""Features for unplayed fixtures of the live season, reusing the ``build_features`` SQL.

``build_features`` reads ``hist_teams`` / ``hist_players`` / ``hist_player_gw``. ``live_features``
shadows those three names with TEMP tables on the same connection (DuckDB resolves temp first), so
the main tables are never modified:

* played live-season fixtures missing from ``hist_player_gw`` (vaastav lags the live API) are added
  from ``element_history``;
* one target-less row is added per squad player per fixture of the target gameweek, taken from
  ``fixture_snapshots`` and priced at ``player_snapshots.now_cost``.

Features for a row in gameweek G only look at gameweeks before G, so the target-less rows leak
nothing; the only inputs are results up to G-1 (check ``Live.last_played``).
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from fpl.features import FEATURE_COLUMNS, feature_sql
from fpl.optimizer import Player, Selection, optimize_squad, pick_lineup, score_selection

_SHADOWED = ("hist_player_gw", "hist_players", "hist_teams")


@dataclass(frozen=True)
class Live:
    season: str
    event: int
    snapshot_id: int
    last_played: int  # latest gameweek with results in the (shadowed) history
    columns: list[str]
    rows: list[tuple]

    def dicts(self) -> list[dict]:
        return [dict(zip(self.columns, r, strict=True)) for r in self.rows]


def _latest_snapshot(con: duckdb.DuckDBPyConnection) -> int:
    (sid,) = con.execute("SELECT MAX(snapshot_id) FROM snapshots").fetchall()[0]
    if sid is None:
        raise RuntimeError("no snapshot in the database; run `fpl snapshot`")
    return sid


def _shadow(con: duckdb.DuckDBPyConnection, season: str, event: int, sid: int) -> None:
    for t in _SHADOWED:
        con.execute(f"DROP TABLE IF EXISTS temp.{t}")
        con.execute(f"CREATE TEMP TABLE {t} AS SELECT * FROM main.{t}")
    # Teams / players of the live season that vaastav has not (yet) provided.
    con.execute(
        """
        INSERT INTO hist_teams
        SELECT ?, team_id, name FROM team_snapshots
        WHERE snapshot_id = ? AND team_id NOT IN (SELECT team_id FROM hist_teams WHERE season = ?)
        """,
        [season, sid, season],
    )
    con.execute(
        """
        INSERT INTO hist_players
        SELECT ?, element_id, CAST(json_extract(raw, '$.code') AS INTEGER), web_name,
               json_extract_string(raw, '$.first_name'), json_extract_string(raw, '$.second_name'),
               team_id, position
        FROM player_snapshots
        WHERE snapshot_id = ?
          AND element_id NOT IN (SELECT element_id FROM hist_players WHERE season = ?)
        """,
        [season, sid, season],
    )

    # Played fixtures that the live API has and vaastav does not (scores from the fixture list).
    con.execute(
        """
        INSERT INTO hist_player_gw (season, element_id, fixture_id, round, opponent_team, was_home,
                                    kickoff_time, team_h_score, team_a_score, minutes, total_points,
                                    value, influence, creativity, threat)
        SELECT ?, h.element_id, h.fixture_id, h.round, h.opponent_team, h.was_home,
               h.kickoff_time, f.team_h_score, f.team_a_score, h.minutes, h.total_points, h.value,
               CAST(json_extract_string(h.raw, '$.influence') AS DOUBLE),
               CAST(json_extract_string(h.raw, '$.creativity') AS DOUBLE),
               CAST(json_extract_string(h.raw, '$.threat') AS DOUBLE)
        FROM element_history h
        JOIN fixture_snapshots f ON f.snapshot_id = ? AND f.fixture_id = h.fixture_id
        WHERE h.round < ?
          AND NOT EXISTS (SELECT 1 FROM hist_player_gw g
                          WHERE g.season = ? AND g.element_id = h.element_id
                            AND g.fixture_id = h.fixture_id)
        """,
        [season, sid, event, season],
    )

    # Target rows: every squad player x each fixture of the target gameweek, no outcome.
    con.execute(
        """
        INSERT INTO hist_player_gw (season, element_id, fixture_id, round, opponent_team, was_home,
                                    kickoff_time, value)
        SELECT ?, p.element_id, f.fixture_id, f.event,
               CASE WHEN p.team_id = f.team_h THEN f.team_a ELSE f.team_h END,
               p.team_id = f.team_h, f.kickoff_time, p.now_cost
        FROM fixture_snapshots f
        JOIN player_snapshots p ON p.snapshot_id = f.snapshot_id
                               AND p.team_id IN (f.team_h, f.team_a)
        WHERE f.snapshot_id = ? AND f.event = ?
        """,
        [season, sid, event],
    )


def live_features(
    con: duckdb.DuckDBPyConnection, season: str, event: int, *, snapshot_id: int | None = None
) -> Live:
    """Feature rows (no target) for every player-fixture of ``event`` in ``season``.

    Columns: ``element_id, fixture_id, round, kickoff_time, ep, <FEATURE_COLUMNS>``; ``ep`` is FPL's
    own expected points for the gameweek (``ep_this`` if it is the snapshot's current gameweek,
    else ``ep_next``), a live stand-in for vaastav's ``xp``. Only price, club, position and
    ``ep`` are read from the snapshot; its running totals include the target gameweek and are
    never used.
    """
    sid = snapshot_id or _latest_snapshot(con)
    _shadow(con, season, event, sid)
    try:
        (last_played,) = con.execute(
            "SELECT MAX(round) FROM hist_player_gw WHERE season = ? AND round < ? "
            "AND minutes IS NOT NULL",
            [season, event],
        ).fetchall()[0]
        (current_gw,) = con.execute(
            "SELECT current_gw FROM snapshots WHERE snapshot_id = ?", [sid]
        ).fetchall()[0]
        ep = (
            "CAST(json_extract_string(s.raw, '$.ep_this') AS DOUBLE)"
            if current_gw == event
            else "s.ep_next"
        )
        feats = ", ".join(f"f.{c}" for c in FEATURE_COLUMNS)
        cur = con.execute(
            f"""
            WITH f AS ({feature_sql()})
            SELECT f.element_id, f.fixture_id, f.round, f.kickoff_time, {ep} AS ep, {feats}
            FROM f
            LEFT JOIN player_snapshots s ON s.snapshot_id = ? AND s.element_id = f.element_id
            WHERE f.season = ? AND f.round = ?
            ORDER BY f.element_id, f.kickoff_time
            """,
            [sid, season, event],
        )
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        for t in _SHADOWED:
            con.execute(f"DROP TABLE IF EXISTS temp.{t}")
    return Live(season, event, sid, last_played, columns, rows)


def predictions(live: Live, *, min_history: int = 5) -> dict[str, dict[int, float]]:
    """Per-player predicted points for the target gameweek (fixtures summed, DGW = sum).

    ``rolling_mean_5`` is ``pts_per_fix_5``; ``fpl_ep`` is FPL's own ``ep``. Both are restricted
    to the same players (``n_prior_fixtures >= min_history`` and no missing value), as in the
    backtest's common-row comparison.
    """
    out: dict[str, dict[int, float]] = {"rolling_mean_5": {}, "fpl_ep": {}}
    skip: set[int] = set()
    for r in live.dicts():
        i = r["element_id"]
        if r["n_prior_fixtures"] < min_history or r["pts_per_fix_5"] is None or r["ep"] is None:
            skip.add(i)
            continue
        out["rolling_mean_5"][i] = out["rolling_mean_5"].get(i, 0.0) + r["pts_per_fix_5"]
        out["fpl_ep"][i] = out["fpl_ep"].get(i, 0.0) + r["ep"]
    for preds in out.values():
        for i in skip:
            preds.pop(i, None)
    return out


def ep_model_predictions(live: Live, model, *, min_history: int = 5) -> dict[int, float]:
    """``lgbm_xp`` fed FPL's live ``ep`` in place of vaastav's ``xp`` (fixtures summed per player).

    Rows without ``ep`` or enough history are skipped, as for ``fpl_ep``. ``model`` is a fitted
    ``fpl.model.LightGBMPredictor`` with ``use_xp=True``.
    """
    rows = [r for r in live.dicts() if r["n_prior_fixtures"] >= min_history and r["ep"] is not None]
    out: dict[int, float] = {}
    for r, y in zip(rows, model.predict_rows([dict(r, xp=r["ep"]) for r in rows]), strict=True):
        out[r["element_id"]] = out.get(r["element_id"], 0.0) + y
    return out


def player_pool(
    con: duckdb.DuckDBPyConnection, live: Live, points: dict[int, float]
) -> list[Player]:
    """Optimizer pool: players with a prediction, positioned and priced from the snapshot."""
    rows = con.execute(
        "SELECT element_id, position, team_id, now_cost FROM player_snapshots "
        "WHERE snapshot_id = ?",
        [live.snapshot_id],
    ).fetchall()
    return [Player(i, pos, team, cost, points[i]) for i, pos, team, cost in rows if i in points]


def score_blind(con: duckdb.DuckDBPyConnection, frozen: dict) -> dict[str, dict]:
    """Score frozen ``blind-pick`` output on actual points against the hindsight ceiling.

    Per predictor: the fresh squad's achieved points vs ``optimize_squad`` on actuals over the same
    pool and budget, and (if present) the user's own squad vs its best hindsight lineup. Scoring
    is ``score_selection`` (no auto-subs). Raises if the gameweek is unfinished or incomplete.
    """
    gw, sid = frozen["gw"], frozen["snapshot_id"]
    # Latest snapshot, not the frozen one: only it knows whether the fixtures have finished.
    latest = _latest_snapshot(con)
    unfinished, total = con.execute(
        "SELECT COUNT(*) FILTER (WHERE NOT COALESCE(finished, false)), COUNT(*) "
        "FROM fixture_snapshots WHERE snapshot_id = ? AND event = ?",
        [latest, gw],
    ).fetchone()
    if not total or unfinished:
        raise RuntimeError(f"GW{gw} not finished ({unfinished}/{total} fixtures open)")
    actual: dict[int, float] = {}
    n_rows = 0
    for i, pts in con.execute(
        "SELECT element_id, total_points FROM element_history WHERE round = ?", [gw]
    ).fetchall():
        actual[i] = actual.get(i, 0.0) + (pts or 0)
        n_rows += 1
    if not n_rows:
        raise RuntimeError(f"no element_history rows for GW{gw}; run `fpl history`")
    info = {
        i: (pos, team, cost)
        for i, pos, team, cost in con.execute(
            "SELECT element_id, position, team_id, now_cost FROM player_snapshots "
            "WHERE snapshot_id = ?", [sid]).fetchall()
    }  # fmt: skip
    out: dict[str, dict] = {}
    for name, entry in frozen["predictors"].items():
        # Same pool as the pick: players the predictor priced (blank players score 0).
        pool = [Player(i, *info[i], actual.get(i, 0.0)) for i in map(int, entry["predicted"])]
        res = {"fresh": _result(_as_selection(entry["fresh"]), optimize_squad(pool), actual)}
        if "entry" in entry:
            sel = _as_selection(entry["entry"])
            have = {p.id for p in pool}
            padded = pool + [Player(i, *info[i], actual.get(i, 0.0))
                             for i in sel.squad if i not in have]  # fmt: skip
            res["entry"] = _result(sel, pick_lineup(padded, sel.squad), actual)
        out[name] = res
    return out


def mean_captured(scored: dict[int, dict]) -> dict[tuple[str, str], tuple[float, int]]:
    """Mean captured fraction and gameweek count per (predictor, ``fresh``/``entry``).

    ``scored`` is ``{gw: score_blind(...)}``. Only ``fresh`` fractions are comparable across
    predictors; ``entry`` ones share the user's squad, so compare them within a predictor pair.
    """
    acc: dict[tuple[str, str], list[float]] = {}
    for res in scored.values():
        for name, by_who in res.items():
            for who, r in by_who.items():
                acc.setdefault((name, who), []).append(r["captured_fraction"])
    return {k: (sum(v) / len(v), len(v)) for k, v in acc.items()}


def _as_selection(d: dict) -> Selection:
    return Selection(tuple(d["squad"]), tuple(d["xi"]), d["captain"], 0.0, d.get("cost", 0))


def _result(sel: Selection, best: Selection, actual: dict[int, float]) -> dict:
    achieved, ceiling = score_selection(sel, actual), score_selection(best, actual)
    return {"achieved": achieved, "ceiling": ceiling, "captured_fraction": achieved / ceiling,
            "captain_points": actual.get(sel.captain, 0.0)}  # fmt: skip
