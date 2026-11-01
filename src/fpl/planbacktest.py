"""Season-long backtest of the transfer planner against simple policies, scored on actual points.

Each policy manages one squad through a season. Before gameweek g it sees only predictions made
from results before g (the walk-forward dataset's rows for g), asks ``plan_transfers`` for the best
plan over ``horizon`` gameweeks, applies it, picks the XI and captain *from predictions*, and is
scored on the actual gameweek points minus 4 per hit. Sale price = FPL selling price (half of any
rise); auto-subs and vice-captain are applied when the gameweek's minutes are known.

Future gameweeks (horizon > 1) cannot use the dataset's rows for g+j: their features include
results of g..g+j-1. Instead a player's predicted points for g+j are his latest per-fixture
prediction times the number of fixtures he has in g+j (the schedule is known in advance), i.e.
persistence. ``horizon=1`` needs no such assumption.

Chips (``Policy.chips``): one of each per half (GW1-19, GW20-38). Before each gameweek the policy
compares the predicted gain of playing the chip now with playing it in each later gameweek of the
window (to the end of the half) and plays it now if now is the best and the gain is at least
``chip_min``, or in the last gameweek of the half rather than lose it. Triple captain adds the
captain's points again; bench boost adds the points of every bench player who played (both are
judged on the squad the policy has just chosen).

Free hit and wildcard (``freehit`` / ``wildcard``) are decided *before* the normal transfer plan and
replace it that gameweek (one chip per gameweek, never in the first). Both buy a fresh squad with
the budget the current squad sells for (selling prices) plus the bank, chosen on the predictions
(``freehit``: this gameweek only, then the old squad comes back; ``wildcard``: the next
``wc_horizon`` gameweeks, persistence beyond the first, and it is kept), with no hit and no free
transfer used or added (as in ``fpl.replay``). Their predicted gain is the fresh squad's best XI
minus the current squad's best XI on the same points (summed over ``wc_horizon`` for the wildcard
and divided by it, so ``chip_min`` is per gameweek for every chip). It ignores that normal
transfers could close part of the gap, so it overstates the gain; ``chip_min`` guards against that.

``simulate`` is pure (no database); ``season_inputs`` builds its inputs from the walk-forward data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

import duckdb

from fpl.backtest import Dataset, GwKey, Predictor, walk_forward_splits
from fpl.horizon import HorizonPredictor
from fpl.optimizer import (
    BUDGET,
    GK,
    XI_BOUNDS,
    Player,
    Selection,
    optimize_squad,
    pick_lineup,
    score_selection,
)
from fpl.planner import best_plan, plan_transfers

MAX_FREE_TRANSFERS = 5


@dataclass(frozen=True)
class Policy:
    name: str
    max_transfers: int = 0  # 0 = never transfer
    margin: float = 1.0  # ``best_plan`` margin
    chips: tuple[str, ...] = ()  # subset of ("3xc", "bboost", "freehit", "wildcard")
    chip_min: float = 0.0  # least predicted gain (per gameweek) to play a chip before its half ends
    chip_window: int = 6  # gameweeks looked ahead when timing a chip
    wc_horizon: int = 4  # gameweeks a wildcard squad is chosen for


HOLD = Policy("hold")
PLANNER = Policy("planner", max_transfers=3, margin=1.0)
PLANNER_HITS = Policy("planner_hits", max_transfers=3, margin=0.0)
PLANNER_CHIPS = Policy("planner_chips", max_transfers=3, margin=1.0, chips=("3xc", "bboost"))
PLANNER_SWAP = Policy("planner_swap", max_transfers=3, margin=1.0, chips=("freehit", "wildcard"))
DEFAULT_POLICIES = (HOLD, PLANNER, PLANNER_HITS)
HALF_END = (19, 38)  # last gameweek of each chip half
SWAP_CHIPS = ("freehit", "wildcard")  # replace the squad instead of adding to a gameweek's score


@dataclass(frozen=True)
class GwInput:
    """What a policy may know before gameweek ``key``, plus the actuals used only to score it."""

    key: GwKey
    predicted: Mapping[int, float]  # eligible players: predicted GW points (fixtures summed)
    fixtures: Mapping[int, int]  # fixtures per player this GW (schedule; absent = blank)
    price: Mapping[int, int]  # tenths, carried forward over blanks
    actual: Mapping[int, float]
    minutes: Mapping[int, int] | None = None  # played minutes; None = no auto-subs
    # predicted points for the next gameweeks (j = 1, 2, ...) made with only what is known now;
    # when shorter than the horizon, ``horizon_points`` falls back to persistence
    ahead: tuple[Mapping[int, float], ...] = ()


@dataclass(frozen=True)
class GwResult:
    key: GwKey
    points: float  # actual points of the chosen XI + captain, after the hit
    hit: int
    transfers: int
    out: tuple[int, ...]
    into: tuple[int, ...]
    free_transfers: int  # available before this gameweek's transfers
    bank: int  # tenths, after transfers
    chip: str | None = None


@dataclass
class SeasonRun:
    policy: str
    results: list[GwResult] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(r.points for r in self.results)

    @property
    def hits(self) -> int:
        return sum(r.hit for r in self.results)

    @property
    def transfers(self) -> int:
        return sum(r.transfers for r in self.results)


def next_free_transfers(free: int, used: int) -> int:
    """Free transfers for the next gameweek: unused ones bank (up to 5) plus one new."""
    return min(MAX_FREE_TRANSFERS, max(0, free - used) + 1)


def selling_price(buy: int, now: int) -> int:
    """FPL selling price (tenths): a rise is kept at half, rounded down; a fall is lost in full."""
    return now if now <= buy else buy + (now - buy) // 2


def autosub_points(
    xi: Sequence[int],
    captain: int,
    bench: Sequence[int],
    info: Mapping[int, tuple[int, int]],
    predicted: Mapping[int, float],
    actual: Mapping[int, float],
    minutes: Mapping[int, int],
) -> float:
    """XI + captain points after FPL's automatic substitutions.

    A starter with no minutes is replaced by the first legal bench player who played: the bench
    goalkeeper only for the goalkeeper, outfield bench players in order of predicted points, and
    only if the formation stays legal. If the captain did not play, the vice-captain (the starter
    with the highest prediction who played) takes the armband. Blanks have no ``minutes`` entry.
    """
    played = {i for i in set(xi) | set(bench) if minutes.get(i, 0) > 0}
    final = list(xi)
    counts = Counter(info[i][0] for i in final)
    bench_gk = [i for i in bench if info[i][0] == GK]
    bench_out = sorted((i for i in bench if info[i][0] != GK), key=lambda i: -predicted.get(i, 0.0))
    for i in list(xi):
        if i in played:
            continue
        pos = info[i][0]
        pool = bench_gk if pos == GK else bench_out
        for b in pool:
            if b not in played:
                continue
            bp = info[b][0]
            new = counts.copy()
            new[pos] -= 1
            new[bp] += 1
            if all(XI_BOUNDS[q][0] <= new[q] <= XI_BOUNDS[q][1] for q in XI_BOUNDS):
                final[final.index(i)] = b
                counts = new
                pool.remove(b)
                break
    total = sum(actual.get(i, 0.0) for i in final if i in played)
    if captain not in played:
        alt = [i for i in final if i in played]
        captain = max(alt, key=lambda i: predicted.get(i, 0.0), default=None)
    return total + (actual.get(captain, 0.0) if captain is not None else 0.0)


def _players(
    ids: set[int], info: Mapping[int, tuple[int, int]], price: Mapping[int, int]
) -> list[Player]:
    return [Player(i, info[i][0], info[i][1], price[i], 0.0) for i in sorted(ids)]


def horizon_points(gws: Sequence[GwInput], i: int, horizon: int, per_fixture: Mapping[int, float]):
    """Predicted points for gameweeks i..i+horizon-1: the real prediction now, then the
    horizon models' ``ahead`` predictions where present, persistence otherwise."""
    out: list[dict[int, float]] = [dict(gws[i].predicted)]
    for j in range(i + 1, min(i + horizon, len(gws))):
        if j - i <= len(gws[i].ahead):
            out.append(dict(gws[i].ahead[j - i - 1]))
        else:
            out.append({p: v * gws[j].fixtures.get(p, 0) for p, v in per_fixture.items()})
    return out


