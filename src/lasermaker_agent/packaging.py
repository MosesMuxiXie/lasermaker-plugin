"""Local archives from explicit allowlists, never the whole workspace."""
from pathlib import Path
import hashlib
import zipfile
from . import __version__

PLUGIN_CONTENT = ("plugin.json", "mcp.json", ".agents", ".claude-plugin", "kimi.plugin.json",
                  "package.json", "adapters", "skills", "docs", "examples", "README.md", "LICENSE",
                  "THIRD_PARTY_NOTICES.md", "licenses", "PUBLICATION.json", "README.zh-CN.md", "bin", "installer")
SOURCE_CONTENT = (*PLUGIN_CONTENT, "src", "tests", "scripts", "pyproject.toml", "requirements.lock.txt", "lasermaker-agent.spec", ".gitignore", ".gitattributes")


def _files(root, entries):
    for entry in entries:
        path = root / entry
        if not path.exists():
            continue
        if path.is_symlink():
            raise ValueError("SYMLINK_IN_RELEASE")
        if path.is_file():
            yield path
        else:
            for file in sorted(path.rglob("*")):
                if file.is_symlink():
                    raise ValueError("SYMLINK_IN_RELEASE")
                if file.is_file() and "__pycache__" not in file.parts and not file.name.endswith(".pyc"):
                    yield file


def package_release(root, runtime, output):
    root, runtime, output = (Path(p).resolve() for p in (root, runtime, output))
    if not (runtime / "lasermaker-agent.exe").is_file() or not (runtime / "_internal").is_dir():
        raise ValueError("COMPLETE_WINDOWS_RUNTIME_REQUIRED")
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for kind, entries in (("plugin", PLUGIN_CONTENT), ("source", SOURCE_CONTENT)):
        target = output / f"lasermaker-agent-{__version__}-{kind}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file in _files(root, entries):
                archive.write(file, "lasermaker-agent/" + file.relative_to(root).as_posix())
            if kind == "plugin":
                for file in _files(runtime, [p.name for p in runtime.iterdir()]):
                    archive.write(file, "lasermaker-agent/runtime/" + file.relative_to(runtime).as_posix())
        result[kind + "_zip"] = str(target)
    # Small native overlays share the portable core, rather than duplicating its runtime.
    for host, entries in {
        "codex": ("plugin.json", "mcp.json", ".agents"),
        "claude": (".claude-plugin", "adapters/claude.mcp.json"),
        "kimi": ("kimi.plugin.json",),
        "deepseek": ("package.json", "adapters/deepseek"),
    }.items():
        target = output / f"lasermaker-agent-{__version__}-{host}-adapter.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in _files(root, (*entries, "skills", "docs/安装.md", "LICENSE")):
                archive.write(file, "lasermaker-agent/" + file.relative_to(root).as_posix())
        result[host + "_adapter_zip"] = str(target)
    result["sha256"] = {}
    for key in tuple(k for k in result if k.endswith("_zip")):
        result["sha256"][Path(result[key]).name] = hashlib.sha256(Path(result[key]).read_bytes()).hexdigest()
    return result
