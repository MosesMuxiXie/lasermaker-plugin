import json
from pathlib import Path

import pytest

from lasermaker_agent.service import Service
from lasermaker_agent.geometry import EXPORT_PROFILE


def test_api_builds_real_files_and_can_resume_from_another_instance(tmp_path):
    root = str(tmp_path / "中文 path")
    service = Service()
    created = service.call("create_project", {"root": root, "name": "Example", "design": {
        "units": "mm", "sheet_mm": [100, 80], "objects": [
            {"id": "a", "role": "cut_outer", "closed": True,
             "points": [[10, 10], [30, 10], [30, 20], [10, 20]]}]}})
    assert created["revision"] == 0
    service.call("apply_design_ops", {"root": root, "expected_revision": 0, "request_id": "edit",
        "operations": [{"op": "move", "ids": ["a"], "dx": 2, "dy": 3}]})
    resumed = Service().call("resume_project", {"root": root})
    assert resumed["revision"] == 1
    result = service.call("export_delivery", {"root": root})
    assert Path(result["artifacts"]["svg"]).is_file()
    assert Path(result["artifacts"]["dxf"]).is_file()
    assert json.loads(Path(result["artifacts"]["preflight"]).read_text(encoding="utf-8"))["bounds_mm"] == [12, 13, 32, 23]
    assert result["manufacturing_ready"] is False
    assert result["native_current"] is False


def test_discretization_upgrade_preserves_old_delivery_directory(tmp_path,monkeypatch):
    import lasermaker_agent.service as module
    service=Service();root=str(tmp_path/'profiles')
    service.call('create_project',{'root':root,'name':'Profiles','design':{'units':'mm','objects':[
        {'id':'a','role':'cut_outer','closed':True,'points':[[0,0],[10,0],[10,10],[0,10]]}]}})
    old=service.call('export_delivery',{'root':root})
    prior=Path(old['artifacts']['dxf']).read_bytes()
    monkeypatch.setattr(module,'DISCRETIZATION_PROFILE','future-profile',raising=False)
    new=service.call('export_delivery',{'root':root})
    assert Path(old['artifacts']['dxf']).parent!=Path(new['artifacts']['dxf']).parent
    assert Path(old['artifacts']['dxf']).read_bytes()==prior


def test_service_rejects_unknown_or_extra_arguments_without_side_effects(tmp_path):
    service = Service()
    with pytest.raises(ValueError):
        service.call("start_job", {})
    with pytest.raises(ValueError):
        service.call("create_project", {"root": str(tmp_path / "bad"), "name": "bad",
                                       "design": {"units": "mm", "objects": []}, "shell": "whoami"})
    assert not (tmp_path / "bad").exists()


