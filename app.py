"""
Smart Home Energy Advisor — Flask Backend
IBM Watsonx.ai  |  IBM Granite Model  |  Sydney Region
"""

import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, render_template_string, request, jsonify, session
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

# Inline template — avoids any filesystem template-folder lookup on Render
_INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>⚡ Smart Home Energy Advisor — Powered by IBM Granite</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" />
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet" />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet" />
  <link href="/static/css/style.css" rel="stylesheet" />
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-custom sticky-top">
  <div class="container-fluid px-3 px-lg-4">
    <a class="navbar-brand d-flex align-items-center gap-2" href="#">
      <div class="brand-icon"><i class="bi bi-lightning-charge-fill"></i></div>
      <div>
        <span class="brand-name">{{ agent_name }}</span>
        <span class="brand-sub d-none d-sm-inline"> · Smart Energy Advisor</span>
      </div>
    </a>
    <div class="d-flex align-items-center gap-2 ms-auto">
      <div class="status-pill" id="connectionStatus">
        <span class="status-dot"></span>
        <span class="status-text d-none d-sm-inline">Connecting…</span>
      </div>
      <button class="btn-icon" id="themeToggle" title="Toggle Dark Mode">
        <i class="bi bi-moon-stars-fill" id="themeIcon"></i>
      </button>
      <button class="navbar-toggler btn-icon" type="button" data-bs-toggle="collapse" data-bs-target="#navMenu">
        <i class="bi bi-list"></i>
      </button>
    </div>
    <div class="collapse navbar-collapse" id="navMenu">
      <ul class="navbar-nav ms-auto gap-1 py-2 py-lg-0">
        <li class="nav-item"><a class="nav-link" href="#" onclick="showSection('dashboard')"><i class="bi bi-speedometer2 me-1"></i>Dashboard</a></li>
        <li class="nav-item"><a class="nav-link" href="#" onclick="showSection('chat')"><i class="bi bi-chat-dots me-1"></i>AI Chat</a></li>
        <li class="nav-item"><a class="nav-link" href="#" onclick="showSection('bill')"><i class="bi bi-receipt me-1"></i>Bill Analyzer</a></li>
        <li class="nav-item"><a class="nav-link" href="#" onclick="showSection('appliance')"><i class="bi bi-plug me-1"></i>Appliances</a></li>
        <li class="nav-item"><a class="nav-link" href="#" onclick="showSection('carbon')"><i class="bi bi-tree me-1"></i>Carbon</a></li>
      </ul>
    </div>
  </div>
</nav>
<section class="hero-banner" id="heroBanner">
  <div class="container text-center py-5">
    <div class="hero-badge mb-3 animate-fade-in">⚡ Powered by IBM Granite AI</div>
    <h1 class="hero-title animate-slide-up">Smart Home Energy Advisor</h1>
    <p class="hero-sub animate-slide-up delay-1">
      AI-powered electricity analysis, bill estimation, and personalised energy-saving tips<br class="d-none d-md-block"/>
      for Indian households — built on IBM Watsonx.ai
    </p>
    <div class="d-flex justify-content-center gap-3 flex-wrap animate-slide-up delay-2">
      <button class="btn btn-hero-primary" onclick="showSection('chat')">
        <i class="bi bi-chat-dots-fill me-2"></i>Ask {{ agent_name }}
      </button>
      <button class="btn btn-hero-outline" onclick="showSection('dashboard')">
        <i class="bi bi-bar-chart-line me-2"></i>View Dashboard
      </button>
    </div>
  </div>
</section>
<section class="kpi-strip" id="kpiStrip">
  <div class="container-fluid px-3 px-lg-5">
    <div class="row g-3 justify-content-center">
      <div class="col-6 col-md-3">
        <div class="kpi-card animate-pop delay-1">
          <i class="bi bi-lightning-charge kpi-icon text-warning"></i>
          <div class="kpi-value" id="kpiUnits">—</div>
          <div class="kpi-label">Units This Month</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="kpi-card animate-pop delay-2">
          <i class="bi bi-currency-rupee kpi-icon text-success"></i>
          <div class="kpi-value" id="kpiBill">—</div>
          <div class="kpi-label">Estimated Bill</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="kpi-card animate-pop delay-3">
          <i class="bi bi-tree kpi-icon text-info"></i>
          <div class="kpi-value" id="kpiCarbon">—</div>
          <div class="kpi-label">CO₂ Emitted (kg)</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="kpi-card animate-pop delay-4">
          <i class="bi bi-graph-down-arrow kpi-icon text-danger"></i>
          <div class="kpi-value" id="kpiSavings">—</div>
          <div class="kpi-label">Potential Savings</div>
        </div>
      </div>
    </div>
  </div>
