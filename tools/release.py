"""Build the current portable release from a clean, explicit set of files."""
from importlib import metadata
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from build import ROOT, main as build_world
from build_save_pack import main as build_save_pack
from release_support import prepare_uploads, write_version_file

sys.path.insert(0, str(ROOT))
from zh.version import VERSION

RELEASE_NAME = f"ZeroHour-Archipelago-{VERSION}-Windows"
DIAGNOSTICS = ("Watch Game.cmd", "Inspect Dozer.cmd", "Inspect Builders.cmd",
               "Inspect Effects.cmd", "Inspect DeathLink.cmd", "Check Compatibility.cmd")


def main(archive_only=False):
    build_world()
    save_pack = build_save_pack()
    release = ROOT / "dist" / RELEASE_NAME
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    version_file = build / 'windows-version.txt'
    write_version_file(version_file, VERSION)
    # Empty staging prevents local progress or obsolete seeds entering the ZIP.
    with tempfile.TemporaryDirectory(prefix="release-", dir=build) as directory:
        stage = Path(directory)
        subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--windowed",
                        "--version-file", str(version_file),
                        "--icon", str(ROOT / "assets/zero_hour_archipelago.ico"),
                        "--add-data", str(ROOT / "assets/zero_hour_archipelago.ico") + ";assets",
                        "--name", "ZeroHourClient", "--noconfirm", "--distpath", str(stage),
                        "--specpath", str(build), str(ROOT / "ZeroHourClient.py")],
                       cwd=ROOT, check=True)
        shutil.copyfile(ROOT / "assets/zero_hour_archipelago.ico", stage / "ZeroHourArchipelago.ico")
        shutil.copyfile(save_pack, stage / "Optional-Mission-Start-Saves.zip")
        shutil.copyfile(ROOT / "dist/generals_zh.apworld", stage / "generals_zh.apworld")
        shutil.copyfile(ROOT / "Zero Hour Options.html", stage / "Zero Hour Options.html")
        shutil.copyfile(ROOT / "players/ZeroHour.yaml", stage / "ZeroHour.yaml")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme = readme.split("## Source workspace", 1)[0]
        readme = readme.replace("dist/generals_zh.apworld", "generals_zh.apworld")
        readme = readme.replace("players/ZeroHour.yaml", "ZeroHour.yaml")
        readme = readme.replace("tools/diagnostics/", "Diagnostics/")
        (stage / "README.md").write_text(readme, encoding="utf-8")
        (stage / 'docs').mkdir()
        for name in ('COMPATIBILITY.md', 'EA_APP_VALIDATION.md'):
            shutil.copyfile(ROOT / 'docs' / name, stage / 'docs' / name)
        for name in ('THIRD_PARTY_NOTICES.md', 'CHANGELOG.md'):
            shutil.copyfile(ROOT / name, stage / name)
        diagnostics = stage / "Diagnostics"
        diagnostics.mkdir()
        subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--console",
                        "--version-file", str(version_file),
                        "--icon", str(ROOT / "assets/zero_hour_archipelago.ico"),
                        "--name", "ZeroHourClientConsole", "--noconfirm", "--distpath", str(diagnostics),
                        "--specpath", str(build), str(ROOT / "ZeroHourConsole.py")],
                       cwd=ROOT, check=True)
        for name in DIAGNOSTICS:
            content = (ROOT / "tools/diagnostics" / name).read_text(encoding="utf-8")
            (diagnostics / name).write_text(content, encoding="utf-8")
        licenses = stage / "licenses"
        licenses.mkdir()
        for package in ('websockets', 'pyinstaller'):
            distribution = metadata.distribution(package)
            for file in distribution.files or []:
                if 'LICENSE' in file.name.upper() or 'COPYING' in file.name.upper():
                    shutil.copyfile(distribution.locate_file(file), licenses / f'{package}-{file.name}')
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        if python_license.exists():
            shutil.copyfile(python_license, licenses / "Python-LICENSE.txt")
        for component in ('tcl8.6', 'tk8.6'):
            license_file = Path(sys.base_prefix) / 'tcl' / component / 'license.terms'
            if component == 'tcl8.6' and not license_file.is_file():
                license_file = ROOT / 'assets/licenses/Tcl-license.terms'
            if not license_file.is_file():
                raise FileNotFoundError(f'Missing bundled {component} license: {license_file}')
            shutil.copyfile(license_file, licenses / f'{component}-license.terms')
        archive_path = release.parent / (release.name + ".zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(stage.rglob("*")):
                if file.is_file():
                    archive.write(file, release.name + "/" + file.relative_to(stage).as_posix())
        # Archive-only permits packaging while the installed client is running.
        # Publish staged files while preserving any local user files.
        if not archive_only:
            shutil.copytree(stage, release, dirs_exist_ok=True)
    print(archive_path)
    print(prepare_uploads(ROOT, VERSION, archive_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-only", action="store_true",
                        help="Build the ZIP without overwriting an extracted client that may be running.")
    main(archive_only=parser.parse_args().archive_only)
