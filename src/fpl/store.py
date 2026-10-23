"""DuckDB storage for point-in-time FPL snapshots.

Every ``snapshot`` row freezes bootstrap-static + fixtures as seen at ``taken_at`` (prices,
ownership, injury flags and fixture difficulty all drift), so training can join on
``snapshot_id`` instead of leaking later state. Per-gameweek player history and a manager's own
picks/transfers are append-only facts and are upserted by natural key.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS snapshot_seq START 1;

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id INTEGER PRIMARY KEY DEFAULT nextval('snapshot_seq'),
    taken_at    TIMESTAMP NOT NULL,
    current_gw  INTEGER,   -- NULL before GW1
    next_gw     INTEGER    -- NULL after GW38
);

CREATE TABLE IF NOT EXISTS player_snapshots (
    snapshot_id INTEGER NOT NULL,
    element_id  INTEGER NOT NULL,
    web_name    VARCHAR,
    team_id     INTEGER,
    position    INTEGER,   -- element_type: 1 GKP, 2 DEF, 3 MID, 4 FWD
    now_cost    INTEGER,   -- tenths of a million
    selected_by_percent DOUBLE,
    form        DOUBLE,
    status      VARCHAR,
    chance_of_playing_next_round INTEGER,
    minutes     INTEGER,
    total_points INTEGER,
    goals_scored INTEGER,
    assists     INTEGER,
    clean_sheets INTEGER,
    bonus       INTEGER,
    bps         INTEGER,
    expected_goals DOUBLE,
    expected_assists DOUBLE,
    expected_goal_involvements DOUBLE,
    expected_goals_conceded DOUBLE,
    ep_next     DOUBLE,
    transfers_in_event INTEGER,
    transfers_out_event INTEGER,
    cost_change_event INTEGER,
    raw         JSON,
    PRIMARY KEY (snapshot_id, element_id)
);

CREATE TABLE IF NOT EXISTS team_snapshots (
    snapshot_id INTEGER NOT NULL,
    team_id     INTEGER NOT NULL,
    name        VARCHAR,
    short_name  VARCHAR,
    strength    INTEGER,
    strength_overall_home INTEGER,
    strength_overall_away INTEGER,
    strength_attack_home INTEGER,
    strength_attack_away INTEGER,
    strength_defence_home INTEGER,
    strength_defence_away INTEGER,
    raw         JSON,
    PRIMARY KEY (snapshot_id, team_id)
);

CREATE TABLE IF NOT EXISTS event_snapshots (
    snapshot_id INTEGER NOT NULL,
    event_id    INTEGER NOT NULL,
    deadline_time TIMESTAMP,
    finished    BOOLEAN,
    is_current  BOOLEAN,
    is_next     BOOLEAN,
    average_entry_score INTEGER,
    highest_score INTEGER,
    PRIMARY KEY (snapshot_id, event_id)
);

CREATE TABLE IF NOT EXISTS fixture_snapshots (
    snapshot_id INTEGER NOT NULL,
    fixture_id  INTEGER NOT NULL,
    event       INTEGER,   -- NULL while unscheduled
    kickoff_time TIMESTAMP,
    team_h      INTEGER,
    team_a      INTEGER,
    team_h_difficulty INTEGER,
    team_a_difficulty INTEGER,
    team_h_score INTEGER,
    team_a_score INTEGER,
    finished    BOOLEAN,
    PRIMARY KEY (snapshot_id, fixture_id)
);

-- One row per player per fixture (a double gameweek yields two rows for the same round).
CREATE TABLE IF NOT EXISTS element_history (
    element_id  INTEGER NOT NULL,
    fixture_id  INTEGER NOT NULL,
    round       INTEGER,
    opponent_team INTEGER,
    was_home    BOOLEAN,
    kickoff_time TIMESTAMP,
    minutes     INTEGER,
    total_points INTEGER,
    goals_scored INTEGER,
    assists     INTEGER,
    clean_sheets INTEGER,
    bonus       INTEGER,
    bps         INTEGER,
    expected_goals DOUBLE,
    expected_assists DOUBLE,
    expected_goal_involvements DOUBLE,
    expected_goals_conceded DOUBLE,
    value       INTEGER,   -- price at that fixture, tenths of a million
    selected    INTEGER,
    transfers_balance INTEGER,
    raw         JSON,
    PRIMARY KEY (element_id, fixture_id)
);

CREATE TABLE IF NOT EXISTS entry_picks (
    entry_id    INTEGER NOT NULL,
    gameweek    INTEGER NOT NULL,
    element_id  INTEGER NOT NULL,
    slot        INTEGER,   -- 1-11 starters, 12-15 bench
    multiplier  INTEGER,
    is_captain  BOOLEAN,
    is_vice_captain BOOLEAN,
    PRIMARY KEY (entry_id, gameweek, element_id)
);

CREATE TABLE IF NOT EXISTS entry_gameweeks (
    entry_id    INTEGER NOT NULL,
    gameweek    INTEGER NOT NULL,
    points      INTEGER,
    total_points INTEGER,
    rank        INTEGER,
    overall_rank INTEGER,
    bank        INTEGER,
    value       INTEGER,
    event_transfers INTEGER,
    event_transfers_cost INTEGER,
    points_on_bench INTEGER,
    active_chip VARCHAR,
    PRIMARY KEY (entry_id, gameweek)
);

CREATE TABLE IF NOT EXISTS entry_transfers (
    entry_id    INTEGER NOT NULL,
    gameweek    INTEGER NOT NULL,
    transferred_at TIMESTAMP NOT NULL,
    element_in  INTEGER NOT NULL,
    element_out INTEGER NOT NULL,
    element_in_cost INTEGER,
    element_out_cost INTEGER,
    PRIMARY KEY (entry_id, element_in, element_out, transferred_at)
);
"""