</section>
<main class="main-content container-fluid px-3 px-lg-5 py-4">
  <section id="dashboard" class="content-section active">
    <div class="section-header mb-4">
      <h2><i class="bi bi-speedometer2 me-2"></i>Energy Dashboard</h2>
      <p class="text-muted">Monitor your home's electricity consumption at a glance</p>
    </div>
    <div class="row g-4">
      <div class="col-lg-8">
        <div class="card-panel h-100">
          <div class="card-panel-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="bi bi-bar-chart-fill me-2 text-primary"></i>Monthly Consumption (kWh)</h5>
            <select class="form-select form-select-sm w-auto" id="dashboardYear" onchange="updateDashboardCharts()">
              <option value="2024">2024</option>
              <option value="2025" selected>2025</option>
            </select>
          </div>
          <div class="chart-container"><canvas id="monthlyChart"></canvas></div>
        </div>
      </div>
      <div class="col-lg-4">
        <div class="card-panel h-100">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-pie-chart-fill me-2 text-warning"></i>Appliance Share</h5>
          </div>
          <div class="chart-container-sm"><canvas id="applianceDonut"></canvas></div>
        </div>
      </div>
      <div class="col-lg-6">
        <div class="card-panel">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-activity me-2 text-success"></i>Daily Usage Pattern</h5>
          </div>
          <div class="chart-container"><canvas id="dailyPattern"></canvas></div>
        </div>
      </div>
      <div class="col-lg-6">
        <div class="card-panel">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-cash-stack me-2 text-danger"></i>Bill Trend (₹)</h5>
          </div>
          <div class="chart-container"><canvas id="billTrend"></canvas></div>
        </div>
      </div>
    </div>
  </section>
  <section id="chat" class="content-section">
    <div class="section-header mb-4">
      <h2><i class="bi bi-chat-dots me-2"></i>Ask {{ agent_name }}</h2>
      <p class="text-muted">Your AI-powered electricity advisor — ask anything about energy, bills, or savings</p>
    </div>
    <div class="row g-4 justify-content-center">
      <div class="col-lg-10 col-xl-8">
        <div class="chat-window">
          <div class="chat-header">
            <div class="d-flex align-items-center gap-3">
              <div class="agent-avatar"><i class="bi bi-lightning-charge-fill"></i></div>
              <div>
                <div class="fw-600">{{ agent_name }}</div>
                <div class="chat-status text-success"><span class="online-dot"></span> Online</div>
              </div>
            </div>
            <button class="btn-icon" onclick="clearChat()" title="Clear chat">
              <i class="bi bi-trash3"></i>
            </button>
          </div>
          <div class="chat-messages" id="chatMessages"></div>
          <div class="quick-prompts px-3 pb-2" id="quickPrompts">
            <div class="quick-prompts-label">Quick questions:</div>
            <div class="d-flex flex-wrap gap-2">
              <button class="chip" onclick="sendQuickPrompt('How can I reduce my electricity bill?')">💡 Reduce bill</button>
              <button class="chip" onclick="sendQuickPrompt('Which AC temperature is most energy efficient?')">❄️ AC tips</button>
              <button class="chip" onclick="sendQuickPrompt('What are BEE star ratings?')">⭐ BEE ratings</button>
              <button class="chip" onclick="sendQuickPrompt('Is solar panel a good investment for my home?')">☀️ Solar ROI</button>
              <button class="chip" onclick="sendQuickPrompt('How to calculate my monthly electricity bill?')">🧮 Bill calc</button>
              <button class="chip" onclick="sendQuickPrompt('What is peak hour electricity usage?')">⏰ Peak hours</button>
            </div>
          </div>
          <div class="chat-input-area">
            <div class="input-group">
              <textarea id="chatInput" class="form-control chat-textarea"
                placeholder="Ask about electricity, appliances, solar, bills, savings…"
                rows="1" onkeydown="handleChatKey(event)" oninput="autoResize(this)"></textarea>
              <button class="btn btn-send" id="sendBtn" onclick="sendMessage()">
                <i class="bi bi-send-fill"></i>
              </button>
            </div>
            <div class="input-hint">Press Enter to send · Shift+Enter for new line</div>
          </div>
        </div>
      </div>
    </div>
  </section>
  <section id="bill" class="content-section">
    <div class="section-header mb-4">
      <h2><i class="bi bi-receipt me-2"></i>Electricity Bill Analyzer</h2>
      <p class="text-muted">Enter your meter readings and get a detailed bill breakdown with AI insights</p>
    </div>
    <div class="row g-4">
      <div class="col-lg-5">
        <div class="card-panel">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-input-cursor me-2"></i>Enter Details</h5>
          </div>
          <div class="p-3">
            <div class="mb-3">
              <label class="form-label fw-500">State / DISCOM</label>
              <select class="form-select" id="billState"><option value="">Select your state…</option></select>
            </div>
            <div class="mb-3">
              <label class="form-label fw-500">Billing Month</label>
              <select class="form-select" id="billMonth">
                <option>January</option><option>February</option><option>March</option>
                <option>April</option><option>May</option><option>June</option>
                <option>July</option><option>August</option><option>September</option>
                <option>October</option><option>November</option><option selected>December</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label fw-500">Units Consumed (kWh)</label>
              <input type="number" class="form-control" id="billUnits" placeholder="e.g. 350" min="0" />
            </div>
            <div class="mb-3">
              <label class="form-label fw-500">Previous Month Units (kWh)</label>
              <input type="number" class="form-control" id="billPrevUnits" placeholder="e.g. 300" min="0" />
            </div>
            <button class="btn btn-primary w-100 btn-animate" onclick="analyzeBill()">
              <i class="bi bi-calculator me-2"></i>Analyse Bill
            </button>
          </div>
        </div>
      </div>
      <div class="col-lg-7">
        <div class="card-panel h-100" id="billResults" style="display:none;">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-clipboard-data me-2"></i>Bill Breakdown</h5>
          </div>
          <div class="p-3">
            <div class="row g-3 mb-4" id="billSummaryRow"></div>
            <h6 class="fw-600 mb-2">Tariff Slab Breakdown</h6>
            <div class="table-responsive mb-4">
              <table class="table table-sm table-striped" id="slabTable">
                <thead><tr><th>Slab</th><th>Units</th><th>Rate (₹)</th><th>Cost (₹)</th></tr></thead>
                <tbody id="slabTableBody"></tbody>
              </table>
            </div>
            <div class="chart-container-sm"><canvas id="billSlabChart"></canvas></div>
          </div>
        </div>
        <div class="card-panel mt-4" id="billAiPanel" style="display:none;">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-robot me-2 text-primary"></i>AI Energy Analysis</h5>
          </div>
          <div class="p-3 ai-response-box" id="billAiText"></div>
        </div>
      </div>
    </div>
  </section>
  <section id="appliance" class="content-section">
    <div class="section-header mb-4">
      <h2><i class="bi bi-plug me-2"></i>Appliance Usage Tracker</h2>
      <p class="text-muted">Fill in the appliance details below, then click <strong>Calculate Consumption</strong> — it will auto-add and calculate instantly.</p>
    </div>
    <div class="row g-4">
      <div class="col-lg-5">
        <div class="card-panel">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-plus-circle me-2"></i>Add Appliance</h5>
          </div>
          <div class="p-3">
            <div class="mb-3">
              <label class="form-label fw-500">State</label>
              <select class="form-select" id="applianceState"><option value="">Select state…</option></select>
            </div>
            <div class="mb-3">
              <label class="form-label fw-500">Appliance</label>
              <select class="form-select" id="applianceSelect"><option value="">Select appliance…</option></select>
            </div>
            <div class="row g-2 mb-3">
              <div class="col-6">
                <label class="form-label fw-500">Quantity</label>
                <input type="number" class="form-control" id="applianceQty" value="1" min="1" max="20" />
              </div>
              <div class="col-6">
                <label class="form-label fw-500">Hours / Day</label>
                <input type="number" class="form-control" id="applianceHours" placeholder="e.g. 5" min="0.1" max="24" step="0.5" />
              </div>
            </div>
            <div class="step-hint mb-3">
              <span class="step-badge">Step 1</span> Fill appliance details above, then click <strong>Add to List</strong>.<br/>
              <span class="step-badge">Step 2</span> Add more appliances if needed.<br/>
              <span class="step-badge">Step 3</span> Click <strong>Calculate Consumption</strong> to get results.<br/>
              <small class="text-muted">💡 Tip: You can also click Calculate directly — it will auto-add the current appliance.</small>
            </div>
            <button class="btn btn-secondary w-100 btn-animate mb-2" onclick="addAppliance()">
              <i class="bi bi-plus-lg me-2"></i>Add to List
            </button>
            <button class="btn btn-primary w-100 btn-animate" onclick="calculateAppliances()">
              <i class="bi bi-calculator me-2"></i>Calculate Consumption
            </button>
          </div>
        </div>
        <div class="card-panel mt-4">
          <div class="card-panel-header d-flex justify-content-between">
            <h5 class="mb-0"><i class="bi bi-list-ul me-2"></i>My Appliances</h5>
            <button class="btn-link-sm" onclick="clearAppliances()">Clear all</button>
          </div>
          <div class="p-3">
            <div id="applianceList" class="appliance-list">
              <div class="empty-state">No appliances added yet.</div>
            </div>
          </div>
        </div>
      </div>
      <div class="col-lg-7">
        <div class="card-panel" id="applianceResults" style="display:none;">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-table me-2"></i>Consumption Breakdown</h5>
          </div>
          <div class="p-3">
            <div class="row g-3 mb-4" id="applianceSummaryRow"></div>
            <div class="table-responsive mb-4">
              <table class="table table-sm table-hover" id="applianceTable">
                <thead>
                  <tr>
                    <th>Appliance</th><th>Watts</th><th>Qty</th><th>Hrs/Day</th>
                    <th>kWh/Day</th><th>kWh/Mo</th><th>Cost/Mo (₹)</th>
                  </tr>
                </thead>
                <tbody id="applianceTableBody"></tbody>
              </table>
            </div>
            <div class="chart-container-sm"><canvas id="applianceBarChart"></canvas></div>
          </div>
        </div>
      </div>
    </div>
  </section>
  <section id="carbon" class="content-section">
    <div class="section-header mb-4">
      <h2><i class="bi bi-tree me-2"></i>Carbon Footprint Monitor</h2>
      <p class="text-muted">Understand your electricity's environmental impact and how to offset it</p>
    </div>
    <div class="row g-4">
      <div class="col-lg-5">
        <div class="card-panel">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-input-cursor me-2"></i>Monthly Usage</h5>
          </div>
          <div class="p-3">
            <div class="mb-3">
              <label class="form-label fw-500">Monthly Consumption (kWh)</label>
              <input type="number" class="form-control" id="carbonKwh" placeholder="e.g. 300" min="0" />
              <div class="form-text">India grid emission factor: 0.82 kg CO₂/kWh (CEA 2023)</div>
            </div>
            <button class="btn btn-primary w-100 btn-animate" onclick="calculateCarbon()">
              <i class="bi bi-calculator me-2"></i>Calculate Footprint
            </button>
          </div>
        </div>
      </div>
      <div class="col-lg-7">
        <div class="card-panel" id="carbonResults" style="display:none;">
          <div class="card-panel-header">
            <h5 class="mb-0"><i class="bi bi-cloud-haze2 me-2"></i>Your Carbon Footprint</h5>
          </div>
          <div class="p-3">
            <div class="row g-3 mb-4" id="carbonSummaryRow"></div>
            <div class="row g-3 mb-3">
              <div class="col-md-6">
                <div class="equivalence-card">
                  <div class="eq-icon">🌳</div>
                  <div class="eq-value" id="eqTrees">—</div>
                  <div class="eq-label">Trees needed to offset annual CO₂</div>
                </div>
              </div>
              <div class="col-md-6">
                <div class="equivalence-card">
                  <div class="eq-icon">🚗</div>
                  <div class="eq-value" id="eqCar">—</div>
                  <div class="eq-label">Km driven by an average car</div>
                </div>
              </div>
            </div>
            <div class="chart-container-sm"><canvas id="carbonGauge"></canvas></div>
          </div>
        </div>
      </div>
    </div>
  </section>
</main>
<div class="loading-overlay" id="loadingOverlay">
  <div class="loading-spinner">
    <div class="spinner-ring"></div>
    <div class="loading-text" id="loadingText">Analysing…</div>
  </div>
</div>
<footer class="app-footer">
  <div class="container text-center">
    <p class="mb-1">⚡ Smart Home Energy Advisor · Powered by <strong>IBM Watsonx.ai</strong> &amp; <strong>IBM Granite</strong></p>
    <p class="text-muted small">Built for Indian households · Sydney Region (au-syd) · © 2025</p>
  </div>
</footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="/static/js/app.js"></script>
</body>
</html>"""

@app.route("/")
def index():
    """Serve the main dashboard page."""
    if "session_id" not in session:
        session["session_id"] = os.urandom(16).hex()
    return render_template_string(_INDEX_HTML, agent_name=AGENT_NAME)


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
