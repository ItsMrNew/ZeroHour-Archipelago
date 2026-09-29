"""Exercise a COPY of installed AP 0.6.7; never install into the real custom_worlds.

Opens and closes only test client windows. Does not connect to a room or the game.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / "build/launcher-bundle-audit/Archipelago sandbox"
INSTALLED = Path(r"C:\ProgramData\Archipelago")
PACKAGE = ROOT / "dist/ZeroHour-Archipelago-0.8.4-Launcher"


def windows():
    result = []
    user = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(hwnd, text, len(text))
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            result.append((hwnd, pid.value, text.value))
        return True
    user.EnumWindows(callback_type(visit), 0)
    return result


def main():
    SANDBOX.mkdir(parents=True, exist_ok=True)
    for directory in ("lib", "data", "share"):
        shutil.copytree(INSTALLED / directory, SANDBOX / directory, dirs_exist_ok=True)
    for name in ("ArchipelagoLauncher.exe", "python3.dll", "python313.dll"):
        shutil.copyfile(INSTALLED / name, SANDBOX / name)
    custom = SANDBOX / "custom_worlds"
    custom.mkdir(exist_ok=True)
    shutil.copyfile(PACKAGE / "generals_zh.apworld", custom / "generals_zh.apworld")
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(SANDBOX / "LocalAppData")
    env["APPDATA"] = str(SANDBOX / "AppData")
    env["KIVY_HOME"] = str(SANDBOX / "kivy")
    cache = Path(env["LOCALAPPDATA"]) / "ZeroHourArchipelagoLauncher"
    results = []
    for attempt in (1, 2):
        existing = {pid for _, pid, _ in windows()}
        log = SANDBOX / f"launch-{attempt}.txt"
        with log.open("wb") as output:
            launcher = subprocess.Popen([str(SANDBOX / "ArchipelagoLauncher.exe"),
                                         "Zero Hour Client"],
                                        cwd=SANDBOX, env=env, stdout=output, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            opened = None
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                for hwnd, pid, title in windows():
                    if pid not in existing and title.startswith("Zero Hour Archipelago 0.8.4"):
                        # Confirm this is OUR extracted test process, not a main client.
                        kernel = ctypes.windll.kernel32
                        kernel.OpenProcess.restype = wintypes.HANDLE
                        process = kernel.OpenProcess(0x1000, False, pid)
                        try:
                            path = ctypes.create_unicode_buffer(32768)
                            size = wintypes.DWORD(len(path))
                            kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                                        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
                            if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                                if Path(path.value).is_relative_to(cache):
                                    opened = (hwnd, pid, title, path.value)
                                    break
                        finally:
                            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                            kernel.CloseHandle(process)
                if opened:
                    break
                time.sleep(0.2)
            if not opened:
                raise AssertionError(f"Client did not appear. Inspect {log}")
            hwnd, pid, title, path = opened
            time.sleep(0.5)
            ctypes.windll.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            ctypes.windll.user32.PostMessageW(hwnd, 0x10, 0, 0)  # WM_CLOSE, only our verified window
            launcher.wait(timeout=10)
            results.append({"attempt": attempt, "launcher_exit": launcher.returncode,
                            "client_pid": pid, "window_title": title, "executable": path,
                            "client_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()})
            time.sleep(1)
            assert not any(window_pid == pid for _, window_pid, _ in windows())
    assert results[0]["executable"] == results[1]["executable"], "Second launch should reuse cache"
    assert all(result["launcher_exit"] == 0 for result in results)
    assert (cache / "UserData/ZeroHourArchipelago/launcher.json").is_file()
    (SANDBOX.parent / "packaged-launcher-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
