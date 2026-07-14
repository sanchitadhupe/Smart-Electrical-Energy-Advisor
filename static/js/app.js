/* ══════════════════════════════════════════════════════════════════════════════
   Smart Home Energy Advisor — Main JavaScript
   Features: Chat UI · Dashboard Charts · Bill Analyzer · Appliance Tracker
             Carbon Footprint · Dark Mode · Responsive
══════════════════════════════════════════════════════════════════════════════ */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  activeSection: "dashboard",
  darkMode: true,           // defaults to dark
  applianceList: [],        // [{id, label, quantity, hours, watts}]
  charts: {},               // Chart.js instances
  tariffRates: {},
  applianceCatalog: {},
};

// ── Chart colour palette ──────────────────────────────────────────────────────
const PALETTE = {
  blue:   "#4f8ef7",
  purple: "#7c4dff",
  green:  "#00e676",
  orange: "#ff9800",
  cyan:   "#00bcd4",
  red:    "#f44336",
  yellow: "#ffeb3b",
  pink:   "#e91e63",
  teal:   "#009688",
  lime:   "#cddc39",
};

const CHART_COLORS = Object.values(PALETTE);

// ══════════════════════════════════════════════════════════════════════════════
//  INITIALISATION
// ══════════════════════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  checkHealth();
  loadTariffs();
  loadApplianceCatalog();
  initDashboardCharts();
  showSection("dashboard");
  addWelcomeMessage();
  updateKPIs(287, 2583, 235, 412);   // demo KPI values on load
});

// ── Theme init ────────────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("energyTheme") || "dark";
  applyTheme(saved);
}

function applyTheme(theme) {
  state.darkMode = theme === "dark";
  document.documentElement.setAttribute("data-theme", theme);
  const icon = document.getElementById("themeIcon");
  if (icon) icon.className = state.darkMode ? "bi bi-sun-fill" : "bi bi-moon-stars-fill";
  localStorage.setItem("energyTheme", theme);
  // Re-render charts with new theme colours
  Object.values(state.charts).forEach(c => { if (c) c.update(); });
}

document.getElementById("themeToggle")?.addEventListener("click", () => {
  applyTheme(state.darkMode ? "light" : "dark");
});

