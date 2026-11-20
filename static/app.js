const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" });

async function api(path, options) {
  const res = await fetch(path, options);
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : res.statusText);
  return body;
}

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

async function loadHealth() {
  try {
    const h = await api("/api/health");
    $("health").textContent = `Connected: ${h.stations} stations in the database.`;
    $("health").className = "ok";
  } catch (e) {
    $("health").textContent = `Database error: ${e.message}`;
    $("health").className = "warn";
  }
}

let lowDocks = 3;
async function loadModelInfo() {
  try {
    const m = await api("/api/model");
    lowDocks = m.low_docks;
    const t = m.trained_on;
    $("model-info").textContent = `Model: linear regression, ${m.minutes_ahead} minutes ahead, trained on ` +
      `${t.rows.toLocaleString()} rows from ${t.stations.toLocaleString()} stations (${t.first_day} to ${t.last_day}, weekdays 4-7 PM).`;
  } catch (e) {
    $("model-info").textContent = `Model info unavailable: ${e.message}`;
  }
}

async function loadTimes() {
  const times = await api("/api/times");
  $("time").innerHTML = times.map((t) => `<option value="${t}">${fmtTime(t)}</option>`).join("");
  $("time").value = times[times.length - 1];
}

async function loadStations() {
  const at = $("time").value;
  const rows = await api(`/api/stations?at=${encodeURIComponent(at)}`);
  rows.sort((a, b) => a.name.localeCompare(b.name));

  const dest = $("destination");
  const selected = dest.value;
  dest.innerHTML = rows.map((r) => `<option value="${r.station_id}">${esc(r.name)}</option>`).join("");
  if (selected) dest.value = selected;

  $("stations").innerHTML = rows
    .map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${r.bikes_available}</td>
      <td class="num">${r.docks_available}</td>
      <td class="num ${r.predicted_docks < lowDocks ? "warn" : ""}">${r.predicted_docks}</td><td class="num">${r.capacity}</td></tr>`)
    .join("");
  return rows;
}

let chart;
async function loadChart(stations) {
  const series = await Promise.all(stations.map((s) => api(`/api/stations/${s.station_id}/status`)));
  const labels = series[0].map((p) => fmtTime(p.fetched_at));
  const datasets = stations.map((s, i) => ({
    label: s.name,
    data: series[i].map((p) => p.bikes_available),
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.2,
  }));
  chart?.destroy();
  chart = new Chart($("chart"), {
    type: "line",
    data: { labels, datasets },
    options: { interaction: { mode: "index", intersect: false }, scales: { y: { beginAtZero: true } } },
  });
}

async function loadTrips() {
  const trips = await api("/api/trips");
  $("trips").innerHTML = trips.length
    ? trips.map((t) => `<li>#${t.id} · ${esc(t.rider)} · ${t.started_at ? fmtTime(t.started_at) : ""} →
        ${t.suggested.length ? "suggested " + t.suggested.map(esc).join(", ") : "docked at destination"}</li>`).join("")
    : "<li>No trips yet. Submit the form above.</li>";
}

$("trip-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  data.min_docks = Number(data.min_docks);
  const box = $("result");
  box.hidden = false;
  try {
    const r = await api("/api/trips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    box.className = "result" + (r.reroute ? " reroute" : "");
    box.innerHTML = `<strong>Trip #${r.trip_id} saved.</strong> ${esc(r.reason)}` +
      (r.reroute
        ? r.suggestions.length
          ? "<br>Try instead: " + r.suggestions.map((s) => `${esc(s.name)} (${s.predicted_docks} docks predicted, ${s.docks_available} now, ~${s.distance_m} m)`).join("; ")
          : "<br>No nearby station is predicted to have enough open docks."
        : " Dock there.");
    loadTrips();
  } catch (err) {
    box.className = "result reroute";
    box.textContent = `Error: ${err.message}`;
  }
});

$("time").addEventListener("change", loadStations);

(async () => {
  await Promise.all([loadHealth(), loadModelInfo()]);
  await loadTimes();
  const stations = await loadStations();
  await Promise.all([loadChart(stations), loadTrips()]);
})();
