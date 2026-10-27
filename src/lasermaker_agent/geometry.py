"""Millimetre geometry, deterministic edits and independent manufacturing preflight."""
from __future__ import annotations

import copy
import html
import io
import math
import re
from pathlib import Path as FilePath

from shapely import affinity, normalize, to_wkb
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from svgpathtools import parse_path, Path as SvgPath, Arc

ROLES = ("score", "engrave", "cut_inner", "cut_outer")
COLORS = {"score": "#ff0000", "engrave": "#0000ff", "cut_inner": "#000000", "cut_outer": "#000000"}
TOLERANCE_MM = 0.01
PIXELS_PER_MM = 96 / 25.4
EXPORT_PROFILE = 'lasermaker2172-svg-mm-v2-complete-curved-closure'
DISCRETIZATION_PROFILE = 'adaptive-chord-v2-exact-source-endpoints'
MAX_OBJECTS = 20000


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("FINITE_NUMBER_REQUIRED")
    if abs(value) > 100000:
        raise ValueError("COORDINATE_LIMIT")
    return float(value)


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("POINT_REQUIRES_X_Y")
    return [number(v) for v in value]


def _path(obj):
    d = obj.get("d", "")
    if not isinstance(d, str) or not d or len(d) > 1000000:
        raise ValueError("INVALID_PATH")
    if not re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\-\s]+", d):
        raise ValueError("UNSAFE_OR_INVALID_PATH")
    try:
        p = parse_path(d)
        if not p or len(p) > 20000:
            raise ValueError("PATH_SEGMENT_LIMIT")
        for seg in p:
            values = [seg.start.real, seg.start.imag, seg.end.real, seg.end.imag]
            for attr in ("control", "control1", "control2", "radius"):
                if hasattr(seg, attr):
                    v = getattr(seg, attr)
                    values.extend((v.real, v.imag))
            for value in values:
                number(value)
        return p
    except (AssertionError, IndexError, TypeError) as exc:
        raise ValueError("INVALID_PATH") from exc


def validate(document):
    if document.get("units") != "mm":
        raise ValueError("MILLIMETRES_REQUIRED")
    objects = document.get("objects")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise ValueError("OBJECT_LIMIT_OR_INVALID_LIST")
    ids = set()
    if "sheet_mm" in document:
        sheet = _point(document["sheet_mm"])
        if min(sheet) <= 0:
            raise ValueError("INVALID_SHEET")
    for obj in objects:
        oid = obj.get("id")
        if not isinstance(oid, str) or not re.fullmatch(r"[\w.-]{1,128}", oid) or oid in ids:
            raise ValueError("INVALID_OR_DUPLICATE_OBJECT_ID")
        ids.add(oid)
        if obj.get("role") not in ROLES or not isinstance(obj.get("closed"), bool):
            raise ValueError("INVALID_ROLE_OR_CLOSED_FLAG")
        if ("points" in obj) == ("d" in obj):
            raise ValueError("EXACTLY_ONE_PATH_REPRESENTATION_REQUIRED")
        if "points" in obj:
            pts = obj["points"]
            if not isinstance(pts, list) or not 2 <= len(pts) <= 100000:
                raise ValueError("INVALID_POINT_COUNT")
            for point in pts:
                _point(point)
        else:
            path = _path(obj)
            if obj["closed"] and any(not sub.isclosed() for sub in path.continuous_subpaths()):
                raise ValueError("CLOSED_PATH_REQUIRED")
        if obj["role"].startswith("cut") and not obj["closed"]:
            raise ValueError("CUT_MUST_BE_CLOSED")
    material = document.get("material", {})
    if material.get("thickness_mm") is not None and number(material["thickness_mm"]) <= 0:
        raise ValueError("INVALID_THICKNESS")
    if material.get("kerf_mm") is not None and number(material["kerf_mm"]) < 0:
        raise ValueError("INVALID_KERF")
    return document