// ── Health check ──────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const res  = await fetch("/api/health");
    const data = await res.json();
    const dot  = document.querySelector(".status-dot");
    const txt  = document.querySelector(".status-text");
    if (data.status === "healthy" && data.watsonx_connected) {
      dot.classList.add("online");
      if (txt) txt.textContent = "AI Online";
    } else {
      dot.classList.add("offline");
      if (txt) txt.textContent = "AI Offline";
    }
  } catch {
    const dot = document.querySelector(".status-dot");
    dot?.classList.add("offline");
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  SECTION NAVIGATION
// ══════════════════════════════════════════════════════════════════════════════

function showSection(name) {
  document.querySelectorAll(".content-section").forEach(s => {
    s.classList.remove("active");
  });
  const target = document.getElementById(name);
  if (target) {
    target.classList.add("active");
    state.activeSection = name;
  }
  // Highlight active nav link
  document.querySelectorAll(".nav-link").forEach(a => {
    a.classList.toggle("active", a.getAttribute("onclick")?.includes(name));
  });
  // Hide hero on non-dashboard
  const hero = document.getElementById("heroBanner");
  if (hero) hero.style.display = name === "dashboard" ? "" : "none";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ══════════════════════════════════════════════════════════════════════════════
//  KPI STRIP
// ══════════════════════════════════════════════════════════════════════════════

function updateKPIs(units, bill, carbon, savings) {
  animateCount("kpiUnits",   units,   1, " kWh");
  animateCount("kpiBill",    bill,    0, "",    "₹");
  animateCount("kpiCarbon",  carbon,  1, " kg");
  animateCount("kpiSavings", savings, 0, "",    "₹");
}

function animateCount(id, target, decimals, suffix = "", prefix = "") {
  const el = document.getElementById(id);
  if (!el) return;
  const start    = 0;
  const duration = 1200;
  const step     = (timestamp) => {
    if (!start_ts) start_ts = timestamp;
    const progress = Math.min((timestamp - start_ts) / duration, 1);
    const eased    = 1 - Math.pow(1 - progress, 3);
    const current  = start + (target - start) * eased;
    el.textContent = prefix + current.toFixed(decimals) + suffix;
    if (progress < 1) requestAnimationFrame(step);
  };
  let start_ts = null;
  requestAnimationFrame(step);
}

// ══════════════════════════════════════════════════════════════════════════════
//  DASHBOARD CHARTS
// ══════════════════════════════════════════════════════════════════════════════

function getChartDefaults() {
  const isDark = state.darkMode;
  return {
    gridColor:  isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
    textColor:  isDark ? "rgba(255,255,255,0.5)"  : "rgba(0,0,0,0.5)",
    bgCard:     isDark ? "#16213e" : "#ffffff",
  };
}

function destroyChart(key) {
  if (state.charts[key]) {
    state.charts[key].destroy();
    state.charts[key] = null;
  }
}

function initDashboardCharts() {
  buildMonthlyChart();
  buildApplianceDonut();
  buildDailyPattern();
  buildBillTrend();
}

function updateDashboardCharts() { initDashboardCharts(); }

// Monthly bar chart
function buildMonthlyChart() {
  destroyChart("monthly");
  const ctx = document.getElementById("monthlyChart");
  if (!ctx) return;
  const { gridColor, textColor } = getChartDefaults();
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const data2025 = [210, 195, 220, 260, 310, 380, 370, 360, 290, 245, 230, 287];
  const data2024 = [190, 180, 205, 240, 295, 360, 345, 340, 270, 225, 215, 265];
  const year = document.getElementById("dashboardYear")?.value || "2025";
  const values = year === "2025" ? data2025 : data2024;

  state.charts.monthly = new Chart(ctx, {
    type: "bar",
    data: {
      labels: months,
      datasets: [{
        label: `Monthly Consumption ${year} (kWh)`,
        data: values,
        backgroundColor: values.map((v, i) =>
          i === values.length - 1 ? PALETTE.orange : PALETTE.blue + "cc"
        ),
        borderColor: values.map((v, i) =>
          i === values.length - 1 ? PALETTE.orange : PALETTE.blue
        ),
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: chartOptions(gridColor, textColor, "kWh"),
  });
}

// Appliance donut
function buildApplianceDonut() {
  destroyChart("donut");
  const ctx = document.getElementById("applianceDonut");
  if (!ctx) return;
  state.charts.donut = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["AC", "Refrigerator", "Geyser", "Lighting", "TV", "Others"],
      datasets: [{
        data: [40, 18, 12, 10, 8, 12],
        backgroundColor: [PALETTE.blue, PALETTE.green, PALETTE.orange, PALETTE.yellow, PALETTE.cyan, PALETTE.purple],
        borderWidth: 2,
        borderColor: state.darkMode ? "#16213e" : "#ffffff",
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: {
          position: "right",
          labels: { color: getChartDefaults().textColor, font: { size: 11 }, boxWidth: 12, padding: 10 },
        },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.raw}%`,
          },
        },
      },
    },
  });
}

// Daily pattern line chart
function buildDailyPattern() {
  destroyChart("daily");
  const ctx = document.getElementById("dailyPattern");
  if (!ctx) return;
  const { gridColor, textColor } = getChartDefaults();
  const hours = ["00","02","04","06","08","10","12","14","16","18","20","22"];
  state.charts.daily = new Chart(ctx, {
    type: "line",
    data: {
      labels: hours.map(h => `${h}:00`),
      datasets: [{
        label: "Power Demand (W)",
        data: [180, 120, 100, 300, 850, 600, 550, 600, 700, 1200, 1400, 950],
        borderColor: PALETTE.green,
        backgroundColor: PALETTE.green + "22",
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: PALETTE.green,
      }],
    },
    options: chartOptions(gridColor, textColor, "W"),
  });
}

// Bill trend
function buildBillTrend() {
  destroyChart("billTrend");
  const ctx = document.getElementById("billTrend");
  if (!ctx) return;
  const { gridColor, textColor } = getChartDefaults();
  state.charts.billTrend = new Chart(ctx, {
    type: "line",
    data: {
      labels: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
      datasets: [{
        label: "Monthly Bill (₹)",
        data: [1890, 1755, 1980, 2340, 2790, 3420, 3330, 3240, 2610, 2205, 2070, 2583],
        borderColor: PALETTE.orange,
        backgroundColor: PALETTE.orange + "22",
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointBackgroundColor: PALETTE.orange,
      }],
    },
    options: chartOptions(gridColor, textColor, "₹"),
  });
}

function chartOptions(gridColor, textColor, unit = "") {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: textColor, font: { size: 11 } } },
      tooltip: {
        callbacks: {
          label: ctx => ` ${ctx.dataset.label}: ${unit}${ctx.raw}`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: gridColor },
        ticks: { color: textColor, font: { size: 11 } },
      },
      y: {
        grid: { color: gridColor },
        ticks: { color: textColor, font: { size: 11 } },
      },
    },
  };
}

// ══════════════════════════════════════════════════════════════════════════════
//  CHAT
// ══════════════════════════════════════════════════════════════════════════════

function addWelcomeMessage() {
  const welcome = `👋 Hello! I'm **Vidyut**, your AI-powered Smart Home Energy Advisor.

I can help you with:
• 💡 Reducing your electricity bill
• 🔌 Analysing appliance consumption
• ☀️ Solar panel recommendations
• 📊 Electricity bill breakdowns
• 🌱 Carbon footprint estimation
• ⭐ BEE star rating guidance

**Ask me anything about electricity & energy savings!**`;
  appendMessage("bot", welcome);
}

function appendMessage(role, text, time = null) {
  const container = document.getElementById("chatMessages");
  if (!container) return;

  const now = time || new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const avatarIcon = role === "bot" ? "bi-lightning-charge-fill" : "bi-person-fill";
  const formatted  = formatMessageText(text);

  div.innerHTML = `
    <div class="message-avatar"><i class="bi ${avatarIcon}"></i></div>
    <div class="message-content">
      <div class="message-bubble">${formatted}</div>
      <div class="message-time">${now}</div>
    </div>`;

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function formatMessageText(text) {
  // Convert markdown-like syntax to HTML
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^#{1,3}\s+(.+)$/gm, "<strong>$1</strong>")
    .replace(/^•\s+(.+)$/gm, "• $1")
    .replace(/\n/g, "<br>");
}

function showTyping() {
  const container = document.getElementById("chatMessages");
  if (!container) return;
  const div = document.createElement("div");
  div.className = "message bot typing-indicator";
  div.id = "typingIndicator";
  div.innerHTML = `
    <div class="message-avatar"><i class="bi bi-lightning-charge-fill"></i></div>
    <div class="message-content">
      <div class="message-bubble">
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
      </div>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function hideTyping() {
  document.getElementById("typingIndicator")?.remove();
}

async function sendMessage() {
  const input = document.getElementById("chatInput");
  const btn   = document.getElementById("sendBtn");
  const text  = input?.value.trim();
  if (!text) return;

  input.value = "";
  autoResize(input);
  btn.disabled = true;

  // Hide quick prompts after first message
  document.getElementById("quickPrompts").style.display = "none";

  appendMessage("user", text);
  showTyping();

  try {
    const res  = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    hideTyping();
    if (data.error) {
      appendMessage("bot", `⚠️ Error: ${data.error}`);
    } else {
      appendMessage("bot", data.response, data.timestamp);
    }
  } catch (err) {
    hideTyping();
    appendMessage("bot", "⚠️ Network error. Please check your connection and try again.");
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

function sendQuickPrompt(text) {
  const input = document.getElementById("chatInput");
  if (input) input.value = text;
  sendMessage();
}

function handleChatKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

async function clearChat() {
  document.getElementById("chatMessages").innerHTML = "";
  document.getElementById("quickPrompts").style.display = "";
  try { await fetch("/api/clear-history", { method: "POST" }); } catch {}
  addWelcomeMessage();
}

// ══════════════════════════════════════════════════════════════════════════════
//  BILL ANALYZER
// ══════════════════════════════════════════════════════════════════════════════

async function loadTariffs() {
  try {
    const res  = await fetch("/api/tariffs");
    state.tariffRates = await res.json();
    populateStateDropdowns();
  } catch (e) {
    console.warn("Could not load tariffs", e);
  }
}

function populateStateDropdowns() {
  const states = Object.keys(state.tariffRates).sort();
  const dropdowns = ["billState", "applianceState"];
  dropdowns.forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    states.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = `${s} (₹${state.tariffRates[s]}/kWh)`;
      sel.appendChild(opt);
    });
    // Default to Maharashtra
    sel.value = "Maharashtra";
  });
}

async function analyzeBill() {
  const units     = parseFloat(document.getElementById("billUnits")?.value) || 0;
  const prevUnits = parseFloat(document.getElementById("billPrevUnits")?.value) || 0;
  const state_    = document.getElementById("billState")?.value || "Maharashtra";
  const month     = document.getElementById("billMonth")?.value || "December";

  if (!units) { alert("Please enter units consumed."); return; }

  showLoading("Analysing your electricity bill…");

  try {
    const res  = await fetch("/api/analyze-bill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ units, prev_units: prevUnits, state: state_, month }),
    });
    const data = await res.json();
    hideLoading();

    if (data.error) { alert("Error: " + data.error); return; }

    renderBillResults(data);
    // Update KPIs
    updateKPIs(units, data.bill_amount, data.carbon_kg, Math.round(data.bill_amount * 0.2));
  } catch (e) {
    hideLoading();
    alert("Network error. Please try again.");
  }
}

function renderBillResults(data) {
  const summaryRow = document.getElementById("billSummaryRow");
  summaryRow.innerHTML = `
    ${kpiCard("₹" + data.bill_amount.toLocaleString("en-IN"), "Total Bill")}
    ${kpiCard(data.units + " kWh", "Units Consumed")}
    ${kpiCard("₹" + data.tariff + "/kWh", "Tariff Rate")}
    ${kpiCard(data.carbon_kg + " kg", "CO₂ Emitted")}`;

  // Slab table
  const tbody = document.getElementById("slabTableBody");
  tbody.innerHTML = "";
  data.slab_breakdown.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.slab}</td><td>${row.units}</td><td>₹${row.rate}</td><td><strong>₹${row.cost}</strong></td>`;
    tbody.appendChild(tr);
  });

  // Slab chart
  destroyChart("billSlab");
  const ctx = document.getElementById("billSlabChart");
  if (ctx && data.slab_breakdown.length) {
    const { gridColor, textColor } = getChartDefaults();
    state.charts.billSlab = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.slab_breakdown.map(r => r.slab),
        datasets: [{
          label: "Cost (₹)",
          data: data.slab_breakdown.map(r => r.cost),
          backgroundColor: [PALETTE.blue + "cc", PALETTE.green + "cc", PALETTE.orange + "cc", PALETTE.red + "cc"],
          borderRadius: 6,
        }],
      },
      options: chartOptions(gridColor, textColor, "₹"),
    });
  }

  document.getElementById("billResults").style.display = "";
  document.getElementById("billAiPanel").style.display  = "";
  const aiBox = document.getElementById("billAiText");
  aiBox.textContent = "⏳ Generating AI analysis…";

  if (data.ai_analysis) {
    aiBox.innerHTML = formatMessageText(data.ai_analysis);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  APPLIANCE TRACKER
// ══════════════════════════════════════════════════════════════════════════════

async function loadApplianceCatalog() {
  try {
    const res = await fetch("/api/appliances");
    state.applianceCatalog = await res.json();
    populateApplianceDropdown();
  } catch (e) {
    console.warn("Could not load appliances", e);
  }
}

function populateApplianceDropdown() {
  const sel = document.getElementById("applianceSelect");
  if (!sel) return;
  Object.entries(state.applianceCatalog).forEach(([id, info]) => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = `${info.label} (${info.watts}W)`;
    sel.appendChild(opt);
  });
}

function addAppliance() {
  const id    = document.getElementById("applianceSelect")?.value;
  const qty   = parseFloat(document.getElementById("applianceQty")?.value) || 1;
  const hours = parseFloat(document.getElementById("applianceHours")?.value) || 0;

  if (!id) { alert("Please select an appliance."); return; }
  if (!hours || hours <= 0) { alert("Please enter hours per day (e.g. 5)."); return; }

  const info  = state.applianceCatalog[id];
  if (!info) return;

  // Prevent exact duplicates
  const exists = state.applianceList.find(a => a.id === id && a.hours === hours && a.quantity === qty);
  if (exists) { alert(`${info.label} with same settings is already in the list.`); return; }

  state.applianceList.push({ id, label: info.label, watts: info.watts, quantity: qty, hours });
  renderApplianceList();

  // Visual feedback — flash the list panel
  const listEl = document.getElementById("applianceList");
  if (listEl) { listEl.style.outline = "2px solid #4f8ef7"; setTimeout(() => listEl.style.outline = "", 800); }
}

function renderApplianceList() {
  const container = document.getElementById("applianceList");
  if (!container) return;

  if (!state.applianceList.length) {
    container.innerHTML = '<div class="empty-state">No appliances added yet.</div>';
    return;
  }

  container.innerHTML = state.applianceList.map((item, idx) => `
    <div class="appliance-item">
      <div>
        <div class="ai-name">⚡ ${item.label}</div>
        <div class="ai-meta">${item.quantity} × ${item.watts}W · ${item.hours} hrs/day</div>
      </div>
      <button class="btn-remove-item" onclick="removeAppliance(${idx})">
        <i class="bi bi-x"></i> Remove
      </button>
    </div>`).join("");
}

function removeAppliance(idx) {
  state.applianceList.splice(idx, 1);
  renderApplianceList();
}

function clearAppliances() {
  state.applianceList = [];
  renderApplianceList();
  document.getElementById("applianceResults").style.display = "none";
}

async function calculateAppliances() {
  // Auto-add the currently filled form item if fields are complete and list is empty
  const currentId    = document.getElementById("applianceSelect")?.value;
  const currentHours = parseFloat(document.getElementById("applianceHours")?.value) || 0;
  if (currentId && currentHours > 0) {
    const info = state.applianceCatalog[currentId];
    if (info) {
      const qty = parseFloat(document.getElementById("applianceQty")?.value) || 1;
      const already = state.applianceList.find(a => a.id === currentId && a.hours === currentHours && a.quantity === qty);
      if (!already) {
        state.applianceList.push({ id: currentId, label: info.label, watts: info.watts, quantity: qty, hours: currentHours });
        renderApplianceList();
      }
    }
  }

  if (!state.applianceList.length) { alert("Please select an appliance and enter hours per day first."); return; }

  const stateName = document.getElementById("applianceState")?.value || "Maharashtra";

  showLoading("Calculating appliance consumption…");

  try {
    const payload = {
      appliances: state.applianceList.map(a => ({
        id: a.id, quantity: a.quantity, hours: a.hours,
      })),
      state: stateName,
    };

    const res  = await fetch("/api/calculate-appliance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    hideLoading();

    if (data.error) { alert("Error: " + data.error); return; }
    renderApplianceResults(data);
  } catch {
    hideLoading();
    alert("Network error. Please try again.");
  }
}

function renderApplianceResults(data) {
  const summaryRow = document.getElementById("applianceSummaryRow");
  summaryRow.innerHTML = `
    ${kpiCard(data.total_daily_kwh + " kWh", "Daily Usage")}
    ${kpiCard(data.total_monthly_kwh + " kWh", "Monthly Usage")}
    ${kpiCard("₹" + data.total_monthly_cost.toLocaleString("en-IN"), "Monthly Cost")}
    ${kpiCard(data.total_carbon_monthly + " kg", "CO₂/Month")}`;

  // Table
  const tbody = document.getElementById("applianceTableBody");
  tbody.innerHTML = "";
  data.appliances.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.label}</td>
      <td>${row.watts}W</td>
      <td>${row.quantity}</td>
      <td>${row.hours}h</td>
      <td>${row.daily_kwh}</td>
      <td>${row.monthly_kwh}</td>
      <td><strong>₹${row.monthly_cost}</strong></td>`;
    tbody.appendChild(tr);
  });

  // Bar chart
  destroyChart("applianceBar");
  const ctx = document.getElementById("applianceBarChart");
  if (ctx) {
    const { gridColor, textColor } = getChartDefaults();
    state.charts.applianceBar = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.appliances.map(a => a.label),
        datasets: [{
          label: "Monthly Cost (₹)",
          data: data.appliances.map(a => a.monthly_cost),
          backgroundColor: CHART_COLORS.map(c => c + "cc"),
          borderColor: CHART_COLORS,
          borderWidth: 1.5,
          borderRadius: 6,
        }],
      },
      options: {
        ...chartOptions(gridColor, textColor, "₹"),
        indexAxis: "y",
      },
    });
  }

  document.getElementById("applianceResults").style.display = "";
}

