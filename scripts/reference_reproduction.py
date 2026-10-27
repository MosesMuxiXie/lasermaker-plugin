"""Specific, auditable reconstruction of the five randomly selected reference plans.

This is a test-data builder, not a general SVG import tool. Only explicitly
reviewed source IDs are consumed; headers, logos and annotation paths stay out.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import warnings
from pathlib import Path

from shapely.geometry import Polygon, LineString
from shapely.ops import polygonize, unary_union
from shapely import affinity
from svgpathtools import Document, Path as SvgPath, Line

from lasermaker_agent.geometry import _mapped_path, contours, object_shape, preflight, export_svg, apply_ops
from lasermaker_agent.store import json_bytes


def polygon_d(poly):
    return ' '.join('M'+' L'.join(f'{x:.9f},{y:.9f}' for x,y in list(ring.coords)[:-1])+' Z'
                    for ring in [poly.exterior,*poly.interiors])


def nonzero_fill(path):
    """Resolve the selected authors' nonzero SVG fills at <=.005mm chord error."""
    rings=contours({'d':path.d()})
    faces=polygonize(unary_union([LineString(r) for r in rings]))
    def winding(point):
        x,y=point.x,point.y;count=0
        for ring in rings:
            for (ax,ay),(bx,by) in zip(ring,ring[1:]):
                cross=(bx-ax)*(y-ay)-(x-ax)*(by-ay)
                if ay<=y<by and cross>0:count+=1
                elif by<=y<ay and cross<0:count-=1
        return count
    return unary_union([face for face in faces if winding(face.representative_point())!=0])


def physical_mm(text):
    match=re.fullmatch(r'\s*([\d.eE+\-]+)(mm|cm|in|pt|px)?\s*',text)
    if not match:
        raise ValueError('UNSUPPORTED_PHYSICAL_UNIT')
    return float(match[1])*{'mm':1,'cm':10,'in':25.4,'pt':25.4/72,'px':25.4/96,None:25.4/96}[match[2]]


def source_paths(path,audit=None):
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='Replacing degenerate .*Arc.*')
        doc=Document(str(path))
        root=doc.tree.getroot()
        width,height=physical_mm(root.get('width')),physical_mm(root.get('height'))
        view=[float(v) for v in re.split(r'[\s,]+',root.get('viewBox',f'0 0 {width*96/25.4} {height*96/25.4}').strip())]
        if len(view)!=4 or min(view[2:])<=0:
            raise ValueError('INVALID_VIEWBOX')
        sx,sy=width/view[2],height/view[3]
        # SVG's default preserveAspectRatio is xMidYMid meet. Tiny rounding
        # differences in the author's viewBox must not turn circles into
        # anisotropic scale requests or silently distort the geometry.
        if root.get('preserveAspectRatio','xMidYMid meet') not in ('xMidYMid meet','xMidYMid'):
            raise ValueError('VIEWPORT_ALIGNMENT_REQUIRES_REVIEW')
        scale=min(sx,sy)
        offset=complex((width-view[2]*scale)/2,(height-view[3]*scale)/2)
        paths={}
        for p in doc.paths():
            oid=p.element.get('id')
            if not oid:
                continue
            # Root viewBox coordinates are converted after all ancestor transforms.
            normalized=_mapped_path(p,lambda q:q.translated(complex(-view[0],-view[1])).scaled(scale,origin=0j).translated(offset))
            subpaths=[]
            for sub_index,sub in enumerate(normalized.continuous_subpaths()):
                if sub.isclosed() and len(sub)>1 and isinstance(sub[-1],Line) and 0<abs(sub[-1].end-sub[-1].start)<=1e-9:
                    before=sub[-2].end;target=sub[0].start
                    sub=SvgPath(*sub[:-1]);sub[-1].end=target
                    if audit is not None:
                        audit.append({'source_id':oid,'source_subpath':sub_index,'operation':'snap_declared_closing_endpoint',
                                      'displacement_mm':abs(before-target),'limit_mm':1e-9})
                subpaths.extend(sub)
            normalized=SvgPath(*subpaths)
            # SVG rect rx=0 generates zero-radius arcs in svgpathtools. Only
            # zero-length Lines are removed; curved geometry is never refitted.
            normalized=SvgPath(*(s for s in normalized if not isinstance(s,Line) or s.end!=s.start))
            paths[oid]=normalized
    return paths,[width,height]


