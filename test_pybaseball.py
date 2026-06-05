import pybaseball
pybaseball.cache.enable()

# Baseball Savant statcast 데이터
stats = pybaseball.statcast_batter('2024-04-01', '2024-09-30', player_id=592450)
print(stats[['game_date', 'events', 'launch_speed', 'launch_angle', 'estimated_ba_using_speedangle']].head(10))