def start_squad(first: GwInput, info: Mapping[int, tuple[int, int]]) -> tuple[Selection, int]:
    """Best squad for the first gameweek's predictions under the opening budget, and the bank."""
    ids = set(first.predicted) & set(first.price) & set(info)
    pool = [Player(i, *info[i], first.price[i], first.predicted[i]) for i in sorted(ids)]
    sel = optimize_squad(pool, budget=BUDGET)
    return sel, BUDGET - sel.cost


def chip_gains(
    squad: Sequence[int],
    info: Mapping[int, tuple[int, int]],
    points: Sequence[Mapping[int, float]],
    available: Sequence[str],
) -> dict[str, list[float]]:
    """Predicted gain per horizon gameweek of each chip on a fixed squad: the captain's points for
    triple captain, the bench's for bench boost (XI and captain picked from the same points)."""
    out: dict[str, list[float]] = {c: [] for c in available}
    for pts in points:
        if "3xc" in available:
            out["3xc"].append(max((pts.get(i, 0.0) for i in squad), default=0.0))
        if "bboost" in available:
            players = [Player(i, *info[i], 0, pts.get(i, 0.0)) for i in squad]
            sel = pick_lineup(players, squad)
            out["bboost"].append(sum(pts.get(i, 0.0) for i in sel.bench))
    return out


