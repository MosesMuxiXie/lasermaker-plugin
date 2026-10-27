"""Volume interference check for this axis-aligned flat-pack fixture only.

Contacts are allowed. Polygons use the core's existing curve approximation;
this checks 39 wood plates, not the purchased dowel or assembly sequence.
"""
from itertools import combinations
from math import sqrt
from pathlib import Path

from shapely import affinity
from shapely.geometry import box, LineString

from lasermaker_agent.tank import build_tank, part_stock, mesh_part
from lasermaker_agent.store import json_bytes


def check_assembly(model):
    solids = []
    for part in model['parts']:
        t = part['transform']
        for column in range(3):
            assert sum(abs(t[i][column]) for i in range(3))==1, 'Only axis-aligned basis vectors supported'
        normal = next(i for i in range(3) if abs(t[i][2])>.5)
        axes = [i for i in range(3) if i!=normal]
        j,k = axes
        shape = affinity.affine_transform(part_stock(part),
            [t[j][0],t[j][1],t[k][0],t[k][1],t[j][3],t[k][3]])
        assert all(abs(v)<1000 for v in shape.bounds), 'Fixture exceeds integration bounds'
        lo,hi = sorted([t[normal][3],t[normal][3]+part['thickness_mm']*t[normal][2]])
        solids.append((part['id'],normal,axes,shape,lo,hi))
    def crop(solid,other):
        axes,shape=solid[2:4];axis=other[1];lo,hi=other[4:6]
        band=box(lo,-1000,hi,1000) if axes[0]==axis else box(-1000,lo,1000,hi)
        return shape.intersection(band)
    def levels(poly,index):
        if poly.is_empty or poly.area<1e-12:
            return []
        if poly.geom_type=='Polygon':
            return [p[index] for ring in (poly.exterior,*poly.interiors) for p in ring.coords]
        return [x for child in poly.geoms for x in levels(child,index)]
    def section(poly,index,value):
        line=LineString([(value,-1000),(value,1000)]) if index==0 else LineString([(-1000,value),(1000,value)])
        return poly.intersection(line).length
    collisions=[]
    for a,b in combinations(solids,2):
        if a[1]==b[1]:
            depth=max(0,min(a[5],b[5])-max(a[4],b[4]))
            volume=depth*a[3].intersection(b[3]).area
        else:
            common=next(i for i in range(3) if i not in (a[1],b[1]))
            pa,pb=crop(a,b),crop(b,a);ia,ib=a[2].index(common),b[2].index(common)
            breaks=sorted(set(levels(pa,ia)+levels(pb,ib)))
            volume=0
            for lo,hi in zip(breaks,breaks[1:]):
                mid=(lo+hi)/2;delta=(hi-lo)/(2*sqrt(3))
                volume+=(hi-lo)/2*sum(section(pa,ia,v)*section(pb,ib,v) for v in (mid-delta,mid+delta))
        if volume>1e-6:
            collisions.append({'parts':[a[0],b[0]],'overlap_mm3':round(volume,9)})
    volumes=[]
    for part in model['parts']:
        triangles,_=mesh_part(part)
        volume=sum(sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6 for a,b,c in triangles)
        volumes.append(volume)
    return {'parts':len(solids),'positive_volume_intersections':collisions,
            'all_signed_mesh_volumes_positive':bool(volumes) and min(volumes)>0,
            'intersection_threshold_mm3':1e-6,'physical_fit_verified':False,
            'coverage':'Axis-aligned wood plates only; source curve approximation; contacts allowed; dowel excluded.'}


if __name__=='__main__':
    result=check_assembly(build_tank())
    assert not result['positive_volume_intersections'] and result['all_signed_mesh_volumes_positive'],result
    path=Path(__file__).resolve().parent.parent/'examples/sherman-tank/assembly-check.json'
    path.write_bytes(json_bytes(result))
    print(json_bytes(result).decode())
