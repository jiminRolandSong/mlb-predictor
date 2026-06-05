from datetime import date, timedelta
from app.core.celery_app import celery
from app.core.database import SessionLocal
from app.models.player import Player
from app.services.batter_service import ingest_batter_stats
from app.services.pitcher_service import ingest_pitcher_stats
from app.core.cache import invalidate_all_predictions


@celery.task(bind=True, name="tasks.ingest_player")
def ingest_player_task(self, mlbam_id: int, name: str, position: str, start_date: str, end_date: str) -> dict:
    db = SessionLocal()
    try:
        if position == "B":
            rows = ingest_batter_stats(db, mlbam_id, name, start_date, end_date)
        else:
            rows = ingest_pitcher_stats(db, mlbam_id, name, start_date, end_date)
        invalidate_all_predictions(mlbam_id)
        return {"mlbam_id": mlbam_id, "name": name, "position": position, "rows_inserted": rows}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10, max_retries=3)
    finally:
        db.close()


@celery.task(name="tasks.ingest_all_players")
def ingest_all_players() -> dict:
    db = SessionLocal()
    try:
        players = db.query(Player).all()
        today = date.today()
        start = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        results = []
        for player in players:
            try:
                if player.position == "B":
                    rows = ingest_batter_stats(db, player.mlbam_id, player.name, start, end)
                else:
                    rows = ingest_pitcher_stats(db, player.mlbam_id, player.name, start, end)
                invalidate_all_predictions(player.mlbam_id)
                results.append({"mlbam_id": player.mlbam_id, "rows_inserted": rows})
            except Exception as e:
                results.append({"mlbam_id": player.mlbam_id, "error": str(e)})
        return {"updated": len(results), "results": results}
    finally:
        db.close()
