import httpx

from fpl.history import (
    BASE_URL,
    import_season,
    import_seasons,
    parse_gw_rows,
    seasons_between,
)
from fpl.store import HIST_GW_COLUMNS

MASTER = "season,team,team_name\n2022-23,1,Arsenal\n2022-23,2,Brentford\n2016-17,1,Arsenal\n"
TEAMS = "id,name\n1,Arsenal FC\n2,Brentford\n"
PLAYERS = (
    "id,code,web_name,first_name,second_name,team,element_type\n"
    "10,111,Saka,Bukayo,Saka,1,3\n"
    "11,222,Toney,Ivan,Toney,2,4\n"
)
# 2022-23 style: xG columns present, 'None' artefacts, a double gameweek for element 10.
MERGED = (
    "name,position,team,xP,assists,bonus,bps,clean_sheets,creativity,element,expected_goals,"
    "fixture,goals_conceded,goals_scored,ict_index,influence,kickoff_time,minutes,"
    "opponent_team,round,selected,starts,team_a_score,team_h_score,threat,total_points,"
    "transfers_balance,value,was_home\n"
    "Saka,MID,Arsenal,5.5,1,3,40,1,20.0,10,0.55,101,0,1,12.5,30.0,2022-08-06T14:00:00Z,90,"
    "2,1,3000000,1,0,2,60.0,9,5000,80,True\n"
    "Saka,MID,Arsenal,4.0,0,0,10,0,5.0,10,0.10,102,1,0,2.0,5.0,2022-08-09T19:00:00Z,20,"
    "2,1,3000000,0,1,1,3.0,1,5000,80,False\n"
    "Toney,FWD,Brentford,,0,0,0,0,0.0,11,None,101,2,0,0.0,0.0,2022-08-06T14:00:00Z,0,"
    "1,1,500000,0,0,2,0.0,0,-10,75,False\n"
)


def _http(files: dict[str, str]) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        key = req.url.path.removeprefix("/vaastav/Fantasy-Premier-League/master/data/")
        if key in files:
            return httpx.Response(200, text=files[key])
        return httpx.Response(404)

    return httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))


FILES = {
    "master_team_list.csv": MASTER,
    "2022-23/teams.csv": TEAMS,
    "2022-23/players_raw.csv": PLAYERS,
    "2022-23/gws/merged_gw.csv": MERGED,
}


def q(store, sql, *params):
    return store.con.execute(sql, list(params)).fetchall()


def test_seasons_between():
    assert seasons_between("2022-23", "2024-25") == ["2022-23", "2023-24", "2024-25"]
    assert seasons_between("1999-00", "1999-00") == ["1999-00"]


def test_gw_columns_match_table(store):
    cols = [r[0] for r in q(store, "SELECT column_name FROM information_schema.columns "
                                   "WHERE table_name='hist_player_gw' ORDER BY ordinal_position")]
    assert tuple(cols) == HIST_GW_COLUMNS


def test_import_season(store, tmp_path):
    assert import_season(_http(FILES), store, "2022-23", cache_dir=tmp_path) == 3

    assert q(store, "SELECT team_id, name FROM hist_teams ORDER BY team_id") == [
        (1, "Arsenal FC"), (2, "Brentford"),  # per-season teams.csv wins over master list
    ]
    assert q(store, "SELECT element_id, code, position, team_id FROM hist_players "
                    "ORDER BY element_id") == [(10, 111, 3, 1), (11, 222, 4, 2)]
    # double gameweek: two rows for the same round
    assert q(store, "SELECT fixture_id, round, minutes, was_home FROM hist_player_gw "
                    "WHERE element_id=10 ORDER BY fixture_id") == [
        (101, 1, 90, True), (102, 1, 20, False)]
    row = q(store, "SELECT expected_goals, xp, ict_index, starts, kickoff_time "
                   "FROM hist_player_gw WHERE element_id=10 AND fixture_id=101")[0]
    assert row[:4] == (0.55, 5.5, 12.5, 1)
    assert str(row[4]) == "2022-08-06 14:00:00"
    # 'None' / '' cells become NULL rather than failing the cast
    assert q(store, "SELECT expected_goals, xp FROM hist_player_gw WHERE element_id=11") == [
        (None, None)]
    assert q(store, "SELECT raw->>'name' FROM hist_player_gw WHERE element_id=11") == [("Toney",)]


def test_old_season_columns_missing_become_null():
    rows = parse_gw_rows("2016-17", [{"element": "5", "fixture": "9", "round": "1",
                                      "was_home": "False", "minutes": "90"}])
    by_col = dict(zip(HIST_GW_COLUMNS, rows[0], strict=True))
    assert (by_col["minutes"], by_col["was_home"], by_col["expected_goals"]) == (90, False, None)


def test_rows_without_fixture_are_skipped():
    assert parse_gw_rows("2022-23", [{"element": "5", "fixture": ""}]) == []


def test_reimport_replaces_season_and_uses_cache(store, tmp_path):
    import_season(_http(FILES), store, "2022-23", cache_dir=tmp_path)
    # Cached: a client that 404s everything must still work on the second run.
    assert import_season(_http({}), store, "2022-23", cache_dir=tmp_path) == 3
    assert q(store, "SELECT count(*) FROM hist_player_gw")[0][0] == 3

    # Upstream correction (one fixture dropped) + refresh: stale rows must not linger.
    trimmed = "\n".join(MERGED.splitlines()[:2]) + "\n"
    http = _http({**FILES, "2022-23/gws/merged_gw.csv": trimmed})
    import_season(http, store, "2022-23", cache_dir=tmp_path, refresh=True)
    assert q(store, "SELECT count(*) FROM hist_player_gw")[0][0] == 1


def test_teams_fall_back_to_master_list(store, tmp_path):
    files = {  # 2016-17 has no teams.csv upstream
        "master_team_list.csv": MASTER,
        "2016-17/players_raw.csv": PLAYERS,
        "2016-17/gws/merged_gw.csv": MERGED,
    }
    import_season(_http(files), store, "2016-17", cache_dir=tmp_path)
    assert q(store, "SELECT team_id, name FROM hist_teams") == [(1, "Arsenal")]


def test_missing_season_is_skipped(store, tmp_path):
    done = import_seasons(_http(FILES), store, ["2021-22", "2022-23"], cache_dir=tmp_path)
    assert done == {"2022-23": 3}
