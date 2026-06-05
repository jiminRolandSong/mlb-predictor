from fastapi import FastAPI
from app.core.database import engine, Base
from app.models import Player, BatterStat, PitcherStat, Matchup
from app.api import players, matchups

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MLB Predictor API")

app.include_router(players.router)
app.include_router(matchups.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/players/refresh-all")
def refresh_all_players():
    from app.tasks import ingest_all_players
    task = ingest_all_players.delay()
    return {"task_id": task.id, "status": "queued"}
