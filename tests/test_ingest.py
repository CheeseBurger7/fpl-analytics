import duckdb

from fpl.ingest import (
    export_snapshot_parquet,
    sync_element_history,
    sync_entry,
    take_snapshot,
)


def q(store, sql, *params):
    return store.con.execute(sql, list(params)).fetchall()


def test_snapshot_rows_and_types(client, store):
    sid = take_snapshot(client, store)

    gws = q(store, "SELECT current_gw, next_gw FROM snapshots WHERE snapshot_id=?", sid)
    assert gws == [(2, 3)]
    assert q(store, "SELECT count(*) FROM player_snapshots")[0][0] == 2
    saka = q(store, "SELECT now_cost, selected_by_percent, form, expected_goals "
                    "FROM player_snapshots WHERE element_id=10")[0]
    assert saka == (100, 35.2, 6.5, 0.85)  # string numerics are cast
    # blank string -> NULL rather than a cast error
    assert q(store, "SELECT form FROM player_snapshots WHERE element_id=11") == [(None,)]
    assert q(store, "SELECT event FROM fixture_snapshots WHERE fixture_id=102") == [(None,)]
    assert q(store, "SELECT count(*) FROM team_snapshots")[0][0] == 2
    assert q(store, "SELECT count(*) FROM event_snapshots")[0][0] == 3


def test_snapshots_are_point_in_time(client, store, make_client):
    first = take_snapshot(client, store)

    from tests.conftest import BOOTSTRAP, ROUTES  # noqa: PLC0415

    moved = {**BOOTSTRAP, "elements": [{**BOOTSTRAP["elements"][0], "now_cost": 101}]}
    import httpx  # noqa: PLC0415

    def handler(req):
        key = req.url.path.removeprefix("/api/")
        return httpx.Response(200, json=moved if key == "bootstrap-static/" else ROUTES[key])

    second = take_snapshot(make_client(handler), store)

    assert second > first
    cost = q(store, "SELECT snapshot_id, now_cost FROM player_snapshots WHERE element_id=10 "
                    "ORDER BY snapshot_id")
    assert cost == [(first, 100), (second, 101)]


def test_failed_snapshot_rolls_back(client, store, monkeypatch):
    monkeypatch.setattr(store, "_fixture_row", lambda *a: (_ for _ in ()).throw(ValueError("x")))
    try:
        take_snapshot(client, store)
    except ValueError:
        pass
    assert q(store, "SELECT count(*) FROM snapshots")[0][0] == 0
    assert q(store, "SELECT count(*) FROM player_snapshots")[0][0] == 0


def test_element_history_is_idempotent(client, store):
    take_snapshot(client, store)
    assert sync_element_history(client, store) == 1
    assert sync_element_history(client, store) == 1
    rows = q(store, "SELECT element_id, fixture_id, round, expected_goals, was_home "
                    "FROM element_history")
    assert rows == [(10, 101, 1, 0.55, True)]


def test_element_history_skips_failed_players(make_client, store):
    import httpx  # noqa: PLC0415

    def handler(req):
        if req.url.path.endswith("element-summary/10/"):
            return httpx.Response(404)
        return httpx.Response(200, json={"history": []})

    assert sync_element_history(make_client(handler), store, [10, 11]) == 0


def test_sync_entry(client, store):
    assert sync_entry(client, store, 7) == 1
    assert q(store, "SELECT element_id, multiplier, is_captain FROM entry_picks "
                    "ORDER BY element_id") == [(10, 2, True), (11, 1, False)]
    assert q(store, "SELECT points, active_chip FROM entry_gameweeks") == [(60, "wildcard")]
    assert q(store, "SELECT element_in, element_out FROM entry_transfers") == [(10, 11)]
    sync_entry(client, store, 7)  # re-run must not duplicate
    assert q(store, "SELECT count(*) FROM entry_picks")[0][0] == 2


def test_parquet_export(client, store, tmp_path):
    sid = take_snapshot(client, store)
    out = export_snapshot_parquet(store, sid, tmp_path)
    path = (out / "player_snapshots.parquet").as_posix()
    assert duckdb.sql(f"SELECT count(*) FROM '{path}'").fetchall() == [(2,)]
