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
    model.updateMatrixWorld(true);
    const adapter = model.getObjectByName("04_(PMA)_Pressurized_Mating_Adapter_2");
    if (!adapter) throw new Error("PMA-2 docking adapter missing");
    const tip = new THREE.Box3().setFromObject(adapter).max.z;
    const face = new THREE.Box3();
    adapter.traverse((object) => {
      const vertices = object.geometry?.attributes.position;
      if (!vertices) return;
      for (let index = 0; index < vertices.count; index++) {
        const point = new THREE.Vector3()
          .fromBufferAttribute(vertices, index)
          .applyMatrix4(object.matrixWorld);
        if (point.z >= tip - 0.005) face.expandByPoint(point);
      }
    });
    if (face.isEmpty()) throw new Error("PMA-2 docking face missing");
    const port = face.getCenter(new THREE.Vector3());
    model.position.copy(port).negate();
    const alignment = new THREE.Group();
    alignment.rotation.y = Math.PI / 2;
    alignment.add(model);
    parent.add(alignment);
    placeholder.visible = false;
    status.textContent = "ISS model · NASA";
    status.dataset.state = "ready";
    onLoaded(port.toArray());
  } catch {
    status.textContent =
      "ISS model unavailable · schematic target shown. Reload to retry.";
    status.dataset.state = "error";
  }
}
