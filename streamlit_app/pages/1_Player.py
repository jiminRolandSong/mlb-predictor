import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from utils.api import (
    ingest_player,
    get_player_stats,
    get_season_stats,
    predict_player,
    search_player,
)


st.set_page_config(page_title="Player Analysis", page_icon="MLB", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.4rem;
        max-width: 1500px;
    }
    div[data-testid="stMetric"] {
        background: #f7f8fb;
        border: 1px solid #e6e8ef;
        border-radius: 8px;
        padding: 12px 14px;
    }
    .player-hero {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 18px 20px;
        background: #fbfcfe;
        margin-bottom: 16px;
    }
    .player-name {
        font-size: 28px;
        line-height: 1.15;
        font-weight: 750;
        margin: 0 0 6px 0;
        color: #111827;
    }
    .player-subtitle {
        color: #4b5563;
        font-size: 14px;
        margin: 0;
    }
    .role-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 4px 10px;
        background: #eef2ff;
        color: #3730a3;
        font-weight: 650;
        margin-left: 6px;
    }
    .soft-note {
        color: #6b7280;
        font-size: 13px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


POSITION_OPTIONS = {"Pitcher": "P", "Batter": "B"}
POSITION_LABELS = {"P": "Pitcher", "B": "Batter"}


def _init_state() -> None:
    defaults = {
        "selected_mlbam_id": None,
        "selected_name": "",
        "search_results": [],
        "analysis_position": "P",
        "load_player_data": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _safe_df(records) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _position_code_from_label(label: str) -> str:
    return POSITION_OPTIONS.get(label, "P")


def _position_label_from_code(code: str) -> str:
    return POSITION_LABELS.get(code, "Unknown")


def _format_number(value, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _clean_label(value) -> str:
    if not isinstance(value, str) or not value:
        return "Unknown"
    return value.replace("_", " ").title()


def _render_pitcher_charts(df: pd.DataFrame) -> None:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Pitch Mix")
        if {"pitch_type"}.issubset(df.columns) and df["pitch_type"].notna().any():
            mix_df = df["pitch_type"].dropna().value_counts().reset_index()
            mix_df.columns = ["Pitch", "Count"]
            fig = px.pie(mix_df, names="Pitch", values="Count", hole=0.42)
            fig.update_layout(height=360, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No pitch mix data yet.")

    with col2:
        st.markdown("#### Average Spin by Pitch")
        if {"spin_rate", "pitch_type"}.issubset(df.columns) and df["spin_rate"].notna().any():
            spin_df = (
                df[df["spin_rate"].notna()]
                .groupby("pitch_type", dropna=True)["spin_rate"]
                .mean()
                .reset_index()
                .rename(columns={"spin_rate": "Avg Spin Rate"})
                .sort_values("Avg Spin Rate", ascending=False)
            )
            fig = px.bar(
                spin_df,
                x="pitch_type",
                y="Avg Spin Rate",
                color="Avg Spin Rate",
                color_continuous_scale="Viridis",
                labels={"pitch_type": "Pitch", "Avg Spin Rate": "rpm"},
            )
            fig.update_layout(height=360, margin=dict(t=10, b=10), coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No spin-rate data yet.")

    st.markdown("#### Average Velocity by Pitch")
    if {"release_speed", "pitch_type"}.issubset(df.columns) and df["release_speed"].notna().any():
        velo_df = (
            df[df["release_speed"].notna()]
            .groupby("pitch_type", dropna=True)["release_speed"]
            .agg(["mean", "max", "count"])
            .reset_index()
            .rename(columns={"mean": "Avg Velo", "max": "Max Velo", "count": "Pitches"})
            .sort_values("Avg Velo", ascending=False)
        )
        velo_df["Avg Velo"] = velo_df["Avg Velo"].round(1)
        velo_df["Max Velo"] = velo_df["Max Velo"].round(1)
        fig = px.bar(
            velo_df,
            x="pitch_type",
            y="Avg Velo",
            text="Avg Velo",
            hover_data=["Max Velo", "Pitches"],
            color="Avg Velo",
            color_continuous_scale="Tealgrn",
            labels={"pitch_type": "Pitch", "Avg Velo": "mph"},
        )
        y_min = max(0, velo_df["Avg Velo"].min() - 2)
        y_max = velo_df["Avg Velo"].max() + 2
        fig.update_yaxes(range=[y_min, y_max])
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(height=380, margin=dict(t=10, b=10), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No velocity data yet.")


def _render_batter_charts(df: pd.DataFrame) -> None:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Pitch Type Summary")
        if "pitch_type" in df.columns and df["pitch_type"].notna().any():
            agg_spec = {"Pitches": ("pitch_type", "count")}
            if "woba_value" in df.columns:
                agg_spec["wOBA"] = ("woba_value", "mean")
            if "launch_speed" in df.columns:
                agg_spec["Avg EV"] = ("launch_speed", "mean")

            pitch_df = (
                df.dropna(subset=["pitch_type"])
                .groupby("pitch_type")
                .agg(**agg_spec)
                .reset_index()
                .rename(columns={"pitch_type": "Pitch"})
                .sort_values("Pitches", ascending=False)
            )
            if "wOBA" in pitch_df.columns:
                pitch_df["wOBA"] = pitch_df["wOBA"].map(lambda value: _format_number(value, 3))
            if "Avg EV" in pitch_df.columns:
                pitch_df["Avg EV"] = pitch_df["Avg EV"].map(lambda value: _format_number(value, 1))
            st.dataframe(pitch_df, use_container_width=True, hide_index=True)
        else:
            st.info("No pitch-type data yet.")

    with col2:
        st.markdown("#### Plate Appearance Results")
        if "events" in df.columns and df["events"].notna().any():
            ev_df = df["events"].dropna().value_counts().head(10).reset_index()
            ev_df.columns = ["Event", "Count"]
            ev_df["Event"] = ev_df["Event"].map(_clean_label)
            fig = px.bar(
                ev_df,
                x="Count",
                y="Event",
                orientation="h",
                text="Count",
                color_discrete_sequence=["#2563eb"],
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(
                height=360,
                margin=dict(t=10, b=10, r=35),
                yaxis=dict(autorange="reversed"),
                xaxis_title="Count",
                yaxis_title=None,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No event data yet.")

    st.markdown("#### Launch Speed vs Launch Angle")
    if {"launch_speed", "launch_angle"}.issubset(df.columns) and df["launch_speed"].notna().any():
        sc_df = df[df["launch_speed"].notna() & df["launch_angle"].notna()].copy()
        if sc_df.empty:
            st.info("No batted-ball launch data yet.")
        else:
            if "bb_type" not in sc_df.columns:
                sc_df["bb_type"] = "unknown"
            sc_df["bb_type"] = sc_df["bb_type"].fillna("unknown")
            hover_cols = [col for col in ["events", "pitch_type"] if col in sc_df.columns]
            fig = px.scatter(
                sc_df,
                x="launch_speed",
                y="launch_angle",
                color="bb_type",
                hover_data=hover_cols,
                labels={
                    "launch_speed": "Exit Velocity (mph)",
                    "launch_angle": "Launch Angle",
                    "bb_type": "Batted Ball",
                },
                opacity=0.65,
            )
            fig.update_layout(height=400, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No launch data yet.")


_init_state()

st.markdown(
    """
    <div class="player-hero">
      <p class="player-name">Player Analysis</p>
      <p class="player-subtitle">Search a player, choose the role to analyze, then load Statcast-backed charts and AI notes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.container():
    st.markdown("### Player Setup")
    search_col, role_col = st.columns([2.3, 1])

    with search_col:
        with st.form("player_search_form", clear_on_submit=False):
            name_col1, name_col2, button_col = st.columns([1, 1, 0.45])
            last_name = name_col1.text_input("Last name", placeholder="Skenes")
            first_name = name_col2.text_input("First name", placeholder="Paul")
            submitted = button_col.form_submit_button("Search", use_container_width=True)

        if submitted:
            if not last_name.strip():
                st.warning("Enter at least a last name.")
            else:
                with st.spinner("Searching players..."):
                    try:
                        st.session_state.search_results = search_player(last_name.strip(), first_name.strip())
                        st.session_state.selected_mlbam_id = None
                        st.session_state.selected_name = ""
                        st.session_state.load_player_data = False
                    except requests.HTTPError as exc:
                        st.error(f"Search failed: {exc}")

        if st.session_state.search_results:
            options = {
                f"{row['name']} (last MLB: {row.get('mlb_played_last', 'N/A')})": row
                for row in st.session_state.search_results
            }
            selected_option = st.selectbox("Select player", list(options.keys()))
            selected_player = options[selected_option]
            st.session_state.selected_mlbam_id = selected_player["mlbam_id"]
            st.session_state.selected_name = selected_player["name"]

    with role_col:
        current_role_label = _position_label_from_code(st.session_state.analysis_position)
        role_label = st.radio(
            "Analyze as",
            list(POSITION_OPTIONS.keys()),
            index=list(POSITION_OPTIONS.keys()).index(current_role_label),
            horizontal=True,
            help="Use Pitcher for Paul Skenes. This selection is also sent to the API.",
        )
        st.session_state.analysis_position = _position_code_from_label(role_label)

        start_date = st.date_input("Start date", value=date(2025, 4, 1))
        end_date = st.date_input("End date", value=date.today())

    selected_id = st.session_state.selected_mlbam_id
    selected_name = st.session_state.selected_name
    selected_position = st.session_state.analysis_position
    selected_role = _position_label_from_code(selected_position)

    if selected_id:
        st.success(f"Selected {selected_name} as {selected_role} (MLBAM {selected_id})")

        action_col1, action_col2, action_col3 = st.columns([0.8, 0.8, 3])
        ingest_clicked = action_col1.button("Ingest / Update", type="primary", use_container_width=True)
        load_clicked = action_col2.button("Load Data", use_container_width=True)

        if ingest_clicked:
            with st.spinner(f"Fetching {selected_role.lower()} Statcast data..."):
                try:
                    result = ingest_player(
                        selected_id,
                        selected_name,
                        selected_position,
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d"),
                    )
                    st.session_state.load_player_data = True
                    rows = result["rows_inserted"]
                    if rows:
                        st.success(f"Added {rows} new rows for {selected_name} ({selected_role}).")
                    else:
                        st.info(f"No new rows found. Saved {selected_name} as {selected_role}.")
                except requests.HTTPError as exc:
                    st.error(f"Ingest failed: {exc}")

        if load_clicked:
            st.session_state.load_player_data = True
    else:
        st.info("Search and select a player to begin.")
        st.stop()

if not st.session_state.load_player_data:
    st.stop()

with st.spinner("Loading player data..."):
    try:
        stats_data = get_player_stats(selected_id, selected_position)
        season_data = get_season_stats(selected_id, selected_position)
    except requests.HTTPError as exc:
        st.error(f"Could not load stats: {exc}")
        st.stop()

player = stats_data["player"]
stats = stats_data.get("stats", [])
season_stats = season_data.get("season_stats", [])
data_from = season_data.get("data_from")
data_through = season_data.get("data_through")
df = _safe_df(stats)
total_rows = stats_data.get("total", len(df))
displayed_rows = stats_data.get("displayed", len(df))
sample_unit = stats_data.get("sample_unit", "rows")
sample_limit = stats_data.get("sample_limit", displayed_rows)

player_role = _position_label_from_code(player.get("position"))
team = player.get("team") or "Team N/A"
st.markdown(
    f"""
    <div class="player-hero">
      <p class="player-name">{player['name']} <span class="role-pill">{player_role}</span></p>
      <p class="player-subtitle">{team} | MLBAM {player['mlbam_id']}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_cols = st.columns(5)
metric_cols[0].metric("Rows in DB", f"{total_rows:,}")
metric_cols[1].metric("Chart Sample", f"{displayed_rows:,}", f"latest {sample_unit}")
metric_cols[2].metric("Role", player_role)
metric_cols[3].metric("Data From", data_from or "-")
metric_cols[4].metric("Data Through", data_through or "-")
st.caption(
    f"Charts use the latest {displayed_rows:,} of up to {sample_limit:,} {sample_unit}. "
    "For batters, this is pitch-level data, not plate appearances."
)

tab_stats, tab_charts, tab_ai = st.tabs(["Stats", "Charts", "AI Prediction"])

with tab_stats:
    if not season_stats:
        st.info("No stats in DB for this role yet. Run Ingest / Update first.")
    else:
        df_season = pd.DataFrame(season_stats)
        if player.get("position") == "B":
            cols = ["season", "PA", "AB", "H", "HR", "2B", "3B", "BB", "SO", "AVG", "OBP", "SLG", "OPS", "wOBA", "AvgEV"]
        else:
            cols = ["season", "Pitches", "AvgVelo", "AvgSpin", "PrimaryPitch"]
        st.dataframe(df_season[[col for col in cols if col in df_season.columns]], use_container_width=True, hide_index=True)

        if player.get("position") == "P":
            for season_row in season_stats:
                pitch_mix = season_row.get("PitchMix")
                if pitch_mix:
                    st.markdown(f"#### {season_row['season']} Pitch Mix")
                    mix_table = pd.DataFrame(list(pitch_mix.items()), columns=["Pitch", "Usage"])
                    st.dataframe(mix_table, use_container_width=True, hide_index=True)

with tab_charts:
    st.caption(f"Chart sample: latest {displayed_rows:,} {sample_unit}.")
    if df.empty:
        st.info("No chart data available for this role.")
    elif player.get("position") == "P":
        _render_pitcher_charts(df)
    else:
        _render_batter_charts(df)

with tab_ai:
    if df.empty:
        st.info("AI prediction needs player stats first.")
    else:
        ai_unit = "pitches seen" if player.get("position") == "B" else "pitches thrown"
        st.caption(f"AI prediction uses the latest available sample, capped at 500 {ai_unit}.")
        if st.button("Generate AI Prediction", type="primary"):
            with st.spinner("Generating prediction..."):
                try:
                    pred_data = predict_player(selected_id, selected_position)
                    pred = pred_data["prediction"]
                    st.caption(
                        f"AI sample used: latest {pred_data.get('sample_size', 0):,} "
                        f"{pred_data.get('sample_unit', ai_unit)}."
                    )
                    st.info(pred.get("summary", ""))

                    strengths_col, weaknesses_col = st.columns(2)
                    with strengths_col:
                        st.markdown("#### Strengths")
                        for item in pred.get("strengths", []):
                            st.success(item)
                    with weaknesses_col:
                        st.markdown("#### Weaknesses")
                        for item in pred.get("weaknesses", []):
                            st.warning(item)

                    st.markdown("#### Prediction")
                    st.success(pred.get("prediction", ""))
                except requests.HTTPError as exc:
                    st.error(f"AI prediction failed: {exc}")
