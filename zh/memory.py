"""Win32 adapter for the supported Steam executable family.

Reads by default. Effect adapters request checked writes. The power adapter can
allocate a game-thread callback thunk and replace a private instance vtable.
Native addresses are resolved by checked instruction anchors. No on-disk patches.
"""

import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import os
from pathlib import Path
import struct

from .detector import Snapshot
from .compatibility import NativeBase, validate_executable

SUPPORTED_SHA256 = "420fba1dbdc4c14e2418c2b0d3010b9fac6f314eafa1f3a101805b8d98883ea1"
CAMPAIGN_GLOBAL_RVA = 0x639FC8
CAMPAIGN_VTABLE_RVA = 0x54E610


class MemoryReadError(OSError):
    pass


class UnsupportedGame(MemoryReadError):
    pass


def windows_error(action, pid, code):
    if code == 5:
        return MemoryReadError(
            f"Access denied to game process {pid}. Close this client, then right-click "
            "Start Client.cmd (or ZeroHourClient.exe) and choose Run as administrator. "
            "The client needs permission to read the elevated game."
        )
    return MemoryReadError(f"Cannot {action} process {pid} (Windows error {code}).")


class PROCESSENTRY32W(ct.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ct.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", wt.LONG), ("dwFlags", wt.DWORD), ("szExeFile", wt.WCHAR * 260)]


class MODULEENTRY32W(ct.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ct.c_void_p), ("modBaseSize", wt.DWORD), ("hModule", wt.HMODULE),
                ("szModule", wt.WCHAR * 256), ("szExePath", wt.WCHAR * 260)]


def kernel():
    if os.name != "nt":
        raise MemoryReadError("Automatic game detection requires Windows.")
    api = ct.WinDLL("kernel32", use_last_error=True)
    definitions = {
        "CreateToolhelp32Snapshot": ([wt.DWORD, wt.DWORD], wt.HANDLE),
        "Process32FirstW": ([wt.HANDLE, ct.POINTER(PROCESSENTRY32W)], wt.BOOL),
        "Process32NextW": ([wt.HANDLE, ct.POINTER(PROCESSENTRY32W)], wt.BOOL),
        "Module32FirstW": ([wt.HANDLE, ct.POINTER(MODULEENTRY32W)], wt.BOOL),
        "OpenProcess": ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
        "ReadProcessMemory": ([wt.HANDLE, ct.c_void_p, ct.c_void_p, ct.c_size_t,
                               ct.POINTER(ct.c_size_t)], wt.BOOL),
        "WriteProcessMemory": ([wt.HANDLE, ct.c_void_p, ct.c_void_p, ct.c_size_t,
                                ct.POINTER(ct.c_size_t)], wt.BOOL),
        "CloseHandle": ([wt.HANDLE], wt.BOOL),
        "GetExitCodeProcess": ([wt.HANDLE, ct.POINTER(wt.DWORD)], wt.BOOL),
        "VirtualAllocEx": ([wt.HANDLE, ct.c_void_p, ct.c_size_t, wt.DWORD, wt.DWORD], ct.c_void_p),
        "VirtualProtectEx": ([wt.HANDLE, ct.c_void_p, ct.c_size_t, wt.DWORD, ct.POINTER(wt.DWORD)], wt.BOOL),
        "FlushInstructionCache": ([wt.HANDLE, ct.c_void_p, ct.c_size_t], wt.BOOL),
    }
    for name, (args, result) in definitions.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _snapshot(api, flags, pid):
    handle = api.CreateToolhelp32Snapshot(flags, pid)
    if handle == ct.c_void_p(-1).value:
        raise windows_error("inspect", pid, ct.get_last_error())
    return handle