def _sample_segment(seg):
    # Adaptive chord approximation is used only for checks/DXF, never to rewrite a source Bezier.
    points = [seg.start]

    def visit(a, b, depth=0):
        # Polynomial evaluation at t=1 can differ from seg.end by ~1e-13.
        # Keep source endpoints exact so a closed contour cannot acquire a
        # microscopic closing spike and fail the manufacturing preflight.
        pa = seg.start if a == 0 else seg.point(a)
        pb = seg.end if b == 1 else seg.point(b)
        sample = [seg.point(a + (b - a) * f) for f in (.25, .5, .75)]
        chord = LineString([(pa.real, pa.imag), (pb.real, pb.imag)])
        from shapely.geometry import Point
        error = max(chord.distance(Point(p.real, p.imag)) for p in sample)
        if error <= TOLERANCE_MM / 2 or depth >= 16:
            points.append(pb)
        else:
            mid = (a + b) / 2
            visit(a, mid, depth + 1)
            visit(mid, b, depth + 1)
        if len(points) > 100000:
            raise ValueError("PATH_APPROXIMATION_LIMIT")

    visit(0, 1)
    return [[p.real, p.imag] for p in points]


def contours(obj):
    if "points" in obj:
        return [obj["points"]]
    result = []
    for subpath in _path(obj).continuous_subpaths():
        points = []
        for seg in subpath:
            samples = _sample_segment(seg)
            points.extend(samples if not points else samples[1:])
        result.append(points)
    return result


def object_shape(obj):
    cs = contours(obj)
    if obj["closed"] and obj["role"] != "score":
        shapes = [Polygon(c) for c in cs]
        for shape in shapes:
            if not shape.is_valid:
                return shape
        # Compound closed paths use even-odd nesting, preserving glyph counters
        # and internal cutouts rather than filling them through unary_union.
        shape = shapes[0]
        for other in shapes[1:]:
            if shape.boundary.intersects(other.boundary):
                raise ValueError("COMPOUND_CONTOURS_INTERSECT")
            shape = shape.symmetric_difference(other)
        return shape
    else:
        shapes = [LineString(c + [c[0]] if obj["closed"] and c[-1] != c[0] else c) for c in cs]
    return shapes[0] if len(shapes) == 1 else unary_union(shapes)


def object_bounds(obj):
    if "d" in obj:
        xmin, xmax, ymin, ymax = _path(obj).bbox()
        return [xmin, ymin, xmax, ymax]
    return list(object_shape(obj).bounds)


def _mapped_path(path, mapping):
    mapped = mapping(path)
    if len(mapped) != len(path):
        raise ValueError("TRANSFORM_CHANGED_PATH_TOPOLOGY")
    # Restore only connections already present in the source. Polynomial
    # transforms can otherwise split a closed endpoint by ~1e-15 mm.
    start = 0
    for subpath in path.continuous_subpaths():
        stop = start+len(subpath)
        for index in range(start+1, stop):
            mapped[index].start = mapped[index-1].end
        if subpath.isclosed():
            mapped[stop-1].end = mapped[start].start
        start = stop
    return SvgPath(*mapped)


def _transform(obj, func, pathfunc):
    if "points" in obj:
        obj["points"] = [[round(v, 9) for v in func(_point(p))] for p in obj["points"]]
    else:
        obj["d"] = _mapped_path(_path(obj), pathfunc).d()


def _move(obj, dx, dy):
    _transform(obj, lambda p: [p[0] + dx, p[1] + dy], lambda p: p.translated(complex(dx, dy)))


def _scaled_path(path, sx, sy, origin):
    """Keep elliptical arcs exact under reflection/nonuniform axis scaling.

    svgpathtools only implements equal-axis Arc.scaled(). The eigenvectors
    of A R diag(rx², ry²) Rᵀ Aᵀ give the transformed ellipse axes; endpoint
    and large-arc choice stay fixed, and a reflection reverses sweep.
    """
    if sx == sy:
        return path.scaled(sx, sy, origin=origin)
    mapped = []
    def point(z):
        return origin + complex((z.real-origin.real)*sx, (z.imag-origin.imag)*sy)
    for segment in path:
        if not isinstance(segment, Arc):
            mapped.append(segment.scaled(sx, sy, origin=origin))
            continue
        rx, ry = segment.radius.real, segment.radius.imag
        angle = math.radians(segment.rotation)
        c, s = math.cos(angle), math.sin(angle)
        xx, yy = sx*sx*(rx*rx*c*c+ry*ry*s*s), sy*sy*(rx*rx*s*s+ry*ry*c*c)
        xy = sx*sy*(rx*rx-ry*ry)*c*s
        major2 = (xx+yy+math.hypot(xx-yy, 2*xy))/2
        # det / major avoids cancellation for highly eccentric ellipses.
        minor2 = (sx*sy*rx*ry)**2/major2
        rotation = math.degrees(math.atan2(2*xy, xx-yy)/2)
        mapped.append(Arc(point(segment.start), complex(math.sqrt(major2), math.sqrt(minor2)),
                          rotation, segment.large_arc,
                          segment.sweep if sx*sy>0 else not segment.sweep,
                          point(segment.end)))
    return SvgPath(*mapped)


