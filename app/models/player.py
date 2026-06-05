from sqlalchemy import Column, Integer, String, Date, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    mlbam_id = Column(Integer, unique=True, index=True)
    name = Column(String, nullable=False)
    team = Column(String)
    position = Column(String)  # P = 투수, B = 타자
    bats = Column(String)      # L, R, S
    throws = Column(String)    # L, R
    created_at = Column(DateTime, default=func.now())


class Matchup(Base):
    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True, index=True)
    batter_mlbam_id = Column(Integer, index=True)
    pitcher_mlbam_id = Column(Integer, index=True)
    game_date = Column(Date, index=True)
    gemini_prediction = Column(JSON)
    created_at = Column(DateTime, default=func.now())