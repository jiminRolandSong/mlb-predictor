from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.player import Player, Matchup
from app.models.batter import BatterStat
from app.models.pitcher import PitcherStat
from app.schemas.player import MatchupResponse
from app.services.gemini_service import predict_matchup

router = APIRouter(prefix="/matchup", tags=["matchups"])


@router.get("/{batter_id}/{pitcher_id}", response_model=MatchupResponse)
def get_matchup(batter_id: int, pitcher_id: int, db: Session = Depends(get_db)):
    matchup = (
        db.query(Matchup)
        .filter(
            Matchup.batter_mlbam_id == batter_id,
            Matchup.pitcher_mlbam_id == pitcher_id,
        )
        .order_by(Matchup.game_date.desc())
        .first()
    )
    if not matchup:
        raise HTTPException(status_code=404, detail="No matchup prediction found")
    return matchup


@router.post("/{batter_id}/{pitcher_id}", response_model=MatchupResponse)
def create_matchup(batter_id: int, pitcher_id: int, db: Session = Depends(get_db)):
    batter = db.query(Player).filter(Player.mlbam_id == batter_id).first()
    pitcher = db.query(Player).filter(Player.mlbam_id == pitcher_id).first()

    if not batter:
        raise HTTPException(status_code=404, detail=f"Batter {batter_id} not found")
    if not pitcher:
        raise HTTPException(status_code=404, detail=f"Pitcher {pitcher_id} not found")

    batter_stats = (
        db.query(BatterStat)
        .filter(BatterStat.player_mlbam_id == batter_id)
        .order_by(BatterStat.game_date.desc())
        .limit(100)
        .all()
    )
    pitcher_stats = (
        db.query(PitcherStat)
        .filter(PitcherStat.player_mlbam_id == pitcher_id)
        .order_by(PitcherStat.game_date.desc())
        .limit(100)
        .all()
    )

    if not batter_stats:
        raise HTTPException(status_code=404, detail=f"No stats for batter {batter_id}. Run /players/ingest first.")
    if not pitcher_stats:
        raise HTTPException(status_code=404, detail=f"No stats for pitcher {pitcher_id}. Run /players/ingest first.")

    prediction = predict_matchup(batter, batter_stats, pitcher, pitcher_stats)
    prediction["sample_context"] = {
        "batter_sample_size": len(batter_stats),
        "batter_sample_unit": "pitches faced",
        "batter_sample_limit": 100,
        "pitcher_sample_size": len(pitcher_stats),
        "pitcher_sample_unit": "pitches thrown",
        "pitcher_sample_limit": 100,
        "basis": "Recent Statcast pitch-level samples for each player, not direct head-to-head history.",
    }

    matchup = Matchup(
        batter_mlbam_id=batter_id,
        pitcher_mlbam_id=pitcher_id,
        game_date=date.today(),
        gemini_prediction=prediction,
    )
    db.add(matchup)
    db.commit()
    db.refresh(matchup)
    return matchup
