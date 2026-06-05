from pydantic import BaseModel
from datetime import date
from typing import Optional


class BatterStatResponse(BaseModel):
    game_date: date

    pitch_type: Optional[str] = None
    pitch_name: Optional[str] = None

    events: Optional[str] = None
    bb_type: Optional[str] = None

    launch_speed: Optional[float] = None
    launch_angle: Optional[float] = None
    hit_distance: Optional[float] = None
    estimated_ba: Optional[float] = None
    hc_x: Optional[float] = None
    hc_y: Optional[float] = None

    plate_x: Optional[float] = None
    plate_z: Optional[float] = None

    inning: Optional[int] = None
    inning_topbot: Optional[str] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    outs_when_up: Optional[int] = None

    woba_value: Optional[float] = None
    iso_value: Optional[float] = None
    babip_value: Optional[float] = None

    model_config = {"from_attributes": True}
