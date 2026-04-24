const apiStatus = document.querySelector("#api-status");
const airportCount = document.querySelector("#airport-count");
const lastUpdate = document.querySelector("#last-update");
const form = document.querySelector("#search-form");
const input = document.querySelector("#airport-input");
const suggestions = document.querySelector("#suggestions");
const message = document.querySelector("#message");
const results = document.querySelector("#results");
const refreshButton = document.querySelector("#refresh-button");

let airports = [];
let selectedAirport = null;
let searchTimer = null;

const api = async (path) => {
  const response = await fetch(`/api${path}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
};

const setMessage = (text, isError = false) => {
  message.hidden = !text;
  message.textContent = text || "";
  message.style.color = isError ? "#a53b17" : "#334139";
};

const formatTime = (value) =>
  value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "-";

const number = (value, suffix = "") => (value === null || value === undefined ? "-" : `${Math.round(value)}${suffix}`);

const decimal = (value, digits = 4) =>
  value === null || value === undefined ? "-" : Number(value).toFixed(digits);

const esc = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const renderSuggestions = (items) => {
  suggestions.innerHTML = "";
  suggestions.hidden = items.length === 0;

  items.forEach((airport) => {
    const button = document.createElement("button");
    button.className = "suggestion";
    button.type = "button";
    button.innerHTML = `<strong>${esc(airport.icao)}</strong><span>${esc(airport.name)}, ${esc(airport.city || airport.country)}</span>`;
    button.addEventListener("click", () => {
      input.value = airport.icao;
      suggestions.hidden = true;
      loadRunwayStatus(airport.icao);
    });
    suggestions.appendChild(button);
  });
};

const runwayHeading = (runway) => {
  const values = Object.values(runway.headings || {});
  return values.length ? values[0] : 90;
};

const projectRunway = (runway, airport, bounds) => {
  const cosLat = Math.cos((airport.lat * Math.PI) / 180);
  const toPoint = (lat, lon) => ({
    x: (lon - airport.lon) * 111 * cosLat,
    y: (airport.lat - lat) * 111,
  });

  if (
    runway.le_lat !== null &&
    runway.le_lon !== null &&
    runway.he_lat !== null &&
    runway.he_lon !== null
  ) {
    return {
      start: toPoint(runway.le_lat, runway.le_lon),
      end: toPoint(runway.he_lat, runway.he_lon),
    };
  }

  const center = toPoint(runway.lat, runway.lon);
  const heading = runwayHeading(runway);
  const lengthKm = Math.max((runway.length_ft || 3500) * 0.0003048, 0.8);
  const radians = ((90 - heading) * Math.PI) / 180;
  const dx = Math.cos(radians) * lengthKm * 0.5;
  const dy = -Math.sin(radians) * lengthKm * 0.5;
  return {
    start: { x: center.x - dx, y: center.y - dy },
    end: { x: center.x + dx, y: center.y + dy },
  };
};

const renderRunwayLayout = (data) => {
  const container = document.querySelector("#runway-layout");
  const runways = data.all_runways || [];

  if (!runways.length) {
    container.innerHTML = `<div class="runway-card"><strong>No runway layout available</strong></div>`;
    return;
  }

  const projected = runways.map((runway) => ({ runway, ...projectRunway(runway, data.airport) }));
  const xs = projected.flatMap((item) => [item.start.x, item.end.x]);
  const ys = projected.flatMap((item) => [item.start.y, item.end.y]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = 900;
  const height = 420;
  const pad = 60;
  const scale = Math.min(
    (width - pad * 2) / Math.max(maxX - minX, 0.5),
    (height - pad * 2) / Math.max(maxY - minY, 0.5)
  );
  const mapPoint = (point) => ({
    x: width / 2 + (point.x - (minX + maxX) / 2) * scale,
    y: height / 2 + (point.y - (minY + maxY) / 2) * scale,
  });

  const activeDirections = new Set((data.active_runways || []).map((runway) => runway.direction));
  const runwaySvg = projected
    .map(({ runway, start, end }) => {
      const a = mapPoint(start);
      const b = mapPoint(end);
      const active = activeDirections.has(runway.le_ident) || activeDirections.has(runway.he_ident);
      const strokeWidth = Math.max(8, Math.min(22, (runway.width_ft || 150) / 9));
      const meta = [runway.length_ft ? `${runway.length_ft} ft` : null, runway.surface, runway.lighted ? "lighted" : null]
        .filter(Boolean)
        .join(" · ");
      const midX = (a.x + b.x) / 2;
      const midY = (a.y + b.y) / 2;

      return `
        <g>
          <line class="runway-line" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${active ? "#f05d23" : "#17211b"}" stroke-width="${strokeWidth}" />
          <circle class="runway-end" cx="${a.x}" cy="${a.y}" r="7" />
          <circle class="runway-end" cx="${b.x}" cy="${b.y}" r="7" />
          <text class="runway-label" x="${a.x}" y="${a.y - 14}" text-anchor="middle">${esc(runway.le_ident || "")}</text>
          <text class="runway-label" x="${b.x}" y="${b.y - 14}" text-anchor="middle">${esc(runway.he_ident || "")}</text>
          <text class="runway-meta" x="${midX}" y="${midY + 28}" text-anchor="middle">${esc(runway.name)}${meta ? ` · ${esc(meta)}` : ""}</text>
        </g>
      `;
    })
    .join("");

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Runway layout for ${esc(data.airport.icao)}">${runwaySvg}</svg>`;
};

const renderRunways = (data) => {
  const list = document.querySelector("#runway-list");
  list.innerHTML = "";

  if (!data.active_runways.length) {
    list.innerHTML = `<div class="runway-card"><strong>No active runway match</strong><span>Use METAR wind and nearby traffic for context.</span></div>`;
    return;
  }

  data.active_runways.forEach((runway) => {
    const card = document.createElement("div");
    card.className = "runway-card";
    card.innerHTML = `
      <strong>${runway.direction} on ${runway.runway_name}</strong>
      <span>${runway.aircraft_count} aircraft aligned, heading ${number(runway.heading, "°")}</span>
    `;
    list.appendChild(card);
  });
};

const renderWeather = (metar) => {
  const title = document.querySelector("#weather-title");
  const grid = document.querySelector("#weather-grid");
  const raw = document.querySelector("#raw-metar");
  grid.innerHTML = "";
  raw.textContent = "";

  if (!metar) {
    title.textContent = "METAR unavailable";
    return;
  }

  title.textContent = metar.expected_runway_from_wind
    ? `Wind favors ${metar.expected_runway_from_wind}`
    : "Weather received";

  const weatherItems = [
    ["Wind", `${number(metar.wind_direction, "°")} at ${number(metar.wind_speed, " kt")}`],
    ["Gust", number(metar.wind_gust, " kt")],
    ["Visibility", metar.visibility || "-"],
    ["Category", metar.flight_category || "-"],
    ["Temperature", number(metar.temperature, "°C")],
    ["Clouds", metar.clouds || "-"],
  ];

  weatherItems.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "weather-card";
    card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    grid.appendChild(card);
  });

  raw.textContent = metar.raw || "";
};

