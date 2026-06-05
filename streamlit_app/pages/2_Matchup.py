import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from utils.api import create_matchup, search_player, list_players


st.set_page_config(page_title="Matchup Analysis", page_icon="MLB", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.4rem;
        max-width: 1450px;
    }
    .matchup-hero {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 18px 20px;
        background: #fbfcfe;
        margin-bottom: 16px;
    }
    .matchup-title {
        font-size: 28px;
        line-height: 1.15;
        font-weight: 750;
        margin: 0 0 6px 0;
        color: #111827;
    }
    .matchup-subtitle {
        color: #4b5563;
        font-size: 14px;
        margin: 0;
    }
    div[data-testid="stMetric"] {
        background: #f7f8fb;
        border: 1px solid #e6e8ef;
        border-radius: 8px;
        padding: 12px 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="matchup-hero">
      <p class="matchup-title">Matchup Analysis</p>
      <p class="matchup-subtitle">AI prediction plus an AI-driven matchup simulation.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info("Both players need ingested stats from the Player Analysis page first.")


@st.cache_data(ttl=30)
def get_db_players():
    try:
        return list_players()
    except Exception:
        return []


def fmt(player: dict) -> str:
    return f"{player['name']} ({player.get('team') or '?'})"


def init_state() -> None:
    defaults = {
        "b_id": None,
        "b_name": "",
        "p_id": None,
        "p_name": "",
        "b_search_res": [],
        "p_search_res": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def player_picker(role: str, db_list: list, id_key: str, name_key: str, res_key: str) -> None:
    position_code = "B" if role == "Batter" else "P"
    st.markdown(f"### {role}")

    if db_list:
        db_options = ["Select from DB"] + [fmt(player) for player in db_list]
        db_choice = st.selectbox(f"Ingested {role}s", db_options, key=f"{role}_db")
        if db_choice != "Select from DB":
            chosen = db_list[db_options.index(db_choice) - 1]
            st.session_state[id_key] = chosen["mlbam_id"]
            st.session_state[name_key] = chosen["name"]
    else:
        st.caption(f"No ingested {role.lower()}s yet. Search below to find one.")

    with st.expander("Search for a different player"):
        last_col, first_col, button_col = st.columns([1, 1, 0.4])
        last = last_col.text_input("Last name", key=f"{role}_last")
        first = first_col.text_input("First name", key=f"{role}_first")
        if button_col.button("Search", key=f"{role}_search", use_container_width=True):
            if not last.strip():
                st.warning("Enter at least a last name.")
            else:
                with st.spinner("Searching..."):
                    try:
                        st.session_state[res_key] = search_player(last.strip(), first.strip())
                    except requests.HTTPError as exc:
                        st.error(str(exc))

        if st.session_state[res_key]:
            options = {
                f"{row['name']} (last MLB: {row.get('mlb_played_last', 'N/A')})": row
                for row in st.session_state[res_key]
            }
            chosen = options[st.selectbox("Results", list(options.keys()), key=f"{role}_sel")]
            st.session_state[id_key] = chosen["mlbam_id"]
            st.session_state[name_key] = chosen["name"]
            # 선택 시 해당 포지션으로 자동 ingest 안내
            if chosen["mlbam_id"] not in [p["mlbam_id"] for p in db_list]:
                st.info(f"{chosen['name']} is not ingested yet. Go to Player Analysis and ingest as {role}.")

    if st.session_state[id_key]:
        st.success(f"{st.session_state[name_key]} | MLBAM {st.session_state[id_key]}")


def normalize_simulation(simulation: dict) -> dict:
    if not isinstance(simulation, dict) or not simulation.get("available", True):
        return simulation

    rates = simulation.get("outcome_rates", {})
    if isinstance(rates, dict) and rates:
        numeric_rates = {}
        for key, value in rates.items():
            try:
                numeric_rates[key] = float(value)
            except (TypeError, ValueError):
                numeric_rates[key] = 0.0

        total = sum(numeric_rates.values())
        if 0.95 <= total <= 1.05:
            numeric_rates = {key: value * 100 for key, value in numeric_rates.items()}
        elif total and not 95 <= total <= 105:
            numeric_rates = {key: value / total * 100 for key, value in numeric_rates.items()}

        simulation["outcome_rates"] = {
            key: round(max(0.0, value), 1)
            for key, value in numeric_rates.items()
        }

    positive = simulation.get("batter_positive_outcome_rate")
    try:
        positive_value = float(positive)
        if 0 <= positive_value <= 1:
            positive_value *= 100
        simulation["batter_positive_outcome_rate"] = round(positive_value, 1)
    except (TypeError, ValueError):
        rates = simulation.get("outcome_rates", {})
        simulation["batter_positive_outcome_rate"] = round(
            sum(float(rates.get(key, 0)) for key in ("Hit", "Walk/HBP", "Home Run")),
            1,
        )

    return simulation


def render_simulation(simulation: dict) -> None:
    simulation = normalize_simulation(simulation)
    if not simulation:
        return
    if not simulation.get("available"):
        st.info(f"Simulation unavailable: {simulation.get('reason', 'not enough data')}")
        return

    st.markdown("#### AI Matchup Simulation")
    sim_col1, sim_col2 = st.columns(2)
    sim_col1.metric("Simulated PA", f"{simulation.get('simulations', 0):,}")
    sim_col2.metric("Batter Positive Outcome", f"{simulation.get('batter_positive_outcome_rate', 0):.1f}%")
    st.caption(f"Method: {simulation.get('method', 'AI-driven scenario simulation')}")

    outcome_rates = simulation.get("outcome_rates", {})
    if outcome_rates:
        sim_df = pd.DataFrame(
            [{"Outcome": key, "Rate": value} for key, value in outcome_rates.items()]
        )
        fig = px.bar(
            sim_df,
            x="Rate",
            y="Outcome",
            orientation="h",
            text="Rate",
            color_discrete_sequence=["#2563eb"],
            labels={"Rate": "Simulated Rate (%)", "Outcome": "Outcome"},
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
        fig.update_layout(height=320, margin=dict(t=10, b=10, r=45), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    st.caption(simulation.get("basis", ""))
    assumptions = simulation.get("assumptions", [])
    if assumptions:
        with st.expander("Simulation assumptions"):
            for assumption in assumptions:
                st.write(f"- {assumption}")


init_state()
db_players = get_db_players()
batters = [player for player in db_players if player["position"] == "B"]
pitchers = [player for player in db_players if player["position"] == "P"]

col_b, col_p = st.columns(2)
with col_b:
    player_picker("Batter", batters, "b_id", "b_name", "b_search_res")
with col_p:
    player_picker("Pitcher", pitchers, "p_id", "p_name", "p_search_res")

st.divider()
ready = st.session_state.b_id and st.session_state.p_id
st.caption(
    "AI basis: latest 100 pitch-level rows per player. "
    "Simulation basis: AI-generated 1,000 PA scenario distribution from recent Statcast summaries. "
    "Neither is direct head-to-head history."
)

if st.button("Analyze Matchup", disabled=not ready, type="primary"):
    batter_name = st.session_state.b_name
    pitcher_name = st.session_state.p_name
    with st.spinner(f"Analyzing {batter_name} vs {pitcher_name}..."):
        try:
            result = create_matchup(st.session_state.b_id, st.session_state.p_id)
        except requests.HTTPError as exc:
            st.error(f"Matchup analysis failed: {exc}")
            st.stop()

    pred = result.get("gemini_prediction", {})
    sample_context = pred.get("sample_context", {})
    simulation = pred.get("simulation", {})
    advantage = pred.get("advantage", "even").lower()

    adv_color = {"batter": "#16a34a", "pitcher": "#dc2626"}.get(advantage, "#6b7280")
    adv_label = {
        "batter": f"Advantage: Batter - {batter_name}",
        "pitcher": f"Advantage: Pitcher - {pitcher_name}",
        "even": "Advantage: Even",
    }.get(advantage, advantage.upper())

    st.markdown(
        f"<div style='background:{adv_color};color:white;padding:18px 24px;border-radius:8px;"
        f"font-size:1.35rem;font-weight:700;text-align:center;margin-bottom:18px;'>"
        f"{adv_label}</div>",
        unsafe_allow_html=True,
    )

    summary_col, factor_col = st.columns([3, 2])
    with summary_col:
        st.markdown("#### AI Matchup Summary")
        st.write(pred.get("summary", "-"))
        outcome = pred.get("predicted_outcome", "")
        if outcome:
            st.markdown("#### Predicted Outcome")
            st.success(outcome)

    with factor_col:
        key_factors = pred.get("key_factors", [])
        if key_factors:
            st.markdown("#### Key Factors")
            for factor in key_factors:
                st.info(factor)

    render_simulation(simulation)

    if sample_context:
        st.caption(
            "Sample used: "
            f"batter latest {sample_context.get('batter_sample_size', 'N/A')} "
            f"{sample_context.get('batter_sample_unit', 'rows')}; "
            f"pitcher latest {sample_context.get('pitcher_sample_size', 'N/A')} "
            f"{sample_context.get('pitcher_sample_unit', 'rows')}. "
            f"{sample_context.get('basis', '')}"
        )
    st.caption(f"Saved to DB | Game date: {result.get('game_date', 'N/A')}")
