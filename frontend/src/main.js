import "./styles.css";
import {
  createIcons,
  Orbit,
  ArrowUpRight,
  RotateCcw,
  Play,
  Square,
  Focus,
  Link,
  Route,
  Download,
  Shuffle,
  Circle,
  CircleCheck,
} from "lucide";
import { createScene } from "./scene.js";

const icons = {
  Orbit,
  ArrowUpRight,
  RotateCcw,
  Play,
  Square,
  Focus,
  Link,
  Route,
  Download,
  Shuffle,
  Circle,
  CircleCheck,
};
const $ = (id) => document.getElementById(id);
const number = (id) => Number($(id).value);
const vector = (prefix) =>
  ["x", "y", "z"].map((axis) => number(`${prefix}-${axis}`));
const formatVector = (values, digits = 3) =>
  values
    .map((v, i) => `${["X", "Y", "Z"][i]} ${Number(v).toFixed(digits)}`)
    .join(" / ");
const norm = (values) => Math.hypot(...values);
let session = null;
let stream = null;
let running = false;
let decisionCount = 0;
let samples = [];
let latest = null;

function fields(prefix, label, primary) {
  const triple = (name, title, unit, values) =>
    `<div class="group-label">${title}<span>${unit}</span></div><div class="triplet">${["x", "y", "z"].map((axis, i) => `<label>${axis.toUpperCase()}<input id="${prefix}-${name}-${axis}" type="number" value="${values[i]}" step="0.01" required aria-label="${label} ${title} ${axis}"></label>`).join("")}</div>`;
  return `<details ${primary ? "" : "open"}><summary>${label}</summary><div class="satellite-name"><b class="${primary ? "primary" : "secondary"}-key"></b>${primary ? "Target docking port" : "Approaching docking port"}</div>
  ${triple("position", "Position", "m", primary ? [0, 0, 0] : [7.5, 0, 0])}
  ${!primary ? '<p class="field-help">Initial port separation must be 5–10 m. Docking proceeds within 1.25 m.</p>' : ""}
  ${!primary ? '<button id="randomize" class="random-button" type="button"><i data-lucide="shuffle"></i>Randomize secondary position</button>' : ""}
  ${triple("velocity", "Velocity", "m/s", [0, 0, 0])}
  ${triple("attitude", "Attitude · roll / pitch / yaw", "deg", [0, 0, 0])}
  ${triple("omega", "Rotation rate", "rad/s", [0, 0, 0])}
  <div class="pair"><label>Mass <span>kg</span><input id="${prefix}-mass" type="number" value="500" min="1" max="100000" step="1" required></label><label>Fuel <span>%</span><input id="${prefix}-fuel" type="number" value="100" min="0" max="100" step="0.1" required></label></div>
  <div class="pair"><label>Min. transit speed <span>m/s</span><input id="${prefix}-min" type="number" value="0" min="0" max="20" step="0.01" required></label><label>Max. speed <span>m/s</span><input id="${prefix}-max" type="number" value="2" min="0.01" max="20" step="0.01" required></label></div>
  <div class="pair"><label>Max. horizontal <span>m/s</span><input id="${prefix}-horizontal" type="number" value="2" min="0.01" max="20" step="0.01" required></label><label>Max. vertical <span>m/s</span><input id="${prefix}-vertical" type="number" value="1" min="0.01" max="20" step="0.01" required></label></div>
  <label>Port capture radius <span>m</span><input id="${prefix}-radius" type="number" value="1.25" min="0.01" max="1.25" step="0.01" required></label>
  ${primary ? '<label>Orbital semi-major axis <span>m</span><input id="orbit" type="number" value="6878000" min="6371000" step="1" required></label>' : ""}
  <p class="field-help">Zero speed is permitted during braking and capture.</p></details>`;
}
$("satellite-fields").innerHTML =
  fields("p", "Primary spacecraft", true) +
  fields("s", "Secondary spacecraft", false);
