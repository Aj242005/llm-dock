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
    `<div class="group-label">${title}<span>${unit}</span></div><div class="triplet">${["x", "y", "z"].map((axis, i) => `<label>${axis.toUpperCase()}<input id="${prefix}-${name}-${axis}" type="number" value="${values[i]}" step="${name === "position" ? "any" : "0.01"}" required aria-label="${label} ${title} ${axis}"></label>`).join("")}</div>`;
  return `<details ${primary ? "" : "open"}><summary>${label}</summary><div class="satellite-name"><b class="${primary ? "primary" : "secondary"}-key"></b>${primary ? "Target docking port" : "Approaching docking port"}</div>
  ${triple("position", "Position", "m", primary ? [0, 0, 0] : [80, 48, 36])}
  ${!primary ? '<p class="field-help">100 m by default. Any starting port distance from 2 cm to 1 km is allowed.</p>' : ""}
  ${!primary ? '<button id="randomize" class="random-button" type="button"><i data-lucide="shuffle"></i>Randomize secondary position</button>' : ""}
  ${triple("velocity", "Velocity", "m/s", [0, 0, 0])}
  ${triple("attitude", "Attitude · roll / pitch / yaw", "deg", primary ? [0, 0, 0] : [15, -20, 35])}
  ${triple("omega", "Rotation rate", "rad/s", [0, 0, 0])}
  <p class="field-help">Radians per second: 0.01 rad/s ≈ 0.57 deg/s. Use 0 for an initially steady craft. The combined relative rate must stay within the tumble limit.</p>
  <div class="pair"><label>Mass <span>kg</span><input id="${prefix}-mass" type="number" value="500" min="1" max="100000" step="1" required></label><label>Fuel <span>%</span><input id="${prefix}-fuel" type="number" value="100" min="0" max="100" step="0.1" required></label></div>
  <label>Propellant capacity <span>kg</span><input id="${prefix}-propellant" type="number" value="25" min="0.001" step="0.001" required></label>
  <p class="field-help">Mass includes loaded propellant. Fuel percentage measures the fraction of this tank capacity remaining.</p>
  <div class="pair"><label>Min. transit speed <span>m/s</span><input id="${prefix}-min" type="number" value="0" min="0" max="20" step="0.01" required></label><label>Max. speed <span>m/s</span><input id="${prefix}-max" type="number" value="2" min="0.01" max="20" step="0.01" required></label></div>
  <div class="pair"><label>Max. horizontal <span>m/s</span><input id="${prefix}-horizontal" type="number" value="2" min="0.01" max="20" step="0.01" required></label><label>Max. vertical <span>m/s</span><input id="${prefix}-vertical" type="number" value="2" min="0.01" max="20" step="0.01" required></label></div>
  <label>Port capture radius <span>m</span><input id="${prefix}-radius" type="number" value="0.02" min="0.005" max="0.03" step="0.001" required></label>
  ${primary ? '<label>Orbital semi-major axis <span>m</span><input id="orbit" type="number" value="6878000" min="6371000" step="1" required></label>' : ""}
  <p class="field-help">Zero speed is permitted during braking and capture.</p></details>`;
}
$("satellite-fields").innerHTML =
  fields("p", "Primary · International Space Station", true) +
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
    propellant_capacity_kg: number(`${prefix}-propellant`),
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
      initial_separation_range_m: [
        number("start-range-min"),
        number("start-range-max"),
      ],
      max_thrust_n: number("max-thrust"),
      max_acceleration_mps2: number("max-acceleration"),
      near_port_speed_mps: number("near-speed"),
      max_range_m: 1000,
      max_omega_radps: number("tumble-limit"),
      playback_speed: number("playback-speed"),
      specific_impulse_s: number("engine-isp"),
      rcs_specific_impulse_s: number("rcs-isp"),
      rcs_lever_arm_m: number("rcs-arm"),
      attitude_standoff_m: number("standoff"),
      port_corridor_radius_m: number("corridor"),
      alignment_stable_time_s: number("stable-time"),
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
  $("s-omega-x").setCustomValidity("");
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
  $("range").innerHTML = `${norm(relative).toFixed(3)} <small>m</small>`;
  $("speed").innerHTML = `${norm(velocity).toFixed(3)} <small>m/s</small>`;
  $("fuel").innerHTML =
    `${data.secondary.fuel_remaining_pct.toFixed(2)} <small>%</small>`;
  $("propellant-remaining").textContent = `${(data.secondary.propellant_capacity_kg * data.secondary.fuel_remaining_pct / 100).toFixed(3)} kg remaining`;
  $("propellant-used").textContent = "0.000 kg used · 0.000 g/s";
  $("guidance-stage").textContent = "Awaiting session";
  $("approach-gate").textContent = `Final closure requires stable port alignment and entry into the docking axis corridor. Stand-off: ${data.config.attitude_standoff_m} m.`;
  $("primary-velocity").textContent = formatVector(data.primary.velocity_mps);
  $("secondary-velocity").textContent = formatVector(
    data.secondary.velocity_mps,
  );
  const separation = norm(relative);
  const rotationRate = norm(data.secondary.angular_velocity_radps.map(
    (value, index) => value - data.primary.angular_velocity_radps[index],
  ));
  const tumbleLimit = data.config.max_omega_radps;
  const rateError = rotationRate > tumbleLimit + 1e-9
    ? `Relative rotation rate ${rotationRate.toFixed(3)} rad/s exceeds the ${tumbleLimit} rad/s tumble limit. Reduce the rotation-rate components; 1 rad/s ≈ 57.3 deg/s.`
    : "";
  $("s-omega-x").setCustomValidity(rateError);
  $("rotation-validation").textContent = rateError;
  $("rotation-validation").hidden = !rateError;
  const minimum = number("start-range-min"),
    maximum = number("start-range-max");
  $("s-position-x").setCustomValidity(
    minimum >= 0.02 &&
      maximum <= 1000 &&
      minimum <= maximum &&
      separation >= minimum - 1e-9 &&
      separation <= maximum + 1e-9
      ? ""
      : `Initial port separation must be between ${minimum} and ${maximum} m (currently ${separation.toFixed(3)} m).`,
  );
  $("playback-status").textContent =
    `${number("playback-speed")}× playback · ${separation.toFixed(separation < 1 ? 3 : 1)} m initial separation`;
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
    stable_alignment: "Stable alignment",
    port_corridor: "Docking axis corridor",
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
  $("planner-status").textContent =
    event.applied === false
      ? "Delayed response discarded · fresh deterministic guidance"
      : event.source === "heuristic_fallback"
        ? "Provider call failed · deterministic fallback applied"
        : `Plan received from ${event.source} · ${(event.plan_age_s || 0).toFixed(1)} s snapshot age`;
  $("latest-rationale").textContent = event.subgoal.rationale;
  if (event.safety_notes?.length) {
    $("latest-rationale").textContent +=
      ` Applied limits: ${event.safety_notes.join(" ")}`;
  }
  $("scene-state").textContent = "Live telemetry";
  $("latest-rl").textContent =
    (event.rl_advisor
      ? "Verified: a trained PPO proposal was supplied. "
      : event.rl_advisor_status === "disabled"
        ? "Learned advice was switched off for this session. "
        : `Policy unavailable: ${event.rl_advisor_reason || "Check the server log"}. `) +
    (event.subgoal.rl_assessment || "No learned assessment supplied.");
  if (event.recovery_subgoal) {
    $("latest-rationale").textContent +=
      ` Current recovery maneuver: ${event.recovery_subgoal.rationale}`;
  }
  $("latest-alternatives").replaceChildren();
  for (const alternative of event.subgoal.alternatives || []) {
    const item = document.createElement("li");
    item.textContent = alternative;
    $("latest-alternatives").append(item);
  }
  if (!decisionCount) $("decisions").replaceChildren();
  decisionCount++;
  $("decision-count").textContent = `${decisionCount} decisions`;
  const article = document.createElement("article");
  article.className = "decision";
  article.innerHTML =
    '<div class="decision-top"><span class="decision-source"></span><span class="decision-time"></span></div><h3></h3><p></p><div class="decision-target"></div><details><summary>Tools & learned advice</summary><pre></pre></details><details><summary>Alternatives considered</summary><ul></ul></details>';
  article.querySelector(".decision-source").textContent =
    event.source.replaceAll("_", " ") + (event.applied === false ? " · discarded" : "");
  article.querySelector(".decision-time").textContent =
    `${event.sim_time_s.toFixed(1)} s · step ${event.step}`;
  article.querySelector("h3").textContent = event.phase.replaceAll("_", " ");
  article.querySelector("p").textContent = event.subgoal.rationale;
  article.querySelector(".decision-target").textContent =
    `${event.applied === false ? "Discarded proposal" : "Target"}: ${formatVector(event.subgoal.target_position_m, 2)} m · ${event.subgoal.closing_speed_mps.toFixed(3)} m/s`;
  article.querySelector("pre").textContent = JSON.stringify(
    {
      tools: event.tool_results,
      learned_advice: event.rl_advisor || "No learned advice used",
      maneuver_mode: event.subgoal.maneuver_mode,
      target_orientation_quat_wxyz: event.subgoal.target_orientation_quat,
      target_angular_velocity_radps: event.subgoal.target_angular_velocity_radps,
      learned_advice_status: event.rl_advisor_status,
      learned_advice_reason: event.rl_advisor_reason,
      recovery_maneuver: event.recovery_subgoal,
      snapshot_time_s: event.snapshot_sim_time_s,
      age_s: event.plan_age_s,
      applied: event.applied,
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

function clearExplanation(starting = false) {
  $("planner-status").textContent = starting
    ? "Starting guidance request"
    : "Ready for a new session";
  $("latest-rationale").textContent = starting
    ? "Preparing the first maneuver request."
    : "Start a session to request a new maneuver.";
  $("latest-rl").textContent = "No proposal received for this session yet.";
  $("latest-alternatives").replaceChildren();
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
  const maxRange = Math.max(number("capture-range"), ...samples.map((s) => s[1]));
  const points = samples
    .map(
      ([time, range]) =>
        `${24 + (time / maxTime) * span},${120 - (range / maxRange) * 95}`,
    )
    .join(" ");
  const gateY = 120 - (number("capture-range") / maxRange) * 95;
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
    max_thrust_n: number("max-thrust"),
  });
  $("range").innerHTML = `${event.range_m.toFixed(3)} <small>m</small>`;
  $("speed").innerHTML =
    `${norm(event.velocity_mps).toFixed(3)} <small>m/s</small>`;
  $("fuel").innerHTML = `${event.fuel_pct.toFixed(2)} <small>%</small>`;
  $("propellant-remaining").textContent = `${(event.propellant_remaining_kg ?? 0).toFixed(3)} kg remaining`;
  $("propellant-used").textContent = `${(event.propellant_used_kg ?? 0).toFixed(3)} kg used · ${((event.propellant_flow_kgps ?? 0) * 1000).toFixed(3)} g/s`;
  const stages = {
    detumbling: "Damping rotation · closing withheld",
    aligning_at_standoff: "Aligning ports · XYZ transfer to stand-off",
    final_port_approach: "Stable alignment · final axial approach",
    coasting: "Awaiting plan · local safety active",
  };
  $("guidance-stage").textContent = stages[event.guidance_mode] || event.guidance_mode?.replaceAll("_", " ") || "Local guidance";
  const gate = event.approach_gate;
  if (gate) $("approach-gate").textContent = `${gate.alignment_ready && gate.inside_port_corridor ? "Final closure permitted" : "Final closure withheld"}. Stable alignment ${Math.min(gate.stable_time_s, gate.required_stable_time_s).toFixed(1)} / ${gate.required_stable_time_s.toFixed(1)} s; lateral port error ${(gate.lateral_error_m * 100).toFixed(2)} cm / ${(gate.corridor_radius_m * 100).toFixed(2)} cm corridor.`;
  $("time").innerHTML = `${event.sim_time_s.toFixed(1)} <small>s</small>`;
  $("phase").textContent = event.phase.replaceAll("_", " ");
  $("primary-velocity").textContent = formatVector(event.primary_velocity_mps);
  $("secondary-velocity").textContent = formatVector(
    event.secondary_velocity_mps,
  );
  $("thrust").textContent = formatVector(event.command_force_n || [0, 0, 0], 2);
  $("torque").textContent = formatVector(event.command_torque_nm || [0, 0, 0], 2);
  $("rotation-rate").textContent = formatVector(event.angular_velocity_radps || [0, 0, 0]);
  const attitude = event.orientation_quat || [1, 0, 0, 0];
  const angle = 2 * Math.acos(Math.min(1, Math.abs(attitude[0]) / norm(attitude))) * 180 / Math.PI;
  $("attitude-error").textContent = `${angle.toFixed(2)} deg from target`;
  $("command-status").textContent = event.command_limited
    ? "Command adjusted to motion limits"
    : "Within configured actuator envelope";
  if (event.planning_pending) {
    const activity = event.guidance_mode === "coasting"
      ? "coasting under safety limits"
      : event.guidance_mode === "detumbling"
        ? "damping rotation locally"
      : event.guidance_mode?.includes("braking")
        ? "local braking"
        : "following the active maneuver";
    $("planner-status").textContent = `Planning in background · ${activity}`;
    $("scene-state").textContent = "Live telemetry · planning";
  }
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
  clearExplanation(true);
  setRunning(true);
  // Stop needs the newly created session URL. Enable it after the response so
  // an immediate click cannot accidentally cancel the previous session.
  $("cancel").disabled = true;
  $("phase").textContent = "Starting session";
  try {
    session = await request("/api/v1/docking/simulate", data);
    $("cancel").disabled = false;
    $("session-id").textContent = session.session_id.slice(0, 12);
    $("export").disabled = false;
    samples = [];
    chart();
    decisionCount = 0;
    $("decisions").replaceChildren();
    $("decision-count").textContent = "0 decisions";
    if (stream) stream.close();
    stream = new EventSource(session.stream_url);
    stream.addEventListener("planning", (e) => {
      const event = JSON.parse(e.data);
      if (event.status === "started") {
        $("planner-status").textContent =
          `${event.provider} is planning · motion continues`;
        $("scene-state").textContent = "Live telemetry · planning";
        if (!decisionCount) {
          $("latest-rationale").textContent =
            `${event.provider === "vertex" ? "Gemini" : event.provider} is preparing the first maneuver. Physics continues under the local safety envelope; the returned plan will be checked against the current state.`;
        }
      }
    });
    stream.addEventListener("telemetry", (e) => telemetry(JSON.parse(e.data)));
    stream.addEventListener("llm_decision", (e) =>
      renderDecision(JSON.parse(e.data)),
    );
    for (const type of ["docked", "failed"])
      stream.addEventListener(type, (e) => {
        const terminal = JSON.parse(e.data);
        stream.close();
        setRunning(false);
        $("planner-status").textContent =
          type === "docked"
            ? "Capture confirmed · session ended"
            : "Session stopped";
        if (type === "failed") {
          const message = terminal.error || `Session ended: ${terminal.failure_reason.replaceAll("_", " ")}.`;
          $("latest-rationale").textContent = message;
          if (!decisionCount) {
            $("latest-rl").textContent = "The session ended before a planner decision was received.";
            $("latest-alternatives").replaceChildren();
          }
          $("planner-status").textContent = terminal.failure_reason === "cancelled"
            ? "Stopped by user"
            : "Stopped by simulation guard";
        }
        if (latest)
          scene.update({
            ...latest,
            running: false,
            captured: type === "docked",
            primary_capture_radius_m: number("p-radius"),
            secondary_capture_radius_m: number("s-radius"),
    max_thrust_n: number("max-thrust"),
          });
        $("scene-state").textContent =
          type === "docked" ? "Capture confirmed" : "Session ended";
        if (type === "docked") {
          $("capture-status").textContent = "Captured";
          $("dock").textContent = "Docking capture complete";
          $("capture-announcement").hidden = false;
          $("capture-result").textContent =
            `${(latest.range_m * 100).toFixed(2)} cm port separation · ${norm(latest.velocity_mps).toFixed(3)} m/s relative speed`;
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
        if (terminal.error && terminal.failure_reason !== "cancelled") showError(new Error(terminal.error));
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
  updateRlStatus();
  clearExplanation();
  $("decisions").replaceChildren();
  decisionCount = 0;
  $("decision-count").textContent = "0 decisions";
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
for (const name of ["trail", "vectors", "envelope", "grid"])
  $(`show-${name}`).onchange = (event) =>
    scene.setOverlay(name, event.target.checked);
$("grid-spacing").onchange = (event) =>
  scene.setGridSpacing(event.target.value);
$("mission-fields").addEventListener("change", preview);
$("randomize").onclick = () => {
  let seed = number("seed") >>> 0;
  const random = () => {
    seed = (1664525 * seed + 1013904223) >>> 0;
    return seed / 2 ** 32;
  };
  // Sample a seeded direction and distance inside the optional starting band.
  const minimum = number("start-range-min"),
    maximum = number("start-range-max");
  if (minimum > maximum || minimum < 0.02 || maximum > 1000) return;
  const margin = Math.min(0.02, (maximum - minimum) / 4);
  const radius = minimum + margin + random() * (maximum - minimum - 2 * margin);
  const z = random() * 2 - 1;
  const angle = random() * Math.PI * 2;
  const values = [
    Math.sqrt(1 - z * z) * Math.cos(angle),
    Math.sqrt(1 - z * z) * Math.sin(angle),
    z,
  ];
  const primary = vector("p-position");
  ["x", "y", "z"].forEach((axis, i) => {
    $(`s-position-${axis}`).value = String(primary[i] + radius * values[i]);
  });
  preview();
};
captureView();
preview();
function updateRlStatus() {
  if (!$("rl-advisor").disabled)
    $("rl-status").textContent = $("rl-advisor").checked
      ? "Trained policy verified · advice enabled for the next session."
      : "Advice switched off · the planner will receive no learned proposal.";
}
$("rl-advisor").addEventListener("change", updateRlStatus);
request("/api/v1/capabilities")
  .then((data) => {
    $("connection").textContent = "Backend connected";
    $("connection-light").classList.add("connected");
    for (const option of $("provider").options)
      if (!data.providers[option.value]) option.disabled = true;
    $("provider").value = data.default_provider;
    $("model").placeholder =
      data.default_models?.[$("provider").value] || "Use server default";
    $("rl-advisor").disabled = !data.rl_available;
    $("rl-advisor").checked = data.rl_available;
    $("rl-advisor").defaultChecked = data.rl_available;
    $("controller").querySelector('[value="rl"]').disabled = !data.rl_available;
    $("rl-status").textContent = data.rl_reason || "No trained policy available.";
    updateRlStatus();
  })
  .catch((error) => {
    $("connection").textContent = "Backend unavailable";
    showError(
      new Error(
        `Cannot reach the backend. Start uvicorn on port 8000. ${error.message}`,
      ),
    );
  });
