"""
Smart Home Energy Advisor — Flask Backend
IBM Watsonx.ai  |  IBM Granite Model  |  Sydney Region
"""

import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from ibm_watsonx_ai import APIClient, Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Import customisable agent instructions ────────────────────────────────────
from agent_instructions import (
    build_system_prompt,
    COMMON_APPLIANCES,
    STATE_TARIFF_RATES,
    DEFAULT_TARIFF_RATE,
    DEFAULT_CURRENCY,
    AGENT_NAME,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
_base_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(_base_dir, "templates"),
            static_folder=os.path.join(_base_dir, "static"))

# Use env var if set; otherwise generate a stable random key so sessions always work.
_secret = os.getenv("FLASK_SECRET_KEY") or os.urandom(32).hex()
app.secret_key = _secret
CORS(app)

# ── IBM Watsonx.ai configuration ──────────────────────────────────────────────
IBM_API_KEY    = os.getenv("IBM_CLOUD_API_KEY")
PROJECT_ID     = os.getenv("IBM_WATSONX_PROJECT_ID")
_raw_url       = os.getenv("IBM_WATSONX_URL", "https://au-syd.ml.cloud.ibm.com").strip()
# Ensure the URL always carries a proper https:// scheme
if _raw_url and not _raw_url.startswith("https://"):
    _raw_url = "https://" + _raw_url.lstrip("/")
WATSONX_URL    = _raw_url or "https://au-syd.ml.cloud.ibm.com"

# Best available instruct model for this Watsonx.ai project (Sydney region)
# Granite 3-3 is not available in this project — using Llama 3.3 70B instruct
MODEL_ID = "meta-llama/llama-3-3-70b-instruct"

# ── Watsonx client initialisation ─────────────────────────────────────────────
watsonx_client = None
model_inference = None

def init_watsonx():
    """Initialise the IBM Watsonx.ai client and model inference object."""
    global watsonx_client, model_inference
    try:
        credentials = Credentials(
            url=WATSONX_URL,
            api_key=IBM_API_KEY,
        )
        watsonx_client = APIClient(credentials=credentials, project_id=PROJECT_ID)

        model_inference = ModelInference(
            model_id=MODEL_ID,
            credentials=credentials,
            project_id=PROJECT_ID,
        )
        logger.info("✅ IBM Watsonx.ai client initialised — model: %s", MODEL_ID)
    except Exception as exc:
        logger.error("❌ Failed to initialise Watsonx.ai client: %s", exc)
        model_inference = None


init_watsonx()

# ── System prompt (from agent_instructions.py) ────────────────────────────────
SYSTEM_PROMPT = build_system_prompt()

# ── In-memory conversation history per session ────────────────────────────────
conversation_store: dict[str, list[dict]] = {}


def get_or_create_history(session_id: str) -> list[dict]:
    if session_id not in conversation_store:
        conversation_store[session_id] = []
    return conversation_store[session_id]


def build_messages(history: list[dict], user_message: str) -> list[dict]:
    """
    Build the messages list for the chat() API.
    Keeps the last 8 turns to stay within context limits.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-8:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def call_model(messages: list[dict], max_tokens: int = 1024) -> str:
    """Call the Watsonx.ai chat API and return the response text."""
    response = model_inference.chat(
        messages=messages,
        params={
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "top_p": 0.9,
        },
    )
    return response["choices"][0]["message"]["content"].strip()


# ════════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Serve the main dashboard page."""
    if "session_id" not in session:
        session["session_id"] = os.urandom(16).hex()
    return render_template("index.html", agent_name=AGENT_NAME)


# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages and return AI response."""
    try:
        data = request.get_json(force=True)
        user_message = (data.get("message") or "").strip()
        session_id   = session.get("session_id", "default")

        if not user_message:
            return jsonify({"error": "Empty message"}), 400

        history = get_or_create_history(session_id)

        if model_inference is None:
            response_text = (
                "⚠️ The AI model is temporarily unavailable. "
                "Please check your IBM Cloud API key and project ID, then restart the server."
            )
        else:
            messages = build_messages(history, user_message)
            response_text = call_model(messages)
            if not response_text:
                response_text = "I'm sorry, I couldn't generate a response."

        # Store turn in history
        history.append({"role": "user",      "content": user_message})
        history.append({"role": "assistant", "content": response_text})

        return jsonify({
            "response": response_text,
            "timestamp": datetime.now().strftime("%H:%M"),
            "session_id": session_id,
        })

    except Exception as exc:
        logger.exception("Chat error: %s", exc)
        return jsonify({"error": f"Server error: {str(exc)}"}), 500


