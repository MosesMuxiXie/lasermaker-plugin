"""Host-independent, schema-checked application operations."""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path

from jsonschema import validate as validate_schema
from jsonschema.exceptions import ValidationError

from . import __version__
from .geometry import ROLES, COLORS, EXPORT_PROFILE, DISCRETIZATION_PROFILE, export_dxf, export_svg, preflight, object_bounds
from .native import read_native
from .store import ProjectError, ProjectStore, atomic_write, digest, file_lock, json_bytes

STRING = {"type": "string", "minLength": 1}
REVISION = {"type": "integer", "minimum": 0}
ROOT = {"root": STRING}
GUI = {**ROOT, "request_id": STRING, "expected_revision": REVISION}
PROCESS = {"type": "object", "properties": {
    "mode": {"enum": ["cut", "score", "engrave", "shallow_engrave"]},
    "speed_mm_s": {"type": "number", "exclusiveMinimum": 0, "maximum": 10000},
    "power_max_percent": {"type": "number", "minimum": 0, "maximum": 100},
    "power_min_percent": {"type": "number", "minimum": 0, "maximum": 100,
                          "description": "Corner power for cut/score only; omit for engraving modes."}},
    "required": ["mode", "speed_mm_s", "power_max_percent"], "additionalProperties": False}


def _spec(description, properties, required=None):
    return {"description": description, "inputSchema": {
        "type": "object", "properties": properties, "required": list(properties) if required is None else required,
        "additionalProperties": False}}


TOOLS = {
    "doctor": _spec("Inspect runtime and supported capabilities. Does not launch LaserMaker.", {}, []),
    "create_project": _spec("Create a new empty project directory with canonical millimetre geometry.",
                           {**ROOT, "name": STRING, "design": {"type": "object"}}),
    "open_project": _spec("Read a project, its revision and external native-file change status.", ROOT),
    "read_design": _spec("Read strict native PRJF11.12 header diagnostics; not authoritative geometry.",
                        {"path": STRING}),
    "apply_design_ops": _spec("Atomically edit canonical geometry; same request ID is safe to retry.",
                             {**GUI, "operations": {"type": "array", "maxItems": 1000, "items": {"type": "object"}}}),
    "preflight": _spec("Check contours, parts, spacing, units and material uncertainty.", ROOT),
    "export_delivery": _spec("Write versioned SVG/DXF/staged files, reports and current native evidence.", ROOT),
    "checkpoint": _spec("Save a durable project checkpoint and verified native copy when available.",
                        {**ROOT, "label": STRING}),
    "resume_project": _spec("Resume latest revision; never silently rewind to an older checkpoint.", ROOT),
    "inspect_app": _spec("Read only LaserMaker windows, controls, selection dimensions and layers.", {}, []),
    "import_design": _spec("Import generated geometry into a fresh managed LaserMaker document; verify size.",
                          {**GUI, "roles": {"type": "array", "items": {"enum": list(ROLES)}}}, list(GUI)),
    "set_layer_process": _spec("Set a layer process through GUI and read back speed/power; never start a job.",
                              {**GUI, "color": {"enum": ["#000000", "#ff0000", "#ffff00", "#0000ff"]},
                               "process": PROCESS}),
    "verify_layer_process": _spec("Read a reopened document's mode, speed, max and corner power without editing.",
                              {**GUI, "color": {"enum": ["#000000", "#ff0000", "#ffff00", "#0000ff"]},
                               "process": PROCESS}),
    "close_verified_document": _spec("Close only the currently bound, saved and reopened project document.", GUI),
    "save_native": _spec("Save current managed document to a new native file inside this project.",
                         {**GUI, "filename": STRING}, list(GUI)),
    "reload_and_verify": _spec("Reopen the exact saved native path, verify dimensions, layers and settings.",
                              {**GUI, "path": STRING, "expected_size_mm": {"type": "array",
                               "items": {"type": "number"}, "minItems": 2, "maxItems": 2}},
                              list(GUI) + ["path"]),
    "capture_app": _spec("Capture LaserMaker only and read local OCR when available.",
                        {**ROOT, "filename": STRING}, ["root"]),
}


