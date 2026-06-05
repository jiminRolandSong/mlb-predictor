from pydantic import BaseModel
from datetime import date
from typing import Optional


class PitcherStatResponse(BaseModel):
    game_date: date

    pitch_type: Optional[str] = None
    pitch_name: Optional[str] = None

    release_speed: Optional[float] = None
    effective_speed: Optional[float] = None
    spin_rate: Optional[float] = None
    pfx_x: Optional[float] = None
    pfx_z: Optional[float] = None

    plate_x: Optional[float] = None
    plate_z: Optional[float] = None
    zone: Optional[float] = None

    inning: Optional[int] = None
    inning_topbot: Optional[str] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    outs_when_up: Optional[int] = None

    model_config = {"from_attributes": True}
