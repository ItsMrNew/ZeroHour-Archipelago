"""Build the apworld and copy the single shared mission table into it."""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    world = ROOT / "worlds" / "generals_zh"
    shutil.copyfile(ROOT / "zh" / "mission_data.py", world / "mission_data.py")
    shutil.copyfile(ROOT / "zh" / "trap_pool.py", world / "trap_pool.py")
    shutil.copyfile(ROOT / "zh" / "game_options.py", world / "game_options.py")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    package = output / "generals_zh.apworld"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        # APWorldContainer reads container metadata from the ZIP root. Keep the
        # source manifest free of these packaging-only compatibility fields.
        manifest = json.loads((world / "archipelago.json").read_text(encoding="utf-8"))
        manifest.update(version=7, compatible_version=7)
        archive.writestr("archipelago.json", json.dumps(manifest, indent=2) + "\n")
        for path in sorted(world.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, "generals_zh/" + path.relative_to(world).as_posix())
    print(package)


if __name__ == "__main__":
    main()