def _num(value: Any, cast: type = float) -> Any:
    """The API serialises many numerics as strings ("0.12"); tolerate None/empty."""
    if value is None or value == "":
        return None
    return cast(value)


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def _json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"))


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute(SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _insert(self, table: str, rows: Sequence[Sequence[Any]], *, replace: bool = False) -> None:
        if not rows:
            return
        verb = "INSERT OR REPLACE" if replace else "INSERT"
        marks = ",".join("?" * len(rows[0]))
        self.con.executemany(f"{verb} INTO {table} VALUES ({marks})", list(rows))

    # -- snapshots ---------------------------------------------------------------------------

    def save_snapshot(
        self,
        bootstrap: dict[str, Any],
        fixtures: list[dict[str, Any]],
        *,
        taken_at: datetime | None = None,
    ) -> int:
        events = bootstrap["events"]
        current = next((e["id"] for e in events if e.get("is_current")), None)
        nxt = next((e["id"] for e in events if e.get("is_next")), None)
        taken_at = (taken_at or datetime.now(UTC)).replace(tzinfo=None)

        self.con.execute("BEGIN")
        try:
            sid = self.con.execute(
                "INSERT INTO snapshots (taken_at, current_gw, next_gw) VALUES (?, ?, ?) "
                "RETURNING snapshot_id",
                [taken_at, current, nxt],
            ).fetchone()[0]
            players = [self._player_row(sid, e) for e in bootstrap["elements"]]
            self._insert("player_snapshots", players)
            self._insert("team_snapshots", [self._team_row(sid, t) for t in bootstrap["teams"]])
            self._insert("event_snapshots", [self._event_row(sid, e) for e in events])
            self._insert("fixture_snapshots", [self._fixture_row(sid, f) for f in fixtures])
            self.con.execute("COMMIT")
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        return sid

    @staticmethod
    def _player_row(sid: int, e: dict[str, Any]) -> tuple:
        return (
            sid, e["id"], e.get("web_name"), e.get("team"), e.get("element_type"),
            e.get("now_cost"), _num(e.get("selected_by_percent")), _num(e.get("form")),
            e.get("status"), e.get("chance_of_playing_next_round"), e.get("minutes"),
            e.get("total_points"), e.get("goals_scored"), e.get("assists"),
            e.get("clean_sheets"), e.get("bonus"), e.get("bps"),
            _num(e.get("expected_goals")), _num(e.get("expected_assists")),
            _num(e.get("expected_goal_involvements")), _num(e.get("expected_goals_conceded")),
            _num(e.get("ep_next")), e.get("transfers_in_event"), e.get("transfers_out_event"),
            e.get("cost_change_event"), _json(e),
        )  # fmt: skip

    @staticmethod
    def _team_row(sid: int, t: dict[str, Any]) -> tuple:
        return (
            sid, t["id"], t.get("name"), t.get("short_name"), t.get("strength"),
            t.get("strength_overall_home"), t.get("strength_overall_away"),
            t.get("strength_attack_home"), t.get("strength_attack_away"),
            t.get("strength_defence_home"), t.get("strength_defence_away"), _json(t),
        )  # fmt: skip

    @staticmethod
    def _event_row(sid: int, e: dict[str, Any]) -> tuple:
        return (
            sid, e["id"], _ts(e.get("deadline_time")), e.get("finished"), e.get("is_current"),
            e.get("is_next"), e.get("average_entry_score"), e.get("highest_score"),
        )  # fmt: skip

    @staticmethod
    def _fixture_row(sid: int, f: dict[str, Any]) -> tuple:
        return (
            sid, f["id"], f.get("event"), _ts(f.get("kickoff_time")), f.get("team_h"),
            f.get("team_a"), f.get("team_h_difficulty"), f.get("team_a_difficulty"),
            f.get("team_h_score"), f.get("team_a_score"), f.get("finished"),
        )  # fmt: skip

    # -- element history ---------------------------------------------------------------------

    def save_element_history(self, element_id: int, history: Iterable[dict[str, Any]]) -> int:
        rows = [
            (
                element_id, h["fixture"], h.get("round"), h.get("opponent_team"),
                h.get("was_home"), _ts(h.get("kickoff_time")), h.get("minutes"),
                h.get("total_points"), h.get("goals_scored"), h.get("assists"),
                h.get("clean_sheets"), h.get("bonus"), h.get("bps"),
                _num(h.get("expected_goals")), _num(h.get("expected_assists")),
                _num(h.get("expected_goal_involvements")), _num(h.get("expected_goals_conceded")),
                h.get("value"), h.get("selected"), h.get("transfers_balance"), _json(h),
            )  # fmt: skip
            for h in history
        ]
        self._insert("element_history", rows, replace=True)
        return len(rows)

    # -- manager data ------------------------------------------------------------------------

    def save_entry_picks(self, entry_id: int, gameweek: int, picks: dict[str, Any]) -> None:
        rows = [
            (entry_id, gameweek, p["element"], p["position"], p["multiplier"],
             p["is_captain"], p["is_vice_captain"])
            for p in picks["picks"]
        ]  # fmt: skip
        self._insert("entry_picks", rows, replace=True)

    def save_entry_history(self, entry_id: int, history: dict[str, Any]) -> None:
        chips = {c["event"]: c["name"] for c in history.get("chips", [])}
        rows = [
            (entry_id, g["event"], g.get("points"), g.get("total_points"), g.get("rank"),
             g.get("overall_rank"), g.get("bank"), g.get("value"), g.get("event_transfers"),
             g.get("event_transfers_cost"), g.get("points_on_bench"), chips.get(g["event"]))
            for g in history.get("current", [])
        ]  # fmt: skip
        self._insert("entry_gameweeks", rows, replace=True)

    def save_entry_transfers(self, entry_id: int, transfers: Iterable[dict[str, Any]]) -> None:
        rows = [
            (entry_id, t["event"], _ts(t["time"]), t["element_in"], t["element_out"],
             t.get("element_in_cost"), t.get("element_out_cost"))
            for t in transfers
        ]  # fmt: skip
        self._insert("entry_transfers", rows, replace=True)
