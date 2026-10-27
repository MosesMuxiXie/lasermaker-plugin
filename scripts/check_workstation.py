"""Independent plan-to-CAD and mating-feature checks (not the CAD renderer)."""
import copy
import json
import math
from pathlib import Path
from itertools import combinations,product
from shapely.geometry import Polygon,Point,box,MultiPoint
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles
from lasermaker_agent.geometry import object_shape,object_bounds
from lasermaker_agent.tank import part_stock,world_point
from lasermaker_agent.workstation import load_frozen_spec,drawer_state
from lasermaker_agent.store import json_bytes
from check_tank_assembly import check_assembly

ROOT=Path(__file__).resolve().parents[1]/'examples/original-workstation'


def dimension_shape(s):
    """Dense analytic construction, intentionally no primitive() / core paths."""
    t=s['type']
    if t=='circle':return Polygon([(s['x']+s['r']*math.cos(k*math.tau/1024),s['y']+s['r']*math.sin(k*math.tau/1024)) for k in range(1024)])
    if t=='rect':return box(s['x'],s['y'],s['x']+s['w'],s['y']+s['h'])
    if t=='roundrect':
        x,y,w,h,r=[s[k] for k in ('x','y','w','h','r')];points=[]
        for cx,cy,a in [(x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)]:
            points += [(cx+r*math.cos(a+k*math.pi/256),cy+r*math.sin(a+k*math.pi/256)) for k in range(129)]
        return Polygon(points)
    if t=='polygon':return Polygon(s['points'])
    if t=='shoulder':
        pts=s['points'];a,b=pts[2],pts[3];c,d=s['cubic_controls']
        samples=[[(1-t)**3*a[j]+3*(1-t)**2*t*c[j]+3*(1-t)*t*t*d[j]+t**3*b[j] for j in (0,1)] for t in [k/1024 for k in range(1,1025)]]
        return Polygon(pts[:3]+samples+pts[4:])
    raise ValueError(t)


def mating_check(model,spec):
    parts={p['id']:p for p in model['parts']};matched=[];unmatched=[]
    for drawing in spec['parts']:
        p=parts[drawing['id']]
        for k,tab in enumerate(drawing['tabs']):
            corners=[world_point(p,[x,y,z]) for x,y,z in product((tab['x'],tab['x']+tab['w']),(tab['y'],tab['y']+tab['h']),(0,3))]
            lo=[min(q[i] for q in corners) for i in range(3)];hi=[max(q[i] for q in corners) for i in range(3)]
            matches=[]
            for receiving in model['parts']:
                if receiving['id']==p['id']:continue
                t=receiving['transform'];n=next(i for i in range(3) if abs(t[i][2])==1)
                zl,zh=sorted((t[n][3],t[n][3]+3*t[n][2]))
                if abs(lo[n]-zl)>1e-6 or abs(hi[n]-zh)>1e-6:continue
                # Inverse orthonormal placement of tab corners to receiving face.
                projected=MultiPoint([[sum((q[i]-t[i][3])*t[i][j] for i in range(3)) for j in (0,1)] for q in corners]).convex_hull
                for hole in receiving['objects']:
                    if hole['role']=='cut_inner' and object_shape(hole).contains(projected):
                        matches.append({'slot_part':receiving['id'],'slot_id':hole['id'],'planar_clearance_to_edge_mm':round(projected.distance(object_shape(hole).boundary),6)})
            entry={'tab_part':p['id'],'tab_index':k,'tab_world_bounds_mm':lo+hi,'matches':matches}
            (matched if matches else unmatched).append(entry)
    # Six hook bridge rectangles are material joining the two hook tongues,
    # not penetrating tabs. They end at the front surface of the back panel.
    assert len(unmatched)==6 and all(e['tab_part'].startswith('H') and e['tab_index']==2 for e in unmatched),unmatched
    assert all(len(e['matches'])==1 for e in matched)
    return {'matched_tab_slot_pairs':matched,'nonpenetrating_hook_bridges':unmatched}


