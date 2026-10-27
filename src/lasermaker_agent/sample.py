"""Import the user's existing, already checked six-part product without changing it."""
import copy


def _part_objects(parts):
    objects = []
    for part in parts:
        xmin = min(p[0] for p in part["outer"])
        ymin = min(p[1] for p in part["outer"])
        x, y = part["layout"]

        def placed(points):
            return [[round(p[0]-xmin+x, 6), round(p[1]-ymin+y, 6)] for p in points]

        for kind, role in (("engrave", "score"), ("holes", "cut_inner"), ("outer", "cut_outer")):
            lines = [part[kind]] if kind == "outer" else part[kind]
            for index, points in enumerate(lines):
                closed = kind != "engrave"
                if len(points) > 2 and points[0] == points[-1]:
                    points, closed = points[:-1], True
                objects.append({"id": f"{part['id']}-{kind}-{index}", "part_id": part["id"],
                                "role": role, "closed": closed, "points": placed(points)})
    return objects


def convert_legacy(source):
    return {"units": "mm", "sheet_mm": [280, 230], "minimum_web_mm": 2.99,
            "material": {"name": "木板（名义值，尚未试切）", "thickness_mm": 3, "kerf_mm": None,
                         "fit_validated": False}, "objects": _part_objects(source["parts"]),
            "assembly_envelope_mm": [130, 110, 125],
            "assembly": copy.deepcopy(source["parts"]),
            "center_of_mass_mm": source.get("center_of_mass_mm"),
            "note": "Digital baseline only. Changes to material thickness require joinery and assembly review."}


def coupon_design(source):
    coupon = source["coupon"]
    part = coupon.get("part", coupon)
    return {"units": "mm", "sheet_mm": [94, 39], "objects": _part_objects([part]),
            "material": {"thickness_mm": 3, "kerf_mm": None, "fit_validated": False},
            "slot_widths_mm": [2.7, 2.8, 2.9, 3, 3.1, 3.2, 3.3]}


def registration_plan(design):
    """Source-space stage offsets; GUI/machine origin must be checked separately."""
    from .geometry import ROLES,object_bounds
    def bounds(objects):
        boxes=[object_bounds(o) for o in objects]
        return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)] if boxes else None
    full=bounds(design['objects'])
    center=[(full[0]+full[2])/2,(full[1]+full[3])/2] if full else None
    stages=[]
    for role in ROLES:
        box=bounds([o for o in design['objects'] if o['role']==role])
        point=[(box[0]+box[2])/2,(box[1]+box[3])/2] if box else None
        stages.append({'role':role,'empty':box is None,'bounds_mm':box,'source_center_mm':point,
                       'source_center_delta_mm':[point[i]-center[i] for i in range(2)] if point else None})
    return {'units':'mm','source_y_direction':'down','full_bounds_mm':full,'full_source_center_mm':center,
            'stages':stages,'gui_and_machine_registration_verified':False,
            'instruction':'LaserMaker may center each import separately. Fix the center anchor, confirm GUI Y direction and register each stage against the full design. These deltas are not machine coordinates.'}
