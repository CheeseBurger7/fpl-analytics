"""Command line entry point: ``fpl snapshot | history | import-history | entry | backtest``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from fpl.api import FPLClient
from fpl.backtest import default_baselines, format_summary, load_dataset, run_backtest
from fpl.history import DEFAULT_CACHE, FIRST_SEASON, import_seasons, make_http, seasons_between
from fpl.ingest import export_snapshot_parquet, sync_element_history, sync_entry, take_snapshot
from fpl.store import Store

DEFAULT_DB = Path("data/processed/fpl.duckdb")
DEFAULT_PARQUET = Path("data/processed/snapshots")
LAST_COMPLETE_SEASON = "2025-26"


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

    i = sub.add_parser("import-history", help="load past seasons from vaastav/FPL dataset")
    i.add_argument("--from", dest="first", default=FIRST_SEASON, help="first season, e.g. 2016-17")
    i.add_argument("--to", dest="last", default=LAST_COMPLETE_SEASON, help="last season")
    i.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    i.add_argument("--refresh", action="store_true", help="re-download cached CSVs")

    e = sub.add_parser("entry", help="pull a manager's picks, history and transfers")
    e.add_argument(
        "entry_id",
        type=int,
        nargs="?",
        default=int(os.environ["FPL_ENTRY_ID"]) if os.environ.get("FPL_ENTRY_ID") else None,
        help="manager id (default: $FPL_ENTRY_ID)",
    )

    b = sub.add_parser("backtest", help="walk-forward evaluation of baseline predictors")
    b.add_argument("--season", action="append", help="season to evaluate (repeatable)")
    b.add_argument("--step", type=int, default=1, help="gameweeks per refit (0 = per season)")
    b.add_argument("--min-history", type=int, default=5, help="min prior fixtures to be scored")
    b.add_argument("--by-season", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "entry" and args.entry_id is None:
        parser.error("entry_id required (pass it or set FPL_ENTRY_ID)")
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
        elif args.command == "import-history":
            with make_http() as http:
                done = import_seasons(
                    http,
                    store,
                    seasons_between(args.first, args.last),
                    cache_dir=args.cache_dir,
                    refresh=args.refresh,
                    on_season=lambda s, n: print(f"{s}: {n} rows", file=sys.stderr),
                )
            print(f"{len(done)} seasons, {sum(done.values())} player-fixture rows")
        elif args.command == "backtest":
            result = run_backtest(
                load_dataset(store.con),
                default_baselines(),
                args.season or ["2023-24", "2024-25"],
                step=args.step or None,
                min_history=args.min_history,
            )
            print(format_summary(result.summary(by_season=args.by_season)))
        elif args.command == "entry":
            n = sync_entry(client, store, args.entry_id)
            print(f"{n} gameweeks of picks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
