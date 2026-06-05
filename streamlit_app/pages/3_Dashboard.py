import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests
from utils.api import get_matchup, search_player, list_players

st.set_page_config(page_title="Dashboard", page_icon="⚾", layout="wide")
st.title("Dashboard")
st.caption("Look up previously saved matchup predictions.")

# ── Load DB players ───────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_db_players():
    try:
        return list_players()
    except Exception:
        return []

db_players = get_db_players()
batters = [p for p in db_players if p["position"] == "B"]
pitchers = [p for p in db_players if p["position"] == "P"]

def fmt(p):
    return f"{p['name']} ({p.get('team') or '?'})"

# ── Session state ─────────────────────────────────────────────────────────────
for k in ["db_b_id", "db_b_name", "db_p_id", "db_p_name", "db_b_res", "db_p_res"]:
    if k not in st.session_state:
        st.session_state[k] = None if k.endswith("_id") else ("" if k.endswith("_name") else [])

def player_picker(role: str, db_list: list, id_key: str, name_key: str, res_key: str):
    st.markdown(f"### {role}")
    if db_list:
        db_options = ["— Select from DB —"] + [fmt(p) for p in db_list]
        db_choice = st.selectbox(f"Ingested {role}s", db_options, key=f"db_{role}_db")
        if db_choice != "— Select from DB —":
            idx = db_options.index(db_choice) - 1
            chosen = db_list[idx]
            st.session_state[id_key] = chosen["mlbam_id"]
            st.session_state[name_key] = chosen["name"]
    else:
        st.caption("No ingested players yet.")

    with st.expander("Search for a different player"):
        c1, c2, c3 = st.columns([3, 3, 1])
        with c1:
            last = st.text_input("Last Name", key=f"db_{role}_last")
        with c2:
            first = st.text_input("First Name", key=f"db_{role}_first")
        with c3:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("Search", key=f"db_{role}_search", use_container_width=True):
                if last.strip():
                    with st.spinner("Searching..."):
                        try:
                            st.session_state[res_key] = search_player(last.strip(), first.strip())
                        except requests.HTTPError as e:
                            st.error(str(e))
        if st.session_state[res_key]:
            opts = {f"{r['name']} (last MLB: {r.get('mlb_played_last','N/A')})": r
                    for r in st.session_state[res_key]}
            chosen = opts[st.selectbox("Results:", list(opts.keys()), key=f"db_{role}_sel")]
            st.session_state[id_key] = chosen["mlbam_id"]
            st.session_state[name_key] = chosen["name"]

    if st.session_state[id_key]:
        st.success(f"**{st.session_state[name_key]}** — ID: {st.session_state[id_key]}")


col_b, col_p = st.columns(2)
with col_b:
    player_picker("Batter", batters, "db_b_id", "db_b_name", "db_b_res")
with col_p:
    player_picker("Pitcher", pitchers, "db_p_id", "db_p_name", "db_p_res")

# ── Lookup ─────────────────────────────────────────────────────────────────────
st.divider()
ready = st.session_state.db_b_id and st.session_state.db_p_id
if st.button("Look Up Stored Prediction", disabled=not ready, type="primary"):
    try:
        result = get_matchup(st.session_state.db_b_id, st.session_state.db_p_id)
    except requests.HTTPError as e:
        st.error(f"No stored prediction found: {e}")
        st.stop()

    pred = result.get("gemini_prediction", {})
    advantage = pred.get("advantage", "even").lower()
    batter_name = st.session_state.db_b_name
    pitcher_name = st.session_state.db_p_name

    adv_color = {"batter": "#28a745", "pitcher": "#dc3545"}.get(advantage, "#6c757d")
    adv_label = {
        "batter": f"Advantage: BATTER — {batter_name}",
        "pitcher": f"Advantage: PITCHER — {pitcher_name}",
        "even": "Advantage: EVEN",
    }.get(advantage, advantage.upper())

    st.markdown(
        f"<div style='background:{adv_color};color:white;padding:20px 28px;border-radius:10px;"
        f"font-size:1.5rem;font-weight:bold;text-align:center;margin-bottom:20px;'>"
        f"{adv_label}</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Game date: {result.get('game_date','N/A')} | Saved: {result.get('created_at','N/A')}")

    sum_col, factor_col = st.columns([3, 2])
    with sum_col:
        st.markdown("#### Matchup Summary")
        st.write(pred.get("summary", "—"))
        outcome = pred.get("predicted_outcome", "")
        if outcome:
            st.markdown("#### Predicted Outcome")
            st.success(outcome)
    with factor_col:
        key_factors = pred.get("key_factors", [])
        if key_factors:
            st.markdown("#### Key Factors")
            for factor in key_factors:
                st.markdown(
                    f"<div style='background:#f0f2f6;padding:10px 14px;border-radius:6px;"
                    f"margin-bottom:8px;'>• {factor}</div>",
                    unsafe_allow_html=True,
                )

# ── How to use ────────────────────────────────────────────────────────────────
st.divider()
with st.expander("How to use this app"):
    st.markdown("""
1. **Player Analysis** — Search a player by name → select → set position + date → **Ingest Data** → **Load Stats + AI Predict**
2. **Matchup Analysis** — Select ingested batter + pitcher → **Analyze Matchup**
3. **Dashboard (here)** — Look up any previously saved matchup prediction

| Player | MLBAM ID | Team |
|---|---|---|
| Aaron Judge | 592450 | NYY |
| Gerrit Cole | 543037 | NYY |
| Shohei Ohtani | 660271 | LAD |
| Freddie Freeman | 518692 | LAD |
| Spencer Strider | 675911 | ATL |
""")
