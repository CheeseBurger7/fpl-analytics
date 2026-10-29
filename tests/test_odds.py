from __future__ import annotations

import csv
from datetime import date

import httpx

from fpl.odds import BASE_URL, import_odds_season, import_odds_seasons, parse_odds_rows, team_key
from fpl.store import ODDS_COLUMNS, Store

# 2016-17 style (two-digit year, no average / Over-Under / handicap columns) and a blank last line
OLD = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,B365H,B365D,B365A,PSH,PSD,PSA,PSCH,PSCD,PSCA\n"
    "E0,13/08/16,Hull,Leicester,2,1,3.5,3.3,2.2,3.6,3.4,2.1,3.4,3.4,2.2\n"
    "E0,13/08/16,Man United,Tottenham,,,1.8,3.8,4.5,,,,,,\n"
    ",,,,,,,,,,,,,,\n"
)
# 2024-25 style: market average, Over/Under 2.5 and an Asian handicap line
NEW = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,B365H,B365D,B365A,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5,"
    "AHh,AvgAHH,AvgAHA,AvgCH,AvgCD,AvgCA\n"
    "E0,16/08/2024,20:00,Man United,Fulham,1,0,1.6,4.2,5.25,1.66,4.5,5.6,1.53,2.52,-1,2.05,1.88,"
    "1.7,4.33,5.5\n"
)


def _http(files: dict[str, str]) -> httpx.Client:
    def handler(req: httpx.Request) -> httpx.Response:
        key = req.url.path.removeprefix("/mmz4281/")
        return httpx.Response(200, text=files[key]) if key in files else httpx.Response(404)

    return httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))


def _store_with_teams(season, teams):
    s = Store()
    s.con.executemany("INSERT INTO hist_teams VALUES (?, ?, ?)", [(season, i, n) for i, n in teams])
    return s


def test_team_key_joins_the_two_spellings():
    assert team_key("Man United") == team_key("Man Utd") == "man utd"
    assert team_key("Tottenham") == team_key("Spurs") and team_key("Coventry") == "coventry city"
    assert team_key("Arsenal") == "arsenal"


def test_parse_handles_missing_columns_dates_and_blank_lines():
    old = parse_odds_rows("2016-17", csv.DictReader(OLD.splitlines()))
    assert len(old) == 2  # the blank line is dropped
    row = dict(zip(ODDS_COLUMNS, old[0], strict=True))
    assert row["match_date"] == date(2016, 8, 13) and row["home_team"] == "Hull"
    assert (row["home_goals"], row["away_goals"]) == (2, 1)
    assert row["b365_h"] == 3.5 and row["psc_d"] == 3.4
    assert row["avg_h"] is None and row["ah_line"] is None  # not in that season's file
    unplayed = dict(zip(ODDS_COLUMNS, old[1], strict=True))
    assert unplayed["home_goals"] is None and unplayed["ps_h"] is None
    assert unplayed["b365_h"] == 1.8


def test_parse_new_format_columns():
    (row,) = (dict(zip(ODDS_COLUMNS, r, strict=True)) for r in
              parse_odds_rows("2024-25", csv.DictReader(NEW.splitlines())))
    assert row["match_date"] == date(2024, 8, 16)
    assert (row["avg_over25"], row["avg_under25"], row["ah_line"]) == (1.53, 2.52, -1.0)
    assert (row["avg_ah_h"], row["avgc_a"]) == (2.05, 5.5)


def test_import_matches_clubs_to_hist_team_ids_and_replaces_the_season(tmp_path):
    with _store_with_teams("2024-25", [(1, "Man Utd"), (2, "Fulham")]) as s:
        n = import_odds_season(_http({"2425/E0.csv": NEW}), s, "2024-25", cache_dir=tmp_path)
        assert n == 1
        again = import_odds_season(_http({"2425/E0.csv": NEW}), s, "2024-25", cache_dir=tmp_path)
        assert again == 1  # a re-import replaces, never duplicates
        rows = s.con.execute(
            "SELECT home_team, home_team_id, away_team_id, avg_h FROM match_odds").fetchall()
        assert rows == [("Man United", 1, 2, 1.66)]
    assert (tmp_path / "2425.csv").exists()


def test_unmatched_clubs_keep_null_ids_and_missing_seasons_are_skipped(tmp_path):
    with _store_with_teams("2016-17", [(1, "Hull City")]) as s:  # Leicester not in hist_teams
        done = import_odds_seasons(
            _http({"1617/E0.csv": OLD}), s, ["2016-17", "2017-18"], cache_dir=tmp_path)
        assert done == {"2016-17": 2}  # 2017-18 is a 404
        ids = s.con.execute(
            "SELECT home_team_id, away_team_id FROM match_odds ORDER BY match_date, home_team"
        ).fetchall()
        assert ids == [(1, None), (None, None)]
