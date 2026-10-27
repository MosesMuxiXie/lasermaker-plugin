"""Account-free Kimi native plugin loader and MCP probe, isolated local home."""
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    stage, home = root / "work/宿主插件 ref-v10 path", root / "work/hosts/kimi-ref-v10-home"
    home.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0));port = sock.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET"))}
    env["KIMI_CODE_HOME"] = str(home)
    log = root / "work/kimi-server-private.log"
    responses = []
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(["node", str(root / "work/hosts/node_modules/@moonshot-ai/kimi-code/dist/main.mjs"),
            "web", "--no-open", "--port", str(port), "--host", "127.0.0.1", "--debug-endpoints"],
            cwd=stage, env=env, stdout=output, stderr=output, creationflags=0x08000000)
        token = None
        def call(path, data=None):
            nonlocal token
            if token is None:
                tokens = list(home.rglob("server.token"))
                if not tokens:
                    raise RuntimeError("Local server token has not been created")
                token = tokens[0].read_text(encoding="utf-8").strip()
            request = urllib.request.Request(f"http://127.0.0.1:{port}"+path,
                data=None if data is None else json.dumps(data).encode(),
                headers={"Authorization": "Bearer "+token, "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read())
            responses.append({"path": path, "result": result})
            if result.get("code") not in (None, 0):
                raise RuntimeError(str(result))
            return result.get("data", result)
        try:
            deadline = time.monotonic()+45
            while True:
                try:
                    call("/api/v1/meta");break
                except Exception:
                    if time.monotonic() >= deadline or process.poll() is not None:
                        raise
                    time.sleep(.2)
            installed = call("/api/v1/plugins", {"source": str(stage)})
            plugins = call("/api/v1/plugins")
            servers = call("/api/v2/mcp/servers")
            server = next(s for s in servers if "lasermaker" in s["name"])
            probed = call("/api/v2/mcp/servers:test", {"name": server["name"]})
            if not probed["success"]:
                raise RuntimeError(str(probed))
            call("/api/v1/debug/channels")
            passed, error = True, None
        except Exception as exc:
            passed, error = False, f"{type(exc).__name__}: {exc}"
        finally:
            try:
                call("/api/v1/shutdown", {})
            except Exception:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=10)
    report = {"passed": passed, "error": error, "responses": responses, "model_turn_executed": False}
    (root / "work/host-kimi-native.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "error": error, "paths": [r["path"] for r in responses]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
