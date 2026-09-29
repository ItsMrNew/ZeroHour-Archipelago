"""Stage the public Launcher and separate Windows downloads without rebuilding either."""
import hashlib
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from release_support import source_files


def main():
    version = "0.8.4"
    launcher = ROOT / "dist" / f"ZeroHour-Archipelago-{version}-Launcher"
    destination = ROOT / "dist" / f"GitHub-v{version}-Public"
    if destination.exists():
        raise SystemExit("Upload staging already exists; archive it before preparing again.")
    inputs = {
        f"ZeroHour-Archipelago-{version}-Launcher.zip": launcher.with_name(launcher.name + ".zip"),
        f"ZeroHour-Archipelago-{version}-Windows.zip": ROOT / "dist" / f"ZeroHour-Archipelago-{version}-Windows.zip",
        "generals_zh.apworld": launcher / "generals_zh.apworld",
        "README.md": ROOT / "README.md",
        "Zero Hour Options.html": launcher / "Zero Hour Options.html",
        "ZeroHour.yaml": launcher / "ZeroHour.yaml",
        "Optional-Mission-Start-Saves.zip": launcher / "Optional-Mission-Start-Saves.zip",
    }
    selected_source = list(source_files(ROOT))
    for path in inputs.values():
        if not path.is_file():
            raise SystemExit(f"Missing release file: {path.name}")
    if inputs["README.md"].read_bytes() != (launcher / "README.md").read_bytes():
        raise SystemExit("Rebuild the Launcher package with the current README before publishing.")
    destination.mkdir()
    for name, path in inputs.items():
        shutil.copyfile(path, destination / name)
    source_name = f"ZeroHour-Archipelago-{version}-Source"
    with zipfile.ZipFile(destination / (source_name + ".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        for path in selected_source:
            archive.write(path, source_name + "/" + path.relative_to(ROOT).as_posix())
    (destination / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
        for p in sorted(destination.iterdir()) if p.is_file()), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
