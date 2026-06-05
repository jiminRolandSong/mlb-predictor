import pybaseball
import pandas as pd
from sqlalchemy.orm import Session
from app.models.player import Player
from app.models.batter import BatterStat

try:
    pybaseball.cache.enable()
except OSError:
    pass


def _str_or_none(val):
    return val if (isinstance(val, str) and val) else None


def _float_or_none(val):
    return float(val) if pd.notna(val) else None


def _int_or_none(val):
    return int(val) if pd.notna(val) else None


def ingest_batter_stats(db: Session, mlbam_id: int, name: str, start_date: str, end_date: str) -> int:
    player = db.query(Player).filter(Player.mlbam_id == mlbam_id).first()
    if not player:
        player = Player(mlbam_id=mlbam_id, name=name, position="B")
        db.add(player)
        db.commit()
        db.refresh(player)
    elif player.position != "B" or player.name != name:
        player.position = "B"
        player.name = name
        db.commit()

    df = pybaseball.statcast_batter(start_date, end_date, player_id=mlbam_id)
    if df.empty:
        return 0

    # Filter to regular season and postseason only (exclude Spring Training 'S', All-Star 'A')
    if "game_type" in df.columns:
        df = df[df["game_type"].isin(["R", "F", "D", "L", "W"])]
    if df.empty:
        return 0

    # Extract batter's team: away_team when batter is visitor, home_team when home
    # Use the most recent game row
    recent = df.sort_values("game_date", ascending=False).iloc[0]
    team = None
    if "away_team" in df.columns and "home_team" in df.columns:
        # Ohtani as batter (id=batter col) — check inning_topbot: Top=away bats, Bot=home bats
        topbot = recent.get("inning_topbot", "")
        if topbot == "Top" and pd.notna(recent.get("away_team")):
            team = str(recent["away_team"])
        elif topbot == "Bot" and pd.notna(recent.get("home_team")):
            team = str(recent["home_team"])
        elif pd.notna(recent.get("away_team")):
            team = str(recent["away_team"])
    if team and player.team != team:
        player.team = team
        db.commit()
    # Use game_pk+at_bat_number+pitch_number as unique key to prevent duplicate ingest
    existing_keys = {
        (r.game_pk, r.at_bat_number, r.pitch_number)
        for r in db.query(BatterStat.game_pk, BatterStat.at_bat_number, BatterStat.pitch_number)
        .filter(BatterStat.player_mlbam_id == mlbam_id, BatterStat.game_pk.isnot(None))
        .all()
    }
    existing_dates = {
        r.game_date
        for r in db.query(BatterStat.game_date)
        .filter(BatterStat.player_mlbam_id == mlbam_id)
        .all()
    }
    if existing_keys:
        # Precise pitch-level dedup
        mask = df.apply(
            lambda row: (
                int(row["game_pk"]) if pd.notna(row.get("game_pk")) else None,
                int(row["at_bat_number"]) if pd.notna(row.get("at_bat_number")) else None,
                int(row["pitch_number"]) if pd.notna(row.get("pitch_number")) else None,
            ) not in existing_keys,
            axis=1,
        )
        df = df[mask]
    elif existing_dates:
        # Fallback: date-level dedup for legacy rows without game_pk
        df = df[~df["game_date"].isin(existing_dates)]
    if df.empty:
        return 0

    stats = [
        BatterStat(
            player_mlbam_id=mlbam_id,
            game_date=row["game_date"],
            game_pk=_int_or_none(row.get("game_pk")),
            at_bat_number=_int_or_none(row.get("at_bat_number")),
            pitch_number=_int_or_none(row.get("pitch_number")),
            pitch_type=_str_or_none(row.get("pitch_type")),
            pitch_name=_str_or_none(row.get("pitch_name")),
            events=_str_or_none(row.get("events")),
            bb_type=_str_or_none(row.get("bb_type")),
            launch_speed=_float_or_none(row.get("launch_speed")),
            launch_angle=_float_or_none(row.get("launch_angle")),
            hit_distance=_float_or_none(row.get("hit_distance_sc")),
            estimated_ba=_float_or_none(row.get("estimated_ba_using_speedangle")),
            hc_x=_float_or_none(row.get("hc_x")),
            hc_y=_float_or_none(row.get("hc_y")),
            plate_x=_float_or_none(row.get("plate_x")),
            plate_z=_float_or_none(row.get("plate_z")),
            inning=_int_or_none(row.get("inning")),
            inning_topbot=_str_or_none(row.get("inning_topbot")),
            balls=_int_or_none(row.get("balls")),
            strikes=_int_or_none(row.get("strikes")),
            outs_when_up=_int_or_none(row.get("outs_when_up")),
            woba_value=_float_or_none(row.get("woba_value")),
            iso_value=_float_or_none(row.get("iso_value")),
            babip_value=_float_or_none(row.get("babip_value")),
        )
        for _, row in df.iterrows()
    ]
    db.bulk_save_objects(stats)
    db.commit()
    return len(stats)
