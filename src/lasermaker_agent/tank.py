"""Original flat-pack tank fixture; sheets and 3-D solids share the same contours."""
from __future__ import annotations

import copy
import math

from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .geometry import apply_ops, object_bounds, object_shape


def _poly(oid, points, role='cut_outer'):
    return {'id': oid, 'role': role, 'closed': True, 'points': [list(p) for p in points]}


def _rect(oid, x, y, w, h, role='cut_inner'):
    return _poly(oid, [(x, y), (x+w, y), (x+w, y+h), (x, y+h)], role)


def _ellipse(oid, cx, cy, rx, ry, role='cut_outer'):
    return {'id': oid, 'role': role, 'closed': True,
            'd': f'M {cx-rx},{cy} A {rx},{ry} 0 1 0 {cx+rx},{cy} A {rx},{ry} 0 1 0 {cx-rx},{cy} Z'}


def _union_outline(oid, polygons):
    shape = unary_union(polygons)
    assert shape.geom_type == 'Polygon' and not shape.interiors
    return _poly(oid, list(shape.exterior.coords)[:-1])


def _transform(origin, u, v):
    w = [u[(i+1)%3]*v[(i+2)%3]-u[(i+2)%3]*v[(i+1)%3] for i in range(3)]
    return [[u[i], v[i], w[i], origin[i]] for i in range(3)] + [[0, 0, 0, 1]]


def world_point(part, p):
    return [sum(part['transform'][i][j]*p[j] for j in range(3))+part['transform'][i][3] for i in range(3)]