def reconstruct(path,cut_ids,engrave_ids):
    adjustments=[]
    paths,sheet=source_paths(path,adjustments)
    selected=cut_ids|engrave_ids
    if not selected<=paths.keys():
        raise ValueError('SOURCE_OBJECT_NOT_FOUND: '+str(sorted(selected-paths.keys())))
    objects=[];source_map=[]
    for sid in sorted(cut_ids):
        for i,p in enumerate(paths[sid].continuous_subpaths()):
            if not p.isclosed():
                raise ValueError('SOURCE_CUT_NOT_CLOSED: '+sid)
            oid=f'ref-{len(objects):04d}'
            obj={'id':oid,'role':'cut_outer','closed':True,'d':p.d()}
            objects.append(obj)
            source_map.append({'object_id':oid,'source_id':sid,'source_subpath':i,'role':'cut_outer'})
    polys=[object_shape(o) for o in objects]
    if any(not p.is_valid or p.area<=1e-8 for p in polys):
        raise ValueError('INVALID_SOURCE_CUT_POLYGON')
    parents=[]
    for i,poly in enumerate(polys):
        candidates=[j for j,q in enumerate(polys) if j!=i and q.area>poly.area and q.contains(poly)]
        parents.append(min(candidates,key=lambda j:polys[j].area) if candidates else None)
    def depth(i):
        return 0 if parents[i] is None else 1+depth(parents[i])
    for i,obj in enumerate(objects):
        inner=depth(i)%2==1
        obj['role']='cut_inner' if inner else 'cut_outer'
        parent=parents[i] if inner else i
        obj['part_id']='part-'+objects[parent]['id']
        source_map[i]['role']=obj['role']
    for sid in sorted(engrave_ids):
        p=paths[sid]
        if not all(s.isclosed() for s in p.continuous_subpaths()):
            raise ValueError('SOURCE_ENGRAVING_NOT_CLOSED: '+sid)
        shape=nonzero_fill(p)
        candidates=[o for o in objects if o['role']=='cut_outer' and object_shape(o).covers(shape)]
        if len(candidates)!=1:
            raise ValueError('ENGRAVING_STOCK_AMBIGUOUS: '+sid)
        pieces=[shape] if shape.geom_type=='Polygon' else list(shape.geoms)
        for index,piece in enumerate(pieces):
            obj={'id':f'ref-{len(objects):04d}','role':'engrave','closed':True,'d':polygon_d(piece),
                 'part_id':candidates[0]['part_id']}
            objects.append(obj)
            source_map.append({'object_id':obj['id'],'source_id':sid,'source_subpath':None,'role':'engrave',
                               'derivation':'nonzero_fill_polygonized','region_index':index,'chord_tolerance_mm':.005})
    return {'design':{'units':'mm','sheet_mm':sheet,'objects':objects},'source_map':source_map,
            'normalization_adjustments':[a for a in adjustments if a['source_id'] in selected]}


def reviewed_ids(path,key):
    """Explicit per-source choices recorded after looking at the supplied plans."""
    doc=Document(str(path));styles={}
    def visit(e,inherited):
        st=dict(inherited)
        st.update({k:e.get(k) for k in ('fill','stroke','display','visibility') if e.get(k) is not None})
        st.update(dict(s.split(':',1) for s in e.get('style','').split(';') if ':' in s))
        styles[id(e)]=st
        for child in e:visit(child,st)
    visit(doc.tree.getroot(),{})
    cuts=set();engravings=set()
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='Replacing degenerate .*Arc.*')
        for p in doc.paths():
            st=styles[id(p.element)];sid=p.element.get('id')
            if st.get('fill')=='none' and st.get('stroke') in ('#000000','#ff0000'):
                cuts.add(sid)
    if key=='tray':engravings={'path6077'}
    if key=='notebook':engravings={'rect4317-91-3-8-8','rect6234'}
    # Counts pin the reviewed drawings; an upstream change requires a new review.
    expected={'vases':70,'toggle':15,'tray':19,'clamps':12,'notebook':34}
    if len(cuts)!=expected[key]:raise ValueError('SOURCE_SELECTION_REVIEW_REQUIRED')
    return cuts,engravings


