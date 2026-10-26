"""Command line entry point: ``fpl snapshot|history|import-history|entry|backtest|blind-*``."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from fpl.api import FPLClient
from fpl.backtest import default_baselines, format_summary, load_dataset, run_backtest
from fpl.history import DEFAULT_CACHE, FIRST_SEASON, import_seasons, make_http, seasons_between
from fpl.ingest import export_snapshot_parquet, sync_element_history, sync_entry, take_snapshot
from fpl.live import live_features, mean_captured, player_pool, predictions, score_blind
from fpl.optimizer import CapturedFractionHook, Player, optimize_squad, pick_lineup
from fpl.planner import best_plan, horizon_predictions, plan_transfers
from fpl.store import Store

DEFAULT_DB = Path("data/processed/fpl.duckdb")
DEFAULT_PARQUET = Path("data/processed/snapshots")
DEFAULT_BLIND_DIR = Path("data/processed")
LAST_COMPLETE_SEASON = "2025-26"
CURRENT_SEASON = "2026-27"


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
    b.add_argument("--model", action="store_true",
                   help="add LightGBM predictors lgbm / lgbm_xp (needs lightgbm; slow)")
    b.add_argument("--captured", action="store_true",
                   help="add ILP captured-fraction metric (needs scipy; slow)")

    bp = sub.add_parser("blind-pick", help="freeze predictions and lineups for a gameweek")
    bp.add_argument("--season", default=CURRENT_SEASON)
    bp.add_argument("--gw", type=int, required=True)
    bp.add_argument("--entry-id", type=int, default=None, help="also pick for this manager")
    bp.add_argument("--out", type=Path, default=None, help="default blind_gw<N>.json")
    bp.add_argument("--model", action="store_true",
                    help="also freeze lgbm_xp fed FPL's ep as xp (needs lightgbm; ~15s to train)")

    bs = sub.add_parser("blind-score", help="score a frozen blind-pick file")
    bs.add_argument("--gw", type=int, help="one gameweek (default blind_gw<N>.json)")
    bs.add_argument("--all", action="store_true",
                    help="score every data/processed/blind_gw*.json that has finished, with means")
    bs.add_argument("--file", type=Path, default=None, help="default blind_gw<N>.json")

    t = sub.add_parser("transfers", help="best transfers before a gameweek over a horizon")
    t.add_argument("--season", default=CURRENT_SEASON)
    t.add_argument("--gw", type=int, required=True, help="the gameweek about to start")
    t.add_argument("--entry-id", type=int, default=None, help="default $FPL_ENTRY_ID")
    t.add_argument("--horizon", type=int, default=4, help="gameweeks to look ahead")
    t.add_argument("--free", type=int, default=1, help="free transfers available")
    t.add_argument("--max-transfers", type=int, default=3)
    t.add_argument("--discount", type=float, default=1.0, help="weight per later gameweek")
    t.add_argument("--predictor", default="lgbm_xp",
                   choices=["lgbm", "lgbm_xp", "rolling_mean_5", "fpl_ep"])

    pb = sub.add_parser("backtest-planner", help="season-long transfer planner vs hold, on actuals")
    pb.add_argument("--season", action="append", help="season to evaluate (repeatable)")
    pb.add_argument("--predictor", action="append", choices=["fpl_xp", "lgbm_xp"],
                    help="repeatable; default both")
    pb.add_argument("--horizon", type=int, default=1, help="gameweeks to look ahead (1 = no leak)")
    pb.add_argument("--discount", type=float, default=1.0)
    pb.add_argument("--min-history", type=int, default=5)
    return p


def _model_predictors() -> list:
    from fpl.model import model_predictors  # optional dependency

    return model_predictors()


def planner_backtest(store: Store, args: argparse.Namespace) -> None:
    from fpl.backtest import ColumnPredictor
    from fpl.planbacktest import (
        DEFAULT_POLICIES,
        ceiling_points,
        season_inputs,
        simulate,
        start_squad,
        summarize,
    )

    wanted = args.predictor or ["fpl_xp", "lgbm_xp"]
    preds = [ColumnPredictor("fpl_xp", "xp")] if "fpl_xp" in wanted else []
    if "lgbm_xp" in wanted:
        preds.append(_model_predictors()[1])
    data = load_dataset(store.con)
    for season in args.season or ["2023-24", "2024-25"]:
        inputs, info = season_inputs(data, preds, season, store.con, min_history=args.min_history)
        first = next(iter(inputs.values()))
        ceiling = sum(ceiling_points(g, info) for g in first)
        print(f"== {season}, horizon {args.horizon}: hindsight ceiling {ceiling:.0f} "
              f"({ceiling / len(first):.1f}/GW, fresh squad each GW)")  # fmt: skip
        for name, gws in inputs.items():
            start = start_squad(gws[0], info)
            runs = [simulate(gws, info, pol, horizon=args.horizon, discount=args.discount,
                             start=start) for pol in DEFAULT_POLICIES]  # fmt: skip
            print(f"-- predictor {name}")
            print(format_summary(summarize(runs)), flush=True)


def suggest_transfers(store: Store, args: argparse.Namespace, entry_id: int) -> None:
    con = store.con
    (sid,) = con.execute("SELECT MAX(snapshot_id) FROM snapshots").fetchone()
    (pick_gw,) = con.execute(
        "SELECT MAX(gameweek) FROM entry_picks WHERE entry_id = ? AND gameweek <= ?",
        [entry_id, args.gw],
    ).fetchone()
    if pick_gw is None:
        raise SystemExit("no stored picks for this entry; run `fpl entry`")
    squad = [r[0] for r in con.execute(
        "SELECT element_id FROM entry_picks WHERE entry_id = ? AND gameweek = ?",
        [entry_id, pick_gw]).fetchall()]  # fmt: skip
    (bank,) = con.execute(
        "SELECT bank FROM entry_gameweeks WHERE entry_id = ? AND gameweek = ?", [entry_id, pick_gw]
    ).fetchone()
    info = con.execute(
        "SELECT element_id, web_name, position, team_id, now_cost FROM player_snapshots "
        "WHERE snapshot_id = ?", [sid]).fetchall()  # fmt: skip
    names = {r[0]: r[1] for r in info}
    pool = [Player(i, pos, team, cost, 0.0) for i, _, pos, team, cost in info]
    pts = horizon_predictions(con, args.season, args.gw, args.horizon, args.predictor)
    plans = plan_transfers(
        pool, pts, squad, bank=bank or 0, free_transfers=args.free,
        max_transfers=args.max_transfers, discount=args.discount,
    )  # fmt: skip
    best = best_plan(plans)
    print(f"squad from GW{pick_gw}, bank {(bank or 0) / 10:.1f}, {args.free} free, "
          f"{args.predictor}, GW{args.gw}-{args.gw + args.horizon - 1}")  # fmt: skip
    for p in plans:
        mark = "  <-- best" if p is best else ""
        print(f"{p.transfers} transfers: net {p.net:6.1f} (gross {p.gross:6.1f}, hit {p.hit}), "
              f"out [{_names(names, p.out)}] in [{_names(names, p.into)}]{mark}")  # fmt: skip
    print(f"{plans[0].net:.1f} for the unchanged squad; best gains {best.net - plans[0].net:+.1f}")
    print(f"captain GW{args.gw}: {names[best.captain[0]]}")


def _names(names: dict[int, str], ids: tuple[int, ...]) -> str:
    return ", ".join(names[i] for i in ids)


def blind_pick(
    store: Store, season: str, gw: int, entry_id: int | None, out: Path, model: bool = False
) -> None:
    live = live_features(store.con, season, gw)
    names = dict(store.con.execute(
        "SELECT element_id, web_name FROM player_snapshots WHERE snapshot_id = ?",
        [live.snapshot_id],
    ).fetchall())
    squad: list[int] = []
    if entry_id is not None:
        squad = [r[0] for r in store.con.execute(
            "SELECT element_id FROM entry_picks WHERE entry_id = ? AND gameweek = ?", [entry_id, gw]
        ).fetchall()]
    result: dict = {"season": season, "gw": gw, "snapshot_id": live.snapshot_id,
                    "last_played": live.last_played, "predictors": {}}  # fmt: skip
    preds = predictions(live)
    if model:
        from fpl.live import ep_model_predictions

        lgbm = _model_predictors()[1]  # lgbm_xp
        data = load_dataset(store.con)
        lgbm.fit(data, range(len(data)))
        preds["lgbm_xp(ep)"] = ep_model_predictions(live, lgbm)
    for name, pred in preds.items():
        pool = player_pool(store.con, live, pred)
        fresh = optimize_squad(pool)
        entry: dict = {"predicted": {str(i): v for i, v in pred.items()},
                       "fresh": {"squad": fresh.squad, "xi": fresh.xi, "captain": fresh.captain,
                                 "predicted_points": fresh.objective,
                                 "cost": fresh.cost}}  # fmt: skip
        if squad:  # squad members without a prediction (cold start) are valued at 0
            ids = {p.id for p in pool}
            padded = pool + [
                Player(i, pos, team, cost, 0.0)
                for i, pos, team, cost in store.con.execute(
                    "SELECT element_id, position, team_id, now_cost FROM player_snapshots "
                    "WHERE snapshot_id = ?", [live.snapshot_id]).fetchall()
                if i in squad and i not in ids
            ]  # fmt: skip
            mine = pick_lineup(padded, squad)
            entry["entry"] = {"squad": mine.squad, "xi": mine.xi, "captain": mine.captain,
                              "predicted_points": mine.objective}  # fmt: skip
        result["predictors"][name] = entry
        print(f"{name}: fresh XI {_names(names, fresh.xi)} (C {names[fresh.captain]}), "
              f"{fresh.objective:.1f} pts, cost {fresh.cost / 10:.1f}")  # fmt: skip
        if "entry" in entry:
            print(f"  your XI {_names(names, mine.xi)} (C {names[mine.captain]}), "
                  f"{mine.objective:.1f} pts")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"frozen to {out}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # player names; the Windows default is cp1252
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
                default_baselines() + (_model_predictors() if args.model else []),
                args.season or ["2023-24", "2024-25"],
                step=args.step or None,
                min_history=args.min_history,
                hooks=[CapturedFractionHook(store.con)] if args.captured else (),
            )
            print(format_summary(result.summary(by_season=args.by_season)))
        elif args.command == "backtest-planner":
            planner_backtest(store, args)
        elif args.command == "blind-pick":
            env_id = os.environ.get("FPL_ENTRY_ID")
            eid = args.entry_id or (int(env_id) if env_id else None)
            out = args.out or Path(f"data/processed/blind_gw{args.gw}.json")
            blind_pick(store, args.season, args.gw, eid, out, args.model)
        elif args.command == "transfers":
            env_id = os.environ.get("FPL_ENTRY_ID")
            eid = args.entry_id or (int(env_id) if env_id else None)
            if eid is None:
                parser.error("entry id required (--entry-id or FPL_ENTRY_ID)")
            suggest_transfers(store, args, eid)
        elif args.command == "blind-score":
            if args.all == (args.gw is not None):
                parser.error("pass exactly one of --gw N or --all")
            files = (sorted(DEFAULT_BLIND_DIR.glob("blind_gw*.json"),
                            key=lambda f: int(f.stem.removeprefix("blind_gw")))
                     if args.all else [args.file or DEFAULT_BLIND_DIR / f"blind_gw{args.gw}.json"])
            scored: dict[int, dict] = {}
            for path in files:
                frozen = json.loads(path.read_text(encoding="utf-8"))
                try:
                    scored[frozen["gw"]] = score_blind(store.con, frozen)
                except RuntimeError as e:
                    if not args.all:
                        raise
                    print(f"GW{frozen['gw']}: skipped ({e})")
            for gw, res in scored.items():
                for name, by_who in res.items():
                    for who, r in by_who.items():
                        print(f"GW{gw:<3d}{name:15s} {who:6s} {r['achieved']:6.1f} / "
                              f"{r['ceiling']:6.1f} = {r['captured_fraction']:.3f}")
            if len(scored) > 1:
                print(f"-- mean over {len(scored)} gameweeks ({sorted(scored)})")
                for (name, who), (mean, n) in mean_captured(scored).items():
                    print(f"{name:15s} {who:6s} {mean:.3f} (n={n})")
        elif args.command == "entry":
            n = sync_entry(client, store, args.entry_id)
            print(f"{n} gameweeks of picks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