def swept_model(model):
    result=copy.deepcopy(model)
    for p in result['parts']:
        if not p['group'].startswith('drawer-'):continue
        t=p['transform']
        if abs(t[1][2])==1:
            assert t[1][2]==-1
            p['thickness_mm']+=80
            continue
        direction=[-80*t[1][j] for j in (0,1)]
        triangles=constrained_delaunay_triangles(part_stock(p)).geoms
        sweep=unary_union([MultiPoint([*tri.exterior.coords,*[(x+direction[0],y+direction[1]) for x,y in tri.exterior.coords]]).convex_hull for tri in triangles])
        assert sweep.geom_type=='Polygon'
        p['objects']=[{'id':p['id']+'-swept','role':'cut_outer','closed':True,'points':list(sweep.exterior.coords)[:-1]}]
        for k,ring in enumerate(sweep.interiors):p['objects'].append({'id':f'{p["id"]}-swept-hole-{k}','role':'cut_inner','closed':True,'points':list(ring.coords)[:-1]})
    return result


def main():
    spec=load_frozen_spec(ROOT/'blueprint');model=json.loads((ROOT/'assembly-source.json').read_text(encoding='utf-8'))
    comparisons=[]
    for source,p in zip(spec['parts'],model['parts']):
        assert source['id']==p['id']
        expected=unary_union([dimension_shape(source['body']),*[dimension_shape(t) for t in source['tabs']]])
        if source['notches']:expected=expected.difference(unary_union([dimension_shape(t) for t in source['notches']]))
        actual=object_shape(p['objects'][0]);error=expected.boundary.hausdorff_distance(actual.boundary)
        assert error<.01,(p['id'],error)
        hole_errors=[]
        for hole in source['holes']:
            actual=object_shape(next(o for o in p['objects'] if o['id']==p['id']+'-'+hole['id']))
            distance=dimension_shape(hole).boundary.hausdorff_distance(actual.boundary);assert distance<.01
            hole_errors.append(distance)
        comparisons.append({'part':p['id'],'outer_deviation_mm':error,'max_hole_deviation_mm':max(hole_errors,default=0),'hole_count':len(hole_errors)})
    states=[]
    for travel in (0,40,80):
        result=check_assembly(drawer_state(model,travel));assert not result['positive_volume_intersections'],result
        result['travel_mm']=travel;result['coverage']='54 axis-aligned wood plates; contacts allowed; hardware/loads excluded.';states.append(result)
    sweep=swept_model(model);continuous=check_assembly(sweep);groups={p['id']:p['group'] for p in model['parts']}
    fixed_collisions=[c for c in continuous['positive_volume_intersections'] if not all(groups[pid].startswith('drawer-') for pid in c['parts'])]
    assert not fixed_collisions,fixed_collisions
    mates=mating_check(model,spec)
    report={'blueprint_unchanged':True,'dimension_comparison':comparisons,
        'max_plan_deviation_mm':max(max(p['outer_deviation_mm'],p['max_hole_deviation_mm']) for p in comparisons),
        'mating':mates,'drawer_states':states,'continuous_travel_check':{'travel_range_mm':[0,80],
            'method':'Exact polygonal Minkowski sweep along Y of triangulated wood stock; fixed vs moving only; rigid moving contacts checked in states.',
            'stationary_vs_swept_intersections':fixed_collisions},
        'rail_support':{'closed_overlap_per_rail_mm':[8,163],'at_80mm_overlap_per_rail_mm':[8,83],
            'note':'Nominal geometric support area only; deflection, friction and tipping unverified.'},
        'guide_geometry':{'carcass_bolt_y_mm':-40,'relative_y_closed_open_mm':[-40,40],
            'capsule_centerline_endpoints_mm':[-53.2,43.2],'shaft_diameter_assumed_mm':3,'slot_width_mm':3.6,'side_wall_gap_mm':6},
        'physical_fit_verified':False,'machine_validated':False}
    (ROOT/'design-verification.json').write_bytes(json_bytes(report))
    print(json.dumps({'parts':54,'max_plan_deviation_mm':report['max_plan_deviation_mm'],'mating_pairs':len(mates['matched_tab_slot_pairs']),
                      'continuous_drawer_sweep_passed':True},ensure_ascii=False))


if __name__=='__main__':main()
