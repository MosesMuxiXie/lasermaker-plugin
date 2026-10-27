"""Reproducible local release assembly from an explicit allowlist."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
from pathlib import Path

from lasermaker_agent.packaging import package_release


def notices(root):
    entries, pins = [], []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name, version = dist.metadata["Name"], dist.version
        if name == "lasermaker-agent":
            continue
        pins.append(f"{name}=={version}")
        copied = []
        for file in dist.files or []:
            if not any(token in Path(str(file)).name.lower() for token in ("license", "copying", "notice")):
                continue
            source = dist.locate_file(file)
            if not source.is_file() or source.stat().st_size > 8*1024*1024:
                continue
            prefix = hashlib.sha256(str(file).encode()).hexdigest()[:10]
            target = root / "licenses" / name / (prefix + "-" + Path(str(file)).name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(str(target.relative_to(root)).replace("\\", "/"))
        entries.append({"name": name, "version": version,
                        "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                        "license_files": sorted(set(copied))})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("PYTHON_LICENSE_FILE_REQUIRED")
    target = root / "licenses/Python/LICENSE.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(python_license, target)
    entries.append({"name": "Python", "version": sys.version.split()[0], "license": "PSF-2.0",
                    "license_files": ["licenses/Python/LICENSE.txt"]})
    (root / "requirements.lock.txt").write_text(
        "# Windows x64 / Python 3.12; tested exact versions, including build tools.\n" + "\n".join(pins) + "\n", encoding="utf-8")
    (root / "docs/runtime-licenses.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--notices-only", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    notices(root)
    if not args.notices_only:
        output=args.output or root/'releases'
        result = package_release(root, args.runtime or root / "dist/lasermaker-agent", output)
        (output / "SHA256.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
