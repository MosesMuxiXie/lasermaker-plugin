"""Independent acceptance constraints for the new original product."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

from lasermaker_agent.geometry import object_bounds, object_shape, preflight
from lasermaker_agent.tank import assembled_bounds, mesh_part, part_stock
from lasermaker_agent.workstation import build_workstation, load_frozen_spec, drawer_state

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from check_tank_assembly import check_assembly


class WorkstationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=build_workstation(ROOT/'examples/original-workstation/blueprint')

    def test_frozen_blueprint_and_exact_envelope(self):
        spec=load_frozen_spec(ROOT/'examples/original-workstation/blueprint')
        self.assertEqual(len(self.model['parts']),54)
        bounds=assembled_bounds(self.model)
        self.assertEqual([round(bounds[i+3]-bounds[i],5) for i in range(3)],[270,210,280])
        self.assertEqual(spec['drawer_travel_mm'],80)
        self.assertEqual(len({p['id'] for p in self.model['parts']}),54)

    def test_stock_manifold_volume_and_minimum_spacing(self):
        for p in self.model['parts']:
            self.assertTrue(part_stock(p).is_valid,p['id'])
            mesh,area=mesh_part(p)
            from collections import Counter
            edges=Counter(tuple(sorted((tuple(round(v,7) for v in a),tuple(round(v,7) for v in b))))
                for t in mesh for a,b in zip(t,[t[1],t[2],t[0]]))
            self.assertTrue(all(n==2 for n in edges.values()),p['id'])
            volume=sum(sum(a[i]*(b[(i+1)%3]*c[(i+2)%3]-b[(i+2)%3]*c[(i+1)%3]) for i in range(3))/6 for a,b,c in mesh)
            self.assertAlmostEqual(volume,area*3,places=3)
        for sheet in self.model['sheets']:
            report=preflight(sheet)
            self.assertTrue(report['geometry_passed'],report['errors'])
            outer=[object_shape(o) for o in sheet['objects'] if o['role']=='cut_outer']
            for i,a in enumerate(outer):
                for b in outer[:i]:self.assertGreaterEqual(a.distance(b)+.00001,6)

    def test_three_drawer_states_have_no_wood_interference(self):
        for distance in (0,40,80):
            report=check_assembly(drawer_state(self.model,distance))
            self.assertFalse(report['positive_volume_intersections'],(distance,report))
            self.assertTrue(report['all_signed_mesh_volumes_positive'])

    def test_fine_scale_and_hole_feature_dimensions_match_plan(self):
        ruler=next(p for p in self.model['parts'] if p['id']=='R01')
        ticks=sorted((o for o in ruler['objects'] if '-tick-' in o['id']),key=lambda o:o['id'])
        self.assertEqual(len(ticks),361)
        self.assertEqual([o['points'][0][0] for o in ticks],[-90+k*.5 for k in range(361)])
        specification=load_frozen_spec(ROOT/'examples/original-workstation/blueprint')
        for p,source in zip(self.model['parts'],specification['parts']):
            expected={h['id']:h for h in source['holes']}
            holes=[o for o in p['objects'] if o['role']=='cut_inner']
            self.assertEqual(len(holes),len(expected))
            for obj in holes:
                feature=expected[obj['id'][len(p['id'])+1:]];b=object_bounds(obj)
                if feature['type']=='circle':e=[feature['x']-feature['r'],feature['y']-feature['r'],feature['x']+feature['r'],feature['y']+feature['r']]
                else:e=[feature['x'],feature['y'],feature['x']+feature['w'],feature['y']+feature['h']]
                for a,v in zip(b,e):self.assertAlmostEqual(a,v,places=6)

    def test_travel_limit_rejected(self):
        for invalid in (-.1,80.01,float('nan')):
            with self.assertRaises(ValueError):drawer_state(self.model,invalid)

    def test_sheet_maps_engineering_up_to_svg_down_and_preserves_text_face(self):
        # The blueprint uses +localY up; SVG uses +Y down. Explicitly check
        # chirality rather than accepting the same aggregate bounding box.
        part=next(p for p in self.model['parts'] if p['id']=='B01')
        sheet=self.model['sheets'][part['sheet']]
        local=object_shape(part['objects'][0]);actual=object_shape(next(o for o in sheet['objects'] if o['id']=='B01-outer'))
        from shapely import affinity
        b=local.bounds;x,y=part['sheet_position_mm']
        expected=affinity.affine_transform(local,[1,0,0,-1,x-b[0],y+b[3]])
        self.assertLess(actual.hausdorff_distance(expected),1e-8)
        # Independent font outline built by the core in SVG orientation must
        # have the same face after the blueprint-to-local-to-sheet conversion.
        from lasermaker_agent.geometry import apply_ops
        glyph=apply_ops({'units':'mm','objects':[]},[{'op':'text','id':'font-reference','text':'B01',
            'position':[62,205],'height_mm':3,'font_path':'C:/Windows/Fonts/arial.ttf','role':'engrave'}])['objects'][0]
        rendered=next(o for o in sheet['objects'] if o['id']=='B01-label-0-0')
        expected_glyph=affinity.translate(object_shape(glyph),xoff=x-b[0],yoff=y+b[3]-2*205-3)
        self.assertLess(object_shape(rendered).hausdorff_distance(expected_glyph),1e-8)


if __name__=='__main__':unittest.main()
