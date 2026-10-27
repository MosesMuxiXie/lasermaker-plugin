from pathlib import Path
import pytest

from lasermaker_agent.geometry import apply_ops, preflight, object_shape, export_svg


@pytest.mark.parametrize("text,font", [("Laser O", "C:/Windows/Fonts/arial.ttf"),
                                       ("激光", "C:/Windows/Fonts/msyh.ttc")])
def test_outlined_text_uses_exact_visible_height_and_top_left(text, font):
    if not Path(font).is_file():
        pytest.skip("requires this Windows font for the optional real-font check")
    doc = apply_ops({"units": "mm", "objects": []}, [{"op": "text", "id": "label", "text": text,
        "font_path": font, "height_mm": 4, "position": [10, 12]}])
    report = preflight(doc)
    assert report["geometry_passed"], report["errors"]
    left, top, right, bottom = report["bounds_mm"]
    assert [left, top, bottom-top] == pytest.approx([10, 12, 4], abs=1e-7)
    assert right > left
    assert "<text" not in export_svg(doc)
    with pytest.raises(ValueError, match="MISSING_GLYPHS"):
        apply_ops({"units": "mm", "objects": []}, [{"op": "text", "id": "missing", "text": chr(0x10ffff),
            "font_path": font, "height_mm": 4, "position": [10, 12]}])
