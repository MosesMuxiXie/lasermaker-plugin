"""Claude's SDK control channel: initialize/discover only, never submit a model prompt."""
import asyncio
import json
import os
import time
from pathlib import Path


async def run():
    root = Path(__file__).resolve().parent.parent
    stage = root / "work/宿主插件 ref-v10 path"
    workspace = root / "work/hosts/claude-workspace"
    workspace.mkdir(exist_ok=True)
    home = root / "work/hosts/claude-ref-v10-home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET"))}
    env["CLAUDE_CONFIG_DIR"] = str(home)
    executable = root / "work/hosts/node_modules/@anthropic-ai/claude-code-win32-x64/claude.exe"
    process = await asyncio.create_subprocess_exec(str(executable), "--print", "--input-format", "stream-json",
        "--output-format", "stream-json", "--verbose", "--plugin-dir", str(stage), cwd=workspace, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=0x08000000)
    pending, responses = {}, []
    async def reader():
        while line := await process.stdout.readline():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            response = value.get("response", {})
            request_id = response.get("request_id")
            if value.get("type") == "control_response" and request_id in pending:
                pending.pop(request_id).set_result(response)
        for future in pending.values():
            if not future.done():
                future.set_exception(RuntimeError("Claude control process closed"))
    task = asyncio.create_task(reader())
    stderr = asyncio.create_task(process.stderr.read())
    async def control(subtype, **kwargs):
        request_id = "smoke-"+str(len(responses))
        future = asyncio.get_running_loop().create_future()
        pending[request_id] = future
        message = {"type": "control_request", "request_id": request_id,
                   "request": {"subtype": subtype, **kwargs}}
        process.stdin.write((json.dumps(message)+"\n").encode())
        await process.stdin.drain()
        result = await asyncio.wait_for(future, 45)
        responses.append({"subtype": subtype, "response": result if subtype != "initialize" else
                          {"subtype": result.get("subtype"), "fields": sorted(result.get("response", {}))}})
        if result.get("subtype") != "success":
            raise RuntimeError(str(result))
        return result.get("response", {})
    try:
        await control("initialize", sdkMcpServers=[])
        deadline = time.monotonic()+30
        while True:
            status = await control("mcp_status")
            servers = status.get("mcpServers", [])
            matching = [s for s in servers if "lasermaker" in s.get("name", "")]
            if matching and all(s.get("status") != "pending" for s in matching):
                break
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(.5)
        if not matching or not any(s.get("status") == "connected" for s in matching):
            raise RuntimeError("Native plugin server was not connected: "+str(status))
        passed, error = True, None
    except Exception as exc:
        passed, error = False, f"{type(exc).__name__}: {exc}"
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except asyncio.TimeoutError:
            process.terminate();await process.wait()
        await task
        # Do not retain account/provider initialization data or ambient stderr.
        await stderr
    report = {"passed": passed, "error": error, "responses": responses, "model_turn_executed": False}
    (root / "work/host-claude-control.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "error": error, "controls": [r["subtype"] for r in responses]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())