const renderAircraft = (data) => {
  const title = document.querySelector("#aircraft-title");
  const list = document.querySelector("#aircraft-list");
  title.textContent = `${data.total_landing_aircraft} likely landing, ${data.all_aircraft_nearby.length} nearby shown`;
  list.innerHTML = "";

  if (!data.all_aircraft_nearby.length) {
    list.innerHTML = `<div class="aircraft-card"><strong>No aircraft nearby</strong><span>OpenSky returned no traffic in the search radius.</span></div>`;
    return;
  }

  data.all_aircraft_nearby.slice(0, 12).forEach((aircraft) => {
    const card = document.createElement("div");
    card.className = "aircraft-card";
    const runwayMatch = aircraft.matched_direction
      ? ` · matched ${esc(aircraft.matched_direction)} (${decimal(aircraft.runway_lateral_distance_km, 2)} km lateral, ${decimal(aircraft.runway_threshold_distance_km, 1)} km threshold)`
      : "";
    card.innerHTML = `
      <strong>${aircraft.callsign || aircraft.icao24.toUpperCase()}</strong>
      <span>${number(aircraft.altitude_ft, " ft")} · ${number(aircraft.velocity_knots, " kt")} · heading ${number(aircraft.heading, "°")} · ${aircraft.distance_km ?? "-"} km from airport${runwayMatch}</span>
      <span>lat ${decimal(aircraft.latitude)}, lon ${decimal(aircraft.longitude)}</span>
    `;
    list.appendChild(card);
  });
};

const renderResults = (data) => {
  selectedAirport = data.airport.icao;
  results.hidden = false;
  document.querySelector("#airport-title").textContent = data.airport.name;
  document.querySelector("#airport-meta").textContent = `${data.airport.city}, ${data.airport.country} · elevation ${data.airport.elevation_ft} ft`;
  document.querySelector("#airport-code").textContent = data.airport.icao;
  document.querySelector("#runway-message").textContent = data.message;
  lastUpdate.textContent = formatTime(data.timestamp);

  renderRunwayLayout(data);
  renderRunways(data);
  renderWeather(data.metar);
  renderAircraft(data);
};

const loadRunwayStatus = async (icao) => {
  const code = icao.trim().toUpperCase();
  if (!code) {
    setMessage("Enter an ICAO code or choose an airport.", true);
    return;
  }

  setMessage(`Analyzing ${code}...`);
  refreshButton.disabled = true;

  try {
    const data = await api(`/runway-status/${encodeURIComponent(code)}`);
    renderResults(data);
    setMessage("");
  } catch (error) {
    setMessage(error.message, true);
  } finally {
    refreshButton.disabled = false;
  }
};

const boot = async () => {
  try {
    const status = await api("/");
    apiStatus.textContent = "Online";
    airportCount.textContent = String(status.airport_count || "-");
  } catch (error) {
    apiStatus.textContent = "Offline";
    setMessage(error.message, true);
  }
};

input.addEventListener("input", () => {
  const query = input.value.trim().toUpperCase();
  if (query.length < 2) {
    suggestions.hidden = true;
    return;
  }

  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(async () => {
    try {
      airports = await api(`/search-airports/${encodeURIComponent(query)}`);
      renderSuggestions(airports.slice(0, 6));
    } catch {
      suggestions.hidden = true;
    }
  }, 180);
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  suggestions.hidden = true;
  loadRunwayStatus(input.value);
});

refreshButton.addEventListener("click", () => {
  if (selectedAirport) {
    loadRunwayStatus(selectedAirport);
  }
});

boot();