if (window.matchMedia("(max-width: 700px)").matches)
  document.querySelectorAll(".configuration details").forEach((item) => {
    item.open = false;
  });
createIcons({ icons });
const scene = createScene($("scene"));

function attitude(prefix) {
  const [roll, pitch, yaw] = vector(`${prefix}-attitude`).map(
    (v) => (v * Math.PI) / 360,
  );
  const [cx, cy, cz] = [roll, pitch, yaw].map(Math.cos);
  const [sx, sy, sz] = [roll, pitch, yaw].map(Math.sin);
  return [
    cx * cy * cz + sx * sy * sz,
    sx * cy * cz - cx * sy * sz,
    cx * sy * cz + sx * cy * sz,
    cx * cy * sz - sx * sy * cz,
  ];
}

function satellite(prefix, name) {
  return {
    name,
    position_m: vector(`${prefix}-position`),
    velocity_mps: vector(`${prefix}-velocity`),
    orientation_quat: attitude(prefix),
    angular_velocity_radps: vector(`${prefix}-omega`),
    mass_kg: number(`${prefix}-mass`),
    fuel_remaining_pct: number(`${prefix}-fuel`),
    capture_radius_m: number(`${prefix}-radius`),
    motion_limits: {
      min_speed_mps: number(`${prefix}-min`),
      max_speed_mps: number(`${prefix}-max`),
      max_horizontal_speed_mps: number(`${prefix}-horizontal`),
      max_vertical_speed_mps: number(`${prefix}-vertical`),
    },
  };
}

function payload() {
  const anomaly = $("anomaly").value;
  const fault =
    anomaly === "none"
      ? []
      : [
          {
            type: anomaly,
            step: 60,
            detail: "Dashboard fault experiment",
            ...(anomaly === "velocity_impulse"
              ? { impulse_mps: [0.15, -0.1, 0.05] }
              : {}),
            ...(anomaly === "sensor_dropout"
              ? { duration_steps: 20, corrupt: false }
              : {}),
            ...(anomaly === "priority_change"
              ? { priority_change: "abort" }
              : {}),
          },
        ];
  return {
    primary: {
      ...satellite("p", "Primary"),
      orbital_elements: { semi_major_axis_m: number("orbit") },
    },
    secondary: satellite("s", "Secondary"),
    config: {
      initial_separation_range_m: [5, 10],
      controller: $("controller").value,
      provider: $("provider").value,
      model: $("model").value.trim() || null,
      rl_advisor_enabled: $("rl-advisor").checked,
      dock_position_tol_m: number("capture-range"),
      dock_velocity_tol_mps: number("capture-speed"),
      dock_attitude_tol_deg: number("alignment"),
      seed: number("seed"),
      max_steps: number("steps"),
      step_interval_s: number("dt"),
      llm_cadence_steps: number("cadence"),
      stream_pacing_s: 0.025,
      auto_dock: $("auto-dock").checked,
      anomalies: fault,
    },
  };
}

function preview() {
  if (running) return;
  $("s-position-x").setCustomValidity("");
  if (!$("mission-form").checkValidity()) return;
  const data = payload();
  const relative = data.secondary.position_m.map(
    (v, i) => v - data.primary.position_m[i],
  );
  const velocity = data.secondary.velocity_mps.map(
    (v, i) => v - data.primary.velocity_mps[i],
  );
  scene.update(
    {
      position_m: relative,
      velocity_mps: velocity,
      orientation_quat: data.secondary.orientation_quat,
      primary: data.primary,
      primary_capture_radius_m: data.primary.capture_radius_m,
      secondary_capture_radius_m: data.secondary.capture_radius_m,
    },
    true,
  );
  $("range").innerHTML = `${norm(relative).toFixed(2)} <small>m</small>`;
  $("speed").innerHTML = `${norm(velocity).toFixed(3)} <small>m/s</small>`;
  $("fuel").innerHTML =
    `${data.secondary.fuel_remaining_pct.toFixed(1)} <small>%</small>`;
  $("primary-velocity").textContent = formatVector(data.primary.velocity_mps);
  $("secondary-velocity").textContent = formatVector(
    data.secondary.velocity_mps,
  );
  const separation = norm(relative);
  $("s-position-x").setCustomValidity(
    separation >= 5 && separation <= 10
      ? ""
      : `Initial port separation must be between 5 and 10 m (currently ${separation.toFixed(3)} m).`,
  );
}
// Reveal any invalid field before the browser tries to focus it.
$("mission-form").addEventListener(
  "invalid",
  (event) => {
    const section = event.target.closest("details");
    if (section) section.open = true;
  },
  true,
);

