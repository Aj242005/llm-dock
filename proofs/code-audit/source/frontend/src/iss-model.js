import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

// NASA's stationary ISS asset uses metre-scale geometry. Its PMA-2 forward tip
// is aligned with the same docking-port origin used by the physics backend.
export async function loadIssModel(parent, placeholder, onLoaded) {
  const status = document.getElementById("iss-status");
  try {
    const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
    const { scene: model } = await loader.loadAsync("/models/iss.glb");
    model.position.set(0, 0.10062367, -21.00535011);
    const alignment = new THREE.Group();
    alignment.rotation.y = Math.PI / 2;
    alignment.add(model);
    parent.add(alignment);
    placeholder.visible = false;
    status.textContent = "ISS model · NASA";
    status.dataset.state = "ready";
    onLoaded();
  } catch {
    status.textContent =
      "ISS model unavailable · schematic target shown. Reload to retry.";
    status.dataset.state = "error";
  }
}
