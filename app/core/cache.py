import json
import redis as redis_lib
from app.core.config import settings

_client: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    global _client
    if _client is None:
        _client = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _client


PREDICT_TTL = 6 * 3600  # 6시간


def cache_key_predict(mlbam_id: int, position: str) -> str:
    return f"predict:{mlbam_id}:{position}"


def get_prediction(mlbam_id: int, position: str) -> dict | None:
    r = get_redis()
    raw = r.get(cache_key_predict(mlbam_id, position))
    return json.loads(raw) if raw else None


def set_prediction(mlbam_id: int, position: str, data: dict) -> None:
    r = get_redis()
    r.setex(cache_key_predict(mlbam_id, position), PREDICT_TTL, json.dumps(data))


def invalidate_prediction(mlbam_id: int, position: str) -> None:
    r = get_redis()
    r.delete(cache_key_predict(mlbam_id, position))


def invalidate_all_predictions(mlbam_id: int) -> None:
    for pos in ("B", "P"):
        invalidate_prediction(mlbam_id, pos)
