import json
from pathlib import Path
import pytest
from lasermaker_agent.sample import convert_legacy, coupon_design
from lasermaker_agent.geometry import preflight

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-six-part.json"


def test_synthetic_legacy_format_dimensions_and_coupon():
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert source['synthetic_fixture'] is True
    design = convert_legacy(source)
    report = preflight(design)
    assert report["geometry_passed"], report["errors"]
    assert report["part_count"] == 6
    assert report["bounds_mm"] == pytest.approx([10, 8, 262, 216], abs=.001)
    assert design["assembly_envelope_mm"] == [130, 110, 125]
    fit = coupon_design(source)
    assert fit["slot_widths_mm"] == [2.7, 2.8, 2.9, 3, 3.1, 3.2, 3.3]
    assert preflight(fit)["geometry_passed"]
def test_stage_registration_uses_geometry_center_and_marks_empty_stages():
    from lasermaker_agent.sample import registration_plan
    d={'units':'mm','sheet_mm':[200,100],'objects':[
        {'id':'outer','role':'cut_outer','closed':True,'points':[[10,20],[110,20],[110,80],[10,80]]},
        {'id':'mark','role':'score','closed':False,'points':[[20,30],[40,40]]}]}
    plan=registration_plan(d)
    assert plan['full_source_center_mm']==[60,50]
    score=next(s for s in plan['stages'] if s['role']=='score')
    assert score['source_center_delta_mm']==[-30,-15]
    assert next(s for s in plan['stages'] if s['role']=='engrave')['empty']
    assert not plan['gui_and_machine_registration_verified']


