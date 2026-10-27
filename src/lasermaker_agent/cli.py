"""CLI and MCP share exactly the same operations and error contracts."""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .service import Service, TOOLS


def _execute(payload):
    try:
        return {"ok": True, "result": Service().call(payload["name"], payload.get("arguments", {}))}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    if "--worker" in sys.argv:
        data = sys.stdin.buffer.read(16*1024*1024+1)
        if len(data) > 16*1024*1024:
            response = {"ok": False, "error": "INPUT_TOO_LARGE"}
        else:
            try:
                response = _execute(json.loads(data))
            except Exception as exc:
                response = {"ok": False, "error": f"INVALID_JSON: {exc}"}
        print(json.dumps(response, ensure_ascii=False, allow_nan=False))
        return 0 if response["ok"] else 1
    parser = argparse.ArgumentParser(description="LaserMaker Agent — local geometry, GUI, MCP")
    parser.add_argument("command", choices=["mcp", "tools", *TOOLS], nargs="?", default="doctor")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", default=None, help="JSON arguments (quote for your shell)")
    group.add_argument("--args-file", type=Path, help="UTF-8 JSON arguments file; recommended for paths")
    args = parser.parse_args()
    if args.command == "mcp":
        from .server import run
        asyncio.run(run())
        return 0
    if args.command == "tools":
        print(json.dumps(TOOLS, ensure_ascii=False, indent=2))
        return 0
    try:
        arguments = json.loads(args.args_file.read_text(encoding="utf-8-sig") if args.args_file else args.json or "{}")
        response = _execute({"name": args.command, "arguments": arguments})
    except Exception as exc:
        response = {"ok": False, "error": f"INVALID_ARGUMENTS: {exc}"}
    print(json.dumps(response, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if response["ok"] else 1