def _week_points(
    gw: GwInput,
    info: Mapping[int, tuple[int, int]],
    squad: Sequence[int],
    xi: Sequence[int],
    captain: int,
) -> float:
    """Actual points of the chosen XI and captain (auto-subs when the minutes are known)."""
    if gw.minutes is None:
        return score_selection(Selection(tuple(squad), tuple(xi), captain, 0.0, 0), gw.actual)
    bench = [i for i in squad if i not in set(xi)]
    return autosub_points(xi, captain, bench, {i: info[i] for i in squad}, gw.predicted,
                          gw.actual, gw.minutes)  # fmt: skip


def _played(gw: GwInput):
    return (lambda i: True) if gw.minutes is None else (lambda i: gw.minutes.get(i, 0) > 0)


def _effective_captain(xi: Sequence[int], captain: int, gw: GwInput) -> int | None:
    """The captain, or the vice-captain (best predicted starter who played) if he did not play."""
    played = _played(gw)
    if played(captain):
        return captain
    return max((i for i in xi if played(i)), key=lambda i: gw.predicted.get(i, 0.0), default=None)


def chip_week_points(
    chip: str, base: float, hit: int, squad: Sequence[int], xi: Sequence[int], captain: int,
    gw: GwInput,
) -> float:
    """Actual points of a gameweek played with ``chip``. ``base`` is the normal score after the
    hit. Triple captain adds the (effective) captain's points once more; bench boost scores every
    squad member who played (so no auto-subs) plus the captain's bonus, less the hit."""
    played = _played(gw)
    cap = _effective_captain(xi, captain, gw)
    cap_pts = gw.actual.get(cap, 0.0) if cap is not None else 0.0
    if chip == "3xc":
        return base + cap_pts
    return sum(gw.actual.get(i, 0.0) for i in squad if played(i)) + cap_pts - hit


def _half(gw: GwInput) -> int:
    return 0 if gw.key[1] <= HALF_END[0] else 1


def _choose_chip(
    policy: Policy,
    gws: Sequence[GwInput],
    i: int,
    squad: Sequence[int],
    info: Mapping[int, tuple[int, int]],
    per_fixture: Mapping[int, float],
    used: set[tuple[int, str]],
) -> str | None:
    """Chip to play in gameweek i (or None): see the module docstring for the rule."""
    half = _half(gws[i])
    left = [c for c in policy.chips if c not in SWAP_CHIPS and (half, c) not in used]
    if not left:
        return None
    end, window = _chip_window(policy, gws, i)
    gains = chip_gains(squad, info, horizon_points(gws, i, window, per_fixture), left)
    return _timed(gains, left, policy.chip_min, i == end)


