import copy
import math
import xml.etree.ElementTree as ET

import pytest

from lasermaker_agent.geometry import apply_ops, preflight, export_svg, export_dxf


@pytest.mark.parametrize('sx,sy',[(-1,1),(1,-1),(1.7,.65),(-1.7,.65)])
def test_rotated_elliptical_arc_affine_scale_preserves_exact_curve(sx,sy):
    from svgpathtools import parse_path
    source={'units':'mm','objects':[{'id':'arc','role':'score','closed':False,'d':'M 3,7 A 9,4 33 1 1 15,12'}]}
    result=apply_ops(source,[{'op':'scale','ids':['arc'],'sx':sx,'sy':sy,'origin':[4,6]}])
    a=parse_path(source['objects'][0]['d'])[0];b=parse_path(result['objects'][0]['d'])[0]
    for t in (0,.125,.375,.75,1):
        expected=complex(4+(a.point(t).real-4)*sx,6+(a.point(t).imag-6)*sy)
        assert abs(b.point(t)-expected)<1e-7
    assert b.large_arc==a.large_arc
    assert b.sweep==(a.sweep if sx*sy>0 else not a.sweep)


def design():
    return {"units": "mm", "sheet_mm": [100, 80], "material": {"thickness_mm": 3, "kerf_mm": None},
            "objects": [{"id": "box", "part_id": "A", "role": "cut_outer", "closed": True,
                         "points": [[10, 10], [30, 10], [30, 20], [10, 20]]}]}


def test_duplicate_moves_copy_exactly_and_does_not_mutate_input():
    original = design()
    result = apply_ops(original, [{"op": "duplicate", "ids": ["box"], "dx": 25, "dy": 7,
                                  "suffix": "-copy"}])
    assert len(original["objects"]) == 1
    assert result["objects"][1]["points"] == [[35, 17], [55, 17], [55, 27], [35, 27]]
    assert result["objects"][1]["id"] == "box-copy"


def test_rotate_node_edit_and_reject_nonfinite_atomically():
    d = apply_ops(design(), [{"op": "rotate", "ids": ["box"], "degrees": 90, "origin": [10, 10]}])
    assert d["objects"][0]["points"][1] == pytest.approx([10, 30])
    d = apply_ops(d, [{"op": "node", "id": "box", "index": 0, "point": [9, 9]}])
    assert d["objects"][0]["points"][0] == [9, 9]
    with pytest.raises(ValueError):
        apply_ops(d, [{"op": "move", "ids": ["box"], "dx": math.nan, "dy": 0}])


def test_array_alignment_boolean_and_offset_geometry():
    d = apply_ops(design(), [{"op": "array", "ids": ["box"], "columns": 2, "rows": 2,
                              "dx": 30, "dy": 20}])
    assert len(d["objects"]) == 4
    assert d["objects"][-1]["points"][0] == [40, 30]
    d = apply_ops(design(), [{"op": "offset", "ids": ["box"], "distance": 1}])
    assert preflight(d)["bounds_mm"] == pytest.approx([9, 9, 31, 21])
    d = apply_ops(design(), [{"op": "add", "object": {"id": "overlap", "part_id": "B",
         "role": "cut_outer", "closed": True, "points": [[20, 10], [40, 10], [40, 20], [20, 20]]}},
         {"op": "boolean", "ids": ["box", "overlap"], "mode": "union", "result_id": "joined"}])
    assert len(d["objects"]) == 1
    assert preflight(d)["bounds_mm"] == [10, 10, 40, 20]


def test_preflight_finds_self_intersection_duplicate_cuts_and_unknown_material():
    d = design()
    d["objects"].append({**copy.deepcopy(d["objects"][0]), "id": "duplicate"})
    assert "DUPLICATE_CUT" in {v["code"] for v in preflight(d)["errors"]}
    d = design()
    d["objects"][0]["points"] = [[10, 10], [30, 20], [10, 20], [30, 10]]
    assert "INVALID_CONTOUR" in {v["code"] for v in preflight(d)["errors"]}
    assert preflight(design())["manufacturing_ready"] is False


def test_svg_scale_and_staged_export_are_physical_mm():
    root = ET.fromstring(export_svg(design()))
    assert root.get("width") == "100mm"
    path = root.find(".//{http://www.w3.org/2000/svg}path")
    assert "37.79527559" in path.get("d")
    assert "113.38582677" in path.get("d")
    assert "<path" not in export_svg(design(), roles=["score"])
    assert b"$INSUNITS" in export_dxf(design())


def test_bezier_and_text_are_outlined_and_security_rejects_markup():
    d = apply_ops(design(), [{"op": "add", "object": {"id": "curve", "role": "score",
                 "closed": False, "d": "M 10,30 C 15,20 25,40 30,30"}}])
    assert not preflight(d)["errors"]
    with pytest.raises(ValueError):
        apply_ops(design(), [{"op": "add", "object": {"id": "bad", "role": "score",
                   "d": "<script>alert(1)</script>", "closed": False}}])