def _new_from_polygon(template, shape, oid):
    if shape.is_empty or shape.geom_type != "Polygon" or not shape.is_valid:
        raise ValueError("BOOLEAN_OR_OFFSET_REQUIRES_SINGLE_VALID_POLYGON")
    if shape.interiors and template["role"] != "cut_outer":
        # An engraving counter is still an engraving contour, never a new cut.
        # Keep compound cut_inner shapes compound as well, preserving islands.
        rings = [shape.exterior, *shape.interiors]
        d = " ".join("M" + " L".join(f"{x:.9f},{y:.9f}" for x, y in list(r.coords)[:-1]) + " Z" for r in rings)
        obj = {**template, "id": oid, "d": d}
        obj.pop("points", None)
        return [obj]
    result = [{**template, "id": oid, "points": [list(p) for p in shape.exterior.coords][:-1]}]
    result[0].pop("d", None)
    for i, ring in enumerate(shape.interiors):
        hole = {**result[0], "id": f"{oid}-hole-{i}", "role": "cut_inner",
                "points": [list(p) for p in ring.coords][:-1]}
        result.append(hole)
    return result


def _text_objects(op):
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.ttLib import TTFont
    import uharfbuzz as hb

    text, filename = op["text"], FilePath(op["font_path"]).resolve(strict=True)
    if not isinstance(text, str) or len(text) > 2000 or not text.strip():
        raise ValueError("INVALID_TEXT_LENGTH")
    size = number(op["height_mm"])
    if size <= 0:
        raise ValueError("INVALID_TEXT_SIZE")
    with TTFont(filename, fontNumber=0) as font:
        cmap = font.getBestCmap()
        missing = [ch for ch in text if not ch.isspace() and ord(ch) not in cmap]
        if missing:
            raise ValueError("MISSING_GLYPHS: " + "".join(sorted(set(missing))))
        glyph_set, glyph_names = font.getGlyphSet(), font.getGlyphOrder()
        face = hb.Face(filename.read_bytes())
        hbfont = hb.Font(face)
        hbfont.scale = (face.upem, face.upem)
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(hbfont, buffer)
        scale = size / face.upem
        x, y = _point(op.get("position", [0, 0]))
        target_x, target_y = x, y
        result = []
        for i, (info, pos) in enumerate(zip(buffer.glyph_infos, buffer.glyph_positions)):
            pen = SVGPathPen(glyph_set)
            glyph_set[glyph_names[info.codepoint]].draw(pen)
            if pen.getCommands():
                p = _mapped_path(parse_path(pen.getCommands()), lambda path:
                    path.scaled(scale, -scale, origin=0j).translated(
                        complex(x + pos.x_offset * scale, y - pos.y_offset * scale)))
                result.append({"id": f"{op['id']}-{i}", "part_id": op.get("part_id"),
                               "role": op.get("role", "engrave"), "closed": True, "d": p.d()})
            x += pos.x_advance * scale
            y -= pos.y_advance * scale
        if not result:
            raise ValueError("TEXT_HAS_NO_OUTLINES")
        boxes = [object_bounds(obj) for obj in result]
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        visible_height = max(b[3] for b in boxes)-top
        if visible_height <= 0:
            raise ValueError("TEXT_HAS_NO_VISIBLE_HEIGHT")
        factor = size / visible_height
        shift = complex(target_x-left*factor, target_y-top*factor)
        for obj in result:
            obj["d"] = _mapped_path(_path(obj), lambda path:
                path.scaled(factor, origin=0j).translated(shift)).d()
        return result


