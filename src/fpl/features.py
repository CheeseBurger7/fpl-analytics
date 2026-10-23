"""Leakage-free per-fixture features for expected-points models, built in DuckDB SQL.

One output row per ``hist_player_gw`` row (player x fixture, so a double gameweek gives two rows
and a blank none). Every feature for a row in gameweek G uses only rows from gameweeks strictly
before G, so both fixtures of a double gameweek see the same information, as at the deadline.

History is keyed on ``hist_players.code`` so form carries across seasons; gameweeks are ordered by
their earliest kickoff because 2019-20 ``round`` runs to 47. Windows count fixtures played (not
calendar gameweeks), so a blank or a long injury stretches the window instead of adding nulls.

Features are grouped by expected importance, most important first. ICT, xG and FPL's ``xp`` are
deliberately left out for now (xG only exists from 2022-23); they slot in as further lagged
columns in ``_PLAYER_ROLLS``.
"""

from __future__ import annotations

import duckdb

# (name, window in gameweek rows). Windows are over previous player-gameweek rows that have at
# least one fixture, ordered by kickoff.
FORM_WINDOWS = (3, 5, 10)
TEAM_WINDOW = 6

# Tier 1 availability | tier 2 recent output | tier 3 player quality/price | tier 4 fixture context
FEATURE_COLUMNS: tuple[str, ...] = (
    # 1. Availability: playing time drives everything else.
    "mins_per_fix_3", "mins_per_fix_5", "mins_per_fix_10",
    "start_rate_5",
    "zero_min_rate_5",
    # 2. Recent output.
    "pts_per_fix_3", "pts_per_fix_5", "pts_per_fix_10",
    "pts_per_fix_career", "pts_per_60_10",
    # 3. Player quality / market.
    "position", "price", "price_change_5",
    # 4. Fixture context.
    "was_home",
    "opp_goals_for_6", "opp_goals_against_6",
    "own_goals_for_6", "own_goals_against_6",
    # Rows of history behind the features; lets models/backtests mask cold starts.
    "n_prior_fixtures",
)

_FRAME = "ROWS BETWEEN {n} PRECEDING AND 1 PRECEDING"
_FRAME_ALL = "ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING"


def _roll(expr: str, n: int | None, over: str) -> str:
    frame = _FRAME_ALL if n is None else _FRAME.format(n=n)
    return f"SUM({expr}) OVER ({over} {frame})"


def _ratio(num: str, den: str, n: int | None, over: str) -> str:
    return f"{_roll(num, n, over)}::DOUBLE / NULLIF({_roll(den, n, over)}, 0)"


def feature_sql() -> str:
    """SQL producing (season, element_id, fixture_id, target, <FEATURE_COLUMNS>...)."""
    p = "PARTITION BY code ORDER BY gw_start"
    t = "PARTITION BY team_name ORDER BY gw_start"
    form = [f"{_ratio('pts', 'fix', n, p)} AS pts_per_fix_{n}" for n in FORM_WINDOWS]
    mins = [f"{_ratio('mins', 'fix', n, p)} AS mins_per_fix_{n}" for n in FORM_WINDOWS]
    return f"""
WITH base AS (
    SELECT g.season, g.element_id, g.fixture_id, g.round, g.was_home, g.kickoff_time,
           g.opponent_team, g.total_points, g.minutes, g.value, g.team_h_score, g.team_a_score,
           p.code, p.position, p.team_id, tm.name AS team_name, ot.name AS opp_name,
           COALESCE(g.starts, (g.minutes >= 60)::INT) AS started,
           MIN(g.kickoff_time) OVER (PARTITION BY g.season, g.round) AS gw_start
    FROM hist_player_gw g
    JOIN hist_players p USING (season, element_id)
    LEFT JOIN hist_teams tm ON tm.season = g.season AND tm.team_id = p.team_id
    LEFT JOIN hist_teams ot ON ot.season = g.season AND ot.team_id = g.opponent_team
),
-- one row per player per gameweek, so a double gameweek is one step of history
player_gw AS (
    SELECT season, round, code, ANY_VALUE(gw_start) AS gw_start,
           COUNT(*) AS fix, SUM(total_points) AS pts, SUM(minutes) AS mins,
           SUM(started) AS starts, SUM((minutes = 0)::INT) AS zero_min,
           SUM(CASE WHEN minutes > 0 THEN minutes ELSE 0 END) AS played_mins,
           ARG_MAX(value, kickoff_time) AS price
    FROM base GROUP BY season, round, code
),
player_roll AS (
    SELECT season, round, code,
           {", ".join(mins)},
           {_ratio("starts", "fix", 5, p)} AS start_rate_5,
           {_ratio("zero_min", "fix", 5, p)} AS zero_min_rate_5,
           {", ".join(form)},
           {_ratio("pts", "fix", None, p)} AS pts_per_fix_career,
           {_ratio("pts", "played_mins", 10, p)} * 60 AS pts_per_60_10,
           LAG(price, 1) OVER ({p}) - LAG(price, 6) OVER ({p}) AS price_change_5,
           COALESCE({_roll("fix", None, p)}, 0) AS n_prior_fixtures
    FROM player_gw
),
-- team goals for/against per gameweek, from each fixture's score and the player's side
team_fix AS (
    SELECT DISTINCT season, round, fixture_id, team_name, gw_start,
           CASE WHEN was_home THEN team_h_score ELSE team_a_score END AS gf,
           CASE WHEN was_home THEN team_a_score ELSE team_h_score END AS ga
    FROM base WHERE team_name IS NOT NULL
),
team_gw AS (
    SELECT season, round, team_name, ANY_VALUE(gw_start) AS gw_start,
           COUNT(*) AS fix, SUM(gf) AS gf, SUM(ga) AS ga
    FROM team_fix GROUP BY season, round, team_name
),
team_roll AS (
    SELECT season, round, team_name,
           {_ratio("gf", "fix", TEAM_WINDOW, t)} AS goals_for_6,
           {_ratio("ga", "fix", TEAM_WINDOW, t)} AS goals_against_6
    FROM team_gw
)
SELECT b.season, b.element_id, b.fixture_id, b.round, b.kickoff_time,
       b.total_points AS target,
       pr.mins_per_fix_3, pr.mins_per_fix_5, pr.mins_per_fix_10,
       pr.start_rate_5, pr.zero_min_rate_5,
       pr.pts_per_fix_3, pr.pts_per_fix_5, pr.pts_per_fix_10,
       pr.pts_per_fix_career, pr.pts_per_60_10,
       b.position,
       b.value AS price,  -- price at this fixture (set before the deadline)
       pr.price_change_5,
       b.was_home,
       orr.goals_for_6 AS opp_goals_for_6, orr.goals_against_6 AS opp_goals_against_6,
       tr.goals_for_6 AS own_goals_for_6, tr.goals_against_6 AS own_goals_against_6,
       pr.n_prior_fixtures
FROM base b
JOIN player_roll pr USING (season, round, code)
LEFT JOIN team_roll tr ON tr.season = b.season AND tr.round = b.round
                      AND tr.team_name = b.team_name
LEFT JOIN team_roll orr ON orr.season = b.season AND orr.round = b.round
                       AND orr.team_name = b.opp_name
"""


def build_features(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Feature relation for every historical fixture row; order by ``kickoff_time`` to split."""
    return con.sql(feature_sql())
