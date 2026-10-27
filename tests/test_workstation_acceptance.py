"""The acceptance harness must not manufacture success while resuming."""
import copy
import json
from pathlib import Path
import pytest
from lasermaker_agent.store import digest,json_bytes
from scripts.verify_workstation import verify_completed_native


def test_completed_native_cache_rejects_external_change_and_source_change(tmp_path):
    design={'units':'mm','objects':[]};project=tmp_path/'project';(project/'native').mkdir(parents=True)
    file=project/'native/test.lcpx';file.write_bytes(b'native evidence')
    import hashlib
    sha=hashlib.sha256(file.read_bytes()).hexdigest()
    (tmp_path/'design.json').write_bytes(json_bytes(design))
    state={'project_id':'test-id','revision':1,'design':design,'native_parameters_dirty':False,'native_external_change':False,
        'native':{'path':'native/test.lcpx','sha256':sha,'revision':1,'design_digest':digest(design),
            'verification':{'reopen_verified':True},'source_scope':{'complete':True}}}
    record={'project_id':'test-id','revision':1,'design_digest':digest(design),'native_current':True,'native_sha256':sha,
            'source_sha256':hashlib.sha256((tmp_path/'design.json').read_bytes()).hexdigest()}
    (tmp_path/'native-verification.json').write_bytes(json_bytes(record))
    (tmp_path/'delivery.json').write_bytes(json_bytes({'native_current':True,'process_settings_verified':True,
        'artifacts':{'native':'project/native/test.lcpx'},'sha256':{'native':sha}}))
    assert verify_completed_native(tmp_path,state,design)==record
    for change in ({'native_external_change':True},{'native_parameters_dirty':True},{'revision':2}):
        with pytest.raises(ValueError):verify_completed_native(tmp_path,{**state,**change},design)
    file.write_bytes(b'external replacement')
    with pytest.raises(ValueError):verify_completed_native(tmp_path,state,design)
    file.write_bytes(b'native evidence')
    (tmp_path/'design.json').write_bytes(b'changed source')
    with pytest.raises(ValueError):verify_completed_native(tmp_path,state,design)
