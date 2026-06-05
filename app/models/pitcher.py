from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class PitcherStat(Base):
    __tablename__ = "pitcher_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_mlbam_id = Column(Integer, index=True)
    game_date = Column(Date, index=True)
    game_pk = Column(Integer)
    at_bat_number = Column(Integer)
    pitch_number = Column(Integer)

    # 구종
    pitch_type = Column(String)
    pitch_name = Column(String)

    # 구속 / 무브먼트
    release_speed = Column(Float)
    effective_speed = Column(Float)
    spin_rate = Column(Float)
    pfx_x = Column(Float)
    pfx_z = Column(Float)

    # 스트라이크 존
    plate_x = Column(Float)
    plate_z = Column(Float)
    zone = Column(Float)

    # 상황 변수
    inning = Column(Integer)
    inning_topbot = Column(String)
    balls = Column(Integer)
    strikes = Column(Integer)
    outs_when_up = Column(Integer)

    created_at = Column(DateTime, default=func.now())