def apply_ops(document, operations):
    """Apply an atomic batch to a copy. IDs must resolve exactly; never silently skip."""
    result = copy.deepcopy(validate(document))
    if not isinstance(operations, list) or len(operations) > 1000:
        raise ValueError("OPERATION_LIMIT")
    for op in operations:
        kind = op.get("op")
        fields = {
            "add": {"object"}, "text": {"text", "font_path", "height_mm", "position", "id", "part_id", "role"},
            "set_material": {"values"}, "node": {"id", "index", "point"}, "delete": {"ids"},
            "move": {"ids", "dx", "dy"}, "duplicate": {"ids", "dx", "dy", "suffix"},
            "array": {"ids", "dx", "dy", "columns", "rows"}, "rotate": {"ids", "degrees", "origin"},
            "scale": {"ids", "sx", "sy", "origin"}, "mirror": {"ids", "axis", "origin"},
            "align": {"ids", "axis", "mode", "value"}, "distribute": {"ids", "axis", "mode"},
            "offset": {"ids", "distance"}, "boolean": {"ids", "mode", "result_id"},
        }
        if kind not in fields:
            raise ValueError(f"UNKNOWN_OPERATION: {kind}")
        if set(op) - fields[kind] - {"op"}:
            raise ValueError("UNKNOWN_OPERATION_FIELD")
        objects = result["objects"]
        if kind == "add":
            objects.append(copy.deepcopy(op["object"]))
        elif kind == "text":
            objects.extend(_text_objects(op))
        elif kind == "set_material":
            # Changing a declared thickness does not silently resize existing joinery.
            result.setdefault("material", {}).update(copy.deepcopy(op["values"]))
            result["material"]["fit_validated"] = False
        elif kind == "node":
            selected = [o for o in objects if o["id"] == op["id"]]
            if len(selected) != 1 or "points" not in selected[0]:
                raise ValueError("NODE_REQUIRES_POLYLINE_OBJECT")
            index = op["index"]
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(selected[0]["points"]):
                raise ValueError("INVALID_NODE_INDEX")
            selected[0]["points"][index] = _point(op["point"])
        else:
            ids = op.get("ids")
            if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
                raise ValueError("UNIQUE_OBJECT_IDS_REQUIRED")
            by_id = {o["id"]: o for o in objects}
            if any(oid not in by_id for oid in ids):
                raise ValueError("OBJECT_NOT_FOUND")
            selected = [by_id[oid] for oid in ids]
            if kind == "delete":
                result["objects"] = [o for o in objects if o["id"] not in ids]
            elif kind in ("move", "duplicate", "array"):
                dx, dy = number(op.get("dx", 0)), number(op.get("dy", 0))
                if kind == "move":
                    for obj in selected:
                        _move(obj, dx, dy)
                else:
                    columns, rows = (op.get("columns", 1), op.get("rows", 1)) if kind == "array" else (2, 1)
                    if any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 100 for v in (columns, rows)):
                        raise ValueError("INVALID_ARRAY_DIMENSIONS")
                    if len(objects) + len(selected) * (columns * rows - 1) > MAX_OBJECTS:
                        raise ValueError("OBJECT_LIMIT")
                    copied_parts = {o.get("part_id") for o in selected if o["role"] == "cut_outer"}
                    for row in range(rows):
                        for col in range(columns):
                            if row == col == 0:
                                continue
                            suffix = op.get("suffix", "-copy") if kind == "duplicate" else f"-r{row}c{col}"
                            for source in selected:
                                obj = copy.deepcopy(source)
                                obj["id"] += suffix
                                if obj.get("part_id") and obj["part_id"] in copied_parts:
                                    obj["part_id"] += suffix
                                _move(obj, dx * col, dy * (1 if kind == "duplicate" else row))
                                objects.append(obj)
            elif kind in ("rotate", "scale", "mirror"):
                ox, oy = _point(op.get("origin", [0, 0]))
                if kind == "rotate":
                    angle = number(op["degrees"])
                    a = math.radians(angle)
                    def f(p):
                        x, y = p[0] - ox, p[1] - oy
                        return [ox + math.cos(a)*x - math.sin(a)*y, oy + math.sin(a)*x + math.cos(a)*y]
                    pf = lambda p: p.rotated(angle, origin=complex(ox, oy))
                else:
                    sx, sy = (number(op.get("sx", 1)), number(op.get("sy", 1)))
                    if kind == "mirror":
                        if op.get("axis") not in ("x", "y"):
                            raise ValueError("MIRROR_AXIS_REQUIRED")
                        sx, sy = (-1, 1) if op["axis"] == "x" else (1, -1)
                    if sx == 0 or sy == 0:
                        raise ValueError("ZERO_SCALE")
                    f = lambda p: [ox + (p[0]-ox)*sx, oy + (p[1]-oy)*sy]
                    pf = lambda p: _scaled_path(p, sx, sy, complex(ox, oy))
                for obj in selected:
                    _transform(obj, f, pf)
            elif kind in ("align", "distribute"):
                axis = op.get("axis")
                if axis not in ("x", "y"):
                    raise ValueError("AXIS_REQUIRED")
                a = 0 if axis == "x" else 1
                boxes = {o["id"]: object_bounds(o) for o in selected}
                mode = op.get("mode", "min")
                if mode not in ("min", "center", "max"):
                    raise ValueError("INVALID_ALIGNMENT")
                anchor = lambda o: (boxes[o["id"]][a] if mode == "min" else boxes[o["id"]][a+2] if mode == "max"
                                    else (boxes[o["id"]][a]+boxes[o["id"]][a+2])/2)
                ordered = sorted(selected, key=anchor)
                lo, hi = anchor(ordered[0]), anchor(ordered[-1])
                for i, obj in enumerate(ordered):
                    target = number(op.get("value", lo)) if kind == "align" else lo + (hi-lo)*i/max(1, len(ordered)-1)
                    delta = target - anchor(obj)
                    _move(obj, delta if a == 0 else 0, delta if a == 1 else 0)
            elif kind in ("offset", "boolean"):
                if any(not o["closed"] for o in selected):
                    raise ValueError("CLOSED_POLYGONS_REQUIRED")
                shapes = [object_shape(o) for o in selected]
                if any(not s.is_valid for s in shapes):
                    raise ValueError("INVALID_CONTOUR")
                if kind == "offset":
                    distance = number(op["distance"])
                    new = []
                    for obj, shape in zip(selected, shapes):
                        new.extend(_new_from_polygon(obj, shape.buffer(distance, join_style="mitre"), obj["id"]))
                else:
                    mode = op["mode"]
                    shape = shapes[0]
                    for other in shapes[1:]:
                        if mode == "union":
                            shape = shape.union(other)
                        elif mode == "difference":
                            shape = shape.difference(other)
                        elif mode == "intersection":
                            shape = shape.intersection(other)
                        else:
                            raise ValueError("INVALID_BOOLEAN_MODE")
                    new = _new_from_polygon(selected[0], shape, op["result_id"])
                result["objects"] = [o for o in objects if o["id"] not in ids] + new
            else:
                raise ValueError(f"UNKNOWN_OPERATION: {kind}")
        validate(result)
    return result


