import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location("launcher_adapter", Path(__file__).with_name("launcher.py"))
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    resource = tmp_path / "resources"
    resource.mkdir()
    contents = {"ZeroHourClient.exe": b"test executable", "licenses/test.txt": b"license"}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    payload = stream.getvalue()
    manifest = {"payload_sha256": hashlib.sha256(payload).hexdigest(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    (resource / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (resource / "client.zip").write_bytes(payload)
    monkeypatch.setattr(adapter, "resources", lambda: resource)
    return resource, tmp_path / "cache with spaces & punctuation", manifest


def test_extract_and_reuse_without_rewriting(bundle):
    _, root, _ = bundle
    first = adapter.prepare_client(root)
    before = first.stat().st_mtime_ns
    assert first.read_bytes() == b"test executable"
    assert adapter.prepare_client(root) == first
    assert first.stat().st_mtime_ns == before
    assert (first.parent / "licenses/test.txt").read_bytes() == b"license"


def test_damaged_cache_is_preserved_and_repaired(bundle):
    _, root, _ = bundle
    first = adapter.prepare_client(root)
    first.write_bytes(b"damaged")
    assert adapter.prepare_client(root).read_bytes() == b"test executable"
    backups = list((root / "clients").glob("*.damaged-*/ZeroHourClient.exe"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"damaged"


def test_bad_payload_is_not_extracted(bundle):
    resource, root, _ = bundle
    (resource / "client.zip").write_bytes(b"broken zip")
    with pytest.raises(RuntimeError, match="damaged"):
        adapter.prepare_client(root)
    assert not list(root.rglob("*.exe"))


def test_wrong_file_digest_is_not_published(bundle):
    resource, root, manifest = bundle
    manifest["files"]["ZeroHourClient.exe"] = "0" * 64
    (resource / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="integrity"):
        adapter.prepare_client(root)
    assert not list(root.rglob("*.exe"))


@pytest.mark.parametrize("name", ["../escape.exe", "/escape.exe", "C:/escape.exe", "a\\b",
                                  "a/../b", "a//b", "a/./b", "a:stream", "a./b", "a /b", ""])
def test_reject_unsafe_archive_names(name):
    with pytest.raises(RuntimeError):
        adapter.validate_names([name])


def test_reject_case_collisions():
    with pytest.raises(RuntimeError):
        adapter.validate_names(["Client.exe", "client.exe"])


def test_missing_and_extra_files_rejected(bundle):
    resource, root, manifest = bundle
    manifest["files"]["extra.txt"] = "0" * 64
    (resource / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="file list"):
        adapter.prepare_client(root)


def test_child_settings_and_bootloader_environment_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "normal"))
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "parent-runtime")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ap/ArchipelagoLauncher.exe"))
    monkeypatch.setenv("PATH", str(tmp_path / "ap/lib") + adapter.os.pathsep + str(tmp_path / "unrelated"))
    root = adapter.cache_root()
    env = adapter.client_environment(root)
    assert env["LOCALAPPDATA"] == str(root / "UserData")
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "_PYI_APPLICATION_HOME_DIR" not in env
    assert env["PATH"] == str(tmp_path / "unrelated")
    assert adapter.os.environ["LOCALAPPDATA"] == str(tmp_path / "normal")
    assert adapter.os.environ["_PYI_APPLICATION_HOME_DIR"] == "parent-runtime"


def test_registration_is_idempotent_and_does_not_extract(monkeypatch):
    module = ModuleType("worlds.LauncherComponents")
    module.components = []
    module.icon_paths = {}
    module.Type = SimpleNamespace(CLIENT="client")
    module.Component = lambda name, **kwargs: SimpleNamespace(display_name=name, **kwargs)
    monkeypatch.setitem(sys.modules, "worlds.LauncherComponents", module)
    monkeypatch.setattr(adapter, "resources", lambda: pytest.fail("registration must not extract"))
    adapter.register()
    adapter.register()
    assert len(module.components) == 1
    component = module.components[0]
    assert component.display_name == "Zero Hour Client"
    assert "preview" not in component.description.lower()
    assert "experimental" not in component.description.lower()
    assert component.func is adapter.launch_client
    assert component.component_type == "client"
    assert not component.supports_uri


def test_launch_uses_exe_and_never_shell(bundle, monkeypatch):
    _, root, _ = bundle
    monkeypatch.setattr(adapter, "cache_root", lambda: root)
    calls = []
    def popen(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(adapter.subprocess, "Popen", popen)
    assert adapter.launch_client().pid == 123
    args, kwargs = calls[0]
    assert len(args) == 1 and args[0].endswith("ZeroHourClient.exe")
    assert kwargs["cwd"] == str(Path(args[0]).parent)
    assert not kwargs.get("shell")
    assert kwargs["env"]["LOCALAPPDATA"] == str(root / "UserData")


def test_unsupported_platform_shows_actionable_error(monkeypatch):
    messages = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "Utils", SimpleNamespace(messagebox=lambda *a, **kw: messages.append(a)))
    assert adapter.launch_client() is None
    assert "Windows" in messages[0][1]


def test_launch_failure_shows_error(bundle, monkeypatch):
    _, root, _ = bundle
    messages = []
    monkeypatch.setattr(adapter, "cache_root", lambda: root)
    def denied(*a, **kw):
        raise PermissionError("Access denied")
    monkeypatch.setattr(adapter.subprocess, "Popen", denied)
    monkeypatch.setitem(sys.modules, "Utils", SimpleNamespace(messagebox=lambda *a, **kw: messages.append(a)))
    assert adapter.launch_client() is None
    assert "Access denied" in messages[0][1]
