"""Strict, read-only PRJF diagnostics. Header hints are not effective process settings.

Field offsets credited to lasermaker-mcp-cli (MIT), commit
8a31a9593ac7990a06ccbe1789a2531b569e7c07. See THIRD_PARTY_NOTICES.md.
"""
import math
import struct
from pathlib import Path

from .store import file_hash

HEADER_FIELDS = {
    "CUT_SPEED": 0x24, "CUT_LASER1_POWER_MAX": 0x3C, "CUT_LASER1_POWER_MIN": 0x44,
    "CUT_LASER2_POWER_MAX": 0x54, "CUT_LASER2_POWER_MIN": 0x5C,
    "CUT_BRIDGES_LEN": 0x68, "SWEEP_POWER_MAX": 0x70, "SWEEP_SPEED": 0x78,
}


def read_native(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != ".lcpx" or not 346 <= path.stat().st_size <= 64*1024*1024:
        raise ValueError("INVALID_NATIVE_SIZE_OR_EXTENSION")
    with path.open("rb") as stream:
        header = stream.read(301)
    if header[:4] != b"PRJF":
        raise ValueError("INVALID_NATIVE_MAGIC")
    major, minor, layers = struct.unpack_from("<III", header, 4)
    if (major, minor) != (11, 12):
        raise ValueError("UNSUPPORTED_NATIVE_VERSION")
    if layers > 256:
        raise ValueError("INVALID_NATIVE_LAYER_COUNT")
    hints = {}
    for name, offset in HEADER_FIELDS.items():
        v = struct.unpack_from("<d", header, offset)[0]
        hints[name] = v if math.isfinite(v) else None
    return {"format": "PRJF", "version": [major, minor], "layer_count": layers,
            "size": path.stat().st_size, "sha256": file_hash(path), "path": str(path),
            "header_hints": hints, "geometry_authoritative": False,
            "warning": "Header hints may differ from effective per-object/per-layer settings. Verify in GUI."}
