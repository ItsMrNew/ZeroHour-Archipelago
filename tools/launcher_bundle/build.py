"""Build the packaged Archipelago Launcher client without changing the Windows build."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MAIN = ROOT / "dist/ZeroHour-Archipelago-0.8.4-Windows"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build():
    release_name = "ZeroHour-Archipelago-0.8.4-Launcher"
    output = ROOT / "dist" / release_name
    zip_output = output.parent / (output.name + ".zip")
    if output.exists() or zip_output.exists():
        raise SystemExit("Launcher output already exists; archive it before rebuilding.")
    original = {p.relative_to(MAIN).as_posix(): p.read_bytes()
                for p in sorted(MAIN.rglob("*")) if p.is_file()}
    for required in ("ZeroHourClient.exe", "Diagnostics/ZeroHourClientConsole.exe", "generals_zh.apworld"):
        if required not in original:
            raise SystemExit(f"Missing known-good release file: {required}")
    payload_files = {name: data for name, data in original.items()
                     if name not in ("generals_zh.apworld", "Optional-Mission-Start-Saves.zip")}
    # The launcher distribution has its own installation instructions.
    readme = (ROOT / "README.md").read_bytes()
    payload_files["README.md"] = readme
    payload_files["docs/COMPATIBILITY.md"] = (ROOT / "docs/COMPATIBILITY.md").read_bytes()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload_files.items():
            archive.writestr(name, data)
    payload = stream.getvalue()
    manifest = {"release": release_name, "distribution": "archipelago_launcher", "client_version": "0.8.4",
                "base_world_sha256": sha(original["generals_zh.apworld"]),
                "payload_sha256": sha(payload),
                "files": {name: sha(data) for name, data in payload_files.items()}}
    output.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(original["generals_zh.apworld"])) as source:
        with zipfile.ZipFile(output / "generals_zh.apworld", "w", zipfile.ZIP_DEFLATED) as target:
            for entry in source.infolist():
                data = source.read(entry)
                if entry.filename == "generals_zh/__init__.py":
                    data += b"\n# Launcher integration is exclusive to the packaged launcher distribution.\nfrom .launcher_client import register as _register_launcher_client\n_register_launcher_client()\n"
                elif entry.filename == "generals_zh/docs/setup_en.md":
                    data = readme
                target.writestr(entry, data)
            target.writestr("generals_zh/launcher_client.py", (HERE / "launcher.py").read_bytes())
            target.writestr("generals_zh/launcher_bundle/client.zip", payload)
            target.writestr("generals_zh/launcher_bundle/manifest.json", json.dumps(manifest, indent=2))
            target.writestr("generals_zh/launcher_bundle/icon.png", (HERE / "icon.png").read_bytes())
    (output / "README.md").write_bytes(readme)
    for name in ("Zero Hour Options.html", "ZeroHour.yaml", "Optional-Mission-Start-Saves.zip"):
        (output / name).write_bytes(original[name])
    (output / "BUILD.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for name in ("THIRD_PARTY_NOTICES.md", *[n for n in original if n.startswith("licenses/")]):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original[name])
    (output / "SHA256SUMS.txt").write_text("".join(
        f"{sha(p.read_bytes())}  {p.relative_to(output).as_posix()}\n"
        for p in sorted(output.rglob("*")) if p.is_file()), encoding="utf-8")
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(output.rglob("*")):
            if file.is_file():
                archive.write(file, f"{release_name}/{file.relative_to(output).as_posix()}")
    assert all((MAIN / name).read_bytes() == data for name, data in original.items())
    print(output)


if __name__ == "__main__":
    build()