def test_unbound_project_cannot_edit_whatever_document_is_open(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from lasermaker_agent.store import ProjectError
    import lasermaker_agent.windows_driver as driver_module
    root = str(tmp_path / "unbound")
    Service().call("create_project", {"root": root, "name": "Unbound",
                                    "design": {"units": "mm", "objects": []}})
    class NoDesktopAccess:
        def __init__(self):
            raise AssertionError("UI was reached without a managed document binding")
    monkeypatch.setattr(driver_module, "WindowsDriver", NoDesktopAccess)
    monkeypatch.setattr(driver_module, "desktop_lock", nullcontext)
    with pytest.raises(ProjectError, match="IMPORT_OR_RELOAD_REQUIRED"):
        Service().call("set_layer_process", {"root": root, "request_id": "unbound-edit",
            "expected_revision": 0, "color": "#ff0000",
            "process": {"mode": "score", "speed_mm_s": 100, "power_max_percent": 15}})


def test_staged_import_checks_selected_geometry_bounds(tmp_path, monkeypatch):
    from contextlib import nullcontext
    import lasermaker_agent.windows_driver as module
    root = str(tmp_path / "staged")
    service = Service()
    service.call("create_project", {"root": root, "name": "Stage", "design": {
        "units": "mm", "objects": [
            {"id": "outline", "role": "cut_outer", "closed": True,
             "points": [[10, 10], [50, 10], [50, 40], [10, 40]]},
            {"id": "mark", "role": "score", "closed": False, "points": [[20, 20], [30, 25]]}]}})
    class Driver:
        pid = 123
        def import_design(self, path, expected_bounds):
            assert expected_bounds == [20, 20, 30, 25]
            return {"document_name": Path(path).name, "import_verified": True}
    monkeypatch.setattr(module, "WindowsDriver", Driver)
    monkeypatch.setattr(module, "desktop_lock", nullcontext)
    assert service.call("import_design", {"root": root, "request_id": "stage-1", "expected_revision": 0,
                                          "roles": ["score"]})["import_verified"]
    from lasermaker_agent.store import ProjectStore
    store = ProjectStore(root)
    scope = store.read()["gui_binding"]["source_scope"]
    assert scope["complete"] is False and scope["roles"] == ["score"]
    assert scope['export_profile'] == EXPORT_PROFILE
    path = store.output_path("native/stage.lcpx")
    path.parent.mkdir()
    path.write_bytes(b"stage native evidence fixture")
    store.register_native(path, {"source_scope": scope, "save_verified": True, "reopen_verified": True})
    result = service.call("export_delivery", {"root": root})
    assert result["native_current"] is False and "native" not in result["artifacts"]


def test_reopening_an_older_native_cannot_promote_it_to_the_current_revision(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from lasermaker_agent.store import ProjectStore, ProjectError
    import lasermaker_agent.windows_driver as module
    root = str(tmp_path / "old-native")
    service = Service()
    service.call("create_project", {"root": root, "name": "Revision", "design": {
        "units": "mm", "objects": [{"id": "a", "role": "score", "closed": False,
                                        "points": [[10, 10], [20, 20]]}]}})
    store = ProjectStore(root)
    native = store.output_path("native/old.lcpx")
    native.parent.mkdir()
    native.write_bytes(b"old revision")
    store.register_native(native, {"save_verified": True})
    service.call("apply_design_ops", {"root": root, "request_id": "change", "expected_revision": 0,
        "operations": [{"op": "move", "ids": ["a"], "dx": 1, "dy": 0}]})
    monkeypatch.setattr(module, "desktop_lock", nullcontext)
    with pytest.raises(ProjectError, match="NATIVE_SOURCE_REVISION_MISMATCH"):
        service.call("reload_and_verify", {"root": root, "request_id": "stale-reopen",
            "expected_revision": 1, "path": str(native)})


def test_close_requires_a_verified_native_and_replays_without_closing_another_document(tmp_path, monkeypatch):
    import struct
    from contextlib import nullcontext
    from lasermaker_agent.store import ProjectStore, ProjectError, atomic_write, json_bytes
    import lasermaker_agent.windows_driver as module
    root = str(tmp_path / "close")
    service = Service()
    service.call("create_project", {"root": root, "name": "Close", "design": {"units": "mm", "objects": []}})
    store = ProjectStore(root)
    state = store._load()
    state["gui_binding"] = {"document_name": "unique.lcpx", "pid": 123, "revision": 0}
    atomic_write(store.path, json_bytes(state))
    monkeypatch.setattr(module, "desktop_lock", nullcontext)
    request = {"root": root, "expected_revision": 0, "request_id": "close-1"}
    with pytest.raises(ProjectError, match="NATIVE_REOPEN_REQUIRED"):
        service.call("close_verified_document", request)
    native = store.output_path("native/unique.lcpx")
    native.parent.mkdir()
    data = bytearray(346);data[:4] = b"PRJF";struct.pack_into("<III", data, 4, 11, 12, 0)
    native.write_bytes(data)
    store.register_native(native, {"reopen_verified": True})
    closed = []
    class Driver:
        pid = 123
        def assert_document(self, name, expected_pid):
            assert name == "unique.lcpx" and expected_pid == 123
        def _close_saved_tab(self, path):
            closed.append(path)
    monkeypatch.setattr(module, "WindowsDriver", Driver)
    result = service.call("close_verified_document", request)
    assert result["document_closed"] and store.read()["gui_binding"] is None
    assert service.call("close_verified_document", request) == result
    assert closed == [native]


def test_process_argument_typos_are_rejected_before_project_or_desktop_access():
    with pytest.raises(ValueError, match="INVALID_ARGUMENTS"):
        Service().call("set_layer_process", {"root": "nonexistent", "request_id": "bad", "expected_revision": 0,
            "color": "#ff0000", "process": {"mode": "score", "speed_mm_s": 100,
            "power_max_percent": 15, "power_minn": 10}})


@pytest.mark.parametrize("fail_after_write", [False, True])
def test_unsaved_process_change_cannot_export_the_old_native_as_current(tmp_path, monkeypatch, fail_after_write):
    from contextlib import nullcontext
    from lasermaker_agent.store import ProjectStore, atomic_write, json_bytes
    import lasermaker_agent.windows_driver as module
    root = str(tmp_path / "process-dirty")
    service = Service()
    service.call("create_project", {"root": root, "name": "Process", "design": {"units": "mm", "objects": [
        {"id": "a", "role": "cut_outer", "closed": True, "points": [[0, 0], [20, 0], [20, 10], [0, 10]]}]}})
    store = ProjectStore(root)
    native = store.output_path("native/unique.lcpx");native.parent.mkdir();native.write_bytes(b"native fixture")
    scope = {"export_profile": EXPORT_PROFILE, "complete": True, "roles": ["cut_outer"], "bounds_mm": [0, 0, 20, 10]}
    store.register_native(native, {"reopen_verified": True, "source_scope": scope,
                                  "layer_process_readbacks": {"#000000": {"mode": "cut"}}})
    state = store._load();state["gui_binding"] = {"document_name": "unique.lcpx", "pid": 123, "revision": 0, "source_scope": scope}
    atomic_write(store.path, json_bytes(state))
    assert service.call("export_delivery", {"root": root})["native_current"]
    class Driver:
        pid = 123
        def assert_document(self, name, expected_pid):
            pass
        def set_process(self, color, values):
            if fail_after_write:
                raise ValueError("PROCESS_TABLE_READBACK_MISMATCH")
            return {"document_name": "unique.lcpx", "verified": values}
    monkeypatch.setattr(module, "desktop_lock", nullcontext)
    monkeypatch.setattr(module, "WindowsDriver", Driver)
    args = {"root": root, "expected_revision": 0, "request_id": "process",
        "color": "#000000", "process": {"mode": "cut", "speed_mm_s": 20, "power_max_percent": 15}}
    if fail_after_write:
        with pytest.raises(ValueError, match="PROCESS_TABLE_READBACK_MISMATCH"):
            service.call("set_layer_process", args)
    else:
        service.call("set_layer_process", args)
    result = service.call("export_delivery", {"root": root})
    assert result["native_current"] is False and "native" not in result["artifacts"]
    assert result["process_settings_verified"] is False


def test_external_native_change_preserves_previous_delivery_directory(tmp_path):
    from lasermaker_agent.store import ProjectStore
    root = str(tmp_path / "external-native")
    service = Service()
    service.call("create_project", {"root": root, "name": "External", "design": {"units": "mm", "objects": []}})
    store = ProjectStore(root)
    native = store.output_path("native/source.lcpx");native.parent.mkdir();native.write_bytes(b"original")
    store.register_native(native, {"reopen_verified": True, "source_scope": {"complete": True, "export_profile": EXPORT_PROFILE}})
    old = service.call("export_delivery", {"root": root})
    old_manifest = Path(old["artifacts"]["svg"]).parent / "manifest.json"
    original_manifest = old_manifest.read_bytes()
    native.write_bytes(b"external edit")
    new = service.call("export_delivery", {"root": root})
    assert Path(new["artifacts"]["svg"]).parent != old_manifest.parent
    assert old_manifest.read_bytes() == original_manifest
    assert not (Path(new["artifacts"]["svg"]).parent / "design.lcpx").exists()


def test_native_filename_prefix_cannot_follow_a_dangling_symlink_outside_project(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from lasermaker_agent.store import ProjectStore, ProjectError, atomic_write, json_bytes
    import lasermaker_agent.windows_driver as module
    root = str(tmp_path / "contained")
    service = Service()
    service.call("create_project", {"root": root, "name": "Contained", "design": {"units": "mm", "objects": []}})
    store = ProjectStore(root)
    state = store._load();state["gui_binding"] = {"document_name": "managed.svg", "pid": 123, "revision": 0,
                                               "source_scope": {"export_profile": EXPORT_PROFILE}}
    atomic_write(store.path, json_bytes(state))
    outside = tmp_path / "outside.lcpx"
    link = store.root / "native" / (state["project_id"] + "-escape.lcpx")
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("requires Windows Developer Mode or symlink permission")
    class Driver:
        pid = 123
        def assert_document(self, *args, **kwargs):
            pass
        def save_native(self, path):
            path.write_bytes(b"must not escape")
            return {"document_name": path.name}
    monkeypatch.setattr(module, "desktop_lock", nullcontext)
    monkeypatch.setattr(module, "WindowsDriver", Driver)
    with pytest.raises(ProjectError, match="OUTSIDE_PROJECT|SYMLINK_OUTPUT"):
        service.call("save_native", {"root": root, "expected_revision": 0, "request_id": "save",
                                     "filename": "native/escape.lcpx"})
    assert not outside.exists()


@pytest.mark.asyncio
async def test_real_mcp_subprocess_can_discover_and_call_tools(tmp_path):
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=["-m", "lasermaker_agent", "mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "lasermaker-agent"
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"create_project", "apply_design_ops", "import_design", "reload_and_verify"} <= names
            result = await session.call_tool("create_project", {"root": str(tmp_path / "mcp"),
                "name": "MCP", "design": {"units": "mm", "objects": []}})
            assert not result.isError
            assert result.structuredContent["revision"] == 0
            bad = await session.call_tool("apply_design_ops", {"root": str(tmp_path / "mcp"),
                "expected_revision": 9, "request_id": "stale", "operations": []})
            assert bad.isError
            assert "REVISION_CONFLICT" in bad.content[0].text
def test_invalid_engraving_corner_power_never_opens_project_or_desktop(tmp_path):
    from lasermaker_agent.service import Service
    root=tmp_path/'missing-project'
    with pytest.raises(ValueError,match='CORNER_POWER_NOT_APPLICABLE'):
        Service().call('set_layer_process',{'root':str(root),'request_id':'bad-field','expected_revision':0,
            'color':'#0000ff','process':{'mode':'engrave','speed_mm_s':100,'power_max_percent':15,'power_min_percent':13}})
    assert not root.exists()


@pytest.mark.parametrize('old_profile', [None, 'legacy-svg-v1'])
def test_old_exporter_native_requires_reimport_and_cannot_be_promoted(tmp_path, monkeypatch, old_profile):
    from contextlib import nullcontext
    from lasermaker_agent.store import ProjectStore, ProjectError, atomic_write, json_bytes
    import lasermaker_agent.windows_driver as module
    root = str(tmp_path / 'legacy-native')
    service = Service()
    service.call('create_project', {'root': root, 'name': 'Legacy', 'design': {
        'units': 'mm', 'objects': [{'id': 'a', 'role': 'cut_outer', 'closed': True,
            'points': [[0,0],[20,0],[20,10],[0,10]]}]}})
    store = ProjectStore(root)
    native = store.output_path('native/legacy.lcpx')
    native.parent.mkdir(); native.write_bytes(b'legacy exporter geometry')
    scope = {'complete': True, 'roles': ['cut_outer'], 'bounds_mm': [0,0,20,10]}
    if old_profile is not None:
        scope['export_profile'] = old_profile
    store.register_native(native, {'reopen_verified': True, 'source_scope': scope})
    state = store._load()
    state['gui_binding'] = {'document_name': native.name, 'pid': 123, 'revision': 0, 'source_scope': scope}
    atomic_write(store.path, json_bytes(state))
    result = service.call('export_delivery', {'root': root})
    assert not result['native_current'] and 'native' not in result['artifacts']
    class NoDesktopAccess:
        def __init__(self):
            raise AssertionError('Legacy geometry must be refused before desktop access')
    monkeypatch.setattr(module, 'WindowsDriver', NoDesktopAccess)
    monkeypatch.setattr(module, 'desktop_lock', nullcontext)
    for tool, extra in (('reload_and_verify', {'path': str(native)}),
                        ('save_native', {'filename': 'native/promoted.lcpx'})):
        with pytest.raises(ProjectError, match='NATIVE_EXPORT_PROFILE_MISMATCH_REIMPORT_REQUIRED'):
            service.call(tool, {'root': root, 'request_id': tool, 'expected_revision': 0, **extra})