function captureView(capture = {}) {
  const labels = {
    range: "Shared port range",
    relative_speed: "Relative speed",
    alignment: "Port alignment",
    rotation_rate: "Rotation rate",
  };
  $("capture-checks").innerHTML = Object.entries(labels)
    .map(
      ([key, label]) =>
        `<div class="capture-check ${capture.checks?.[key] ? "passed" : ""}"><i data-lucide="${capture.checks?.[key] ? "circle-check" : "circle"}"></i>${label}</div>`,
    )
    .join("");
  $("capture-status").textContent = capture.eligible
    ? "Eligible for capture"
    : "Awaiting approach";
  $("dock").disabled = !running || !capture.eligible;
  createIcons({ icons });
}

function setRunning(value) {
  running = value;
  document.body.classList.toggle("session-running", value);
  if (value) {
    $("capture-announcement").hidden = true;
    $("scene-state").textContent = "Live telemetry";
    latest = null;
    $("dock").innerHTML = '<i data-lucide="link"></i>Engage docking capture';
    createIcons({ icons });
  }
  $("mission-fields").disabled = value;
  $("start").disabled = value;
  $("cancel").disabled = !value;
  $("reset").disabled = value;
  $("export").disabled = !session;
  if (!value) $("dock").disabled = true;
}

function showError(error) {
  $("error").textContent = error.message || String(error);
  $("error").hidden = false;
}

async function request(url, body) {
  const response = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
              .join("; ")
          : JSON.stringify(detail),
    );
  }
  return data;
}

function renderDecision(event) {
  if (!decisionCount) $("decisions").replaceChildren();
  decisionCount++;
  $("decision-count").textContent = `${decisionCount} decisions`;
  const article = document.createElement("article");
  article.className = "decision";
  article.innerHTML =
    '<div class="decision-top"><span class="decision-source"></span><span class="decision-time"></span></div><h3></h3><p></p><div class="decision-target"></div><details><summary>Tools & learned advice</summary><pre></pre></details><details><summary>Alternatives considered</summary><ul></ul></details>';
  article.querySelector(".decision-source").textContent =
    event.source.replaceAll("_", " ");
  article.querySelector(".decision-time").textContent =
    `${event.sim_time_s.toFixed(1)} s · step ${event.step}`;
  article.querySelector("h3").textContent = event.phase.replaceAll("_", " ");
  article.querySelector("p").textContent = event.subgoal.rationale;
  article.querySelector(".decision-target").textContent =
    `Target: ${formatVector(event.subgoal.target_position_m, 2)} m · ${event.subgoal.closing_speed_mps.toFixed(3)} m/s`;
  article.querySelector("pre").textContent = JSON.stringify(
    {
      tools: event.tool_results,
      learned_advice: event.rl_advisor || "No learned advice used",
    },
    null,
    2,
  );
  for (const alternative of event.subgoal.alternatives || []) {
    const item = document.createElement("li");
    item.textContent = alternative;
    article.querySelector("ul").appendChild(item);
  }
  for (const note of event.safety_notes || []) {
    const paragraph = document.createElement("p");
    paragraph.className = "safety-note";
    paragraph.textContent = note;
    article.appendChild(paragraph);
  }
  $("decisions").prepend(article);
  while ($("decisions").children.length > 60)
    $("decisions").lastElementChild.remove();
}

