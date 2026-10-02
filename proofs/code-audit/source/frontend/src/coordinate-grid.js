import * as THREE from "three";

// A fixed local coordinate frame. The shared camera rotates the grid and craft.
export function createCoordinateGrid(scene) {
  const group = new THREE.Group();
  group.name = "XYZ coordinate grid";
  scene.add(group);
  const colors = [0xffb1a5, 0x8fd9c4, 0x90b9e9];
  // Physics Z is screen-up; physics Y points along negative scene Z.
  const directions = [
    new THREE.Vector3(1, 0, 0),
    new THREE.Vector3(0, 0, -1),
    new THREE.Vector3(0, 1, 0),
  ];
  let currentSpacing = 0;

  function label(text, color) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const context = canvas.getContext("2d");
    context.fillStyle = "#10191f";
    context.fillRect(0, 0, 256, 64);
    context.font = "500 30px 'IBM Plex Sans', sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
    context.fillText(text, 128, 32);
    return new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(canvas),
        sizeAttenuation: false,
        depthWrite: false,
      }),
    );
  }

  function setSpacing(spacing) {
    if (spacing === currentSpacing) return;
    currentSpacing = spacing;
    for (const child of [...group.children]) {
      child.traverse((object) => {
        object.geometry?.dispose();
        object.material?.map?.dispose();
        object.material?.dispose();
      });
      group.remove(child);
    }
    const extent = spacing * 10;
    // XY, XZ and YZ intersect at the primary docking port.
    for (let plane = 0; plane < 3; plane++) {
      const grid = new THREE.GridHelper(extent * 2, 20, 0x526d80, 0x526d80);
      if (plane === 1) grid.rotation.x = Math.PI / 2;
      if (plane === 2) grid.rotation.z = Math.PI / 2;
      grid.material.transparent = true;
      grid.material.opacity = 0.14;
      grid.material.depthWrite = false;
      group.add(grid);
    }
    directions.forEach((direction, index) => {
      group.add(
        new THREE.ArrowHelper(
          direction,
          new THREE.Vector3(),
          extent,
          colors[index],
          Math.min(spacing * 0.45, 0.4),
          Math.min(spacing * 0.22, 0.2),
        ),
      );
      const axisLabel = label(
        `${["X", "Y", "Z"][index]} · ${extent < 1 ? (extent * 100).toFixed(0) + " cm" : extent + " m"}`,
        colors[index],
      );
      axisLabel.position.copy(direction).multiplyScalar(extent * 1.08);
      // Constant screen size keeps labels readable without covering a nearby craft.
      axisLabel.scale.set(0.10, 0.025, 1);
      group.add(axisLabel);
      for (const sign of [-1, 1]) {
        const tick = label(`${sign * spacing * 5} m`, colors[index]);
        tick.position.copy(direction).multiplyScalar(sign * spacing * 5);
        tick.scale.set(0.07, 0.0175, 1);
        group.add(tick);
      }
    });
    document.getElementById("grid-readout").textContent =
      `${spacing < 1 ? spacing * 100 + " cm" : spacing + " m"} per division · drag to rotate`;
  }
  return { group, setSpacing };
}
