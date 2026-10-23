"""Orchestration: pull from the FPL API and persist via the Store."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from fpl.api import FPLAPIError, FPLClient
from fpl.store import Store

log = logging.getLogger(__name__)

SNAPSHOT_TABLES = (
    "snapshots",
    "player_snapshots",
    "team_snapshots",
    "event_snapshots",
    "fixture_snapshots",
)


def take_snapshot(client: FPLClient, store: Store) -> int:
    bootstrap = client.bootstrap_static()
    fixtures = client.fixtures()
    sid = store.save_snapshot(bootstrap, fixtures)
    log.info("snapshot %d: %d players, %d fixtures", sid, len(bootstrap["elements"]), len(fixtures))
    return sid


def export_snapshot_parquet(store: Store, snapshot_id: int, out_dir: Path) -> Path:
    """Write one Parquet file per snapshot table under ``out_dir/snapshot_id=N/``."""
    target = out_dir / f"snapshot_id={snapshot_id}"
    target.mkdir(parents=True, exist_ok=True)
    for table in SNAPSHOT_TABLES:
        path = (target / f"{table}.parquet").as_posix()
        store.con.execute(
            f"COPY (SELECT * FROM {table} WHERE snapshot_id = ?) TO '{path}' (FORMAT parquet)",
            [snapshot_id],
        )
    return target


def sync_element_history(
    client: FPLClient,
    store: Store,
    element_ids: Iterable[int] | None = None,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """Fetch per-fixture history for each player (default: all in the latest snapshot).

    Failures on individual players are logged and skipped so one bad id doesn't abort ~700 calls.
    """
    if element_ids is None:
        element_ids = [
            r[0]
            for r in store.con.execute(
                "SELECT element_id FROM player_snapshots WHERE snapshot_id = "
                "(SELECT max(snapshot_id) FROM snapshots) ORDER BY element_id"
            ).fetchall()
        ]
    ids = list(element_ids)
    total = 0
    for i, eid in enumerate(ids, 1):
        try:
            summary = client.element_summary(eid)
        except FPLAPIError as exc:
            log.warning("element %d skipped: %s", eid, exc)
            continue
        total += store.save_element_history(eid, summary.get("history", []))
        if on_progress:
            on_progress(i, len(ids))
    return total


def sync_entry(client: FPLClient, store: Store, entry_id: int) -> int:
    """Pull a manager's GW history, transfers and per-GW picks. Returns GWs with picks stored."""
    history = client.entry_history(entry_id)
    store.save_entry_history(entry_id, history)
    store.save_entry_transfers(entry_id, client.entry_transfers(entry_id))
    stored = 0
    for gw in history.get("current", []):
        store.save_entry_picks(entry_id, gw["event"], client.entry_picks(entry_id, gw["event"]))
        stored += 1
    return stored
