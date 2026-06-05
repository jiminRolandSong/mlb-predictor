import streamlit as st

st.set_page_config(
    page_title="MLB Player Performance Predictor",
    page_icon="⚾",
    layout="wide",
)

st.title("⚾ MLB Player Performance Predictor")
st.markdown("""
Welcome to the MLB Player Performance Predictor powered by **Statcast data** and **Gemini AI**.

### How to use
1. **Player Analysis** — Ingest a player's Statcast data, view charts, and get an AI performance prediction.
2. **Matchup Analysis** — Compare a batter vs. pitcher and get an AI-powered advantage analysis.
3. **Dashboard** — Look up previously saved matchup predictions.

Use the sidebar on the left to navigate between pages.

---
**Data source:** Baseball Savant via pybaseball
**AI:** Google Gemini 2.5 Flash
**Backend:** FastAPI running on `localhost:8000`
""")