def test_partial_part_duplication_keeps_the_retained_stock_relationship():
    d = apply_ops(design(), [{"op": "add", "object": {"id": "mark", "part_id": "A",
        "role": "score", "closed": False, "points": [[15, 15], [20, 15]]}}])
    d = apply_ops(d, [{"op": "duplicate", "ids": ["mark"], "dx": 0, "dy": 1}])
    assert preflight(d)["geometry_passed"], preflight(d)["errors"]
    assert d["objects"][-1]["part_id"] == "A"


def test_closed_flag_cannot_hide_an_open_svg_cut_and_misspelled_ops_are_rejected():
    with pytest.raises(ValueError, match="CLOSED"):
        apply_ops(design(), [{"op": "add", "object": {"id": "open-cut", "role": "cut_outer",
             "closed": True, "d": "M10,10 L20,10 L20,20"}}])
    with pytest.raises(ValueError, match="UNKNOWN_OPERATION_FIELD"):
        apply_ops(design(), [{"op": "move", "ids": ["box"], "dxs": 25, "dy": 0}])


def test_boolean_difference_uses_requested_operand_order():
    d = apply_ops(design(), [{"op": "duplicate", "ids": ["box"], "dx": 10, "dy": 0, "suffix": "-b"}])
    d = apply_ops(d, [{"op": "boolean", "ids": ["box-b", "box"], "mode": "difference", "result_id": "b-minus-a"}])
    assert preflight(d)["bounds_mm"] == [30, 10, 40, 20]


def test_compound_path_hole_survives_offset_and_preflight():
    from lasermaker_agent.geometry import object_shape
    d = {"units": "mm", "objects": [{"id": "ring", "part_id": "R", "role": "cut_outer",
         "closed": True, "d": "M0,0 L20,0 L20,20 L0,20 Z M5,5 L5,15 L15,15 L15,5 Z"}]}
    assert object_shape(d["objects"][0]).area == 300
    result = apply_ops(d, [{"op": "offset", "ids": ["ring"], "distance": 0}])
    assert {o["role"] for o in result["objects"]} == {"cut_inner", "cut_outer"}
    assert preflight(result)["geometry_passed"]


def test_offset_of_engraved_counter_never_creates_a_cut_layer():
    from lasermaker_agent.geometry import object_shape
    d = {"units": "mm", "objects": [{"id": "letter-o", "role": "engrave", "closed": True,
         "d": "M0,0 L20,0 L20,20 L0,20 Z M5,5 L5,15 L15,15 L15,5 Z"}]}
    result = apply_ops(d, [{"op": "offset", "ids": ["letter-o"], "distance": 0}])
    assert all(o["role"] == "engrave" for o in result["objects"])
    assert object_shape(result["objects"][0]).area == 300
@pytest.mark.parametrize('d',[
    'M 10,20 A 10,10 0 1 0 30,20 A 10,10 0 1 0 10,20 Z',
    'M 10,20 C 20,20 20,30 10,30 C 0,30 0,20 10,20 Z',
    'M 10,10 Q 15,5 20,10 Q 15,15 10,10 Z',
])
def test_svg_export_preserves_curved_closing_segment(d):
    import xml.etree.ElementTree as ET
    from svgpathtools import parse_path
    from lasermaker_agent.geometry import export_svg,object_shape,PIXELS_PER_MM,_mapped_path
    obj={'id':'curve','role':'cut_outer','closed':True,'d':d}
    exported=ET.fromstring(export_svg({'units':'mm','sheet_mm':[100,80],'objects':[obj]}))
    path=next(e for e in exported.iter() if e.tag.endswith('path'))
    actual=parse_path(path.attrib['d'])
    assert [type(s).__name__ for s in actual]==[type(s).__name__ for s in parse_path(d)]
    normalized=_mapped_path(actual,lambda p:p.scaled(1/PIXELS_PER_MM,origin=0j))
    result=object_shape({**obj,'d':normalized.d()})
    assert result.hausdorff_distance(object_shape(obj))<1e-7
    assert result.area==pytest.approx(object_shape(obj).area,abs=1e-7)


def test_closed_bezier_sampling_keeps_exact_endpoint_without_false_self_intersection():
    from lasermaker_agent.geometry import contours, preflight
    obj={'id':'circle','part_id':'circle','role':'cut_outer','closed':True,'d':
        'M325.2242 303.99611 C325.2242 320.68269 311.69706 334.20982 295.0105 334.20982 '
        'C278.32393 334.20982 264.79679 320.68269 264.79679 303.99611 '
        'C264.79679 287.30954 278.32393 273.7824 295.0105 273.7824 '
        'C311.69706 273.7824 325.2242 287.30954 325.2242 303.99611'}
    ring=contours(obj)[0]
    assert ring[-1]==ring[0]
    assert preflight({'units':'mm','objects':[obj]})['geometry_passed']

