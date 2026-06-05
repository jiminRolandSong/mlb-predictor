import pybaseball
import pandas as pd
from sqlalchemy.orm import Session
from app.models.player import Player
from app.models.pitcher import PitcherStat

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


def ingest_pitcher_stats(db: Session, mlbam_id: int, name: str, start_date: str, end_date: str) -> int:
    player = db.query(Player).filter(Player.mlbam_id == mlbam_id).first()
    if not player:
        player = Player(mlbam_id=mlbam_id, name=name, position="P")
        db.add(player)
        db.commit()
        db.refresh(player)
    elif player.position != "P" or player.name != name:
        player.position = "P"
        player.name = name
        db.commit()

    df = pybaseball.statcast_pitcher(start_date, end_date, player_id=mlbam_id)
    if df.empty:
        return 0

    # Filter to regular season and postseason only (exclude Spring Training 'S', All-Star 'A')
    if "game_type" in df.columns:
        df = df[df["game_type"].isin(["R", "F", "D", "L", "W"])]
    if df.empty:
        return 0

    # Extract pitcher's team via inning_topbot: Top=home pitches, Bot=away pitches
    recent = df.sort_values("game_date", ascending=False).iloc[0]
    team = None
    if "home_team" in df.columns and "away_team" in df.columns:
        topbot = recent.get("inning_topbot", "")
        if topbot == "Top" and pd.notna(recent.get("home_team")):
            team = str(recent["home_team"])
        elif topbot == "Bot" and pd.notna(recent.get("away_team")):
            team = str(recent["away_team"])
        elif pd.notna(recent.get("home_team")):
            team = str(recent["home_team"])
    if team and player.team != team:
        player.team = team
        db.commit()
    
    
    existing_keys = {
        (r.game_pk, r.at_bat_number, r.pitch_number)
        for r in db.query(PitcherStat.game_pk, PitcherStat.at_bat_number, PitcherStat.pitch_number)
        .filter(PitcherStat.player_mlbam_id == mlbam_id, PitcherStat.game_pk.isnot(None))
        .all()
    }
    existing_dates = {
        r.game_date
        for r in db.query(PitcherStat.game_date)
        .filter(PitcherStat.player_mlbam_id == mlbam_id)
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
        PitcherStat(
            player_mlbam_id=mlbam_id,
            game_date=row["game_date"],
            game_pk=_int_or_none(row.get("game_pk")),
            at_bat_number=_int_or_none(row.get("at_bat_number")),
            pitch_number=_int_or_none(row.get("pitch_number")),
            pitch_type=_str_or_none(row.get("pitch_type")),
            pitch_name=_str_or_none(row.get("pitch_name")),
            release_speed=_float_or_none(row.get("release_speed")),
            effective_speed=_float_or_none(row.get("effective_speed")),
            spin_rate=_float_or_none(row.get("release_spin_rate")),
            pfx_x=_float_or_none(row.get("pfx_x")),
            pfx_z=_float_or_none(row.get("pfx_z")),
            plate_x=_float_or_none(row.get("plate_x")),
            plate_z=_float_or_none(row.get("plate_z")),
            zone=_float_or_none(row.get("zone")),
            inning=_int_or_none(row.get("inning")),
            inning_topbot=_str_or_none(row.get("inning_topbot")),
            balls=_int_or_none(row.get("balls")),
            strikes=_int_or_none(row.get("strikes")),
            outs_when_up=_int_or_none(row.get("outs_when_up")),
        )
        for _, row in df.iterrows()
    ]
    db.bulk_save_objects(stats)
    db.commit()
    return len(stats)
