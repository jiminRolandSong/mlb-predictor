import json
import re
from collections import defaultdict

from google import genai

from app.core.config import settings

_client = genai.Client(api_key=settings.gemini_api_key)
_MODEL = "models/gemini-2.5-flash"

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _parse_json(text: str) -> dict:
    match = _JSON_BLOCK.search(text)
    raw = match.group(1) if match else text
    return json.loads(raw.strip())


def _normalize_simulation(simulation: dict | None) -> dict | None:
    if not isinstance(simulation, dict) or not simulation.get("available", True):
        return simulation

    rates = simulation.get("outcome_rates")
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


def _summarize_batter(stats: list) -> str:
    pitch_woba: dict[str, list] = defaultdict(list)
    pitch_speed: dict[str, list] = defaultdict(list)
    bb_counts: dict[str, int] = defaultdict(int)
    events_counts: dict[str, int] = defaultdict(int)

    for s in stats:
        pt = s.pitch_type or "UNK"
        if s.woba_value is not None:
            pitch_woba[pt].append(s.woba_value)
        if s.launch_speed is not None:
            pitch_speed[pt].append(s.launch_speed)
        if s.bb_type:
            bb_counts[s.bb_type] += 1
        if s.events:
            events_counts[s.events] += 1

    MIN_SAMPLE = 5
    lines = [f"Recent {len(stats)} pitches faced:"]
    woba_reliable = {pt: v for pt, v in pitch_woba.items() if len(v) >= MIN_SAMPLE}
    if woba_reliable:
        lines.append("wOBA by pitch type (min 5 pitches): " + ", ".join(
            f"{pt}={sum(v)/len(v):.3f}(n={len(v)})" for pt, v in sorted(woba_reliable.items(), key=lambda x: -len(x[1]))
        ))
    speed_reliable = {pt: v for pt, v in pitch_speed.items() if len(v) >= MIN_SAMPLE}
    if speed_reliable:
        lines.append("Avg exit velocity by pitch type: " + ", ".join(
            f"{pt}={sum(v)/len(v):.1f}mph(n={len(v)})" for pt, v in sorted(speed_reliable.items(), key=lambda x: -len(x[1]))
        ))
    if bb_counts:
        lines.append("Batted ball distribution: " + ", ".join(
            f"{k}={v}" for k, v in sorted(bb_counts.items(), key=lambda x: -x[1])
        ))
    if events_counts:
        lines.append("Contact results: " + ", ".join(
            f"{k}={v}" for k, v in sorted(events_counts.items(), key=lambda x: -x[1])[:10]
        ))
    return "\n".join(lines)


def _summarize_pitcher(stats: list) -> str:
    pitch_count: dict[str, int] = defaultdict(int)
    pitch_speed: dict[str, list] = defaultdict(list)
    pitch_spin: dict[str, list] = defaultdict(list)

    for s in stats:
        pt = s.pitch_type or "UNK"
        pitch_count[pt] += 1
        if s.release_speed is not None:
            pitch_speed[pt].append(s.release_speed)
        if s.spin_rate is not None:
            pitch_spin[pt].append(s.spin_rate)

    total = sum(pitch_count.values()) or 1
    lines = [f"Recent {len(stats)} pitches:"]
    lines.append("Pitch mix: " + ", ".join(
        f"{pt}={v/total*100:.1f}%" for pt, v in sorted(pitch_count.items(), key=lambda x: -x[1])
    ))
    lines.append("Avg velocity by pitch: " + ", ".join(
        f"{pt}={sum(v)/len(v):.1f}mph" for pt, v in pitch_speed.items()
    ))
    lines.append("Avg spin rate by pitch: " + ", ".join(
        f"{pt}={sum(v)/len(v):.0f}rpm" for pt, v in pitch_spin.items()
    ))
    return "\n".join(lines)


def predict_player(player, stats: list) -> dict:
    if player.position == "B":
        data_summary = _summarize_batter(stats)
        role = "batter"
    else:
        data_summary = _summarize_pitcher(stats)
        role = "pitcher"

    prompt = f"""You are an expert MLB analyst. Analyze the following recent Statcast data for {player.name} ({role}) and provide a performance prediction.

{data_summary}

Respond in English only. Return ONLY a valid JSON object in this exact format (no markdown, no extra text):
{{
  "summary": "2-3 sentence overview of recent performance",
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "prediction": "1-2 sentence prediction for upcoming games"
}}"""

    response = _client.models.generate_content(model=_MODEL, contents=prompt)
    return _parse_json(response.text)


def predict_matchup(batter, batter_stats: list, pitcher, pitcher_stats: list) -> dict:
    batter_summary = _summarize_batter(batter_stats)
    pitcher_summary = _summarize_pitcher(pitcher_stats)

    prompt = f"""You are an expert MLB analyst and simulation analyst. Analyze this batter vs pitcher matchup using recent Statcast data.

Run an AI-driven matchup simulation in your reasoning:
- Treat the batter sample as recent pitch-level pitches faced.
- Treat the pitcher sample as recent pitch-level pitches thrown.
- Use the pitcher's pitch mix, velocity/spin profile, and the batter's pitch-type performance/contact results.
- Simulate 1,000 likely plate-appearance outcomes conceptually.
- This is not direct head-to-head history and not a full physics/game-state engine.
- Keep the numeric probabilities coherent and make outcome rates sum to about 100.

BATTER: {batter.name}
{batter_summary}

PITCHER: {pitcher.name}
{pitcher_summary}

Respond in English only. Return ONLY a valid JSON object in this exact format (no markdown, no extra text):
{{
  "advantage": "batter" or "pitcher" or "even",
  "summary": "2-3 sentence matchup analysis",
  "key_factors": ["factor 1", "factor 2", "factor 3"],
  "predicted_outcome": "1-2 sentence prediction for this matchup",
  "simulation": {{
    "available": true,
    "method": "AI-driven scenario simulation",
    "simulations": 1000,
    "outcome_rates": {{
      "Out": 0.0,
      "Strikeout": 0.0,
      "Hit": 0.0,
      "Walk/HBP": 0.0,
      "Home Run": 0.0,
      "Other": 0.0
    }},
    "batter_positive_outcome_rate": 0.0,
    "basis": "One concise sentence explaining the simulation basis",
    "assumptions": ["assumption 1", "assumption 2"]
  }}
}}"""

    response = _client.models.generate_content(model=_MODEL, contents=prompt)
    result = _parse_json(response.text)
    result["simulation"] = _normalize_simulation(result.get("simulation"))
    return result
