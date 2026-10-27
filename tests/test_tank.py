from collections import Counter

import pytest

from shapely.geometry import MultiPoint
from lasermaker_agent.geometry import preflight, object_shape
from lasermaker_agent.tank import build_tank, mesh_part, assembled_bounds, world_point


def test_tank_parts_and_sheets_are_reproducible_and_have_real_mating_joinery():
    model = build_tank()
    assert model == build_tank()
    assert len(model['sheets']) == 2
    assert len(model['parts']) >= 30
    ids = [p['id'] for p in model['parts']]
    assert len(ids) == len(set(ids))
    for sheet in model['sheets']:
        report = preflight(sheet)
        assert report['geometry_passed'], report['errors']
    assert assembled_bounds(model) == pytest.approx([-88, -45, 0, 110, 45, 78], abs=.01)
    for joint in model['joints']:
        assert joint['clearance_mm'] == pytest.approx(.1)
        assert joint['slot_width_mm'] == pytest.approx(3.1)
        assert joint['tab_width_mm'] == pytest.approx(3)
        assert joint['tab_part'] in ids and joint['slot_part'] in ids
        tab = next(p for p in model['parts'] if p['id']==joint['tab_part'])
        plate = next(p for p in model['parts'] if p['id']==joint['slot_part'])
        x0, y0, x1, y1 = joint['tab_rect_local_mm']
        world = [world_point(tab, [x, y, z]) for x in (x0, x1) for y in (y0, y1) for z in (0, 3)]
        projection = MultiPoint([p[:2] for p in world]).convex_hull
        hole = object_shape(next(o for o in plate['objects'] if o['id']==joint['slot_id']))
        assert hole.contains(projection), joint
        assert [min(p[2] for p in world), max(p[2] for p in world)] == pytest.approx(
            [plate['transform'][2][3], plate['transform'][2][3]+3])
    with pytest.raises(ValueError, match='REDESIGN_JOINERY'):
        build_tank(thickness_mm=4)


def test_each_extruded_part_is_a_closed_solid_with_preserved_holes():
    model = build_tank()
    for part in model['parts']:
        triangles, area = mesh_part(part)
        edges = Counter()
        volume = 0
        for a, b, c in triangles:
            for p, q in ((a, b), (b, c), (c, a)):
                p, q = tuple(round(v, 7) for v in p), tuple(round(v, 7) for v in q)
                edges[tuple(sorted((p, q)))] += 1
            volume += sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6
        assert set(edges.values()) == {2}, part['id']
        assert volume == pytest.approx(area*3, abs=1e-5), part['id']
    assert any(o['role'] == 'cut_inner' for p in model['parts'] for o in p['objects'])


@pytest.mark.parametrize('perpendicular',[False,True])
def test_interference_check_detects_four_cubic_mm_and_allows_touching(perpendicular):
    from scripts.check_tank_assembly import check_assembly
    import copy
    a={'id':'a','thickness_mm':3,'objects':[{'id':'outer','role':'cut_outer','closed':True,
        'points':[[0,0],[2,0],[2,2],[0,2]]}],
        'transform':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}
    b=copy.deepcopy(a);b['id']='b'
    b['transform']=([[0,0,1,1],[1,0,0,0],[0,1,0,0],[0,0,0,1]] if perpendicular else
                    [[1,0,0,1],[0,1,0,0],[0,0,1,1],[0,0,0,1]])
    result=check_assembly({'parts':[a,b]})
    assert result['positive_volume_intersections']==[{'parts':['a','b'],'overlap_mm3':4.0}]
    b['transform'][0][3]=2
    assert not check_assembly({'parts':[a,b]})['positive_volume_intersections']
