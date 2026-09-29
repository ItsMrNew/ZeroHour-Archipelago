import hashlib
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from release_support import SOURCE_FILES, source_files, prepare_uploads, write_version_file
from zh.compatibility_report import executable_report
from zh.version import VERSION


def test_report_rejects_bad_files_and_preserves_hash_without_private_path(tmp_path):
    path = tmp_path / 'Game.dat'
    path.write_bytes(b'not an engine')
    result = executable_report(path)
    assert not result['native_layout_verified']
    assert result['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert str(tmp_path) not in str(result)
    path.unlink()
    result = executable_report(path)
    assert not result['native_layout_verified']
    assert str(tmp_path) not in str(result)


def test_passing_layout_does_not_claim_storefront_or_runtime_certification(tmp_path, monkeypatch):
    path = tmp_path / 'OtherEngine.exe'
    path.write_bytes(b'fixture')
    monkeypatch.setattr('zh.compatibility_report.resolve', lambda data: {1: 2, 3: 4})
    result = executable_report(path)
    assert result['native_layout_verified'] and result['verified_anchors'] == 2
    assert 'Not inferred' in result['store_identity']
    assert 'Not checked' in result['runtime_modifications']
    assert 'does not certify' in result['guidance']


def test_cli_report_never_attaches_or_contacts_server(tmp_path, monkeypatch, capsys):
    from zh import client
    path = tmp_path / 'Game.dat'; path.write_bytes(b'bad')
    monkeypatch.setattr(sys, 'argv', ['client', '--check-executable', str(path)])
    monkeypatch.setattr(client.GameMemory, 'find', lambda: pytest.fail('No live attachment'))
    monkeypatch.setattr(client.ZeroHourClient, 'run', lambda: pytest.fail('No server connection'))
    assert client.main() == 1
    assert '"native_layout_verified": false' in capsys.readouterr().out


def test_source_and_upload_packages_exclude_private_generated_files(tmp_path):
    for name in SOURCE_FILES:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('source fixture')
    for name in (f'docs/releases/{VERSION}.md', 'zh/version.py', 'tests/test_public.py'):
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('source fixture')
    private = ('.env', '.codex-remote-attachments/screenshot.png', '.research/Game.dat',
               '.cleanup-archive/old.txt', 'build/secret.py', 'players/Private.yaml',
               'dist/private.archipelago', 'zh/__pycache__/old.pyc')
    for name in private:
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('private fixture')
    selected = {p.relative_to(tmp_path).as_posix() for p in source_files(tmp_path)}
    assert not selected.intersection(private)
    assert 'zh/version.py' in selected and 'players/ZeroHour.yaml' in selected
    player = tmp_path / 'dist/Player.zip'; player.write_bytes(b'player fixture')
    (tmp_path / 'dist/generals_zh.apworld').write_bytes(b'world fixture')
    uploads = prepare_uploads(tmp_path, VERSION, player)
    with ZipFile(uploads / f'ZeroHour-Archipelago-{VERSION}-Source.zip') as archive:
        assert archive.testzip() is None
        assert {n.split('/', 1)[1] for n in archive.namelist()} == selected
    for line in (uploads / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ')
        assert hashlib.sha256((uploads / name).read_bytes()).hexdigest() == digest


def test_windows_version_metadata(tmp_path):
    from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
    path = tmp_path / 'version.txt'
    write_version_file(path, VERSION)
    info = load_version_info_from_text_file(str(path))
    major, minor, patch = map(int, VERSION.split('.'))
    assert info.ffi.fileVersionMS == (major << 16) | minor
    assert info.ffi.fileVersionLS == patch << 16
