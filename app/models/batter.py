from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class BatterStat(Base):
    __tablename__ = "batter_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_mlbam_id = Column(Integer, index=True)
    game_date = Column(Date, index=True)
    game_pk = Column(Integer)
    at_bat_number = Column(Integer)
    pitch_number = Column(Integer)

    # 구종
    pitch_type = Column(String)
    pitch_name = Column(String)

    # 타격 결과
    events = Column(String)
    bb_type = Column(String)

    # 타구 데이터
    launch_speed = Column(Float)
    launch_angle = Column(Float)
    hit_distance = Column(Float)
    estimated_ba = Column(Float)
    hc_x = Column(Float)
    hc_y = Column(Float)

    # 스트라이크 존
    plate_x = Column(Float)
    plate_z = Column(Float)

    # 상황 변수
    inning = Column(Integer)
    inning_topbot = Column(String)
    balls = Column(Integer)
    strikes = Column(Integer)
    outs_when_up = Column(Integer)

    # 고급 지표
    woba_value = Column(Float)
    iso_value = Column(Float)
    babip_value = Column(Float)

    created_at = Column(DateTime, default=func.now())
