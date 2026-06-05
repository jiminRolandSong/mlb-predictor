from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class PlayerResponse(BaseModel):
    mlbam_id: int
    name: str
    team: Optional[str] = None
    position: Optional[str] = None

    model_config = {"from_attributes": True}


class IngestRequest(BaseModel):
    mlbam_id: int
    name: str
    position: str  # "B" or "P"
    start_date: str
    end_date: str


class IngestResponse(BaseModel):
    mlbam_id: int
    name: str
    position: str
    rows_inserted: int


class MatchupResponse(BaseModel):
    batter_mlbam_id: int
    pitcher_mlbam_id: int
    game_date: Optional[date] = None
    gemini_prediction: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}