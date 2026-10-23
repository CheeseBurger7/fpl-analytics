from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from fpl.api import BASE_URL, FPLClient
from fpl.store import Store

BOOTSTRAP: dict[str, Any] = {
    "events": [
        {"id": 1, "deadline_time": "2025-08-15T17:30:00Z", "finished": True,
         "is_current": False, "is_next": False, "average_entry_score": 55, "highest_score": 120},
        {"id": 2, "deadline_time": "2025-08-23T10:00:00Z", "finished": False,
         "is_current": True, "is_next": False, "average_entry_score": None, "highest_score": None},
        {"id": 3, "deadline_time": "2025-08-30T10:00:00Z", "finished": False,
         "is_current": False, "is_next": True, "average_entry_score": None, "highest_score": None},
    ],
    "teams": [
        {"id": 1, "name": "Arsenal", "short_name": "ARS", "strength": 5,
         "strength_overall_home": 1300, "strength_overall_away": 1330,
         "strength_attack_home": 1340, "strength_attack_away": 1350,
         "strength_defence_home": 1290, "strength_defence_away": 1300},
        {"id": 2, "name": "Brentford", "short_name": "BRE", "strength": 3,
         "strength_overall_home": 1100, "strength_overall_away": 1110,
         "strength_attack_home": 1120, "strength_attack_away": 1130,
         "strength_defence_home": 1090, "strength_defence_away": 1100},
    ],
    "elements": [
        {"id": 10, "web_name": "Saka", "team": 1, "element_type": 3, "now_cost": 100,
         "selected_by_percent": "35.2", "form": "6.5", "status": "a",
         "chance_of_playing_next_round": None, "minutes": 180, "total_points": 20,
         "goals_scored": 1, "assists": 2, "clean_sheets": 1, "bonus": 3, "bps": 80,
         "expected_goals": "0.85", "expected_assists": "0.60",
         "expected_goal_involvements": "1.45", "expected_goals_conceded": "1.10",
         "ep_next": "5.4", "transfers_in_event": 1000, "transfers_out_event": 200,
         "cost_change_event": 0},
        {"id": 11, "web_name": "Mbeumo", "team": 2, "element_type": 3, "now_cost": 80,
         "selected_by_percent": "12.0", "form": "", "status": "d",
         "chance_of_playing_next_round": 75, "minutes": 90, "total_points": 6,
         "goals_scored": 0, "assists": 1, "clean_sheets": 0, "bonus": 1, "bps": 30,
         "expected_goals": "0.20", "expected_assists": "0.10",
         "expected_goal_involvements": "0.30", "expected_goals_conceded": "0.90",
         "ep_next": "3.1", "transfers_in_event": 10, "transfers_out_event": 50,
         "cost_change_event": -1},
    ],
}

FIXTURES: list[dict[str, Any]] = [
    {"id": 101, "event": 1, "kickoff_time": "2025-08-15T19:00:00Z", "team_h": 1, "team_a": 2,
     "team_h_difficulty": 2, "team_a_difficulty": 4, "team_h_score": 2, "team_a_score": 0,
     "finished": True},
    {"id": 102, "event": None, "kickoff_time": None, "team_h": 2, "team_a": 1,
     "team_h_difficulty": 4, "team_a_difficulty": 2, "team_h_score": None, "team_a_score": None,
     "finished": False},
]

ELEMENT_SUMMARY: dict[str, Any] = {
    "history": [
        {"element": 10, "fixture": 101, "round": 1, "opponent_team": 2, "was_home": True,
         "kickoff_time": "2025-08-15T19:00:00Z", "minutes": 90, "total_points": 9,
         "goals_scored": 1, "assists": 1, "clean_sheets": 1, "bonus": 3, "bps": 50,
         "expected_goals": "0.55", "expected_assists": "0.30",
         "expected_goal_involvements": "0.85", "expected_goals_conceded": "0.40",
         "value": 100, "selected": 3_000_000, "transfers_balance": 5000},
    ]
}

ROUTES: dict[str, Any] = {
    "bootstrap-static/": BOOTSTRAP,
    "fixtures/": FIXTURES,
    "element-summary/10/": ELEMENT_SUMMARY,
    "element-summary/11/": {"history": []},
    "entry/7/history/": {
        "current": [
            {"event": 1, "points": 60, "total_points": 60, "rank": 1, "overall_rank": 5,
             "bank": 5, "value": 1000, "event_transfers": 0, "event_transfers_cost": 0,
             "points_on_bench": 4},
        ],
        "chips": [{"name": "wildcard", "event": 1}],
    },
    "entry/7/transfers/": [
        {"event": 1, "time": "2025-08-10T12:00:00.123456Z", "element_in": 10, "element_out": 11,
         "element_in_cost": 100, "element_out_cost": 80},
    ],
    "entry/7/event/1/picks/": {
        "picks": [
            {"element": 10, "position": 1, "multiplier": 2, "is_captain": True,
             "is_vice_captain": False},
            {"element": 11, "position": 2, "multiplier": 1, "is_captain": False,
             "is_vice_captain": True},
        ]
    },
}


@pytest.fixture
def make_client() -> Callable[..., FPLClient]:
    def _make(handler: Callable[[httpx.Request], httpx.Response] | None = None, **kw: Any):
        def default(request: httpx.Request) -> httpx.Response:
            key = request.url.path.removeprefix("/api/")
            if key in ROUTES:
                return httpx.Response(200, json=ROUTES[key])
            return httpx.Response(404)

        http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler or default))
        return FPLClient(client=http, backoff=0.0, **kw)

    return _make


@pytest.fixture
def client(make_client: Callable[..., FPLClient]) -> FPLClient:
    return make_client()


@pytest.fixture
def store() -> Store:
    with Store() as s:
        yield s
