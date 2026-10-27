"""Opt-in real app checks; never start or transmit machine jobs."""
import os
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("LASERMAKER_LIVE_TESTS") != "1",
                                reason="requires local unlocked LaserMaker desktop")


def test_capture_is_bound_to_lasermaker_window(tmp_path):
    from lasermaker_agent.capture import capture_window
    from lasermaker_agent.windows_driver import WindowsDriver
    from PIL import Image, ImageStat
    state = WindowsDriver().inspect()
    path = tmp_path / "laser-only.png"
    result = capture_window(state["hwnd"], path)
    assert result["hwnd"] == state["hwnd"]
    image = Image.open(path)
    assert image.width > 500 and image.height > 400
    assert any(hi > lo for lo, hi in ImageStat.Stat(image).extrema)


def test_import_process_save_and_exact_reopen(tmp_path):
    import json
    import uuid
    from lasermaker_agent.geometry import export_svg
    from lasermaker_agent.sample import convert_legacy
    from lasermaker_agent.windows_driver import WindowsDriver
    source = json.loads((Path(__file__).parent / "fixtures/synthetic-six-part.json").read_text(encoding="utf-8"))
    basename = "agent-live-" + uuid.uuid4().hex[:10]
    svg = tmp_path / f"{basename}.svg"
    svg.write_text(export_svg(convert_legacy(source)), encoding="utf-8")
    imported = WindowsDriver().import_design(svg, expected_bounds=[10, 8, 262, 216])
    assert imported["selection_size_mm"] == [252, 208]
    process = WindowsDriver().set_process("#ff0000", {"mode": "score", "speed_mm_s": 101,
        "power_max_percent": 15, "power_min_percent": 13})
    assert process["verified"]["speed_mm_s"] == 101
    native = tmp_path / f"{basename}-saved-under-different-name.lcpx"
    saved = WindowsDriver().save_native(native)
    assert native.is_file() and saved["sha256"]
    reopened = WindowsDriver().reload_and_verify(native, expected_size=[252, 208])
    assert reopened["path"] == str(native.resolve())
    assert reopened["reopen_verified"] is True
    assert reopened["selection_size_mm"] == [252, 208]
    assert reopened["layers"][0]["speed_mm_s"] == 101
