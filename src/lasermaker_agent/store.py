"""Atomic project snapshots, durable request receipts and cross-process locks."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from .geometry import apply_ops, validate


class ProjectError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


@contextlib.contextmanager
def file_lock(path, timeout=5):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ProjectError("RESOURCE_BUSY") from None
                time.sleep(.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        deadline = time.monotonic()+2
        while True:
            try:
                os.replace(temp, path)
                break
            except PermissionError as exc:
                # Antivirus/OneDrive can briefly open the destination without
                # FILE_SHARE_DELETE. Retry this exact prepared snapshot only.
                if getattr(exc, 'winerror', None) not in (5, 32, 33) or time.monotonic()>=deadline:
                    raise
                time.sleep(.05)
    finally:
        if temp.exists():
            temp.unlink()  # Only this function's checked, newly created temp file.


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.path = self.root / "project.json"
        self.lock = self.root / ".project.lock"

    def _load(self):
        if not self.path.is_file() or self.path.stat().st_size > 100*1024*1024:
            raise ProjectError("PROJECT_NOT_FOUND_OR_TOO_LARGE")
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("schema_version") != 1:
            raise ProjectError("UNSUPPORTED_PROJECT_VERSION")
        validate(state["design"])
        return state

    def _public(self, state):
        result = copy.deepcopy(state)
        result.pop("receipts", None)
        native = result.get("native")
        observed = None
        if native and self.output_path(native["path"]).is_file():
            observed = file_hash(self.output_path(native["path"]))
        result["native_observed_sha256"] = observed
        result["native_external_change"] = bool(native and observed != native["sha256"])
        return result

    def verified_native_bytes(self, state):
        native = state["native"]
        path = self.output_path(native["path"])
        if not path.is_file() or path.stat().st_size > 64*1024*1024:
            raise ProjectError("NATIVE_FILE_MISSING_OR_TOO_LARGE")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != native["sha256"]:
            raise ProjectError("NATIVE_CHANGED_DURING_COPY")
        return data

    def create(self, name, design):
        validate(design)
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ProjectError("INVALID_PROJECT_NAME")
        if self.root.exists() and any(self.root.iterdir()):
            raise ProjectError("PROJECT_DIRECTORY_MUST_BE_EMPTY")
        self.root.mkdir(parents=True, exist_ok=True)
        with file_lock(self.lock):
            if self.path.exists():
                raise ProjectError("PROJECT_ALREADY_EXISTS")
            state = {"schema_version": 1, "project_id": uuid.uuid4().hex, "name": name,
                     "revision": 0, "design": copy.deepcopy(design), "receipts": {},
                     "checkpoints": [], "native": None, "created_at": time.time()}
            atomic_write(self.path, json_bytes(state))
        return self._public(state)

    def read(self):
        with file_lock(self.lock):
            return self._public(self._load())

    def mutate(self, request_id, expected_revision, operations):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 160:
            raise ProjectError("REQUEST_ID_REQUIRED")
        payload_hash = digest({"expected_revision": expected_revision, "operations": operations})
        with file_lock(self.lock):
            state = self._load()
            if request_id in state["receipts"]:
                receipt = state["receipts"][request_id]
                if receipt["digest"] != payload_hash:
                    raise ProjectError("REQUEST_CONFLICT")
                return copy.deepcopy(receipt["result"])
            if expected_revision != state["revision"]:
                raise ProjectError("REVISION_CONFLICT")
            if self._public(state)["native_external_change"]:
                raise ProjectError("EXTERNAL_NATIVE_CHANGE_REQUIRES_FORK")
            design = apply_ops(state["design"], operations)
            state["design"] = design
            state["revision"] += 1
            result = {"project_id": state["project_id"], "revision": state["revision"],
                      "object_count": len(design["objects"]), "request_id": request_id}
            state["receipts"][request_id] = {"digest": payload_hash, "result": result}
            atomic_write(self.path, json_bytes(state))  # Receipt and edit commit together.
        return result

    def output_path(self, name):
        candidate = (self.root / name).resolve()
        if not candidate.is_relative_to(self.root) or candidate == self.root:
            raise ProjectError("OUTSIDE_PROJECT")
        rel = candidate.relative_to(self.root)
        if rel.parts[0] in ("project.json", ".project.lock", ".service.lock", "journal.jsonl"):
            raise ProjectError("RESERVED_PROJECT_PATH")
        return candidate

    def register_native(self, path, verification):
        path = self.output_path(Path(path))
        if not path.is_file():
            raise ProjectError("NATIVE_FILE_NOT_FOUND")
        with file_lock(self.lock):
            state = self._load()
            state["native"] = {"path": str(path.relative_to(self.root)), "sha256": file_hash(path),
                               "revision": state["revision"], "design_digest": digest(state["design"]),
                               "source_scope": verification.get("source_scope"),
                               "verification": verification}
            state.setdefault("native_catalog", {})[str(path.relative_to(self.root)).casefold()] = {
                key: copy.deepcopy(state["native"][key]) for key in ("revision", "design_digest", "sha256", "source_scope")}
            atomic_write(self.path, json_bytes(state))
        return state["native"]

    def checkpoint(self, label):
        if not isinstance(label, str) or not label or len(label) > 200:
            raise ProjectError("INVALID_CHECKPOINT_LABEL")
        with file_lock(self.lock):
            state = self._load()
            cid = uuid.uuid4().hex
            entry = {"id": cid, "label": label, "revision": state["revision"], "time": time.time(),
                     "path": f"checkpoints/{cid}.json"}
            snapshot = self._public(state)
            if state.get("native") and not snapshot["native_external_change"]:
                source = self.output_path(state["native"]["path"])
                target = self.output_path(f"checkpoints/{cid}.lcpx")
                atomic_write(target, self.verified_native_bytes(state))
                entry["native_path"] = str(target.relative_to(self.root))
            atomic_write(self.output_path(entry["path"]), json_bytes(snapshot))
            state["checkpoints"].append(entry)
            atomic_write(self.path, json_bytes(state))
        return entry

    def resume(self):
        # Resumption never rewinds the latest document to an older checkpoint.
        return self.read()
