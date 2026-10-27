"""Read generated SVGs back in mm and compare every object against its source."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from svgpathtools import parse_path
from lasermaker_agent.geometry import object_shape,PIXELS_PER_MM,_mapped_path,TOLERANCE_MM
from lasermaker_agent.store import json_bytes


def main():
    root=Path(__file__).resolve().parent.parent
    reports=[]
    for name in ('creator-cockpit','slot-coupon','sherman-tank/sheet-1','sherman-tank/sheet-2','engraving-modes'):
        folder=root/'examples'/name
        state=json.loads((folder/'project/project.json').read_text(encoding='utf-8'))
        index=json.loads((folder/'delivery.json').read_text(encoding='utf-8'))
        svg=ET.parse(folder/index['artifacts']['svg'])
        paths={e.attrib['id']:e.attrib['d'] for e in svg.iter() if e.tag.endswith('path')}
        assert set(paths)=={o['id'] for o in state['design']['objects']},name
        distances=[]
        for obj in state['design']['objects']:
            path=parse_path(paths[obj['id']])
            if 'd' in obj:
                assert [type(s).__name__ for s in path]==[type(s).__name__ for s in parse_path(obj['d'])],obj['id']
            normalized=_mapped_path(path,lambda p:p.scaled(1/PIXELS_PER_MM,origin=0j))
            other={k:v for k,v in obj.items() if k!='points'};other['d']=normalized.d()
            expected,actual=object_shape(obj),object_shape(other)
            distance=actual.hausdorff_distance(expected)
            assert distance<=TOLERANCE_MM,obj['id']
            assert abs(actual.area-expected.area)<=max(1e-6,expected.length*TOLERANCE_MM),obj['id']
            distances.append(distance)
        reports.append({'project':name,'objects_checked':len(paths),'max_shape_deviation_mm':max(distances),
                        'all_curved_segment_types_preserved':True,'passed':True})
    (root/'work/svg-roundtrip-verification.json').write_bytes(json_bytes(reports))
    print(json.dumps(reports,ensure_ascii=False))


if __name__=='__main__':
    main()