function chart() {
  $("chart-empty").hidden = samples.length >= 2;
  $("range-chart").toggleAttribute("hidden", samples.length < 2);
  if (samples.length < 2) return;
  const width = $("range-chart").clientWidth;
  const right = width - 12;
  const span = right - 24;
  $("range-chart").setAttribute("viewBox", `0 0 ${width} 150`);
  const maxTime = samples.at(-1)[0] || 1;
  const maxRange = Math.max(1.25, ...samples.map((s) => s[1]));
  const points = samples
    .map(
      ([time, range]) =>
        `${24 + (time / maxTime) * span},${120 - (range / maxRange) * 95}`,
    )
    .join(" ");
  const gateY = 120 - (1.25 / maxRange) * 95;
  $("range-chart").innerHTML =
    `<path d="M24 20V120H${right}" fill="none" stroke="#40545f"/><line x1="24" x2="${right}" y1="${gateY}" y2="${gateY}" stroke="#779bd0" stroke-dasharray="4 4"/><polyline points="${points}" fill="none" stroke="#8fd9c4" stroke-width="2"/><text x="24" y="143">0 s</text><text x="${right}" y="143" text-anchor="end">${maxTime.toFixed(1)} s</text><text x="24" y="13">${maxRange.toFixed(1)} m</text>`;
}
new ResizeObserver(chart).observe($("range-chart").parentElement);

function telemetry(event) {
  latest = event;
  scene.update({
    ...event,
    running,
    primary_capture_radius_m: number("p-radius"),
    secondary_capture_radius_m: number("s-radius"),
  });
  $("range").innerHTML = `${event.range_m.toFixed(2)} <small>m</small>`;
  $("speed").innerHTML =
    `${norm(event.velocity_mps).toFixed(3)} <small>m/s</small>`;
  $("fuel").innerHTML = `${event.fuel_pct.toFixed(1)} <small>%</small>`;
  $("time").innerHTML = `${event.sim_time_s.toFixed(1)} <small>s</small>`;
  $("phase").textContent = event.phase.replaceAll("_", " ");
  $("primary-velocity").textContent = formatVector(event.primary_velocity_mps);
  $("secondary-velocity").textContent = formatVector(
    event.secondary_velocity_mps,
  );
  $("thrust").textContent = formatVector(event.command_force_n || [0, 0, 0], 2);
  $("command-status").textContent = event.command_limited
    ? "Command adjusted to motion limits"
    : "Within configured actuator envelope";
  captureView(event.capture);
  samples.push([event.sim_time_s, event.range_m]);
  if (samples.length > 3000) samples = samples.filter((_, i) => i % 2 === 0);
  if (samples.length % 5 === 0) chart();
}

