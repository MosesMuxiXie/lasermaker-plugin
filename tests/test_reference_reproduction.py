import importlib.util
from pathlib import Path

import pytest


def load_script():
    path=Path(__file__).resolve().parents[1]/'scripts/reference_reproduction.py'
    assert path.exists(), 'Reference reconstruction implementation is missing'
    spec=importlib.util.spec_from_file_location('reference_reproduction',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_physical_units_and_parent_transforms_have_literal_mm_bounds(tmp_path):
    mod=load_script()
    path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 400 200">'
        '<g transform="translate(10,20)" fill="none" stroke="#000000">'
        '<rect id="panel" x="10" y="20" width="10" height="20" rx="0"/></g></svg>')
    result=mod.reconstruct(path,cut_ids={'panel'},engrave_ids=set())
    assert result['design']['sheet_mm']==[40,20]
    from lasermaker_agent.geometry import object_bounds,preflight
    assert object_bounds(result['design']['objects'][0])==pytest.approx([2,4,3,6])
    assert preflight(result['design'])['geometry_passed']
    assert result['source_map'][0]['source_id']=='panel'


def test_px_scale_and_holes_are_rebuilt_without_scaling_dimensions(tmp_path):
    mod=load_script();path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="960" height="480" viewBox="0 0 960 480">'
        '<path id="plate" d="M10 10 H110 V70 H10 Z M30 30 H50 V50 H30 Z"/>'
        '<path id="logo" d="M200 100 H300 V200 H200 Z"/></svg>')
    result=mod.reconstruct(path,cut_ids={'plate'},engrave_ids=set())
    objects=result['design']['objects']
    assert result['design']['sheet_mm']==pytest.approx([254,127])
    assert len(objects)==2
    assert {o['role'] for o in objects}=={'cut_outer','cut_inner'}
    assert len({o['part_id'] for o in objects})==1
    from lasermaker_agent.geometry import object_bounds
    outer=next(o for o in objects if o['role']=='cut_outer')
    assert object_bounds(outer)==pytest.approx([2.6458333333333,2.6458333333333,29.104166666667,18.520833333333])


def test_missing_explicit_source_object_fails_visibly(tmp_path):
    mod=load_script();path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"><path id="a" d="M0 0 H1 V1 H0 Z"/></svg>')
    with pytest.raises(ValueError,match='SOURCE_OBJECT_NOT_FOUND'):
        mod.reconstruct(path,cut_ids={'typo'},engrave_ids=set())


def test_tiny_nonzero_closing_line_is_preserved(tmp_path):
    mod=load_script();path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10">'
        '<path id="a" d="M1 0 L2 0 L2 2 L1.0000000000001 0 Z"/></svg>')
    paths,_=mod.source_paths(path)
    assert paths['a'].isclosed()


def test_rounded_viewbox_size_keeps_circle_arcs_and_uniform_scale(tmp_path):
    mod=load_script();path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0 0 20.0000001 10">'
        '<circle id="a" cx="5" cy="5" r="2"/></svg>')
    result=mod.reconstruct(path,cut_ids={'a'},engrave_ids=set())
    from lasermaker_agent.geometry import object_bounds
    from svgpathtools import parse_path,Arc
    obj=result['design']['objects'][0]
    assert object_bounds(obj)==pytest.approx([3,3,7,7],abs=1e-7)
    assert all(isinstance(s,Arc) for s in parse_path(obj['d']))


def test_svg_default_meet_letterboxes_a_different_viewport_aspect(tmp_path):
    mod=load_script();path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 400 400">'
        '<rect id="a" x="100" y="100" width="100" height="100"/></svg>')
    result=mod.reconstruct(path,cut_ids={'a'},engrave_ids=set())
    from lasermaker_agent.geometry import object_bounds
    assert object_bounds(result['design']['objects'][0])==pytest.approx([15,5,20,10])


def test_nonzero_engraving_fill_preserves_overlaps_instead_of_xor(tmp_path):
    mod=load_script();path=tmp_path/'original.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10">'
        '<path id="plate" d="M0 0 H10 V10 H0 Z"/>'
        '<path id="art" d="M1 1 H3 V3 H1 Z M2 1 H4 V3 H2 Z"/></svg>')
    result=mod.reconstruct(path,cut_ids={'plate'},engrave_ids={'art'})
    from lasermaker_agent.geometry import object_shape,preflight
    assert sum(object_shape(o).area for o in result['design']['objects'] if o['role']=='engrave')==pytest.approx(6)
    assert preflight(result['design'])['geometry_passed']


def test_reviewed_vase_gap_repair_joins_tabs_with_a_recorded_subtolerance_move():
    mod=load_script()
    objects=[]
    for x,body,tab in ((0,'ref-0036','ref-0037'),(20,'ref-0040','ref-0041')):
        for oid,points in ((body,[[x,0],[x+10,0],[x+10,10],[x,10]]),
                           (tab,[[x+2,10.002],[x+5.2,10.002],[x+5.2,13.2],[x+2,13.2]])):
            objects.append({'id':oid,'part_id':oid,'role':'cut_outer','closed':True,'points':points})
    design={'units':'mm','sheet_mm':[50,30],'objects':objects}
    ops,audit=mod.candidate_repairs(design,'vases')
    from lasermaker_agent.geometry import apply_ops,preflight
    fixed=apply_ops(design,ops)
    assert len(fixed['objects'])==2 and preflight(fixed)['geometry_passed']
    assert len(audit)==2 and all(0<abs(a['dy_mm'])<.01 for a in audit)