def _chip_window(policy: Policy, gws: Sequence[GwInput], i: int) -> tuple[int, int]:
    """(index of the last gameweek of i's half in the data, gameweeks to look ahead from i)."""
    half = _half(gws[i])
    end = i
    while end + 1 < len(gws) and _half(gws[end + 1]) == half:
        end += 1
    return end, min(policy.chip_window, end - i + 1)


def _timed(
    gains: Mapping[str, Sequence[float]], left: Sequence[str], chip_min: float, last: bool
) -> str | None:
    """Chip to play now: one whose gain now is its best in the window and at least ``chip_min``
    (the one with the biggest gain if several), or any left in the half's last gameweek."""
    now = {c: g[0] for c, g in gains.items()}
    ready = [c for c in left if now[c] >= max(gains[c]) and now[c] >= chip_min]
    if not ready and last:
        ready = list(left)  # use it or lose it
    return max(ready, key=lambda c: now[c]) if ready else None


def swap_gain(players: Sequence[Player], squad: Sequence[int], budget: int,
              points: Mapping[int, float]) -> float:
    """Predicted gain of a fresh squad (cost <= ``budget``) over keeping ``squad``: the best XI
    and captain of each, on the same ``points``."""
    pool = [replace(p, points=points.get(p.id, 0.0)) for p in players]
    return optimize_squad(pool, budget=budget).objective - pick_lineup(pool, squad).objective


def _choose_swap_chip(
    policy: Policy,
    gws: Sequence[GwInput],
    i: int,
    pool: Sequence[Player],
    squad: Sequence[int],
    budget: int,
    per_fixture: Mapping[int, float],
    used: set[tuple[int, str]],
) -> str | None:
    """Free hit or wildcard to play in gameweek i (or None), judged on the squad as it stands
    before this gameweek's transfers. A wildcard's gain is over ``wc_horizon`` gameweeks starting
    at each candidate gameweek, per gameweek, from persistence forecasts made now."""
    half = _half(gws[i])
    left = [c for c in policy.chips if c in SWAP_CHIPS and (half, c) not in used]
    if not left:
        return None
    end, window = _chip_window(policy, gws, i)
    wc = policy.wc_horizon
    pts = horizon_points(gws, i, window + wc - 1, per_fixture)
    gains: dict[str, list[float]] = {}
    for c in left:
        if c == "freehit":
            gains[c] = [swap_gain(pool, squad, budget, p) for p in pts[:window]]
        else:
            gains[c] = []
            for j in range(window):
                total: dict[int, float] = defaultdict(float)
                for p in pts[j : j + wc]:
                    for k, v in p.items():
                        total[k] += v
                n = len(pts[j : j + wc])
                gains[c].append(swap_gain(pool, squad, budget, total) / n)
    return _timed(gains, left, policy.chip_min, i == end)