$("mission-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("error").hidden = true;
  const data = payload();
  preview();
  setRunning(true);
  $("phase").textContent = "Starting session";
  try {
    session = await request("/api/v1/docking/simulate", data);
    $("session-id").textContent = session.session_id.slice(0, 12);
    $("export").disabled = false;
    samples = [];
    chart();
    decisionCount = 0;
    $("decisions").replaceChildren();
    $("decision-count").textContent = "0 decisions";
    if (stream) stream.close();
    stream = new EventSource(session.stream_url);
    stream.addEventListener("telemetry", (e) => telemetry(JSON.parse(e.data)));
    stream.addEventListener("llm_decision", (e) =>
      renderDecision(JSON.parse(e.data)),
    );
    for (const type of ["docked", "failed"])
      stream.addEventListener(type, (e) => {
        const terminal = JSON.parse(e.data);
        stream.close();
        setRunning(false);
        if (latest)
          scene.update({
            ...latest,
            running: false,
            captured: type === "docked",
            primary_capture_radius_m: number("p-radius"),
            secondary_capture_radius_m: number("s-radius"),
          });
        $("scene-state").textContent =
          type === "docked" ? "Capture confirmed" : "Session ended";
        if (type === "docked") {
          $("capture-status").textContent = "Captured";
          $("dock").textContent = "Docking capture complete";
          $("capture-announcement").hidden = false;
          $("capture-result").textContent =
            `${latest.range_m.toFixed(3)} m port separation · ${norm(latest.velocity_mps).toFixed(3)} m/s relative speed`;
        }
        $("command-status").textContent =
          "Last applied command · session ended";
        $("phase").textContent =
          type === "docked"
            ? "Docking complete"
            : `Stopped · ${terminal.failure_reason.replaceAll("_", " ")}`;
        $("time").innerHTML =
          `${terminal.sim_time_s.toFixed(1)} <small>s</small>`;
        chart();
        if (terminal.error) showError(new Error(terminal.error));
      });
    stream.onerror = () => {
      $("connection").textContent = "Stream reconnecting…";
      $("connection-light").classList.remove("connected");
    };
    stream.onopen = () => {
      $("connection").textContent = "Backend connected";
      $("connection-light").classList.add("connected");
    };
  } catch (error) {
    setRunning(false);
    $("phase").textContent = "Session did not start";
    showError(error);
  }
});
$("cancel").onclick = async () => {
  try {
    await request(`${session.summary_url}/cancel`, {});
    $("cancel").disabled = true;
  } catch (error) {
    showError(error);
  }
};
$("dock").onclick = async () => {
  try {
    await request(`${session.summary_url}/dock`, {});
    $("dock").disabled = true;
  } catch (error) {
    showError(error);
  }
};
$("export").onclick = () => {
  window.location.href = `${session.summary_url}/export`;
};
$("reset").onclick = () => {
  $("mission-form").reset();
  $("capture-announcement").hidden = true;
  $("scene-state").textContent = "Mission preview";
  $("phase").textContent = "Ready to simulate";
  $("time").innerHTML = "0.0 <small>s</small>";
  captureView();
  preview();
};
$("camera-reset").onclick = scene.resetCamera;
document.querySelectorAll("[data-camera]").forEach((button) => {
  button.onclick = () => {
    document
      .querySelectorAll("[data-camera]")
      .forEach((item) =>
        item.setAttribute("aria-pressed", String(item === button)),
      );
    scene.setCamera(button.dataset.camera);
  };
});
for (const name of ["trail", "vectors", "envelope"])
  $(`show-${name}`).onchange = (event) =>
    scene.setOverlay(name, event.target.checked);
$("mission-fields").addEventListener("change", preview);
$("randomize").onclick = () => {
  let seed = number("seed") >>> 0;
  const random = () => {
    seed = (1664525 * seed + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
  // Avoid the endpoints so rounding coordinates cannot put a sample outside 5–10 m.
  const radius = 5.02 + random() * 4.96;
  const z = random() * 2 - 1;
  const angle = random() * Math.PI * 2;
  const values = [
    Math.sqrt(1 - z * z) * Math.cos(angle),
    Math.sqrt(1 - z * z) * Math.sin(angle),
    z,
  ];
  const primary = vector("p-position");
  ["x", "y", "z"].forEach((axis, i) => {
    $(`s-position-${axis}`).value = (primary[i] + radius * values[i]).toFixed(
      2,
    );
  });
  preview();
};
captureView();
preview();
request("/api/v1/capabilities")
  .then((data) => {
    $("connection").textContent = "Backend connected";
    $("connection-light").classList.add("connected");
    for (const option of $("provider").options)
      if (!data.providers[option.value]) option.disabled = true;
    $("rl-advisor").disabled = !data.rl_available;
    $("controller").querySelector('[value="rl"]').disabled = !data.rl_available;
    $("rl-status").textContent = data.rl_available
      ? "Trained policy available on the server."
      : "Train in Kaggle and configure the policy paths to enable learned advice.";
  })
  .catch((error) => {
    $("connection").textContent = "Backend unavailable";
    showError(
      new Error(
        `Cannot reach the backend. Start uvicorn on port 8000. ${error.message}`,
      ),
    );
  });
