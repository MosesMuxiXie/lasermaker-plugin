import hashlib
import zipfile
from pathlib import Path
import pytest
from scripts.package_easy_install import assemble_bundle


def test_integration_bundle_keeps_runtime_and_manufacturing_bytes(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'README.md').write_text('English\n',encoding='utf-8')
    (source/'bin').mkdir();(source/'bin/cli.mjs').write_text('console.log("help");',encoding='utf-8')
    original=tmp_path/'base.zip'
    with zipfile.ZipFile(original,'w') as z:
        z.writestr('lasermaker-agent/runtime/lasermaker-agent.exe',b'verified binary')
        z.writestr('lasermaker-agent/examples/plan.lcpx',b'original manufacturing bytes')
        z.writestr('lasermaker-agent/README.md','old docs')
    manifest={'bundleVersion':'0.1.3','coreVersion':'0.1.2','sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'runtimeTreeSha256':'a'*64}
    output=tmp_path/'lasermaker-agent-0.1.3-plugin.zip'
    assemble_bundle(original,source,output,manifest,['README.md','bin'])
    with zipfile.ZipFile(output) as z:
        assert z.read('lasermaker-agent/runtime/lasermaker-agent.exe')==b'verified binary'
        assert z.read('lasermaker-agent/examples/plan.lcpx')==b'original manufacturing bytes'
        assert z.read('lasermaker-agent/README.md')==(source/'README.md').read_bytes()
        assert 'lasermaker-agent/bin/cli.mjs' in z.namelist()
    with pytest.raises(ValueError,match='NEW_OUTPUT'):assemble_bundle(original,source,output,manifest,['README.md'])


def test_integration_bundle_refuses_an_unverified_base_archive(tmp_path):
    original=tmp_path/'bad.zip';original.write_bytes(b'bad')
    with pytest.raises(ValueError,match='BASE_CHECKSUM'):
        assemble_bundle(original,tmp_path,tmp_path/'output.zip',{'sha256':'0'*64},[])
    assert not (tmp_path/'output.zip').exists()
