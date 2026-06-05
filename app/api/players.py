import threading
import requests as http_requests
import pandas as pd
from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.models.player import Player
from app.models.batter import BatterStat
from app.models.pitcher import PitcherStat
from app.schemas.player import PlayerResponse, IngestRequest, IngestResponse
from app.schemas.batter import BatterStatResponse
from app.schemas.pitcher import PitcherStatResponse
from app.services.batter_service import ingest_batter_stats
from app.services.pitcher_service import ingest_pitcher_stats
from app.services.gemini_service import predict_player as gemini_predict_player
from app.core.cache import get_prediction, set_prediction, invalidate_all_predictions

router = APIRouter(prefix="/players", tags=["players"])

AUTO_INGEST_DAYS = 1  # 마지막 업데이트 이후 이 일수 이상 지나면 백그라운드 업데이트


def _last_stat_date(db: Session, mlbam_id: int, position: str) -> date | None:
    if position == "B":
        row = db.query(BatterStat.game_date).filter(
            BatterStat.player_mlbam_id == mlbam_id
        ).order_by(BatterStat.game_date.desc()).first()
    else:
        row = db.query(PitcherStat.game_date).filter(
            PitcherStat.player_mlbam_id == mlbam_id
        ).order_by(PitcherStat.game_date.desc()).first()
    return row[0] if row else None


def _background_ingest(mlbam_id: int, name: str, position: str, start_date: str, end_date: str) -> None:
    db = SessionLocal()
    try:
        if position == "B":
            ingest_batter_stats(db, mlbam_id, name, start_date, end_date)
        else:
            ingest_pitcher_stats(db, mlbam_id, name, start_date, end_date)
        invalidate_all_predictions(mlbam_id)
    finally:
        db.close()


def _trigger_background_ingest(player: Player, start_date: str, end_date: str) -> None:
    t = threading.Thread(
        target=_background_ingest,
        args=(player.mlbam_id, player.name, player.position, start_date, end_date),
        daemon=True,
    )
    t.start()


def _resolve_player_position(player: Player, db: Session, position: str | None = None) -> str:
    if position is None:
        return player.position
    if position not in ("B", "P"):
        raise HTTPException(status_code=422, detail="position must be 'B' or 'P'")
    if player.position != position:
        player.position = position
        db.commit()
        db.refresh(player)
    return position


@router.get("/list")
def list_players(db: Session = Depends(get_db)):
    """Return all players stored in the DB."""
    players = db.query(Player).order_by(Player.name).all()
    return [
        {"mlbam_id": p.mlbam_id, "name": p.name, "team": p.team, "position": p.position}
        for p in players
    ]


@router.get("/ingest/task/{task_id}")
def get_ingest_task(task_id: str):
    from celery.result import AsyncResult
    from app.core.celery_app import celery
    result = AsyncResult(task_id, app=celery)
    response = {"task_id": task_id, "status": result.status}
    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)
    return response


def _get_position_from_mlb_api(mlbam_id: int) -> str:
    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{mlbam_id}"
        res = http_requests.get(url, timeout=5)
        data = res.json()
        pos = data["people"][0]["primaryPosition"]["code"]
        if pos == "1":
            return "P"
        elif pos == "Y":
            return "TWP"
        else:
            return "B"
    except Exception:
        return "B"


@router.get("/search")
def search_player(last: str = Query(..., min_length=1), first: str = Query(default="")):
    from pybaseball import playerid_lookup
    df = playerid_lookup(last, first or None, fuzzy=True)
    results = []
    for _, row in df.iterrows():
        if not pd.notna(row.get("key_mlbam")):
            continue
        last_year = int(row["mlb_played_last"]) if pd.notna(row.get("mlb_played_last")) else 0
        if last_year < 2020:
            continue
        mlbam_id = int(row["key_mlbam"])
        results.append({
            "mlbam_id": mlbam_id,
            "name": f"{str(row['name_first']).title()} {str(row['name_last']).title()}",
            "mlb_played_last": last_year,
            "position": _get_position_from_mlb_api(mlbam_id),
        })
    return results