// ══════════════════════════════════════════════════════════════════════════════
//  CARBON FOOTPRINT
// ══════════════════════════════════════════════════════════════════════════════

async function calculateCarbon() {
  const kwh = parseFloat(document.getElementById("carbonKwh")?.value) || 0;
  if (!kwh) { alert("Please enter monthly kWh consumption."); return; }

  showLoading("Calculating carbon footprint…");

  try {
    const res  = await fetch("/api/carbon-footprint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthly_kwh: kwh }),
    });
    const data = await res.json();
    hideLoading();

    if (data.error) { alert("Error: " + data.error); return; }
    renderCarbonResults(data);
  } catch {
    hideLoading();
    alert("Network error.");
  }
}

function renderCarbonResults(data) {
  const summaryRow = document.getElementById("carbonSummaryRow");
  summaryRow.innerHTML = `
    ${kpiCard(data.monthly_co2 + " kg", "Monthly CO₂")}
    ${kpiCard(data.annual_co2 + " kg", "Annual CO₂")}
    ${kpiCard(data.monthly_kwh + " kWh", "Monthly Usage")}
    ${kpiCard(data.annual_kwh + " kWh", "Annual Usage")}`;

  document.getElementById("eqTrees").textContent = data.trees_to_offset;
  document.getElementById("eqCar").textContent   = data.equivalent_car_km.toLocaleString("en-IN") + " km";

  // Gauge using doughnut
  destroyChart("carbonGauge");
  const ctx = document.getElementById("carbonGauge");
  if (ctx) {
    const maxCo2  = 600;   // kg/month reference maximum
    const pct     = Math.min((data.monthly_co2 / maxCo2) * 100, 100);
    const remaining = 100 - pct;
    const gaugeColor =
      pct < 30 ? PALETTE.green :
      pct < 60 ? PALETTE.orange : PALETTE.red;

    state.charts.carbonGauge = new Chart(ctx, {
      type: "doughnut",
      data: {
        datasets: [{
          data: [pct, remaining],
          backgroundColor: [gaugeColor, state.darkMode ? "#2a3a5c" : "#e5e7eb"],
          borderWidth: 0,
          circumference: 180,
          rotation: 270,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: "70%",
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
        },
      },
      plugins: [{
        id: "centerText",
        beforeDraw(chart) {
          const { ctx: c, chartArea: { top, width, height } } = chart;
          c.save();
          c.textAlign = "center";
          c.fillStyle = state.darkMode ? "#e8eaf6" : "#1a202c";
          c.font = "bold 22px Inter, sans-serif";
          c.fillText(data.monthly_co2 + " kg", width / 2, top + height * 0.7);
          c.font = "12px Inter, sans-serif";
          c.fillStyle = state.darkMode ? "#9aa3c2" : "#718096";
          c.fillText("CO₂ / month", width / 2, top + height * 0.85);
          c.restore();
        },
      }],
    });
  }

  document.getElementById("carbonResults").style.display = "";
}

// ══════════════════════════════════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════════════════════════════════

function kpiCard(value, label) {
  return `
    <div class="col-6 col-md-3">
      <div class="result-kpi">
        <div class="rk-value">${value}</div>
        <div class="rk-label">${label}</div>
      </div>
    </div>`;
}

function showLoading(text = "Processing…") {
  const overlay = document.getElementById("loadingOverlay");
  const msg     = document.getElementById("loadingText");
  if (overlay) overlay.classList.add("visible");
  if (msg) msg.textContent = text;
}

function hideLoading() {
  document.getElementById("loadingOverlay")?.classList.remove("visible");
}