def candidate_repairs(design,key):
    operations=[];audit=[]
    objects={o['id']:o for o in design['objects']}
    if key=='vases':
        for index,(body,tab) in enumerate((('ref-0036','ref-0037'),('ref-0040','ref-0041'))):
            a,b=object_shape(objects[body]),object_shape(objects[tab])
            gap=b.bounds[1]-a.bounds[3]
            if not 0<gap<.005:raise ValueError('REVIEWED_VASE_GAP_CHANGED')
            dy=-gap-.00001
            operations.extend([{'op':'move','ids':[tab],'dx':0,'dy':dy},
                {'op':'boolean','ids':[body,tab],'mode':'union','result_id':f'vase-tab-joined-{index}'}])
            audit.append({'operation':'join_disconnected_vase_tab','body':body,'tab':tab,'dy_mm':dy,
                'original_gap_mm':gap,'curve_chord_tolerance_mm':.005,
                'interpretation':'Manufacturing candidate only: infer that the small tab should join its body; original is retained.'})
    if key=='notebook':
        for obj in design['objects']:
            if obj['role']!='engrave':continue
            shape=object_shape(obj)
            if shape.area<1e-8:
                b=shape.bounds;extent=max(b[2]-b[0],b[3]-b[1])
                if extent>=.01:raise ValueError('TINY_FILL_REGION_REQUIRES_REVIEW')
                operations.append({'op':'delete','ids':[obj['id']]})
                audit.append({'operation':'remove_microscopic_fill_fragment','object_id':obj['id'],
                              'area_mm2':shape.area,'max_extent_mm':extent,'bounds_mm':list(b)})
    return operations,audit


def prepare(root):
    candidates=root/'work/reference-candidates'
    output=root/'examples/reference-reproduction'
    output.mkdir(exist_ok=True)
    selection=json.loads((candidates/'selection.json').read_text(encoding='utf-8'))
    pool=json.loads((candidates/'pool.json').read_text(encoding='utf-8'))
    (output/'selection.json').write_bytes(json_bytes(selection))
    (output/'candidate-pool.json').write_bytes(json_bytes(pool))
    results=[]
    for key in selection['selected_ids']:
        folder=output/key;original=folder/'original';original.mkdir(parents=True,exist_ok=True)
        for suffix in ('svg','pdf','png'):
            source=candidates/f'{key}.{suffix}'
            if source.exists():shutil.copyfile(source,original/f'source.{suffix}')
        cuts,engrave=reviewed_ids(original/'source.svg',key)
        built=reconstruct(original/'source.svg',cuts,engrave)
        (folder/'source-map.json').write_bytes(json_bytes(built['source_map']))
        (folder/'normalization-adjustments.json').write_bytes(json_bytes(built['normalization_adjustments']))
        # Preserve the exact reconstruction separately, including original defects.
        (folder/'original-reconstruction.json').write_bytes(json_bytes(built['design']))
        original_report=preflight(built['design'])
        (folder/'original-preflight.json').write_bytes(json_bytes(original_report))
        operations,audit=candidate_repairs(built['design'],key)
        candidate=apply_ops(built['design'],operations) if operations else built['design']
        (folder/'design.json').write_bytes(json_bytes(candidate))
        (folder/'repair-operations.json').write_bytes(json_bytes(operations))
        (folder/'repair-audit.json').write_bytes(json_bytes(audit))
        report=preflight(candidate)
        (folder/'preflight.json').write_bytes(json_bytes(report))
        result={'id':key,'source':next(r for r in pool if r['id']==key),'cut_source_ids':sorted(cuts),
                'engrave_source_ids':sorted(engrave),'preflight':report,'original_preflight':original_report,
                'repair_audit':audit,
                'source_sha256':hashlib.sha256((original/'source.svg').read_bytes()).hexdigest()}
        results.append(result)
        print(json.dumps({'id':key,'objects':len(built['design']['objects']),'preflight':report['geometry_passed'],
                          'errors':report['errors'][:8]},ensure_ascii=False),flush=True)
    (output/'reconstruction.json').write_bytes(json_bytes(results))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare'])
    parser.parse_args();prepare(Path(__file__).resolve().parents[1])
