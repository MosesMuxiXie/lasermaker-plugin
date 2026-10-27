"""Official MCP SDK transport; each tool runs in a bounded cancellable child."""
import asyncio
import json
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from . import __version__
from .service import TOOLS

server = Server("lasermaker-agent", version=__version__,
                instructions="Use canonical mm geometry and checkpoints. Native diagnostics are not machining proof. "
                "Never transmit/start a laser. GUI mutations require fresh revision and durable request_id.")


def child_command():
    return [sys.executable, "--worker"] if getattr(sys, "frozen", False) else [
        sys.executable, "-X", "utf8", "-m", "lasermaker_agent", "--worker"]


@server.list_tools()
async def list_tools():
    return [Tool(name=name, description=spec["description"], inputSchema=spec["inputSchema"])
            for name, spec in TOOLS.items()]


@server.call_tool()
async def call_tool(name, arguments):
    payload = json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False, allow_nan=False).encode("utf-8")
    process = await asyncio.create_subprocess_exec(*child_command(), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW for helper only.
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(payload), timeout=90)
        response = json.loads(stdout.decode("utf-8"))
        if process.returncode or not response.get("ok"):
            return CallToolResult(isError=True, content=[TextContent(type="text", text=response.get(
                "error", stderr.decode("utf-8", errors="replace")[-1000:]))])
        result = response["result"]
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False,
                              allow_nan=False))], structuredContent=result)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.terminate()
            await process.wait()
        if sys.exc_info()[0] is asyncio.CancelledError:
            raise
        return CallToolResult(isError=True, content=[TextContent(type="text",
            text="CALL_TIMEOUT: worker stopped; inspect request receipt before retrying a UI mutation.")])
    except Exception as exc:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        return CallToolResult(isError=True, content=[TextContent(type="text",
            text=f"WORKER_PROTOCOL_ERROR: {type(exc).__name__}: {exc}")])


async def run():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())
