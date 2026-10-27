"""Public exports must preserve design evidence and omit local-only state."""
import json
from pathlib import Path
import pytest
from scripts.prepare_public_release import redact_json, include_public_path, scan_public_tree


def test_public_filter_omits_private_work_and_failed_sessions():
    for path in ('work/account.json','.venv/token.txt','examples/creator-cockpit/private.lcpx',
                 'examples/original-workstation/superseded/old/project.json',
                 'examples/original-workstation/audit/host-codex-native.json',
                 'examples/original-workstation/sheet-1/project/operations/op.json',
                 'src/lasermaker_agent.egg-info/PKG-INFO','adapters/node_modules/account.json',
                 'tests/fixtures/cockpit-geometry.json'):
        assert not include_public_path(Path(path)),path
    for path in ('src/lasermaker_agent/geometry.py','examples/original-workstation/blueprint/dimensions.json',
                 'examples/original-workstation/sheet-1/project/project.json',
                 'examples/original-workstation/sheet-1/project/native/current.lcpx','LICENSE'):
        assert include_public_path(Path(path)),path


def test_redaction_removes_machine_binding_and_keeps_hash_and_relative_native():
    root=Path('D:/Private/Workspace').resolve()
    source={'gui_binding':{'pid':123},'native':{'sha256':'abc','path':'native/a.lcpx',
            'verification':{'path':str(root/'examples/a.lcpx'),'reopen_verified':True}},
            'runtime':str(root/'work/runtime.exe'),'design':{'objects':[]}}
    result=redact_json(source,root)
    assert 'gui_binding' not in result and result['native']['sha256']=='abc'
    assert result['native']['path']=='native/a.lcpx'
    assert result['native']['verification']['path']=='examples/a.lcpx'
    assert result['runtime']=='work/runtime.exe'
    assert source['gui_binding']['pid']==123


def test_public_scan_rejects_a_realistic_token_without_printing_it(tmp_path):
    (tmp_path/'safe.json').write_text('{"project":"relative/path"}',encoding='utf-8')
    assert scan_public_tree(tmp_path)==[]
    (tmp_path/'bad.txt').write_text('ghp_'+'a'*36,encoding='utf-8')
    result=scan_public_tree(tmp_path)
    assert result==[{'path':'bad.txt','code':'SECRET_PATTERN'}]


def test_private_content_hash_is_rejected_even_after_rename(tmp_path,monkeypatch):
    import hashlib
    import scripts.prepare_public_release as release
    data=b'private artwork stand-in for regression test'
    monkeypatch.setattr(release,'PRIVATE_HASHES',{hashlib.sha256(data).hexdigest()},raising=False)
    (tmp_path/'innocent-name.bin').write_bytes(data)
    assert release.scan_public_tree(tmp_path)==[{'path':'innocent-name.bin','code':'PRIVATE_ARTWORK_HASH'}]
