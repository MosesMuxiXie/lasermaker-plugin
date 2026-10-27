"""Stage B: reconstruct the original workstation from frozen engineering data.

Deliberately independent of the blueprint author/renderer. Native production
files are generated through the existing service, never by editing lcpx bytes.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path

from shapely.ops import unary_union
from .geometry import apply_ops, object_bounds, object_shape
from .tank import _transform


def load_frozen_spec(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'frozen-manifest.json').read_text(encoding='utf-8'))
    for name,sha in manifest['files'].items():
        path=folder/name
        if path.parent.resolve()!=folder.resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise ValueError('FROZEN_BLUEPRINT_HASH_MISMATCH: '+name)
    data=json.loads((folder/'dimensions.json').read_text(encoding='utf-8'))
    if data['schema_version']!=1 or data['units']!='mm' or data['thickness_mm']!=3:
        raise ValueError('UNSUPPORTED_WORKSTATION_SPEC')
    return data


def primitive(s,oid,role='cut_outer'):
    t=s['type'];obj={'id':oid,'role':role,'closed':True}
    if t=='circle':
        x,y,r=s['x'],s['y'],s['r']
        obj['d']=f'M{x-r},{y} A{r},{r} 0 1 0 {x+r},{y} A{r},{r} 0 1 0 {x-r},{y} Z'
    elif t in ('rect','roundrect'):
        x,y,w,h=s['x'],s['y'],s['w'],s['h'];r=s.get('r',0)
        if w<=0 or h<=0 or r<0 or r>min(w,h)/2:raise ValueError('INVALID_ENGINEERING_RECT')
        if not r:obj['points']=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
        else:obj['d']=(f'M{x+r},{y} L{x+w-r},{y} A{r},{r} 0 0 1 {x+w},{y+r} '
            f'L{x+w},{y+h-r} A{r},{r} 0 0 1 {x+w-r},{y+h} L{x+r},{y+h} '
            f'A{r},{r} 0 0 1 {x},{y+h-r} L{x},{y+r} A{r},{r} 0 0 1 {x+r},{y} Z')
    elif t=='polygon':obj['points']=copy.deepcopy(s['points'])
    elif t=='shoulder':
        pts=s['points'];d=f'M{pts[0][0]},{pts[0][1]}'
        for i,p in enumerate(pts[1:],1):
            if i==3:d+=' C'+' '.join(f'{q[0]},{q[1]}' for q in [*s['cubic_controls'],p])
            else:d+=f' L{p[0]},{p[1]}'
        obj['d']=d+' Z'
    else:raise ValueError('UNKNOWN_ENGINEERING_PRIMITIVE: '+t)
    return obj


def build_workstation(blueprint):
    source=load_frozen_spec(blueprint);parts=[]
    for p in source['parts']:
        pid=p['id'];body=primitive(p['body'],pid+'-outer')
        if p['tabs'] or p['notches']:
            solid=unary_union([object_shape(body),*[object_shape(primitive(s,'tab')) for s in p['tabs']]])
            if p['notches']:solid=solid.difference(unary_union([object_shape(primitive(s,'notch')) for s in p['notches']]))
            if solid.geom_type!='Polygon' or solid.interiors or not solid.is_valid:
                raise ValueError('DISCONNECTED_OR_INTERNAL_OUTLINE: '+pid)
            body={'id':pid+'-outer','role':'cut_outer','closed':True,'points':[list(q) for q in list(solid.exterior.coords)[:-1]]}
        objects=[body]+[primitive(s,pid+'-'+s['id'],'cut_inner') for s in p['holes']]
        for mark in p['marks']:
            if mark['type']=='line':objects.append({'id':pid+'-'+mark['id'],'role':'score','closed':False,'points':mark['points']})
            elif mark['type']=='text':
                glyphs=apply_ops({'units':'mm','objects':[]},[{'op':'text','id':pid+'-'+mark['id'],
                    'text':mark['text'],'position':[mark['x'],mark['y']],'height_mm':mark['height'],
                    'font_path':'C:/Windows/Fonts/arial.ttf','role':'engrave'}])['objects']
                # Font helper emits SVG (+Y down). Local engineering coordinates
                # are +Y up. Keep the declared visible bbox while fixing face.
                glyphs=apply_ops({'units':'mm','objects':glyphs},[{'op':'mirror','ids':[o['id'] for o in glyphs],
                    'axis':'y','origin':[0,mark['y']+mark['height']/2]}])['objects']
                objects.extend(glyphs)
            else:raise ValueError('UNKNOWN_ENGINEERING_MARK')
        for o in objects:o['part_id']=pid
        basis=source['assembly_planes'][p['plane']]
        parts.append({'id':pid,'name':p['name'],'group':p['group'],'objects':objects,'thickness_mm':3,
            'transform':_transform(p['origin_mm'],basis['u'],basis['v']),
            'attachment':'榫槽定位并胶合；可拆件按装配说明；五金待试装'})
    # Deterministic shelf packing, no rotation/mirroring of engraving text.
    width,height=source['sheet_mm'];margin=source['sheet_margin_mm'];gap=source['part_gap_mm']
    rows=[];sheets=[]
    for part in sorted(parts,key=lambda p:(-(object_bounds(p['objects'][0])[3]-object_bounds(p['objects'][0])[1]),p['id'])):
        b=object_bounds(part['objects'][0]);w,h=b[2]-b[0],b[3]-b[1]
        if w>width-2*margin or h>height-2*margin:raise ValueError('PART_EXCEEDS_TEST_SHEET')
        placement=None
        for n,levels in enumerate(rows):
            for row in levels:
                if h<=row['h']+1e-8 and row['x']+w<=width-margin+1e-8:
                    placement=(n,row['x'],row['y']);row['x']+=w+gap;break
            if placement:break
            y=margin if not levels else levels[-1]['y']+levels[-1]['h']+gap
            if y+h<=height-margin+1e-8:
                levels.append({'x':margin+w+gap,'y':y,'h':h});placement=(n,margin,y);break
        if placement is None:
            n=len(rows);rows.append([{'x':margin+w+gap,'y':margin,'h':h}]);placement=(n,margin,margin)
        part['sheet'],x,y=placement;part['sheet_position_mm']=[x,y]
    for n in range(len(rows)):
        doc={'units':'mm','sheet_mm':source['sheet_mm'],'minimum_web_mm':source['minimum_web_mm'],
             'material':{'name':'名义 3 mm 木板，待试切','thickness_mm':3,'kerf_mm':None,'fit_validated':False},'objects':[]}
        for p in parts:
            if p['sheet']!=n:continue
            b=object_bounds(p['objects'][0]);x,y=p['sheet_position_mm']
            ids=[o['id'] for o in p['objects']]
            moved=apply_ops({'units':'mm','objects':p['objects']},[
                {'op':'mirror','ids':ids,'axis':'y'},
                {'op':'move','ids':ids,'dx':x-b[0],'dy':y+b[3]}])
            doc['objects'].extend(moved['objects'])
        sheets.append(doc)
    return {'schema_version':1,'name':source['name'],'design_revision':source['design_revision'],
            'blueprint_sha256':hashlib.sha256((Path(blueprint)/'dimensions.json').read_bytes()).hexdigest(),
            'nominal_thickness_mm':3,'parts':parts,'sheets':sheets,'drawer_travel_mm':source['drawer_travel_mm'],
            'drawing_profile':'engineering-up-to-svg-down-v1',
            'physical_fit_verified':False,'machine_validated':False}


def drawer_state(model,travel):
    if not isinstance(travel,(int,float)) or not math.isfinite(travel) or not 0<=travel<=80:
        raise ValueError('DRAWER_TRAVEL_OUT_OF_RANGE')
    result=copy.deepcopy(model)
    for p in result['parts']:
        if p['group'].startswith('drawer-'):p['transform'][1][3]-=travel
    return result