def simulate(
    gws: Sequence[GwInput],
    info: Mapping[int, tuple[int, int]],
    policy: Policy,
    *,
    horizon: int = 1,
    discount: float = 1.0,
    start: tuple[Selection, int] | None = None,
) -> SeasonRun:
    """Run ``policy`` through ``gws``. ``info[id] = (position, team)``.

    The first gameweek is played with the starting squad and no transfers. Afterwards free
    transfers accrue one per gameweek (banked up to 5) and every transfer beyond them costs 4.
    """
    squad_sel, bank = start or start_squad(gws[0], info)
    squad = set(squad_sel.squad)
    buy = {i: gws[0].price[i] for i in squad}  # purchase prices, for the selling price
    free = 1
    per_fixture: dict[int, float] = {}
    run = SeasonRun(policy.name)
    used: set[tuple[int, str]] = set()  # (half, chip) already played
    for i, gw in enumerate(gws):
        for p, v in gw.predicted.items():
            n = gw.fixtures.get(p, 0)
            if n:
                per_fixture[p] = v / n
        pool_ids = (set(gw.predicted) | squad) & set(info)
        pool = _players(pool_ids, info, gw.price)
        sell = {i: selling_price(buy[i], gw.price[i]) for i in squad}
        budget = bank + sum(sell.values())
        swap = (_choose_swap_chip(policy, gws, i, pool, sorted(squad), budget, per_fixture, used)
                if i else None)  # fmt: skip
        if swap:  # free hit / wildcard: a fresh squad instead of this gameweek's transfers
            used.add((_half(gw), swap))
            plan = plan_transfers(
                pool, horizon_points(gws, i, 1 if swap == "freehit" else policy.wc_horizon,
                                     per_fixture),
                squad, bank=bank, free_transfers=free, max_transfers=0, discount=discount,
                sell_prices=sell, chip=swap, chip_gw=0)[0]  # fmt: skip
            new = set(plan.chip_squad)
            points = _week_points(gw, info, plan.chip_squad, plan.xi[0], plan.captain[0])
            if swap == "freehit":
                run.results.append(GwResult(gw.key, points, 0, 0, (), (), free, bank, swap))
            else:
                bank = budget - sum(gw.price[p] for p in new)
                buy = {p: buy[p] if p in buy else gw.price[p] for p in new}
                run.results.append(GwResult(
                    gw.key, points, 0, len(new - squad), tuple(sorted(squad - new)),
                    tuple(sorted(new - squad)), free, bank, swap))  # fmt: skip
                squad = new
            continue  # a chip week uses no free transfer and adds none
        pts = horizon_points(gws, i, horizon, per_fixture)
        k_max = policy.max_transfers if i else 0
        plans = plan_transfers(pool, pts, squad, bank=bank, free_transfers=free,
                               max_transfers=k_max, discount=discount,
                               sell_prices=sell)  # fmt: skip
        plan = best_plan(plans, policy.margin)
        points = _week_points(gw, info, plan.squad, plan.xi[0], plan.captain[0]) - plan.hit
        chip = _choose_chip(policy, gws, i, plan.squad, info, per_fixture, used)
        if chip:
            used.add((_half(gw), chip))
            points = chip_week_points(chip, points, plan.hit, plan.squad, plan.xi[0],
                                      plan.captain[0], gw)  # fmt: skip
        buy = {i: buy[i] if i in buy else gw.price[i] for i in plan.squad}
        run.results.append(GwResult(gw.key, points, plan.hit, plan.transfers, plan.out, plan.into,
                                    free, plan.bank, chip))  # fmt: skip
        squad, bank = set(plan.squad), plan.bank
        free = next_free_transfers(free, plan.transfers)
    return run


def ceiling_points(gw: GwInput, info: Mapping[int, tuple[int, int]]) -> float:
    """Hindsight-best fresh squad under the opening budget (context only)."""
    ids = set(gw.predicted) & set(gw.price) & set(info)
    pool = [Player(i, *info[i], gw.price[i], gw.actual.get(i, 0.0)) for i in sorted(ids)]
    return score_selection(optimize_squad(pool, budget=BUDGET), gw.actual)


# ------------------------------------------------------------------------------------ DB layer


def season_info(
    con: duckdb.DuckDBPyConnection, season: str
) -> tuple[dict[int, tuple[int, int]], dict[int, dict[int, int]]]:
    """``(position, team)`` per player and ``round -> {player: price}`` (last fixture of the round).

    Team is the end-of-season club (see the data gotchas).
    """
    info = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            "SELECT element_id, position, team_id FROM hist_players WHERE season = ?", [season]
        ).fetchall()
        if None not in r
    }
    prices: dict[int, dict[int, int]] = defaultdict(dict)
    for el, rnd, value in con.execute(
        "SELECT element_id, round, ARG_MAX(value, kickoff_time) FROM hist_player_gw "
        "WHERE season = ? GROUP BY ALL", [season]).fetchall():  # fmt: skip
        if value is not None:
            prices[rnd][el] = value
    return info, prices


