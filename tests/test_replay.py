from __future__ import annotations

import duckdb

from fpl.replay import EntryGw, chips_left, free_transfers, load_history, next_free, replay
from fpl.store import Store


def _season():
    # Mirrors a real 8-GW record: free hit GW3, wildcard GW5, hits in GW4 and GW8.
    spec = [(1, 0, 0, None), (2, 0, 0, None), (3, 21, 0, "freehit"), (4, 4, 8, "3xc"),
            (5, 13, 0, "wildcard"), (6, 0, 0, None), (7, 1, 0, None), (8, 3, 4, None)]
    return [EntryGw(*s) for s in spec]


def test_free_transfers_roll_over_and_chip_weeks_add_none():
    free = [f for _, f in free_transfers(_season())]
    assert free == [1, 1, 2, 2, 1, 1, 2, 2]


def test_replay_matches_recorded_hits():
    rows = replay(_season())
    assert all(r.consistent for r in rows)
    assert [r.expected_hit for r in rows] == [0, 0, 0, 8, 0, 0, 0, 4]


def test_mismatch_is_flagged():
    h = _season()
    h[7] = EntryGw(8, 3, 0, None)  # recorded no hit though 3 transfers > 2 free
    assert not replay(h)[-1].consistent


def test_next_free_after_each_kind_of_week():
    assert next_free(_season()) == 1  # 2 free, 3 used
    assert next_free(_season()[:5]) == 1  # wildcard week: unchanged
    assert next_free(_season()[:6]) == 2  # unused free transfer banks
    assert next_free(_season()[:1]) == 1
    assert next_free([]) == 1


def test_free_transfers_cap_at_five():
    h = [EntryGw(g, 0, 0, None) for g in range(1, 12)]
    assert max(f for _, f in free_transfers(h)) == 5


def test_chips_left_per_half():
    assert chips_left(_season(), 9) == ["bboost"]
    assert chips_left(_season(), 20) == ["wildcard", "freehit", "bboost", "3xc"]


def test_load_history_from_store():
    store = Store(":memory:")
    store.save_entry_history(7, {
        "current": [{"event": 1, "points": 50, "bank": 5, "event_transfers": 0,
                     "event_transfers_cost": 0},
                    {"event": 2, "points": 60, "bank": 0, "event_transfers": 2,
                     "event_transfers_cost": 4}],
        "chips": [{"event": 2, "name": "wildcard"}],
    })
    h = load_history(store.con, 7)
    assert h == [EntryGw(1, 0, 0, None, 50, 5), EntryGw(2, 2, 4, "wildcard", 60, 0)]
    assert isinstance(store.con, duckdb.DuckDBPyConnection)
