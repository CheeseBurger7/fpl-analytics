"""Replay a manager's real season from stored ``entry_gameweeks`` / ``entry_transfers``.

The API does not expose free transfers, so they are reconstructed from the recorded transfer counts
and hit costs: unused free transfers bank (cap 5) and one is added each gameweek, except that a
chip week (wildcard / free hit) neither uses nor adds one. ``replay`` checks the reconstruction
against the recorded ``event_transfers_cost`` (4 per transfer beyond the free ones).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import duckdb

MAX_FREE_TRANSFERS = 5
HIT_COST = 4
TRANSFER_CHIPS = ("wildcard", "freehit")
# One use of each chip per half-season window (2025-26 onwards).
CHIPS = ("wildcard", "freehit", "bboost", "3xc")
HALVES = ((1, 19), (20, 38))


@dataclass(frozen=True)
class EntryGw:
    gameweek: int
    transfers: int
    cost: int
    chip: str | None
    points: int | None = None
    bank: int | None = None


@dataclass(frozen=True)
class ReplayRow:
    gameweek: int
    free: int  # free transfers available going into the gameweek
    transfers: int
    hit: int  # points deducted, as recorded
    expected_hit: int  # what ``free`` and ``transfers`` imply
    chip: str | None
    points: int | None
    bank: int | None

    @property
    def consistent(self) -> bool:
        return self.hit == self.expected_hit


def _advance(g: EntryGw, free: int) -> int:
    if g.chip in TRANSFER_CHIPS:
        return free  # chip week: count unchanged, no new transfer
    if g.gameweek == 1:
        return 1  # initial squad
    return min(MAX_FREE_TRANSFERS, max(0, free - g.transfers) + 1)


def free_transfers(history: Sequence[EntryGw]) -> list[tuple[EntryGw, int]]:
    """Free transfers available going into each gameweek, in order (gameweek 1 counts as 1)."""
    out: list[tuple[EntryGw, int]] = []
    free = 1
    for g in sorted(history, key=lambda g: g.gameweek):
        out.append((g, free))
        free = _advance(g, free)
    return out


def next_free(history: Sequence[EntryGw]) -> int:
    """Free transfers for the gameweek after the last one in ``history``."""
    rows = free_transfers(history)
    return _advance(*rows[-1]) if rows else 1


def replay(history: Sequence[EntryGw]) -> list[ReplayRow]:
    rows = []
    for g, free in free_transfers(history):
        paid = 0 if g.chip in TRANSFER_CHIPS or g.gameweek == 1 else max(0, g.transfers - free)
        rows.append(ReplayRow(g.gameweek, free, g.transfers, g.cost, paid * HIT_COST, g.chip,
                              g.points, g.bank))  # fmt: skip
    return rows


def chips_left(history: Sequence[EntryGw], gameweek: int) -> list[str]:
    """Chips still available for ``gameweek``: one of each per half-season window."""
    lo, hi = next(h for h in HALVES if h[0] <= gameweek <= h[1])
    used = {g.chip for g in history if g.chip and lo <= g.gameweek <= hi}
    return [c for c in CHIPS if c not in used]


def load_history(con: duckdb.DuckDBPyConnection, entry_id: int) -> list[EntryGw]:
    rows = con.execute(
        "SELECT gameweek, COALESCE(event_transfers, 0), COALESCE(event_transfers_cost, 0), "
        "active_chip, points, bank FROM entry_gameweeks WHERE entry_id = ? ORDER BY gameweek",
        [entry_id],
    ).fetchall()
    return [EntryGw(*r) for r in rows]


def format_replay(rows: Sequence[ReplayRow]) -> str:
    lines = ["GW  free  xfers  hit  chip       points  bank"]
    for r in rows:
        flag = "" if r.consistent else f"  MISMATCH (expected hit {r.expected_hit})"
        bank = "" if r.bank is None else f"{r.bank / 10:.1f}"
        lines.append(f"{r.gameweek:>2}  {r.free:>4}  {r.transfers:>5}  {r.hit:>3}  "
                     f"{r.chip or '-':<9}  {r.points if r.points is not None else '':>6}  "
                     f"{bank:>4}{flag}")  # fmt: skip
    return "\n".join(lines)
