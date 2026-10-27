import pytest
from lasermaker_agent.store import ProjectStore, ProjectError


def test_durable_mutation_retry_is_exactly_once(tmp_path):
    store = ProjectStore(tmp_path / "project")
    store.create("Example", {"units": "mm", "objects": []})
    first = store.mutate("request-1", 0, [{"op": "add", "object": {"id": "a", "role": "score",
               "closed": False, "points": [[1, 2], [3, 4]]}}])
    retry = ProjectStore(store.root).mutate("request-1", 0, [{"op": "add", "object": {
               "id": "a", "role": "score", "closed": False, "points": [[1, 2], [3, 4]]}}])
    assert first == retry
    assert store.read()["revision"] == 1
    assert len(store.read()["design"]["objects"]) == 1
    with pytest.raises(ProjectError, match="REQUEST_CONFLICT"):
        store.mutate("request-1", 0, [])


def test_failed_batch_and_stale_revision_do_not_change_project(tmp_path):
    store = ProjectStore(tmp_path / "project")
    store.create("Example", {"units": "mm", "objects": []})
    with pytest.raises(ValueError):
        store.mutate("bad", 0, [{"op": "move", "ids": ["missing"], "dx": 1, "dy": 0}])
    assert store.read()["revision"] == 0
    with pytest.raises(ProjectError, match="REVISION_CONFLICT"):
        store.mutate("stale", 5, [])


def test_checkpoint_resume_does_not_lose_latest_revision(tmp_path):
    store = ProjectStore(tmp_path / "project")
    store.create("Example", {"units": "mm", "objects": []})
    checkpoint = store.checkpoint("first")
    store.mutate("next", 0, [])
    resumed = ProjectStore(store.root).resume()
    assert resumed["revision"] == 1
    assert checkpoint["revision"] == 0
    assert resumed["checkpoints"][0]["label"] == "first"
    with pytest.raises(ProjectError, match="OUTSIDE_PROJECT"):
        store.output_path("../escape.svg")


def test_native_external_fork_is_detected_and_not_overwritten(tmp_path):
    store = ProjectStore(tmp_path / "project")
    store.create("Example", {"units": "mm", "objects": []})
    native = store.output_path("native/test.lcpx")
    native.parent.mkdir(parents=True)
    native.write_bytes(b"initial")
    store.register_native(native, {"verified": True})
    native.write_bytes(b"user changed it")
    assert store.resume()["native_external_change"] is True
    assert native.read_bytes() == b"user changed it"
def test_atomic_replace_retries_only_transient_windows_sharing_errors(tmp_path, monkeypatch):
    import os
    from lasermaker_agent.store import atomic_write
    target = tmp_path/'state.json'
    target.write_bytes(b'old')
    actual_replace = os.replace
    attempts = []
    def flaky(source, destination):
        attempts.append(source)
        if len(attempts)<3:
            exc = PermissionError('OneDrive sharing violation')
            exc.winerror = 5
            assert target.read_bytes()==b'old'
            raise exc
        actual_replace(source, destination)
    monkeypatch.setattr(os, 'replace', flaky)
    atomic_write(target, b'new')
    assert target.read_bytes()==b'new'
    assert len(attempts)==3 and len(set(attempts))==1
    assert list(tmp_path.iterdir())==[target]


def test_atomic_replace_does_not_retry_other_permission_failures(tmp_path, monkeypatch):
    import os
    from lasermaker_agent.store import atomic_write
    target = tmp_path/'state.json'
    target.write_bytes(b'original')
    attempts = []
    def denied(*args):
        attempts.append(args)
        raise PermissionError('permanent permission problem')
    monkeypatch.setattr(os, 'replace', denied)
    with pytest.raises(PermissionError):
        atomic_write(target, b'new')
    assert target.read_bytes()==b'original' and len(attempts)==1
    assert list(tmp_path.iterdir())==[target]


