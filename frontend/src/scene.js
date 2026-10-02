import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// One foreground unit is one metre. The origin of each model is its docking port.
// Earth is a separate illustrative backdrop; it never participates in physics.
export function createScene(container) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true });
  } catch {
    const message = document.getElementById("scene-message");
    message.hidden = false;
    message.textContent =
      "WebGL is unavailable. Telemetry and session controls remain available.";
    return { update() {}, resetCamera() {}, setCamera() {}, setOverlay() {} };
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  renderer.setClearColor(0x070e16);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.3;
  renderer.autoClear = false;
  renderer.domElement.setAttribute(
    "aria-label",
    "Orbit the spacecraft with drag; zoom with the scroll wheel. Camera buttons provide fixed views.",
  );
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const backdrop = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.02, 100000);
  const backdropCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 3000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 2;
  controls.maxDistance = 50000;
  scene.add(new THREE.HemisphereLight(0xc3def9, 0x152b41, 2.3));
  const sun = new THREE.DirectionalLight(0xffe5c1, 4);
  sun.position.set(-12, 16, 20);
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0x649ff3, 3);
  rim.position.set(8, -4, -12);
  scene.add(rim);

  function material(color, metalness = 0.4, roughness = 0.4) {
    return new THREE.MeshStandardMaterial({ color, metalness, roughness });
  }
  const silver = material(0xcbd5df, 0.65);
  const white = material(0xe1e5e6, 0.2, 0.7);
  const dark = material(0x202c37, 0.6);
  const foil = material(0xb3985d, 0.65, 0.5);
  const solar = material(0x163f70, 0.6, 0.28);
  const seam = material(0x6685a5, 0.6);

  function addMesh(group, geometry, surface, position = [0, 0, 0]) {
    const object = new THREE.Mesh(geometry, surface);
    object.position.set(...position);
    group.add(object);
    return object;
  }

  function cylinder(group, radius, length, x, surface) {
    const object = addMesh(
      group,
      new THREE.CylinderGeometry(radius, radius, length, 32),
      surface,
      [x, 0, 0],
    );
    object.rotation.z = Math.PI / 2;
    return object;
  }

  function ring(group, radius, thickness, x, surface) {
    const object = addMesh(
      group,
      new THREE.TorusGeometry(radius, thickness, 8, 40),
      surface,
      [x, 0, 0],
    );
    object.rotation.y = Math.PI / 2;
    return object;
  }

  function spacecraft(color, isPrimary) {
    const group = new THREE.Group();
    const direction = isPrimary ? -1 : 1;
    const accent = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.6,
      roughness: 0.3,
    });
    cylinder(group, 0.67, 1.8, direction * 1.1, white);
    cylinder(group, 0.55, 0.45, direction * 2.2, foil);
    cylinder(group, 0.38, 0.6, direction * 0.35, dark);
    cylinder(group, 0.36, 0.09, 0, dark);
    ring(group, 0.46, 0.06, 0, silver);
    ring(group, 0.49, 0.018, direction * 0.07, accent);
    for (const x of [0.42, 0.65, 1.55, 1.95])
      ring(group, 0.68, 0.025, direction * x, silver);
    for (let index = 0; index < 8; index++) {
      const angle = (index / 8) * Math.PI * 2;
      addMesh(group, new THREE.BoxGeometry(0.13, 0.06, 0.06), silver, [
        direction * 0.04,
        Math.cos(angle) * 0.45,
        Math.sin(angle) * 0.45,
      ]);
    }
    // Individual cells, frames, and booms make the panel geometry readable up close.
    for (const side of [-1, 1]) {
      addMesh(group, new THREE.BoxGeometry(0.12, 0.12, 1.5), silver, [
        direction * 1.15,
        0,
        side * 1.1,
      ]);
      addMesh(group, new THREE.BoxGeometry(1.6, 0.07, 2.8), dark, [
        direction * 1.15,
        0,
        side * 2.5,
      ]);
      addMesh(group, new THREE.BoxGeometry(1.55, 0.012, 2.74), solar, [
        direction * 1.15,
        0.043,
        side * 2.5,
      ]);
      addMesh(group, new THREE.BoxGeometry(1.55, 0.012, 2.74), solar, [
        direction * 1.15,
        -0.043,
        side * 2.5,
      ]);
      for (let row = -3; row <= 3; row++) {
        addMesh(group, new THREE.BoxGeometry(1.57, 0.1, 0.018), seam, [
          direction * 1.15,
          0,
          side * 2.5 + row * 0.43,
        ]);
      }
      for (let column = -1; column <= 1; column++) {
        addMesh(group, new THREE.BoxGeometry(0.015, 0.1, 2.75), seam, [
          direction * 1.15 + column * 0.5,
          0,
          side * 2.5,
        ]);
      }
      addMesh(group, new THREE.BoxGeometry(0.35, 0.25, 0.35), foil, [
        direction * 1.75,
        side * 0.65,
        0,
      ]);
    }
    const antenna = addMesh(
      group,
      new THREE.SphereGeometry(0.32, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2),
      silver,
      [direction * 1.65, 0.96, 0],
    );
    antenna.rotation.x = Math.PI;
    addMesh(group, new THREE.CylinderGeometry(0.025, 0.025, 0.5, 8), dark, [
      direction * 1.65,
      0.75,
      0,
    ]);
    addMesh(group, new THREE.BoxGeometry(0.4, 0.012, 0.18), accent, [
      direction * 1.1,
      0.68,
      0,
    ]);
    const exhaust = addMesh(
      group,
      new THREE.ConeGeometry(0.16, 1, 16),
      new THREE.MeshBasicMaterial({
        color: 0xb6e6ff,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
      }),
    );
    exhaust.visible = false;
    return { group, exhaust, direction };
  }

  const primary = spacecraft(0x90b9e9, true);
  const secondary = spacecraft(0x8fd9c4, false);
  scene.add(primary.group, secondary.group);

  function envelope(color) {
    const group = new THREE.Group();
    const surface = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.25,
    });
    for (let axis = 0; axis < 3; axis++) {
      const points = [];
      for (let i = 0; i <= 96; i++) {
        const angle = (i / 96) * Math.PI * 2;
        points.push(
          new THREE.Vector3(Math.cos(angle) * 1.25, Math.sin(angle) * 1.25, 0),
        );
      }
      const circle = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        surface,
      );
      if (axis === 1) circle.rotation.x = Math.PI / 2;
      if (axis === 2) circle.rotation.y = Math.PI / 2;
      group.add(circle);
    }
    return group;
  }
  const primaryEnvelope = envelope(0x90b9e9);
  const secondaryEnvelope = envelope(0x8fd9c4);
  primary.group.add(primaryEnvelope);
  secondary.group.add(secondaryEnvelope);
  const velocityArrow = new THREE.ArrowHelper(
    new THREE.Vector3(-1, 0, 0),
    new THREE.Vector3(),
    2,
    0x8fd9c4,
    0.3,
    0.15,
  );
  scene.add(velocityArrow);
  const trail = new THREE.Line(
    new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({
      color: 0x8fd9c4,
      transparent: true,
      opacity: 0.65,
    }),
  );
  scene.add(trail);
  const separation = new THREE.Line(
    new THREE.BufferGeometry(),
    new THREE.LineDashedMaterial({
      color: 0x90b9e9,
      transparent: true,
      opacity: 0.35,
      dashSize: 0.7,
      gapSize: 0.6,
    }),
  );
  separation.geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(new Float32Array(6), 3),
  );
  scene.add(separation);

  // A bounded, static shader backdrop keeps foreground distances undistorted.
  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(90, 64, 48),
    new THREE.ShaderMaterial({
      vertexShader: `varying vec3 vNormal; varying vec3 vPoint;
      void main() { vNormal = normalize(normalMatrix * normal); vPoint = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `varying vec3 vNormal; varying vec3 vPoint;
      void main() {
        vec3 n = normalize(vNormal);
        float light = max(dot(n, normalize(vec3(-0.6, 0.8, 0.7))), 0.0);
        float cloud = sin(vPoint.x * 0.15 + sin(vPoint.z * 0.1) * 3.0)
          * sin(vPoint.y * 0.2 + sin(vPoint.x * 0.09) * 4.0);
        cloud = smoothstep(0.05, 0.8, cloud) * 0.55;
        vec3 ocean = mix(vec3(0.018, 0.07, 0.13), vec3(0.15, 0.32, 0.46), cloud);
        float limb = pow(1.0 - max(n.z, 0.0), 4.0);
        vec3 color = ocean * (0.12 + light * 0.9) + vec3(0.15, 0.39, 0.62) * limb * light;
        gl_FragColor = vec4(color, 1.0);
      }`,
    }),
  );
  earth.position.set(-10, -99, -135);
  backdrop.add(earth);
  const atmosphere = new THREE.Mesh(
    new THREE.SphereGeometry(91, 64, 48),
    new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: `varying vec3 vNormal; void main() {
      vNormal = normalize(normalMatrix * normal);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: `varying vec3 vNormal; void main() {
      float rim = pow(1.0 - max(normalize(vNormal).z, 0.0), 5.0);
      gl_FragColor = vec4(0.32, 0.63, 0.88, rim * 0.55); }`,
    }),
  );
  atmosphere.position.copy(earth.position);
  backdrop.add(atmosphere);
  const starPositions = [];
  let starSeed = 42;
  const random = () => {
    starSeed = (1664525 * starSeed + 1013904223) >>> 0;
    return starSeed / 2 ** 32;
  };
  for (let i = 0; i < 900; i++)
    starPositions.push(
      (random() - 0.5) * 1600,
      (random() - 0.5) * 1000,
      -600 - random() * 800,
    );
  const starGeometry = new THREE.BufferGeometry();
  starGeometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(starPositions, 3),
  );
  backdrop.add(
    new THREE.Points(
      starGeometry,
      new THREE.PointsMaterial({
        color: 0xa7c0d8,
        size: 1.2,
        transparent: true,
        opacity: 0.65,
        sizeAttenuation: false,
      }),
    ),
  );

  // Physics Z becomes scene Y through a proper basis rotation, including attitude.
  const basis = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(1, 0, 0),
    -Math.PI / 2,
  );
  const inverseBasis = basis.clone().invert();
  const vector = (values) =>
    new THREE.Vector3(...values).applyQuaternion(basis);
  const quaternion = (values) =>
    new THREE.Quaternion(values[1], values[2], values[3], values[0])
      .premultiply(basis)
      .multiply(inverseBasis);
  let desiredPosition = new THREE.Vector3(50, 0, 0);
  let desiredQuaternion = new THREE.Quaternion();
  let primaryQuaternion = new THREE.Quaternion();
  let velocity = new THREE.Vector3();
  let force = new THREE.Vector3();
  let running = false;
  let captured = false;
  let cameraMode = "chaser";
  let followCamera = true;
  const overlays = { trail: true, vectors: true, envelope: true };
  const points = [];
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const cameraTarget = new THREE.Vector3();
  const cameraPosition = new THREE.Vector3();
  let lastFrame = performance.now();
  let visible = true;
  controls.addEventListener("start", () => {
    followCamera = false;
  });

  function cameraPlacement() {
    const position = secondary.group.position;
    const distance = position.length();
    if (cameraMode === "port") {
      cameraTarget.set(0, 0, 0);
      cameraPosition.set(5.5, 3, 6.5);
    } else if (cameraMode === "overview" || distance < 10 || captured) {
      const radius = Math.max(7, distance * 0.65);
      cameraTarget.copy(position).multiplyScalar(0.5);
      cameraPosition
        .copy(cameraTarget)
        .add(new THREE.Vector3(radius * 0.7, radius * 0.6, radius * 1.4));
    } else {
      // Track the chaser at true model scale. The separate overview fits both ports.
      cameraTarget.copy(position).multiplyScalar(0.98);
      cameraPosition.copy(position).add(new THREE.Vector3(8, 6, 11));
    }
  }

  function resetCamera() {
    followCamera = true;
    cameraPlacement();
    controls.target.copy(cameraTarget);
    camera.position.copy(cameraPosition);
    controls.update();
  }

  function setCamera(mode) {
    cameraMode = mode;
    followCamera = true;
    if (reducedMotion.matches) resetCamera();
  }

  function setOverlay(name, enabled) {
    overlays[name] = enabled;
    trail.visible = overlays.trail;
    primaryEnvelope.visible = secondaryEnvelope.visible = overlays.envelope;
  }

  function update(state, reset = false) {
    desiredPosition = vector(state.position_m);
    desiredQuaternion = quaternion(state.orientation_quat || [1, 0, 0, 0]);
    primaryQuaternion = quaternion(
      state.primary?.orientation_quat || [1, 0, 0, 0],
    );
    if (state.type === "telemetry")
      desiredQuaternion.premultiply(primaryQuaternion);
    velocity = vector(state.velocity_mps || [0, 0, 0]);
    force = vector(state.command_force_n || [0, 0, 0]);
    running = !!state.running;
    captured = !!state.captured;
    primaryEnvelope.scale.setScalar(
      (state.primary_capture_radius_m || 1.25) / 1.25,
    );
    secondaryEnvelope.scale.setScalar(
      (state.secondary_capture_radius_m || 1.25) / 1.25,
    );
    for (const envelope of [primaryEnvelope, secondaryEnvelope]) {
      for (const circle of envelope.children)
        circle.material.opacity = captured ? 0.6 : 0.25;
    }
    if (reset) {
      secondary.group.position.copy(desiredPosition);
      secondary.group.quaternion.copy(desiredQuaternion);
      primary.group.quaternion.copy(primaryQuaternion);
      points.length = 0;
      trail.geometry.dispose();
      trail.geometry = new THREE.BufferGeometry();
      resetCamera();
    }
    if (state.type === "telemetry") {
      points.push(desiredPosition.clone());
      if (points.length > 3000) points.shift();
      trail.geometry.dispose();
      trail.geometry = new THREE.BufferGeometry().setFromPoints(points);
    }
  }

  function projectLabel(id, craft) {
    const label = document.getElementById(id);
    const position = craft.position
      .clone()
      .add(new THREE.Vector3(0, 1.25, 0))
      .project(camera);
    const onScreen =
      position.z > -1 &&
      position.z < 1 &&
      Math.abs(position.x) < 0.88 &&
      Math.abs(position.y) < 0.75;
    label.hidden = !onScreen;
    if (onScreen) {
      label.style.left = `${(position.x * 0.5 + 0.5) * container.clientWidth}px`;
      label.style.top = `${(-position.y * 0.5 + 0.5) * container.clientHeight}px`;
    }
    return onScreen ? position : null;
  }

  new ResizeObserver(() => {
    const width = container.clientWidth;
    const height = container.clientHeight;
    renderer.setSize(width, height);
    camera.aspect = backdropCamera.aspect = width / height;
    camera.updateProjectionMatrix();
    backdropCamera.updateProjectionMatrix();
  }).observe(container);
  new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
  }).observe(container);
  secondary.group.position.copy(desiredPosition);
  resetCamera();
  renderer.setAnimationLoop(() => {
    const now = performance.now();
    const seconds = Math.min((now - lastFrame) / 1000, 0.05);
    lastFrame = now;
    if (!visible || document.hidden) return;
    const blend = reducedMotion.matches ? 1 : 1 - Math.exp(-seconds * 18);
    // Smooth toward measured positions only; never extrapolate a capture or invent motion.
    secondary.group.position.lerp(desiredPosition, blend);
    secondary.group.quaternion.slerp(desiredQuaternion, blend);
    primary.group.quaternion.copy(primaryQuaternion);
    if (followCamera) {
      cameraPlacement();
      const cameraBlend = reducedMotion.matches
        ? 1
        : 1 - Math.exp(-seconds * 5);
      camera.position.lerp(cameraPosition, cameraBlend);
      controls.target.lerp(cameraTarget, cameraBlend);
    }
    velocityArrow.position.copy(secondary.group.position);
    velocityArrow.visible = overlays.vectors && velocity.length() > 0.001;
    if (velocityArrow.visible) {
      velocityArrow.setDirection(velocity.clone().normalize());
      velocityArrow.setLength(
        Math.max(0.7, Math.min(12, velocity.length() * 8)),
        0.3,
        0.15,
      );
    }
    secondary.exhaust.visible = running && force.length() > 0.1;
    if (secondary.exhaust.visible) {
      const direction = force
        .clone()
        .normalize()
        .negate()
        .applyQuaternion(secondary.group.quaternion.clone().invert());
      secondary.exhaust.position
        .copy(direction)
        .multiplyScalar(1.1)
        .add(new THREE.Vector3(1.1, 0, 0));
      secondary.exhaust.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, -1, 0),
        direction,
      );
      secondary.exhaust.scale.y = Math.min(
        3,
        Math.max(0.3, force.length() / 25),
      );
    }
    const linePositions = separation.geometry.attributes.position;
    linePositions.setXYZ(1, ...secondary.group.position.toArray());
    linePositions.needsUpdate = true;
    separation.geometry.computeBoundingSphere();
    separation.computeLineDistances();
    controls.update();
    const primaryLabel = projectLabel("primary-label", primary.group);
    const secondaryLabel = projectLabel("secondary-label", secondary.group);
    if (
      primaryLabel &&
      secondaryLabel &&
      (Math.abs(primaryLabel.x - secondaryLabel.x) * container.clientWidth) /
        2 <
        145 &&
      (Math.abs(primaryLabel.y - secondaryLabel.y) * container.clientHeight) /
        2 <
        65
    ) {
      // Keep the two names distinct when the measured ports converge.
      const center =
        ((primaryLabel.x + secondaryLabel.x) / 4 + 0.5) * container.clientWidth;
      document.getElementById("primary-label").style.left = `${center - 72}px`;
      document.getElementById("secondary-label").style.left =
        `${center + 72}px`;
    }
    renderer.clear();
    renderer.render(backdrop, backdropCamera);
    renderer.clearDepth();
    renderer.render(scene, camera);
  });
  return { update, resetCamera, setCamera, setOverlay };
}
