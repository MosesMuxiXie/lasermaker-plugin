"""Account-free native Codex app-server plugin/tool smoke (tested CLI0.164)."""
import asyncio
import json
import os
import uuid
from pathlib import Path


async def run():
    root = Path(__file__).resolve().parent.parent
    stage = root / "work/宿主插件 ref-v10 path"
    home = root / "work/hosts/codex-ref-v10-home"
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET"))}
    env["CODEX_HOME"] = str(home)
    executable = root / "work/hosts/node_modules/@openai/codex/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
    if not executable.exists():
        matches = list((root / "work/hosts/node_modules").glob("@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"))
        if not matches:
            raise RuntimeError("Install @openai/codex under work/hosts before this optional smoke")
        executable = matches[0]
    process = await asyncio.create_subprocess_exec(str(executable), "app-server", cwd=stage, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    pending, events, responses = {}, [], []
    async def reader():
        while line := await process.stdout.readline():
            value = json.loads(line)
            if "id" in value and value["id"] in pending:
                pending.pop(value["id"]).set_result(value)
            else:
                events.append(value)
    task = asyncio.create_task(reader())
    errors = asyncio.create_task(process.stderr.read())
    async def request(method, params):
        index = len(responses)+1
        future = asyncio.get_running_loop().create_future()
        pending[index] = future
        process.stdin.write((json.dumps({"id": index, "method": method, "params": params})+"\n").encode())
        await process.stdin.drain()
        value = await asyncio.wait_for(future, 90)
        responses.append({"method": method, "response": value})
        if "error" in value:
            raise RuntimeError(str(value["error"]))
        return value["result"]
    try:
        await request("initialize", {"clientInfo": {"name": "lasermaker-plugin-smoke", "version": "0.1.0"},
                                     "capabilities": {"experimentalApi": True}})
        process.stdin.write(b'{"method":"initialized","params":{}}\n')
        await process.stdin.drain()
        catalog = await request("plugin/list", {"cwds": [str(stage)], "marketplaceKinds": ["local"]})
        marketplace = next(m for m in catalog["marketplaces"] if m["name"] == "lasermaker-local")
        await request("plugin/read", {"marketplacePath": marketplace["path"], "pluginName": "lasermaker-agent"})
        thread = await request("thread/start", {"cwd": str(stage), "ephemeral": True,
                                                "approvalPolicy": "never", "sandbox": "read-only"})
        tid = thread["thread"]["id"]
        status = await request("mcpServerStatus/list", {"threadId": tid, "detail": "toolsAndAuthOnly"})
        servers = status.get("data", [])
        matches = [s for s in servers if "lasermaker" in s.get("name", "")]
        if not matches:
            raise RuntimeError("Native plugin MCP was not discovered: " + str(status))
        result = await request("mcpServer/tool/call", {"threadId": tid, "server": matches[0]["name"], "tool": "doctor", "arguments": {}})
        if result.get("isError"):
            raise RuntimeError(str(result))
        assert len(matches[0]['tools'])==17
        async def plugin_call(name, arguments):
            value = await request('mcpServer/tool/call', {'threadId': tid, 'server': matches[0]['name'],
                'tool': name, 'arguments': arguments})
            assert not value.get('isError'), value
            return value['structuredContent']
        project = root/'work'/('cross-host-'+uuid.uuid4().hex[:8])/'project'
        if not (project/'project.json').exists():
            await plugin_call('create_project', {'root': str(project), 'name': '跨宿主接续与轮廓文字',
                'design': {'units':'mm','sheet_mm':[160,80],'objects':[]}})
        operations = [{'op':'add','object':{'id':'P-outer','part_id':'P','role':'cut_outer','closed':True,
                       'points':[[5,5],[65,5],[65,35],[5,35]]}},
                      {'op':'text','id':'label','part_id':'P','role':'score','text':'Laser O',
                       'height_mm':4,'position':[10,12],'font_path':'C:/Windows/Fonts/arial.ttf'}]
        edited = await plugin_call('apply_design_ops', {'root':str(project),'request_id':'codex-native-edit-001',
            'expected_revision':0,'operations':operations})
        assert edited['revision']==1
        report = await plugin_call('preflight', {'root':str(project)})
        assert report['geometry_passed'], report
        await plugin_call('checkpoint', {'root':str(project),'label':'Codex native saved revision 1'})
        (root/'work/host-handoff-project.json').write_text(json.dumps({'root':str(project)}),encoding='utf-8')
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
        stderr = (await errors).decode("utf-8", errors="replace")
        report = {"passed": passed, "error": error, "responses": responses,
                  "event_methods": sorted({e.get("method", "response") for e in events}),
                  "stderr": stderr[-6000:], "model_turn_executed": False}
        (root / "work/host-codex-native.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"passed": passed, "error": error, "methods": [r["method"] for r in responses]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())

