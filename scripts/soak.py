"""Real continuous MCP/UI workload. No sleeps counted as workload; never starts a machine."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from lasermaker_agent.sample import convert_legacy
from lasermaker_agent.store import json_bytes


async def run(root, minutes):
    root = root.resolve()
    log = root.parent / (root.name + "-events.jsonl")
    summary = root.parent / (root.name + "-summary.json")
    start = time.monotonic()
    count, calls, sessions, active = 0, 0, 0, 0.0
    def event(value):
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": time.time(), **value}, ensure_ascii=False) + "\n")
        print(json.dumps(value, ensure_ascii=False), flush=True)
    try:
        while time.monotonic() - start < minutes * 60:
            sessions += 1
            params = StdioServerParameters(command=sys.executable, args=["-m", "lasermaker_agent", "mcp"])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    async def call(name, args):
                        nonlocal calls, active
                        before = time.monotonic()
                        result = await session.call_tool(name, args)
                        elapsed = time.monotonic() - before
                        calls += 1
                        active += elapsed
                        data = result.structuredContent
                        event({"cycle": count, "session": sessions, "tool": name,
                               "seconds": round(elapsed, 3), "is_error": bool(result.isError),
                               "result": data if data is not None else [c.model_dump() for c in result.content]})
                        if result.isError:
                            raise RuntimeError(str(result.content))
                        return data
                    if not (root / "project.json").exists():
                        source = json.loads(Path("tests/fixtures/synthetic-six-part.json").read_text(encoding="utf-8"))
                        await call("create_project", {"root": str(root), "name": "连续编辑验收副本", "design": convert_legacy(source)})
                    state = await call("resume_project", {"root": str(root)})
                    if state["pending_ui_operations"]:
                        raise RuntimeError("PENDING_UI_OPERATIONS_REQUIRE_RECONCILIATION")
                    # Restart MCP every two cycles; each call itself starts a new bounded worker.
                    for _ in range(2):
                        revision = state["revision"]
                        request = {"root": str(root), "request_id": f"cycle-{count}-edit",
                                   "expected_revision": revision, "operations": [{"op": "move",
                                   "ids": ["A-engrave-1"], "dx": .01 if count % 2 == 0 else -.01, "dy": 0}]}
                        edited = await call("apply_design_ops", request)
                        replay = await call("apply_design_ops", request)
                        assert replay == edited
                        revision = edited["revision"]
                        base = {"root": str(root), "expected_revision": revision}
                        await call("preflight", {"root": str(root)})
                        imported = await call("import_design", {**base, "request_id": f"cycle-{count}-import"})
                        assert await call("import_design", {**base, "request_id": f"cycle-{count}-import"}) == imported
                        for color, mode, speed, power, corner in (("#ff0000", "score", 100+count%2, 15, 13),
                                                                ("#000000", "cut", 10+count%2, 15, 13)):
                            await call("set_layer_process", {**base, "request_id": f"cycle-{count}-{mode}",
                                "color": color, "process": {"mode": mode, "speed_mm_s": speed,
                                "power_max_percent": power, "power_min_percent": corner}})
                        saved = await call("save_native", {**base, "request_id": f"cycle-{count}-save",
                            "filename": f"native/cycle-{count:04d}.lcpx"})
                        reopened = await call("reload_and_verify", {**base, "request_id": f"cycle-{count}-reopen",
                            "path": saved["path"], "expected_size_mm": [252, 208]})
                        assert reopened["reopen_verified"]
                        for color, mode, speed in (("#ff0000", "score", 100+count%2), ("#000000", "cut", 10+count%2)):
                            await call("verify_layer_process", {**base, "request_id": f"cycle-{count}-verify-{mode}",
                                "color": color, "process": {"mode": mode, "speed_mm_s": speed,
                                "power_max_percent": 15, "power_min_percent": 13}})
                        await call("checkpoint", {"root": str(root), "label": f"cycle-{count:04d}"})
                        await call("export_delivery", {"root": str(root)})
                        if count in (1, 2):
                            await asyncio.to_thread(fault_check, count, saved["path"], event)
                        await call("close_verified_document", {**base, "request_id": f"cycle-{count}-close"})
                        state = await call("resume_project", {"root": str(root)})
                        count += 1
                        event({"completed_cycles": count, "elapsed_seconds": round(time.monotonic()-start, 3),
                               "active_call_seconds": round(active, 3)})
                        if time.monotonic()-start >= minutes*60:
                            break
        result = {"passed": count > 0 and time.monotonic()-start >= minutes*60,
                  "required_minutes": minutes, "completed_cycles": count, "mcp_sessions": sessions,
                  "calls": calls, "elapsed_seconds": time.monotonic()-start, "active_call_seconds": active,
                  "waiting_seconds_added": 0, "project": str(root), "log": str(log)}
    except Exception as exc:
        result = {"passed": False, "error": f"{type(exc).__name__}: {exc}", "completed_cycles": count,
                  "calls": calls, "elapsed_seconds": time.monotonic()-start, "active_call_seconds": active,
                  "project": str(root), "log": str(log)}
        event(result)
    summary.write_bytes(json_bytes(result))
    return 0 if result["passed"] else 1


def fault_check(cycle, path, event):
    import win32gui, win32con
    from lasermaker_agent.windows_driver import WindowsDriver, DriverError, desktop_lock
    with desktop_lock():
        driver = WindowsDriver()
        w = driver.assert_document(Path(path).name)
        if cycle == 1:
            driver._menu(1)
            dialog = driver._common_dialog()
            try:
                try:
                    WindowsDriver()._idle()
                except DriverError as exc:
                    assert "UNEXPECTED_MODAL" in str(exc), str(exc)
                    event({"fault": "existing_native_file_dialog", "passed": True, "reason": str(exc)})
                else:
                    raise AssertionError("Unknown dialog was not rejected")
            finally:
                # Cancel only the exact harmless Open dialog this test created.
                if win32gui.IsWindow(dialog) and win32gui.GetClassName(dialog) == "#32770":
                    win32gui.PostMessage(dialog, win32con.WM_CLOSE, 0, 0)
                driver._wait(lambda: not win32gui.IsWindow(dialog))
        else:
            old = win32gui.GetWindowRect(w.handle)
            try:
                win32gui.SetWindowPos(w.handle, None, old[0]+30, old[1]+20, 0, 0,
                                     win32con.SWP_NOSIZE | win32con.SWP_NOZORDER)
                restored = WindowsDriver()._idle().rectangle()
                assert abs(restored.left-old[0]-30) <= 2 and abs(restored.top-old[1]-20) <= 2
                event({"fault": "window_moved_within_screen", "passed": True,
                       "recovered_rectangle": [restored.left, restored.top, restored.right, restored.bottom]})
            finally:
                win32gui.SetWindowPos(w.handle, None, old[0], old[1], old[2]-old[0], old[3]-old[1], win32con.SWP_NOZORDER)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--minutes", type=float, default=120)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.root, args.minutes)))
