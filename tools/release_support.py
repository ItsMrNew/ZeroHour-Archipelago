"""Explicit source packaging, Windows metadata and GitHub upload artifacts."""
import hashlib
from pathlib import Path
import shutil
import zipfile


SOURCE_FILES = ('.gitignore', 'README.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md',
                'requirements.txt', 'requirements-dev.txt', 'ZeroHourClient.py',
                'ZeroHourConsole.py', 'CheckMissionDifficulty.py',
                'Start Client.cmd', 'Zero Hour Options.html',
                'players/ZeroHour.yaml', 'assets/zero_hour_archipelago.ico',
                'assets/zero_hour_archipelago.png', 'assets/licenses/Tcl-license.terms')
SOURCE_DIRS = ('.github', 'zh', 'worlds/generals_zh', 'tests', 'tools', 'docs')
SOURCE_SUFFIXES = {'.py', '.cjs', '.json', '.md', '.txt', '.cmd', '.ps1', '.yml', '.yaml'}


def source_files(root):
    """Never recurse through the workspace root, local archives or player folders."""
    root = Path(root).resolve()
    selected = {root / name for name in SOURCE_FILES}
    for name in SOURCE_DIRS:
        for path in (root / name).rglob('*'):
            if (path.is_file() and not path.is_symlink()
                    and '__pycache__' not in path.parts
                    and path.suffix.lower() in SOURCE_SUFFIXES):
                selected.add(path)
    for path in sorted(selected):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Missing or unsafe source file: {path.name}')
        yield path


def write_version_file(path, version):
    numbers = tuple(int(part) for part in version.split('.'))
    if len(numbers) != 3 or any(not 0 <= n <= 65535 for n in numbers):
        raise ValueError('Expected a three-part Windows release version')
    fields = dict(FileDescription='Zero Hour Archipelago - Steam preview',
                  FileVersion=version, ProductName='Zero Hour Archipelago',
                  ProductVersion=version)
    text = ('VSVersionInfo(ffi=FixedFileInfo(filevers=' + repr(numbers + (0,))
            + ', prodvers=' + repr(numbers + (0,))
            + ', mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), '
            + 'kids=[StringFileInfo([StringTable("040904B0", ['
            + ','.join(f'StringStruct({k!r},{v!r})' for k, v in fields.items())
            + '])]), VarFileInfo([VarStruct("Translation", [1033,1200])])])\n')
    Path(path).write_text(text, encoding='utf-8')


def prepare_uploads(root, version, player_zip):
    root = Path(root)
    uploads = root / 'dist' / f'GitHub-v{version}'
    uploads.mkdir(exist_ok=True)
    source = uploads / f'ZeroHour-Archipelago-{version}-Source.zip'
    prefix = f'ZeroHour-Archipelago-{version}-Source/'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in source_files(root):
            archive.write(path, prefix + path.relative_to(root.resolve()).as_posix())
    player = uploads / player_zip.name
    shutil.copyfile(player_zip, player)
    world = uploads / 'generals_zh.apworld'
    shutil.copyfile(root / 'dist/generals_zh.apworld', world)
    notes = uploads / 'RELEASE_NOTES.md'
    shutil.copyfile(root / f'docs/releases/{version}.md', notes)
    sums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
                   for p in (player, source, world, notes))
    (uploads / 'SHA256SUMS.txt').write_text(sums, encoding='ascii')
    return uploads