# ── Bill analysis endpoint ────────────────────────────────────────────────────
@app.route("/api/analyze-bill", methods=["POST"])
def analyze_bill():
    """Analyse an electricity bill and return AI-powered insights."""
    try:
        data         = request.get_json(force=True)
        units        = float(data.get("units", 0))
        state        = data.get("state", "Maharashtra")
        month        = data.get("month", "January")
        prev_units   = float(data.get("prev_units", 0))

        tariff = STATE_TARIFF_RATES.get(state, DEFAULT_TARIFF_RATE)
        bill_amount = units * tariff

        # Tiered slab calculation (generic Indian domestic structure)
        slab_breakdown = _calculate_slab(units, tariff)

        carbon_kg = round(units * 0.82, 2)   # India's grid emission factor ≈ 0.82 kg CO₂/kWh
        change_pct = round(((units - prev_units) / prev_units * 100), 1) if prev_units else 0

        # AI narrative
        analysis_prompt = (
            f"A household in {state} consumed {units} kWh in {month}. "
            f"The tariff is ₹{tariff}/kWh, total bill ≈ ₹{bill_amount:.0f}. "
            f"Previous month usage was {prev_units} kWh (change: {change_pct}%). "
            f"Carbon footprint: {carbon_kg} kg CO₂. "
            "Provide a 5-point personalised energy-saving action plan with estimated monthly savings in INR."
        )

        ai_analysis = ""
        if model_inference:
            messages = build_messages([], analysis_prompt)
            ai_analysis = call_model(messages)
        else:
            ai_analysis = "AI analysis unavailable — model not initialised."

        return jsonify({
            "units": units,
            "state": state,
            "tariff": tariff,
            "bill_amount": round(bill_amount, 2),
            "slab_breakdown": slab_breakdown,
            "carbon_kg": carbon_kg,
            "change_pct": change_pct,
            "ai_analysis": ai_analysis,
            "currency": DEFAULT_CURRENCY,
        })

    except Exception as exc:
        logger.exception("Bill analysis error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Appliance tracker endpoint ────────────────────────────────────────────────
@app.route("/api/calculate-appliance", methods=["POST"])
def calculate_appliance():
    """Calculate energy consumption for a list of appliances."""
    try:
        data       = request.get_json(force=True)
        appliances = data.get("appliances", [])   # [{id, quantity, hours}, ...]
        state      = data.get("state", "Maharashtra")
        tariff     = STATE_TARIFF_RATES.get(state, DEFAULT_TARIFF_RATE)

        results = []
        total_daily_kwh   = 0.0
        total_monthly_kwh = 0.0

        for item in appliances:
            app_id   = item.get("id")
            qty      = float(item.get("quantity", 1))
            hours    = float(item.get("hours", 0))
            base     = COMMON_APPLIANCES.get(app_id)
            if not base:
                continue
            watts        = base["watts"]
            daily_kwh    = round(watts * qty * hours / 1000, 3)
            monthly_kwh  = round(daily_kwh * 30, 2)
            monthly_cost = round(monthly_kwh * tariff, 2)
            total_daily_kwh   += daily_kwh
            total_monthly_kwh += monthly_kwh
            results.append({
                "label":        base["label"],
                "watts":        watts,
                "quantity":     qty,
                "hours":        hours,
                "daily_kwh":    daily_kwh,
                "monthly_kwh":  monthly_kwh,
                "monthly_cost": monthly_cost,
            })

        total_monthly_cost   = round(total_monthly_kwh * tariff, 2)
        total_carbon_monthly = round(total_monthly_kwh * 0.82, 2)

        return jsonify({
            "appliances":           results,
            "total_daily_kwh":      round(total_daily_kwh, 3),
            "total_monthly_kwh":    round(total_monthly_kwh, 2),
            "total_monthly_cost":   total_monthly_cost,
            "total_carbon_monthly": total_carbon_monthly,
            "tariff":               tariff,
            "state":                state,
        })

    except Exception as exc:
        logger.exception("Appliance calculation error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Appliance list endpoint ───────────────────────────────────────────────────
@app.route("/api/appliances", methods=["GET"])
def list_appliances():
    """Return the list of common Indian appliances."""
    return jsonify(COMMON_APPLIANCES)


# ── State tariff endpoint ─────────────────────────────────────────────────────
@app.route("/api/tariffs", methods=["GET"])
def list_tariffs():
    """Return state-wise tariff rates."""
    return jsonify(STATE_TARIFF_RATES)


# ── Energy tips endpoint ──────────────────────────────────────────────────────
@app.route("/api/energy-tips", methods=["POST"])
def energy_tips():
    """Generate personalised energy-saving tips based on usage profile."""
    try:
        data    = request.get_json(force=True)
        profile = data.get("profile", {})

        prompt = (
            f"Based on this Indian household energy profile: {json.dumps(profile)}, "
            "generate 6 highly specific, actionable energy-saving tips. "
            "Include estimated monthly savings in INR for each tip. "
            "Format as a numbered list."
        )

        tips = ""
        if model_inference:
            messages = build_messages([], prompt)
            tips = call_model(messages)
        else:
            tips = "AI tips unavailable — model not initialised."

        return jsonify({"tips": tips})

    except Exception as exc:
        logger.exception("Energy tips error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Carbon footprint endpoint ─────────────────────────────────────────────────
@app.route("/api/carbon-footprint", methods=["POST"])
def carbon_footprint():
    """Calculate and contextualise carbon footprint from electricity usage."""
    try:
        data         = request.get_json(force=True)
        monthly_kwh  = float(data.get("monthly_kwh", 0))
        annual_kwh   = monthly_kwh * 12

        emission_factor = 0.82     # kg CO₂ per kWh (India grid average, CEA 2023)
        monthly_co2  = round(monthly_kwh  * emission_factor, 2)
        annual_co2   = round(annual_kwh   * emission_factor, 2)

        # Equivalences
        trees_year   = round(annual_co2 / 21.77, 1)   # 1 tree absorbs ~21.77 kg CO₂/yr
        car_km       = round(annual_co2 / 0.21, 0)    # avg car ~0.21 kg CO₂/km

        return jsonify({
            "monthly_kwh":  monthly_kwh,
            "annual_kwh":   annual_kwh,
            "monthly_co2":  monthly_co2,
            "annual_co2":   annual_co2,
            "trees_to_offset": trees_year,
            "equivalent_car_km": car_km,
            "emission_factor": emission_factor,
        })

    except Exception as exc:
        logger.exception("Carbon footprint error: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "watsonx_connected": model_inference is not None,
        "model": MODEL_ID,
        "region": "Sydney (au-syd)",
        "timestamp": datetime.now().isoformat(),
    })


# ── Clear conversation history ────────────────────────────────────────────────
@app.route("/api/clear-history", methods=["POST"])
def clear_history():
    """Clear conversation history for the current session."""
    session_id = session.get("session_id", "default")
    conversation_store.pop(session_id, None)
    return jsonify({"status": "cleared"})


# ════════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def _calculate_slab(units: float, tariff: float) -> list[dict]:
    """
    Generic Indian domestic slab structure.
    Adjust slabs per your DISCOM's schedule.
    """
    slabs = [
        {"range": "0–100 units",   "rate_factor": 0.70},
        {"range": "101–200 units", "rate_factor": 0.90},
        {"range": "201–300 units", "rate_factor": 1.00},
        {"range": "300+ units",    "rate_factor": 1.20},
    ]
    breakdown = []
    remaining = units
    boundaries = [100, 200, 300]
    rate_factors = [0.70, 0.90, 1.00, 1.20]
    labels = ["0–100 units", "101–200 units", "201–300 units", "300+ units"]
    prev = 0

    for i, boundary in enumerate([100, 100, 100, float("inf")]):
        if remaining <= 0:
            break
        consumed = min(remaining, boundary)
        cost = round(consumed * tariff * rate_factors[i], 2)
        breakdown.append({
            "slab":     labels[i],
            "units":    round(consumed, 2),
            "rate":     round(tariff * rate_factors[i], 2),
            "cost":     cost,
        })
        remaining -= consumed

    return breakdown


# ════════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port  = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    logger.info("🚀 Starting Smart Home Energy Advisor on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
