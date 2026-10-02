"""Verify artifact hashes exported by the Kaggle evaluation workflow."""

import hashlib
import json
from pathlib import Path


def main():
    manifests = list(Path("proofs").glob("*/manifest.json"))
    if not manifests:
        raise SystemExit("No proof manifests found")
    for path in manifests:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            artifact = path.parent / name
            if not artifact.is_file():
                raise SystemExit(f"Missing artifact: {artifact}")
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                raise SystemExit(f"Hash mismatch: {artifact}")
        print(f"{path.parent.name}: verified {len(manifest['files'])} files")
    presentation = Path("proofs/presentation-manifest.json")
    if presentation.exists():
        files = json.loads(presentation.read_text(encoding="utf-8"))["files"]
        for name, expected in files.items():
            artifact = Path("proofs") / name
            if (
                not artifact.is_file()
                or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected
            ):
                raise SystemExit(f"Presentation evidence mismatch: {artifact}")
        print(f"Presentation bundle: verified {len(files)} files")


if __name__ == "__main__":
    main()