@router.post("/fix-positions")
def fix_positions(db: Session = Depends(get_db)):
    players = db.query(Player).all()
    updated = []
    for player in players:
        if player.position == "TWP":
            continue
        try:
            correct = _get_position_from_mlb_api(player.mlbam_id)
            if correct == "TWP" or correct == player.position:
                continue
            player.position = correct
            updated.append({"mlbam_id": player.mlbam_id, "name": player.name, "new_position": correct})
        except Exception:
            continue
    db.commit()
    return {"updated": updated, "count": len(updated)}


@router.get("/{mlbam_id}/season-stats")
def get_season_stats(
    mlbam_id: int,
    position: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Compute season-level stats from statcast data stored in DB."""
    player = db.query(Player).filter(Player.mlbam_id == mlbam_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player_position = _resolve_player_position(player, db, position)

    # Get data date range
    if player_position == "B":
        dates = db.query(BatterStat.game_date).filter(BatterStat.player_mlbam_id == mlbam_id).all()
    else:
        dates = db.query(PitcherStat.game_date).filter(PitcherStat.player_mlbam_id == mlbam_id).all()
    all_dates = [d[0] for d in dates if d[0]]
    data_from = str(min(all_dates)) if all_dates else None
    data_through = str(max(all_dates)) if all_dates else None

    if player_position == "B":
        rows = db.query(BatterStat).filter(BatterStat.player_mlbam_id == mlbam_id).all()
        if not rows:
            return {"player": PlayerResponse.model_validate(player), "season_stats": []}

        # Group by game_date year → season
        by_season: dict = defaultdict(lambda: {
            "PA": 0, "AB": 0, "H": 0, "HR": 0, "2B": 0, "3B": 0,
            "BB": 0, "SO": 0, "HBP": 0,
            "woba_vals": [], "launch_speeds": [],
        })
        for r in rows:
            yr = r.game_date.year if r.game_date else 0
            s = by_season[yr]
            ev = r.events
            if ev in ("single", "double", "triple", "home_run",
                       "field_out", "strikeout", "walk", "hit_by_pitch",
                       "grounded_into_double_play", "force_out",
                       "sac_fly", "sac_bunt", "fielders_choice",
                       "fielders_choice_out", "double_play", "triple_play"):
                s["PA"] += 1
                if ev not in ("walk", "hit_by_pitch", "sac_fly", "sac_bunt", "intent_walk"):
                    s["AB"] += 1
                if ev == "single":
                    s["H"] += 1
                elif ev == "double":
                    s["H"] += 1; s["2B"] += 1
                elif ev == "triple":
                    s["H"] += 1; s["3B"] += 1
                elif ev == "home_run":
                    s["H"] += 1; s["HR"] += 1
                elif ev == "strikeout":
                    s["SO"] += 1
                elif ev == "walk":
                    s["BB"] += 1
                elif ev == "hit_by_pitch":
                    s["HBP"] += 1
            elif ev in ("walk", "intent_walk"):
                s["PA"] += 1; s["BB"] += 1
            if r.woba_value is not None:
                s["woba_vals"].append(r.woba_value)
            if r.launch_speed is not None:
                s["launch_speeds"].append(r.launch_speed)

        season_stats = []
        for yr in sorted(by_season.keys(), reverse=True):
            s = by_season[yr]
            ab = s["AB"] or 1
            pa = s["PA"] or 1
            avg = round(s["H"] / ab, 3) if ab else 0
            obp_num = s["H"] + s["BB"] + s["HBP"]
            obp_den = pa
            obp = round(obp_num / obp_den, 3) if obp_den else 0
            slg = round((s["H"] - s["2B"] - s["3B"] - s["HR"] + 2*s["2B"] + 3*s["3B"] + 4*s["HR"]) / ab, 3) if ab else 0
            season_stats.append({
                "season": yr,
                "PA": s["PA"], "AB": s["AB"], "H": s["H"],
                "HR": s["HR"], "2B": s["2B"], "3B": s["3B"],
                "BB": s["BB"], "SO": s["SO"],
                "AVG": f"{avg:.3f}", "OBP": f"{obp:.3f}", "SLG": f"{slg:.3f}",
                "OPS": f"{obp + slg:.3f}",
                "wOBA": f"{sum(s['woba_vals'])/len(s['woba_vals']):.3f}" if s["woba_vals"] else "—",
                "AvgEV": f"{sum(s['launch_speeds'])/len(s['launch_speeds']):.1f}" if s["launch_speeds"] else "—",
            })
        return {
            "player": PlayerResponse.model_validate(player),
            "season_stats": season_stats,
            "data_from": data_from,
            "data_through": data_through,
        }

    else:  # Pitcher
        rows = db.query(PitcherStat).filter(PitcherStat.player_mlbam_id == mlbam_id).all()
        if not rows:
            return {"player": PlayerResponse.model_validate(player), "season_stats": [], "data_from": None, "data_through": None}

        by_season: dict = defaultdict(lambda: {
            "pitches": 0,
            "speeds": [], "spins": [],
            "pitch_types": defaultdict(int),
        })
        for r in rows:
            yr = r.game_date.year if r.game_date else 0
            s = by_season[yr]
            s["pitches"] += 1
            pt = r.pitch_type or "UNK"
            s["pitch_types"][pt] += 1
            if r.release_speed is not None:
                s["speeds"].append(r.release_speed)
            if r.spin_rate is not None:
                s["spins"].append(r.spin_rate)

        season_stats = []
        for yr in sorted(by_season.keys(), reverse=True):
            s = by_season[yr]
            total = s["pitches"] or 1
            top_pitch = max(s["pitch_types"], key=s["pitch_types"].get) if s["pitch_types"] else "—"
            season_stats.append({
                "season": yr,
                "Pitches": s["pitches"],
                "AvgVelo": f"{sum(s['speeds'])/len(s['speeds']):.1f}" if s["speeds"] else "—",
                "AvgSpin": f"{sum(s['spins'])/len(s['spins']):.0f}" if s["spins"] else "—",
                "PrimaryPitch": top_pitch,
                "PitchMix": {pt: f"{cnt/total*100:.1f}%" for pt, cnt in sorted(s["pitch_types"].items(), key=lambda x: -x[1])},
            })
        return {
            "player": PlayerResponse.model_validate(player),
            "season_stats": season_stats,
            "data_from": data_from,
            "data_through": data_through,
        }


@router.get("/{mlbam_id}/stats")
def get_player_stats(
    mlbam_id: int,
    position: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    player = db.query(Player).filter(Player.mlbam_id == mlbam_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player_position = _resolve_player_position(player, db, position)

    last_date = _last_stat_date(db, mlbam_id, player_position)
    today = date.today()

    if last_date is None:
        # DB에 없으면 즉시 ingest
        start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        if player_position == "B":
            ingest_batter_stats(db, mlbam_id, player.name, start, end)
        else:
            ingest_pitcher_stats(db, mlbam_id, player.name, start, end)
    elif (today - last_date).days >= AUTO_INGEST_DAYS:
        # 1일 이상 지났으면 백그라운드 업데이트
        start = last_date.strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        _trigger_background_ingest(player, start, end)

    if player_position == "B":
        total = db.query(BatterStat).filter(BatterStat.player_mlbam_id == mlbam_id).count()
        stats = db.query(BatterStat).filter(BatterStat.player_mlbam_id == mlbam_id)\
            .order_by(BatterStat.game_date.desc()).limit(100).all()
        return {
            "player": PlayerResponse.model_validate(player),
            "stats": [BatterStatResponse.model_validate(s) for s in stats],
            "total": total,
            "displayed": len(stats),
            "sample_unit": "pitches seen",
            "sample_limit": 100,
        }
    else:
        total = db.query(PitcherStat).filter(PitcherStat.player_mlbam_id == mlbam_id).count()
        stats = db.query(PitcherStat).filter(PitcherStat.player_mlbam_id == mlbam_id)\
            .order_by(PitcherStat.game_date.desc()).limit(100).all()
        return {
            "player": PlayerResponse.model_validate(player),
            "stats": [PitcherStatResponse.model_validate(s) for s in stats],
            "total": total,
            "displayed": len(stats),
            "sample_unit": "pitches thrown",
            "sample_limit": 100,
        }


@router.post("/ingest", response_model=IngestResponse)
def ingest_player(body: IngestRequest, db: Session = Depends(get_db)):
    if body.position not in ("B", "P"):
        raise HTTPException(status_code=422, detail="position must be 'B' or 'P'")

    if body.position == "B":
        rows = ingest_batter_stats(db, body.mlbam_id, body.name, body.start_date, body.end_date)
    else:
        rows = ingest_pitcher_stats(db, body.mlbam_id, body.name, body.start_date, body.end_date)

    return IngestResponse(
        mlbam_id=body.mlbam_id,
        name=body.name,
        position=body.position,
        rows_inserted=rows,
    )


@router.post("/ingest/async")
def ingest_player_async(body: IngestRequest):
    if body.position not in ("B", "P"):
        raise HTTPException(status_code=422, detail="position must be 'B' or 'P'")

    from app.tasks import ingest_player_task
    task = ingest_player_task.delay(
        body.mlbam_id, body.name, body.position, body.start_date, body.end_date
    )
    return {"task_id": task.id, "status": "queued"}


@router.post("/{mlbam_id}/refresh")
def refresh_player_cache(mlbam_id: int, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.mlbam_id == mlbam_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    invalidate_all_predictions(mlbam_id)
    today = date.today()
    last_date = _last_stat_date(db, mlbam_id, player.position)
    start = (last_date or today - timedelta(days=365)).strftime("%Y-%m-%d")
    _trigger_background_ingest(player, start, today.strftime("%Y-%m-%d"))
    return {"mlbam_id": mlbam_id, "status": "cache invalidated, background ingest triggered"}


@router.get("/{mlbam_id}/predict")
def predict_player(
    mlbam_id: int,
    position: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    player = db.query(Player).filter(Player.mlbam_id == mlbam_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    player_position = _resolve_player_position(player, db, position)

    # Redis 캐시 확인
    cached = get_prediction(mlbam_id, player_position)
    if cached:
        return cached

    last_date = _last_stat_date(db, mlbam_id, player_position)
    today = date.today()
    if last_date is None:
        start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        if player_position == "B":
            ingest_batter_stats(db, mlbam_id, player.name, start, end)
        else:
            ingest_pitcher_stats(db, mlbam_id, player.name, start, end)
    elif (today - last_date).days >= AUTO_INGEST_DAYS:
        start = last_date.strftime("%Y-%m-%d")
        _trigger_background_ingest(player, start, today.strftime("%Y-%m-%d"))

    if player_position == "B":
        stats = db.query(BatterStat).filter(BatterStat.player_mlbam_id == mlbam_id)\
            .order_by(BatterStat.game_date.desc()).limit(500).all()
    else:
        stats = db.query(PitcherStat).filter(PitcherStat.player_mlbam_id == mlbam_id)\
            .order_by(PitcherStat.game_date.desc()).limit(500).all()

    if not stats:
        raise HTTPException(status_code=404, detail="No stats found. Run /players/ingest first.")

    prediction = gemini_predict_player(player, stats)
    sample_unit = "pitches seen" if player_position == "B" else "pitches thrown"
    result = {
        "player": PlayerResponse.model_validate(player).model_dump(),
        "prediction": prediction,
        "sample_size": len(stats),
        "sample_unit": sample_unit,
        "sample_limit": 500,
        "cached": False,
    }
    set_prediction(mlbam_id, player_position, result)
    return result