def build_tank(thickness_mm=3):
    if thickness_mm != 3:
        raise ValueError('REDESIGN_JOINERY: this fixture is designed for nominal 3 mm stock')
    parts, joints = [], []

    def add(pid, name, objects, sheet, xy, origin=(0, 0, 0), u=(1, 0, 0), v=(0, 1, 0), note='胶合'):
        objects = copy.deepcopy(objects)
        for obj in objects:
            obj['id'] = pid + '-' + obj['id']
            obj['part_id'] = pid
        part = {'id': pid, 'name': name, 'objects': objects, 'thickness_mm': 3,
                'sheet': sheet, 'sheet_position_mm': list(xy), 'transform': _transform(origin, u, v),
                'attachment': note}
        parts.append(part)
        return part

    floor = add('H01', '底板', [_rect('outer', -72, -34, 144, 68, 'cut_outer')], 0, (5, 5), (0, 0, 18), note='榫接并少量胶合')
    deck = add('H02', '顶板', [_rect('outer', -80, -34, 160, 68, 'cut_outer'),
                              _ellipse('pivot', 5, 0, 3.1, 3.1, 'cut_inner')], 0, (5, 76), (0, 0, 54), note='榫接；转轴孔直径 6.2 mm')
    for index, y in enumerate((-27, 30)):
        tabs = [box(x, z, x+12, z+3) for x in (-60, 48) for z in (18, 54)]
        outer = _union_outline('outer', [box(-75, 21, 75, 54), *tabs])
        # A five-point star is a score outline, not an extra cutout.
        star = [(9*math.cos(a), 38+9*math.sin(a)) if k%2==0 else
                (4*math.cos(a), 38+4*math.sin(a)) for k, a in
                enumerate(-math.pi/2+k*math.pi/5 for k in range(10))]
        side = add(f'H0{3+index}', '车体左侧' if index==0 else '车体右侧',
                   [outer, _poly('star', star, 'score')], 0, (5, 146+44*index),
                   (0, y, 0), (1, 0, 0), (0, 0, 1), '上下四榫进入底板、顶板')
        for plate in (floor, deck):
            for x in (-60, 48):
                slot = _rect(f'slot-{side["id"]}-{x}', x-.1, y-3.05, 12.2, 3.1)
                slot['id'] = plate['id']+'-'+slot['id']; slot['part_id'] = plate['id']
                plate['objects'].append(slot)
                joints.append({'tab_part': side['id'], 'slot_part': plate['id'], 'slot_id': slot['id'],
                               'tab_rect_local_mm': [x, plate['transform'][2][3], x+12, plate['transform'][2][3]+3],
                               'tab_width_mm': 3, 'slot_width_mm': 3.1, 'clearance_mm': .1})
    for index, x in enumerate((-50, 50)):
        outer = _union_outline('outer', [box(-27, 21, 27, 54),
            *[box(y, z, y+10, z+3) for y in (-18, 8) for z in (18, 54)]])
        bulk = add(f'H0{5+index}', '内部隔板', [outer], 0, (180, 5+44*index),
                   (x-1.5, 0, 0), (0, 1, 0), (0, 0, 1), '上下四榫；两侧贴合侧板')
        for plate in (floor, deck):
            for y in (-18, 8):
                slot = _rect(f'slot-{bulk["id"]}-{y}', x-1.55, y-.1, 3.1, 10.2)
                slot['id'] = plate['id']+'-'+slot['id']; slot['part_id'] = plate['id']
                plate['objects'].append(slot)
                joints.append({'tab_part': bulk['id'], 'slot_part': plate['id'], 'slot_id': slot['id'],
                               'tab_rect_local_mm': [y, plate['transform'][2][3], y+10, plate['transform'][2][3]+3],
                               'tab_width_mm': 3, 'slot_width_mm': 3.1, 'clearance_mm': .1})
    for index, x in enumerate((-75, 72)):
        add(f'H0{7+index}', '前后封板', [_rect('outer', -27, 21, 54, 33, 'cut_outer')],
            0, (180, 93+38*index), (x, 0, 0), (0, 1, 0), (0, 0, 1))

    for side, y in enumerate((-39, 42)):
        outline = {'id': 'outer', 'role': 'cut_outer', 'closed': True,
                   'd': 'M -67,0 L 67,0 A 21,21 0 0 1 67,42 L -67,42 A 21,21 0 0 1 -67,0 Z'}
        tread = {'id': 'tread', 'role': 'score', 'closed': False, 'points': [[-60, 36], [-60, 39]]}
        detail = apply_ops({'units': 'mm', 'objects': [outline, tread]},
                           [{'op': 'array', 'ids': ['tread'], 'columns': 11, 'rows': 1, 'dx': 12, 'dy': 0}])
        add(f'T0{side+1}', '左履带侧板' if side==0 else '右履带侧板', detail['objects'],
            1, (5, 5+48*side), (0, y, 0), (1, 0, 0), (0, 0, 1), '通过两块 9 mm 桥接垫块与车体连接')
        for k, x in enumerate((-55, -33, -11, 11, 33, 55, -72, 72)):
            radius, z = (9, 13) if k<6 else (10, 25)
            j = side*8+k
            add(f'W{j+1:02}', '胶贴路轮' if k<6 else '胶贴端轮',
                [_ellipse('outer', 0, 0, radius, radius), _ellipse('ring', 0, 0, radius-2, radius-2, 'score'),
                 _ellipse('hub', 0, 0, 2.5, 2.5, 'score')], 1, (187+23*(j%4), 5+23*(j//4)),
                (x, -42 if side==0 else 45, z), (1, 0, 0), (0, 0, 1), f'胶贴于 T0{side+1} 外侧')
        for k, x in enumerate((-50, 50)):
            add(f'S{side*2+k+1:02}', '履带桥接垫块', [_rect('outer', -4, 0, 8, 9, 'cut_outer')],
                1, (100+16*(side*2+k), 219), (x, -39 if side==0 else 30, 30))

    for k, rx in enumerate((31, 30.5, 30, 29, 28, 27)):
        obj = [_ellipse('outer', 5, 0, rx, rx-5)]
        if k<2:
            obj.append(_ellipse('pivot', 5, 0, 3.1, 3.1, 'cut_inner'))
        if k==2:
            # The original layer has an open-front channel for the decorative barrel.
            doc = apply_ops({'units': 'mm', 'objects': obj+[_rect('channel', 24.9, -3.6, 20, 7.2, 'cut_outer')]},
                [{'op': 'boolean', 'ids': ['outer', 'channel'], 'mode': 'difference', 'result_id': 'outer'}])
            obj = doc['objects']
        add(f'R{k+1:02}', '炮塔叠层（自下向上）', obj, 1, (5+69*(k%3), 101+59*(k//3)),
            (0, 0, 57+3*k), note='各层对齐中心；R03 凹口朝前，避免胶进入轴孔')
    add('R07', '大舱盖', [_ellipse('outer', 0, 0, 9, 9), _rect('handle', -3, -1, 6, 2, 'score')],
        1, (220, 110), (3, 6, 75))
    add('R08', '小舱盖', [_ellipse('outer', 0, 0, 6, 6)], 1, (246, 112), (-12, -8, 75))
    add('R09', '平面装饰炮管', [_poly('outer', [(0, 1.5), (75, 1.5), (75, 0), (85, 0),
                    (85, 10), (75, 10), (75, 8.5), (0, 8.5)])], 1, (5, 218), (25, -5, 63),
        note='根部插入 R03 前开口，夹在 R02 与 R04 之间胶合')
    sheets = []
    for n in range(2):
        doc = {'units': 'mm', 'sheet_mm': [280, 230], 'minimum_web_mm': 2.99,
               'material': {'name': '名义 3 mm 木板', 'thickness_mm': 3, 'kerf_mm': None, 'fit_validated': False}, 'objects': []}
        for part in parts:
            if part['sheet'] != n:
                continue
            outer = next(o for o in part['objects'] if o['role']=='cut_outer')
            b = object_bounds(outer)
            moved = apply_ops({'units': 'mm', 'objects': part['objects']}, [{'op': 'move',
                'ids': [o['id'] for o in part['objects']], 'dx': part['sheet_position_mm'][0]-b[0],
                'dy': part['sheet_position_mm'][1]-b[1]}])
            doc['objects'].extend(moved['objects'])
        sheets.append(doc)
    return {'schema_version': 1, 'name': 'Sherman-inspired flat-pack plugin fixture', 'nominal_thickness_mm': 3,
            'parts': parts, 'sheets': sheets, 'joints': joints,
            'purchased_components': [{'name': '直径 6 mm 木圆棒', 'quantity': 1, 'length_mm': 12,
                                      'center_xy_mm': [5, 0], 'bottom_z_mm': 51}],
            'physical_fit_verified': False}


def part_stock(part):
    outer = next(object_shape(o) for o in part['objects'] if o['role']=='cut_outer')
    holes = [object_shape(o) for o in part['objects'] if o['role']=='cut_inner']
    return orient(outer.difference(unary_union(holes)), sign=1)


def mesh_part(part):
    """Return outward oriented world-space triangles and source planar area."""
    source = part_stock(part)
    # Polygonal mesh only: collapse numerical arc closure gaps below 1e-8 mm.
    # Exact source arcs remain unchanged in the machining SVG.
    def ring_points(ring):
        points = []
        for p in ring.coords:
            p = tuple(round(v, 8) for v in p)
            if not points or points[-1] != p:
                points.append(p)
        return points
    shape = orient(Polygon(ring_points(source.exterior), [ring_points(r) for r in source.interiors]), sign=1)
    triangles = []
    height = part['thickness_mm']
    for tri in constrained_delaunay_triangles(shape).geoms:
        points = list(orient(tri, sign=1).exterior.coords)[:3]
        triangles.append([world_point(part, [*p, height]) for p in points])
        triangles.append([world_point(part, [*p, 0]) for p in reversed(points)])
    for ring in (shape.exterior, *shape.interiors):
        for a, b in zip(ring.coords, list(ring.coords)[1:]):
            a0, b0, a1, b1 = (world_point(part, [*p, z]) for p, z in ((a, 0), (b, 0), (a, height), (b, height)))
            triangles.extend(((a0, b0, b1), (a0, b1, a1)))
    return triangles, source.area


def assembled_bounds(model):
    points = [p for part in model['parts'] for tri in mesh_part(part)[0] for p in tri]
    return [min(p[i] for p in points) for i in range(3)]+[max(p[i] for p in points) for i in range(3)]
