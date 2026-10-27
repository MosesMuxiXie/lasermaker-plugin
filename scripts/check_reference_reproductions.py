"""Measure source->raw reconstruction and candidate->actual SVG/DXF separately."""
import argparse
import json
from pathlib import Path

import ezdxf
from shapely import hausdorff_distance
from shapely.geometry import LineString
from shapely.ops import unary_union
from svgpathtools import parse_path

from reference_reproduction import source_paths,nonzero_fill
from lasermaker_agent.geometry import object_shape,contours,TOLERANCE_MM
from lasermaker_agent.store import json_bytes


def wire(obj):
    return unary_union([LineString(c) for c in contours(obj)])


def check(folder,require_delivery):
    raw=json.loads((folder/'original-reconstruction.json').read_text(encoding='utf-8'))
    candidate=json.loads((folder/'design.json').read_text(encoding='utf-8'))
    mapping=json.loads((folder/'source-map.json').read_text(encoding='utf-8'))
    paths,_=source_paths(folder/'original/source.svg')
    raw_objects={o['id']:o for o in raw['objects']}
    source_deviation=[];source_curved_segments=0
    for entry in mapping:
        obj=raw_objects[entry['object_id']]
        if obj['role']=='engrave':continue
        source=paths[entry['source_id']].continuous_subpaths()[entry['source_subpath']]
        rebuilt=parse_path(obj['d'])
        assert [type(s) for s in source]==[type(s) for s in rebuilt],obj['id']
        for a,b in zip(source,rebuilt):
            if type(a).__name__!='Line':source_curved_segments+=1
            source_deviation.extend(abs(a.point(t)-b.point(t)) for t in (0,.125,.25,.5,.75,.875,1))
    fill_checks=[]
    for sid in sorted({e['source_id'] for e in mapping if e['role']=='engrave'}):
        source=nonzero_fill(paths[sid])
        rebuilt=unary_union([object_shape(raw_objects[e['object_id']]) for e in mapping if e['source_id']==sid])
        deviation=float(hausdorff_distance(source.boundary,rebuilt.boundary))
        area=source.symmetric_difference(rebuilt).area
        assert deviation<=TOLERANCE_MM and area<=max(1e-7,source.length*TOLERANCE_MM)
        fill_checks.append({'source_id':sid,'boundary_deviation_mm':deviation,'symmetric_difference_mm2':area,
                            'fill_rule':'nonzero','curve_chord_tolerance_mm':.005})
    assert max(source_deviation,default=0)<=TOLERANCE_MM
    old_cuts={o['id']:o for o in raw['objects'] if o['role'].startswith('cut')}
    new_cuts={o['id']:o for o in candidate['objects'] if o['role'].startswith('cut')}
    repairs=json.loads((folder/'repair-audit.json').read_text(encoding='utf-8'))
    cut_change=0.0
    if old_cuts!=new_cuts:
        assert folder.name=='vases','UNREVIEWED_CUT_CHANGE'
        changed_old=set();changed_new=set()
        for index,repair in enumerate(repairs):
            before=unary_union([wire(old_cuts[repair[k]]) for k in ('body','tab')])
            oid=f'vase-tab-joined-{index}';after=wire(new_cuts[oid])
            cut_change=max(cut_change,float(hausdorff_distance(before,after,densify=.25)))
            changed_old.update(repair[k] for k in ('body','tab'));changed_new.add(oid)
        assert {k:v for k,v in old_cuts.items() if k not in changed_old}=={k:v for k,v in new_cuts.items() if k not in changed_new}
    report={'id':folder.name,'source_cut_curve_sample_deviation_mm':max(source_deviation,default=0),
        'source_cut_curved_segments_preserved':source_curved_segments,'source_fill_checks':fill_checks,
        'raw_reconstruction_source_checks_passed':True,'candidate_cutline_change_from_raw_mm':cut_change,
        'candidate_is_unmodified_cutline_reproduction':cut_change<=TOLERANCE_MM,
        'repairs':repairs,
        'svg_dxf_roundtrip_passed':False,'native_verification':'not_checked',
        'accuracy_scope':'Numerical vector reconstruction only; no claim of machine/assembly accuracy or per-node lcpx parsing.'}
    if not (folder/'delivery.json').exists():
        assert not require_delivery,'DELIVERY_NOT_READY: '+folder.name
    else:
        delivery=json.loads((folder/'delivery.json').read_text(encoding='utf-8'))
        exported,_=source_paths(folder/delivery['artifacts']['svg'])
        assert set(exported)=={o['id'] for o in candidate['objects']}
        deviations=[]
        for obj in candidate['objects']:
            readback={k:v for k,v in obj.items() if k!='points'};readback['d']=exported[obj['id']].d()
            a,b=object_shape(obj),object_shape(readback)
            deviation=float(hausdorff_distance(a,b))
            assert deviation<=TOLERANCE_MM,obj['id']
            deviations.append(deviation)
        entities=list(ezdxf.readfile(folder/delivery['artifacts']['dxf']).modelspace())
        expected=[(o,c) for o in candidate['objects'] for c in contours(o)]
        assert len(entities)==len(expected)
        dxf_deviation=[]
        for entity,(obj,points) in zip(entities,expected):
            assert entity.dxftype()=='LWPOLYLINE' and entity.closed and entity.dxf.layer==obj['role']
            actual=[(p[0],-p[1]) for p in entity.get_points()]
            if actual[0]!=actual[-1]:actual.append(actual[0])
            deviation=float(hausdorff_distance(LineString(points),LineString(actual)))
            assert deviation<=TOLERANCE_MM,obj['id']
            dxf_deviation.append(deviation)
        native=json.loads((folder/'native-verification.json').read_text(encoding='utf-8'))
        assert native['reopened']['reopen_verified'] and native['native_current']
        report.update(svg_dxf_roundtrip_passed=True,svg_objects_checked=len(exported),dxf_contours_checked=len(entities),
            svg_max_deviation_mm=max(deviations),dxf_max_deviation_mm=max(dxf_deviation),
            dxf_metric_scope='serialization against adaptively sampled contours; analytical-curve chord budget is separate',
            dxf_chord_error_target_mm=.005,
            native_verification='saved_reopened_dimensions_and_layer_parameters_read_back',
            native_size_mm=native['expected_selection_mm'])
    (folder/'comparison.json').write_bytes(json_bytes(report))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--require-delivery',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'examples/reference-reproduction'
    selection=json.loads((root/'selection.json').read_text(encoding='utf-8'))
    reports=[]
    for name in selection['selected_ids']:
        reports.append(check(root/name,args.require_delivery))
        print(json.dumps({k:v for k,v in reports[-1].items() if k in ('id','source_cut_curve_sample_deviation_mm',
            'candidate_cutline_change_from_raw_mm','svg_dxf_roundtrip_passed','svg_max_deviation_mm')},ensure_ascii=False),flush=True)
    (root/'comparison.json').write_bytes(json_bytes(reports))