def season_inputs(
    data: Dataset,
    predictors: Sequence[Predictor],
    season: str,
    con: duckdb.DuckDBPyConnection,
    *,
    min_history: int = 5,
    ahead_models: Mapping[str, Sequence[HorizonPredictor]] | None = None,
) -> tuple[dict[str, list[GwInput]], dict[int, tuple[int, int]]]:
    """Per predictor, the season's ``GwInput`` list; fits each predictor once for the season.

    All predictors share one eligible pool per gameweek (enough history and a prediction from
    every predictor). Prices carry forward over a player's blank gameweeks. Rounds with no
    eligible player are left out, so all policies are scored on the same gameweeks.

    ``ahead_models[name]`` = horizon predictors for h = 1, 2, ... of predictor ``name``: they are
    fitted on the season's training rows and fill ``GwInput.ahead`` (player sums over the later
    gameweek's fixtures, from features as of the current gameweek; eligible players only).
    """
    info, round_prices = season_info(con, season)
    round_minutes: dict[int, dict[int, int]] = defaultdict(dict)
    for el, rnd, mins in con.execute(
        "SELECT element_id, round, SUM(minutes) FROM hist_player_gw "
        "WHERE season = ? AND minutes IS NOT NULL GROUP BY ALL", [season]).fetchall():  # fmt: skip
        round_minutes[rnd][el] = int(mins)
    (split,) = [s for s in walk_forward_splits(data, [season], step=None)]
    for p in predictors:
        p.fit(data, split.train)
    for models in (ahead_models or {}).values():
        for m in models:
            m.fit(data, split.train)
    elements, targets = data.columns["element_id"], data.columns["target"]
    n_prior, ordinals = data.columns["n_prior_fixtures"], data.columns["gw_ordinal"]
    out: dict[str, list[GwInput]] = {p.name: [] for p in predictors}
    kept: list[tuple[int, int, set[int]]] = []  # (first, end, eligible) of each GwInput
    carried: dict[int, int] = {}
    for key, first, end in split.eval:
        carried.update(round_prices.get(key[1], {}))
        idx = range(first, end)
        fixtures: dict[int, int] = defaultdict(int)
        actual: dict[int, float] = defaultdict(float)
        for i in idx:
            fixtures[elements[i]] += 1
            actual[elements[i]] += targets[i]
        sums: dict[str, dict[int, float | None]] = {}
        for p in predictors:
            s: dict[int, float | None] = defaultdict(float)
            for i, v in zip(idx, p.predict(data, idx), strict=True):
                el = elements[i]
                s[el] = None if (v is None or s[el] is None) else s[el] + v
            sums[p.name] = s
        eligible = {
            elements[i] for i in idx if (n_prior[i] or 0) >= min_history
        } & {el for el in fixtures if all(s[el] is not None for s in sums.values())}
        eligible &= set(info) & set(carried)
        if not eligible:
            continue  # no forecast this round (e.g. vaastav has no xp): skipped for every policy
        for p in predictors:
            out[p.name].append(GwInput(
                key, {el: sums[p.name][el] for el in eligible}, dict(fixtures),
                dict(carried), dict(actual), round_minutes.get(key[1]) or None,
            ))  # fmt: skip
        kept.append((first, end, eligible))
    for name, models in (ahead_models or {}).items():
        for k, (first, _, eligible) in enumerate(kept):
            as_of = ordinals[first]
            ahead = []
            for h, m in enumerate(models, start=1):
                if k + h >= len(kept):
                    break
                ahead.append(_gw_sums(m, data, range(*kept[k + h][:2]), eligible, as_of))
            out[name][k] = replace(out[name][k], ahead=tuple(ahead))
    return out, info


def _gw_sums(
    model: HorizonPredictor, data: Dataset, idx: range, eligible: set[int], as_of: int
) -> dict[int, float]:
    """Horizon-model points per eligible player over the fixtures of ``idx`` (one gameweek)."""
    elements = data.columns["element_id"]
    out: dict[int, float] = {}
    for i, v in zip(idx, model.predict(data, idx, as_of), strict=True):
        if v is not None and elements[i] in eligible:
            out[elements[i]] = out.get(elements[i], 0.0) + v
    return out


def summarize(runs: Sequence[SeasonRun]) -> list[dict[str, object]]:
    return [
        {"policy": r.policy, "n_gws": len(r.results), "total": r.total,
         "per_gw": r.total / len(r.results), "hit_pts": r.hits, "transfers": r.transfers}
        for r in runs
    ]  # fmt: skip


def chip_log(run: SeasonRun) -> str:
    """'3xc GW12, bboost GW19' for the chips a run played."""
    return ", ".join(f"{r.chip} GW{r.key[1]}" for r in run.results if r.chip) or "none"