class Service:
    def call(self, name, arguments):
        if name not in TOOLS:
            raise ValueError("UNKNOWN_TOOL: " + name)
        try:
            validate_schema(arguments, TOOLS[name]["inputSchema"])
        except ValidationError as exc:
            raise ValueError("INVALID_ARGUMENTS: " + exc.message) from exc
        if name in ('set_layer_process','verify_layer_process'):
            from .windows_driver import validate_process
            validate_process(arguments['process'])  # Reject invalid mode fields before any state/UI changes.
        if "root" in arguments and name != "create_project":
            store = ProjectStore(arguments["root"])
            store.read()  # Refuse invalid/non-project roots before creating a lock.
            with file_lock(store.root / ".service.lock", timeout=3):
                return self._dispatch(name, arguments)
        return self._dispatch(name, arguments)

    def _dispatch(self, name, arguments):
        if name == "doctor":
            return self.doctor()
        if name == "read_design":
            return read_native(arguments["path"])
        if name == "inspect_app":
            from .windows_driver import WindowsDriver, desktop_lock
            with desktop_lock():
                return WindowsDriver().inspect()
        store = ProjectStore(arguments["root"])
        if name == "create_project":
            return store.create(arguments["name"], arguments["design"])
        if name in ("open_project", "resume_project"):
            result = store.resume()
            pending = []
            for path in store.root.glob("operations/*.json"):
                entry = json.loads(path.read_text(encoding="utf-8"))
                if entry["status"] != "complete":
                    pending.append({"request_id": entry["request_id"], "status": entry["status"],
                                    "tool": entry["tool"], "evidence": str(path)})
            result["pending_ui_operations"] = pending
            return result
        if name == "apply_design_ops":
            return store.mutate(arguments["request_id"], arguments["expected_revision"], arguments["operations"])
        if name == "preflight":
            return {"revision": store.read()["revision"], **preflight(store.read()["design"])}
        if name == "checkpoint":
            return store.checkpoint(arguments["label"])
        if name == "export_delivery":
            return self.export(store)
        if name == "capture_app":
            from .windows_driver import WindowsDriver, desktop_lock
            store.read()
            path = store.output_path(arguments.get("filename", "evidence/app.png"))
            if path.suffix.lower() != ".png" or path.exists():
                raise ProjectError("NEW_PNG_PATH_REQUIRED")
            with desktop_lock():
                return WindowsDriver().screenshot(path)
        return self._gui(name, store, arguments)

    def doctor(self):
        from .windows_driver import EXECUTABLE
        packages = {}
        for name in ("mcp", "pywinauto", "Pillow", "shapely", "svgpathtools"):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = "bundled_or_unavailable"
        return {"name": "lasermaker-agent", "version": __version__, "platform": platform.platform(),
                "windows": os.name == "nt", "lasermaker_executable": str(EXECUTABLE),
                "lasermaker_installed": EXECUTABLE.is_file(), "supported_lasermaker": ["2.1.7.2"],
                "transport": "stdio", "packages": packages,
                "capabilities": {"geometry": True, "native_header_read": True,
                                 "windows_gui": os.name == "nt", "device_start": False,
                                 "raw_native_geometry_write": False},
                "limitations": ["Machine, material fit and actual cutting have not been validated.",
                                "GUI requires an unlocked local interactive Windows desktop."]}

    def export(self, store):
        state = store.read()
        report = preflight(state["design"])
        if not report["geometry_passed"]:
            raise ProjectError("GEOMETRY_PREFLIGHT_FAILED: " + json.dumps(report["errors"], ensure_ascii=False))
        # Revision- and content-addressed outputs cannot overwrite earlier deliveries.
        native = state.get("native")
        token = digest({"export_profile": EXPORT_PROFILE, "discretization_profile": DISCRETIZATION_PROFILE,
                        "design": state["design"], "native": native,
                        "native_observed_sha256": state.get("native_observed_sha256"),
                        "native_parameters_dirty": state.get("native_parameters_dirty", False)})[:12]
        directory = store.output_path(f"artifacts/r{state['revision']:06d}-{token}")
        directory.mkdir(parents=True, exist_ok=True)
        artifacts = {}
        outputs = {"svg": ("design.svg", export_svg(state["design"]).encode("utf-8")),
                   "dxf": ("design.dxf", export_dxf(state["design"])),
                   "source": ("design.json", json_bytes(state["design"])),
                   "preflight": ("preflight.json", json_bytes(report))}
        for role in ROLES:
            outputs[role] = (f"stage-{role}.svg", export_svg(state["design"], [role]).encode("utf-8"))
        for name, (filename, data) in outputs.items():
            path = directory / filename
            atomic_write(path, data)
            artifacts[name] = str(path)
        native_current = bool(native and native["revision"] == state["revision"] and
                              not state.get("native_parameters_dirty", False) and
                              native.get("design_digest") == digest(state["design"]) and
                              (native.get("source_scope") or {}).get("complete") and
                              (native.get("source_scope") or {}).get("export_profile") == EXPORT_PROFILE and
                              not state["native_external_change"] and
                              native["verification"].get("reopen_verified"))
        if native_current:
            path = directory / "design.lcpx"
            atomic_write(path, store.verified_native_bytes(state))
            artifacts["native"] = str(path)
        result = {"project_id": state["project_id"], "revision": state["revision"], "artifacts": artifacts,
                  "export_profile": EXPORT_PROFILE,
                  "discretization_profile": DISCRETIZATION_PROFILE,
                  "native_current": native_current, "native_evidence": native,
                  "process_settings_verified": bool(native_current and
                      {COLORS[o["role"]] for o in state["design"]["objects"]} <=
                      set(native["verification"].get("layer_process_readbacks", {}))),
                  "geometry_passed": True, "manufacturing_ready": False,
                  "required_on_site": ["machine/bed/controller", "material thickness and slot fit",
                                       "speed/power test", "inner-before-outer execution"],
                  "process_order": ["score/engrave", "cut_inner", "cut_outer"]}
        result["sha256"] = {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                            for name, path in artifacts.items()}
        atomic_write(directory / "manifest.json", json_bytes(result))
        return result

    def _gui(self, name, store, arguments):
        from .windows_driver import WindowsDriver, desktop_lock
        request_id = arguments["request_id"]
        entry_path = store.output_path("operations/" + hashlib.sha256(request_id.encode()).hexdigest() + ".json")
        payload_digest = digest({"tool": name, "arguments": arguments})
        with desktop_lock():
            state = store.read()
            if entry_path.exists():
                entry = json.loads(entry_path.read_text(encoding="utf-8"))
                if entry["digest"] != payload_digest:
                    raise ProjectError("REQUEST_CONFLICT")
                if entry["status"] == "complete":
                    return entry["result"]
                raise ProjectError("UI_OUTCOME_UNKNOWN: inspect and reconcile before issuing a new request.")
            if state["revision"] != arguments["expected_revision"]:
                raise ProjectError("REVISION_CONFLICT")
            if state["native_external_change"]:
                raise ProjectError("EXTERNAL_NATIVE_CHANGE_REQUIRES_FORK")
            if name == "reload_and_verify":
                target = store.output_path(arguments["path"])
                association = state.get("native_catalog", {}).get(str(target.relative_to(store.root)).casefold())
                if not association or association["revision"] != state["revision"] or association["design_digest"] != digest(state["design"]):
                    raise ProjectError("NATIVE_SOURCE_REVISION_MISMATCH")
                if (association.get("source_scope") or {}).get("export_profile") != EXPORT_PROFILE:
                    raise ProjectError("NATIVE_EXPORT_PROFILE_MISMATCH_REIMPORT_REQUIRED")
                from .store import file_hash
                if not target.is_file() or file_hash(target) != association["sha256"]:
                    raise ProjectError("EXTERNAL_NATIVE_CHANGE_REQUIRES_FORK")
            binding = state.get("gui_binding")
            if name in ("set_layer_process", "verify_layer_process", "save_native", "close_verified_document") and (
                    not binding or binding["revision"] != state["revision"]):
                raise ProjectError("IMPORT_OR_RELOAD_REQUIRED")
            if name == "save_native" and (binding.get("source_scope") or {}).get("export_profile") != EXPORT_PROFILE:
                raise ProjectError("NATIVE_EXPORT_PROFILE_MISMATCH_REIMPORT_REQUIRED")
            if name == "close_verified_document":
                if state.get("native_parameters_dirty"):
                    raise ProjectError("UNSAVED_PROCESS_CHANGES")
                native = state.get("native")
                if not native or native["revision"] != state["revision"] or not native["verification"].get("reopen_verified"):
                    raise ProjectError("NATIVE_REOPEN_REQUIRED")
                if binding["document_name"] not in (Path(native["path"]).name, Path(native["path"]).stem):
                    raise ProjectError("BOUND_NATIVE_DOCUMENT_MISMATCH")
            entry = {"request_id": request_id, "tool": name, "digest": payload_digest,
                     "status": "started", "revision": state["revision"], "started_at": time.time()}
            atomic_write(entry_path, json_bytes(entry))
            driver = WindowsDriver()
            scope = binding.get("source_scope") if binding else None
            try:
                if name in ("set_layer_process", "verify_layer_process", "save_native", "close_verified_document"):
                    driver.assert_document(binding["document_name"], expected_pid=binding["pid"])
                if name == "import_design":
                    report = preflight(state["design"])
                    if not report["geometry_passed"]:
                        raise ProjectError("GEOMETRY_PREFLIGHT_FAILED")
                    roles = arguments.get("roles")
                    selected = [o for o in state["design"]["objects"] if roles is None or o["role"] in roles]
                    if not selected:
                        raise ProjectError("EMPTY_IMPORT_SELECTION")
                    boxes = [object_bounds(o) for o in selected]
                    bounds = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                              max(b[2] for b in boxes), max(b[3] for b in boxes)]
                    path = store.output_path(f"imports/{state['project_id']}-{hashlib.sha256(request_id.encode()).hexdigest()[:32]}.svg")
                    atomic_write(path, export_svg(state["design"], roles).encode("utf-8"))
                    result = driver.import_design(path, expected_bounds=bounds)
                    scope = {"export_profile": EXPORT_PROFILE,
                             "roles": sorted({o["role"] for o in selected}),
                             "complete": len(selected) == len(state["design"]["objects"]),
                             "bounds_mm": bounds}
                elif name == "set_layer_process":
                    # Persist before any UI write: a readback failure or killed
                    # worker must never leave the old native marked current.
                    with file_lock(store.lock):
                        updated = store._load()
                        updated["native_parameters_dirty"] = True
                        atomic_write(store.path, json_bytes(updated))
                    result = driver.set_process(arguments["color"], arguments["process"])
                elif name == "verify_layer_process":
                    result = driver.verify_process(arguments["color"], arguments["process"])
                elif name == "close_verified_document":
                    path = store.output_path(native["path"])
                    driver._close_saved_tab(path)
                    result = {"document_name": binding["document_name"], "path": str(path), "document_closed": True}
                elif name == "save_native":
                    filename = arguments.get("filename", f"native/r{state['revision']:06d}-{uuid_token()}.lcpx")
                    path = store.output_path(filename)
                    if not path.name.startswith(state["project_id"] + "-"):
                        path = path.with_name(state["project_id"] + "-" + path.name)
                    if path.is_symlink():
                        raise ProjectError("SYMLINK_OUTPUT_REJECTED")
                    path = store.output_path(path)
                    if path.suffix.lower() != ".lcpx" or path.exists():
                        raise ProjectError("NEW_LCPX_OUTPUT_PATH_REQUIRED")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    result = {**driver.save_native(path), "source_scope": scope}
                    store.register_native(path, result)
                elif name == "reload_and_verify":
                    path = store.output_path(arguments["path"])
                    read_native(path)
                    expected = arguments.get("expected_size_mm")
                    scope = association.get("source_scope")
                    if expected is None:
                        bounds = (scope or {}).get("bounds_mm")
                        expected = [bounds[2]-bounds[0], bounds[3]-bounds[1]] if bounds else None
                    result = {**driver.reload_and_verify(path, expected_size=expected), "source_scope": scope}
                    store.register_native(path, result)
                else:
                    raise ValueError("UNKNOWN_GUI_TOOL")
                result = {**result, "project_id": state["project_id"], "revision": state["revision"],
                          "request_id": request_id, "manufacturing_ready": False}
                with file_lock(store.lock):
                    updated = store._load()
                    if updated["revision"] != state["revision"]:
                        raise ProjectError("REVISION_CHANGED_DURING_UI_OPERATION")
                    updated["gui_binding"] = {"document_name": result["document_name"],
                                              "revision": state["revision"], "last_tool": name,
                                              "source_scope": scope,
                                              "pid": driver.pid}
                    if name == "close_verified_document":
                        updated["gui_binding"] = None
                    if name == "set_layer_process":
                        updated["native_parameters_dirty"] = True
                    elif name in ("save_native", "reload_and_verify"):
                        updated["native_parameters_dirty"] = False
                    elif name == "verify_layer_process" and updated.get("native"):
                        native_name = Path(updated["native"]["path"]).name
                        if result["document_name"] in (native_name, Path(native_name).stem):
                            updated["native"]["verification"].setdefault("layer_process_readbacks", {})[
                                arguments["color"]] = result["process_readback"]
                    atomic_write(store.path, json_bytes(updated))
                entry.update(status="complete", result=result, completed_at=time.time())
            except Exception as exc:
                entry.update(status="needs_reconciliation", error=f"{type(exc).__name__}: {exc}")
                atomic_write(entry_path, json_bytes(entry))
                raise
            atomic_write(entry_path, json_bytes(entry))
            return result


def uuid_token():
    import uuid
    return uuid.uuid4().hex[:12]
