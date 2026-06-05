from app.core.database import SessionLocal
from app.services.pybaseball_service import ingest_batter_stats, ingest_pitcher_stats

db = SessionLocal()
count = ingest_batter_stats(db, 592450, "Aaron Judge", "2026-04-01", "2026-06-01")
print(f"Aaron Judge 2026: {count}개 저장됨")

count = ingest_pitcher_stats(db, 543037, "Gerrit Cole", "2026-04-01", "2026-06-01")
print(f"Gerrit Cole 2026: {count}개 저장됨")