import os
import requests

BASE_URL = os.getenv("API_URL", "https://mlb-predictor-production-2093.up.railway.app")


def _handle(response: requests.Response) -> dict:
    try:
        response.raise_for_status()
    except requests.HTTPError:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise requests.HTTPError(detail, response=response)
    return response.json()


def ingest_player(mlbam_id: int, name: str, position: str, start_date: str, end_date: str) -> dict:
    return _handle(requests.post(f"{BASE_URL}/players/ingest", json={
        "mlbam_id": mlbam_id,
        "name": name,
        "position": position,
        "start_date": start_date,
        "end_date": end_date,
    }))


def get_player_stats(mlbam_id: int, position: str | None = None) -> dict:
    params = {"position": position} if position else None
    return _handle(requests.get(f"{BASE_URL}/players/{mlbam_id}/stats", params=params))


def predict_player(mlbam_id: int, position: str | None = None) -> dict:
    params = {"position": position} if position else None
    return _handle(requests.get(f"{BASE_URL}/players/{mlbam_id}/predict", params=params))


def create_matchup(batter_id: int, pitcher_id: int) -> dict:
    return _handle(requests.post(f"{BASE_URL}/matchup/{batter_id}/{pitcher_id}"))


def list_players() -> list:
    return _handle(requests.get(f"{BASE_URL}/players/list"))


def search_player(last: str, first: str = "") -> list:
    return _handle(requests.get(f"{BASE_URL}/players/search", params={"last": last, "first": first}))


def get_season_stats(mlbam_id: int, position: str | None = None) -> dict:
    params = {"position": position} if position else None
    return _handle(requests.get(f"{BASE_URL}/players/{mlbam_id}/season-stats", params=params))


def get_matchup(batter_id: int, pitcher_id: int) -> dict:
    return _handle(requests.get(f"{BASE_URL}/matchup/{batter_id}/{pitcher_id}"))