def preflight(document):
    validate(document)
    errors, warnings, shapes, cuts = [], [], {}, {}
    objects = document["objects"]
    minimum_web = number(document.get("minimum_web_mm", 0))
    for obj in objects:
        try:
            shape = object_shape(obj)
            shapes[obj["id"]] = shape
            if shape.is_empty or not shape.is_valid or (
                obj["closed"] and obj["role"] != "score" and shape.area < 1e-8
            ):
                errors.append({"code": "INVALID_CONTOUR", "object_id": obj["id"]})
            if obj["role"].startswith("cut"):
                key = to_wkb(normalize(shape))
                if key in cuts:
                    errors.append({"code": "DUPLICATE_CUT", "object_ids": [cuts[key], obj["id"]]})
                cuts[key] = obj["id"]
            box = shape.bounds
            if box and "sheet_mm" in document:
                w, h = document["sheet_mm"]
                if box[0] < -TOLERANCE_MM or box[1] < -TOLERANCE_MM or box[2] > w+TOLERANCE_MM or box[3] > h+TOLERANCE_MM:
                    errors.append({"code": "OUTSIDE_SHEET", "object_id": obj["id"]})
        except ValueError as exc:
            errors.append({"code": "INVALID_CONTOUR", "object_id": obj["id"], "detail": str(exc)})
    part_ids = {o.get("part_id") for o in objects if o.get("part_id")}
    outers = []
    for part_id in sorted(part_ids):
        part = [o for o in objects if o.get("part_id") == part_id and o["id"] in shapes]
        outer_objs = [o for o in part if o["role"] == "cut_outer"]
        holes = [o for o in part if o["role"] == "cut_inner"]
        if len(outer_objs) != 1:
            errors.append({"code": "PART_REQUIRES_ONE_OUTER", "part_id": part_id})
            continue
        outer = shapes[outer_objs[0]["id"]]
        outers.append((part_id, outer))
        valid_holes = []
        for obj in holes:
            hole = shapes[obj["id"]]
            if not outer.is_valid or not hole.is_valid:
                continue
            if not outer.contains(hole):
                errors.append({"code": "HOLE_OUTSIDE_PART", "object_id": obj["id"]})
            if outer.boundary.distance(hole) + TOLERANCE_MM < minimum_web:
                errors.append({"code": "THIN_WEB", "object_id": obj["id"]})
            for previous in valid_holes:
                if hole.intersects(previous) or hole.distance(previous) + TOLERANCE_MM < minimum_web:
                    errors.append({"code": "HOLE_OVERLAP_OR_THIN_WEB", "object_id": obj["id"]})
            valid_holes.append(hole)
        if outer.is_valid and all(h.is_valid for h in valid_holes):
            stock = outer.difference(unary_union(valid_holes))
            for obj in part:
                if obj["role"] in ("score", "engrave") and not stock.buffer(TOLERANCE_MM).covers(shapes[obj["id"]]):
                    errors.append({"code": "MARK_OUTSIDE_STOCK", "object_id": obj["id"]})
    for i, (pid, outer) in enumerate(outers):
        for qid, other in outers[:i]:
            if outer.is_valid and other.is_valid and (outer.intersection(other).area > TOLERANCE_MM**2 or
                                                      outer.distance(other) < TOLERANCE_MM):
                errors.append({"code": "PARTS_OVERLAP_OR_TOUCH", "part_ids": [pid, qid]})
    boxes = [object_bounds(o) for o in objects]
    bounds = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None
    material = document.get("material", {})
    if material.get("kerf_mm") is None:
        warnings.append({"code": "KERF_UNMEASURED"})
    if not material.get("fit_validated"):
        warnings.append({"code": "PHYSICAL_FIT_UNVERIFIED"})
    warnings.append({"code": "MACHINE_AND_PROCESS_REQUIRE_ON_SITE_VALIDATION"})
    return {"geometry_passed": not errors, "manufacturing_ready": False, "bounds_mm": bounds,
            "object_count": len(objects), "part_count": len(part_ids), "errors": errors, "warnings": warnings,
            "geometry_tolerance_mm": TOLERANCE_MM}


