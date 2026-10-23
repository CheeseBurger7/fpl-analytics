"""Command line entry point: ``fpl snapshot | history | entry``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from fpl.api import FPLClient
from fpl.ingest import export_snapshot_parquet, sync_element_history, sync_entry, take_snapshot
from fpl.store import Store

DEFAULT_DB = Path("data/processed/fpl.duckdb")
DEFAULT_PARQUET = Path("data/processed/snapshots")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fpl")
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="DuckDB file")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("snapshot", help="freeze bootstrap-static + fixtures")
    s.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET)
    s.add_argument("--no-parquet", action="store_true")

    h = sub.add_parser("history", help="fetch per-fixture player history")
    h.add_argument("--element", type=int, action="append", help="limit to these player ids")

    e = sub.add_parser("entry", help="pull a manager's picks, history and transfers")
    e.add_argument("entry_id", type=int)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    with Store(args.db) as store, FPLClient(min_interval=0.2) as client:
        if args.command == "snapshot":
            sid = take_snapshot(client, store)
            if not args.no_parquet:
                export_snapshot_parquet(store, sid, args.parquet_dir)
            print(f"snapshot {sid}")
        elif args.command == "history":
            n = sync_element_history(
                client,
                store,
                args.element,
                on_progress=lambda i, t: i % 50 == 0 and print(f"{i}/{t}", file=sys.stderr),
            )
            print(f"{n} history rows")
        elif args.command == "entry":
            n = sync_entry(client, store, args.entry_id)
            print(f"{n} gameweeks of picks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