class GameMemory:
    def __init__(self, api, handle, pid, base, path):
        self.api, self.handle, self.pid, self.base, self.path = api, handle, pid, base, path

    @classmethod
    def find(cls):
        api = kernel()
        handle = _snapshot(api, 0x2, 0)
        entry = PROCESSENTRY32W()
        entry.dwSize = ct.sizeof(entry)
        candidates = []
        try:
            success = api.Process32FirstW(handle, ct.byref(entry))
            while success:
                if entry.szExeFile.lower() in {"game.dat", "generals.exe", "modded.exe"}:
                    candidates.append((entry.th32ProcessID, entry.szExeFile.lower()))
                success = api.Process32NextW(handle, ct.byref(entry))
        finally:
            api.CloseHandle(handle)
        errors = []
        for pid, name in candidates:
            try:
                module_handle = _snapshot(api, 0x18, pid)
                module = MODULEENTRY32W()
                module.dwSize = ct.sizeof(module)
                try:
                    if not api.Module32FirstW(module_handle, ct.byref(module)):
                        raise MemoryReadError("Could not find game module.")
                finally:
                    api.CloseHandle(module_handle)
                path = Path(module.szExePath)
                try:
                    addresses, digest = validate_executable(path)
                except ValueError as error:
                    if name == "generals.exe":
                        continue
                    raise UnsupportedGame(
                        f"Cannot verify {path.name} compatibility: {error} No game memory was changed. "
                        "This release supports stock English Steam Zero Hour. EA App, Origin, First Decade "
                        "and replacement engines are not validated. Use --check-executable with Game.dat "
                        "to produce a read-only compatibility report."
                    ) from error
                process = api.OpenProcess(0x1010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
                if not process:
                    raise windows_error("read", pid, ct.get_last_error())
                return cls(api, process, pid, NativeBase(module.modBaseAddr, addresses), path)
            except OSError as error:
                errors.append(str(error))
        if errors:
            raise MemoryReadError("; ".join(errors))
        return None

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def read(self, address, size):
        if not 0x10000 <= address <= 0xFFFFFFFF or not 0 < size <= 512:
            raise MemoryReadError("Invalid game pointer.")
        buffer = ct.create_string_buffer(size)
        read = ct.c_size_t()
        if not self.api.ReadProcessMemory(self.handle, address, buffer, size, ct.byref(read)) or read.value != size:
            raise MemoryReadError("Game state changed or the game exited; waiting to reconnect.")
        return buffer.raw

    def pointer(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def replace_pointer(self, address, expected, replacement):
        """Write a validated four-byte field, only if its value still matches."""
        if self.pointer(address) != expected:
            raise MemoryReadError("Game data changed during update; retrying.")
        handle = self.api.OpenProcess(0x1038, False, self.pid)
        if not handle:
            raise windows_error("update", self.pid, ct.get_last_error())
        try:
            if self.pointer(address) != expected:
                raise MemoryReadError("Game data changed during update; retrying.")
            data = ct.c_uint32(replacement)
            written = ct.c_size_t()
            if not self.api.WriteProcessMemory(handle, address, ct.byref(data), 4, ct.byref(written)) or written.value != 4:
                raise MemoryReadError("Could not write the game data field; update unconfirmed.")
            if self.pointer(address) != replacement:
                raise MemoryReadError("Game data write verification failed; update unconfirmed.")
        finally:
            self.api.CloseHandle(handle)

    def string(self, address):
        pointer = self.pointer(address)
        if not pointer:
            return ""
        _, capacity = struct.unpack("<HH", self.read(pointer, 4))
        if not 1 <= capacity <= 512:
            raise MemoryReadError("Unrecognized game string layout.")
        data = self.read(pointer + 4, capacity)
        if b"\0" not in data:
            raise MemoryReadError("Unterminated game string.")
        try:
            return data.split(b"\0", 1)[0].decode("ascii").lower().replace("\\", "/")
        except UnicodeDecodeError as error:
            raise MemoryReadError("Unrecognized campaign name.") from error

    def snapshot(self):
        manager = self.pointer(self.base + CAMPAIGN_GLOBAL_RVA)
        if not manager:
            return Snapshot()
        if self.pointer(manager) != self.base + CAMPAIGN_VTABLE_RVA:
            raise MemoryReadError("Campaign manager layout does not match the supported Steam build.")
        raw = self.read(manager + 8, 9)
        campaign, mission, victorious = struct.unpack("<IIB", raw)
        if victorious not in (0, 1):
            raise MemoryReadError("Invalid victory state.")
        campaign_name = self.string(campaign + 4) if campaign else None
        mission_name = self.string(mission + 4) if mission else None
        map_name = self.string(mission + 8) if mission else None
        if self.read(manager + 8, 9) != raw:
            # A transition between the individual reads is not a coherent sample.
            return None
        return Snapshot(campaign_name, mission_name, map_name, bool(victorious))