def export_svg(document, roles=None):
    validate(document)
    objects = [o for o in document["objects"] if roles is None or o["role"] in roles]
    w, h = document.get("sheet_mm", [300, 300])
    k = PIXELS_PER_MM
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}mm" height="{h:g}mm" '
           f'viewBox="0 0 {w*k:.8f} {h*k:.8f}">',
           "<desc>1:1 millimetres; LaserMaker2.1.7.2 profile; process parameters require material testing.</desc>"]
    for role in ROLES:
        out.append(f'<g id="{role}" fill="none" stroke="{COLORS[role]}" stroke-width="{.1*k:.8f}">')
        for obj in objects:
            if obj["role"] != role:
                continue
            if "points" in obj:
                d = "M" + " L".join(f"{x*k:.8f},{y*k:.8f}" for x, y in obj["points"])
                if obj["closed"]:
                    d += " Z"
            else:
                path = _mapped_path(_path(obj), lambda p: p.scaled(k, origin=0j))
                # svgpathtools' use_closed_attrib=True drops the last segment,
                # including a curved closing segment. Keep every segment and
                # append Z explicitly so native import cannot replace an arc
                # or Bezier with a straight closing edge.
                d = " ".join(sub.d()+" Z" for sub in path.continuous_subpaths()) if obj["closed"] else path.d()
            out.append(f'<path id="{html.escape(obj["id"], quote=True)}" d="{d}"/>')
        out.append("</g>")
    return "\n".join(out + ["</svg>"])


def export_dxf(document, roles=None):
    import ezdxf
    validate(document)
    doc = ezdxf.new("R2010")
    doc.units = 4  # INSUNITS=millimetres; no font-dependent DXF TEXT entities.
    for role in ROLES:
        doc.layers.new(role, dxfattribs={"color": 1 if role == "score" else 5 if role == "engrave" else 7})
    space = doc.modelspace()
    for obj in document["objects"]:
        if roles is not None and obj["role"] not in roles:
            continue
        for points in contours(obj):
            # DXF Y points up. Negating here preserves SVG top-down layout on import.
            space.add_lwpolyline([(x, -y) for x, y in points], close=obj["closed"],
                                 dxfattribs={"layer": obj["role"]})
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
