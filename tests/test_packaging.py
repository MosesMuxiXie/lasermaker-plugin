from pathlib import Path
import zipfile
import pytest
from lasermaker_agent.packaging import package_release


def test_release_is_self_contained_and_excludes_private_work_and_venv(tmp_path):
    root = tmp_path / "插件 path"
    root.mkdir()
    for name in ("plugin.json", "mcp.json", "kimi.plugin.json", "package.json", "README.md",
                 "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml"):
        (root / name).write_text("{}" if name.endswith(".json") else "fixture", encoding="utf-8")
    (root/'.gitattributes').write_text('examples/** -text\n',encoding='utf-8')
    (root/'PUBLICATION.json').write_text('{"private_artwork_excluded":true}',encoding='utf-8')
    for directory in ("src", "tests", "scripts", "skills", "docs", "adapters", "examples",
                      ".codex-plugin", ".claude-plugin", "work", ".venv"):
        (root / directory).mkdir()
        (root / directory / "entry.txt").write_text(directory, encoding="utf-8")
    runtime = root / "build-runtime"
    runtime.mkdir()
    (runtime / "lasermaker-agent.exe").write_bytes(b"MZ-test-fixture")
    (runtime / "_internal").mkdir()
    (runtime / "_internal" / "python312.dll").write_bytes(b"test-fixture")
    result = package_release(root, runtime, root / "dist")
    with zipfile.ZipFile(result["plugin_zip"]) as archive:
        names = set(archive.namelist())
        assert "lasermaker-agent/runtime/lasermaker-agent.exe" in names
        assert "lasermaker-agent/.claude-plugin/entry.txt" in names
        assert all("/work/" not in p and "/.venv/" not in p for p in names)
        assert "lasermaker-agent/runtime/_internal/python312.dll" in names
    with zipfile.ZipFile(result["source_zip"]) as archive:
        assert "lasermaker-agent/src/entry.txt" in archive.namelist()
        assert 'lasermaker-agent/.gitattributes' in archive.namelist()
        assert 'lasermaker-agent/PUBLICATION.json' in archive.namelist()
    assert len(result["sha256"]) == 6
    for host in ("codex", "claude", "kimi", "deepseek"):
        with zipfile.ZipFile(result[host + "_adapter_zip"]) as archive:
            assert all("/runtime/" not in n for n in archive.namelist())
            assert any("/skills/" in n for n in archive.namelist())


def test_release_without_runtime_fails_instead_of_shipping_a_stub(tmp_path):
    with pytest.raises(ValueError, match="RUNTIME"):
        package_release(tmp_path, tmp_path / "missing", tmp_path / "dist")
