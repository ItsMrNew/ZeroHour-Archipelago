"""Per-user launcher preferences, separate from seed progress and releases."""
import base64
import ctypes as ct
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import tempfile

DEFAULTS = {'server': 'archipelago.gg:5000', 'slot': 'ZeroHour', 'password': '', 'theme': 'light'}


def settings_path():
    return Path(os.environ.get('LOCALAPPDATA', '.')) / 'ZeroHourArchipelago' / 'launcher.json'


def password_bytes(data, decrypt=False):
    """DPAPI encrypts the remembered password for the current Windows user."""
    class Blob(ct.Structure):
        _fields_ = [('size', wt.DWORD), ('data', ct.POINTER(ct.c_ubyte))]
    crypt = ct.WinDLL('crypt32', use_last_error=True)
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ct.POINTER(Blob), ct.c_void_p, ct.c_void_p, ct.c_void_p,
                     ct.c_void_p, wt.DWORD, ct.POINTER(Blob)]
    func.restype = wt.BOOL
    kernel.LocalFree.argtypes = [ct.c_void_p]
    kernel.LocalFree.restype = ct.c_void_p
    buffer = ct.create_string_buffer(data)
    source = Blob(len(data), ct.cast(buffer, ct.POINTER(ct.c_ubyte)))
    result = Blob()
    if not func(ct.byref(source), None, None, None, None, 1, ct.byref(result)):
        raise OSError('Could not access the saved room password.')
    try:
        return ct.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def normalize(values):
    result = dict(DEFAULTS)
    if not isinstance(values, dict):
        return result
    for name in ('server', 'slot', 'password'):
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            result[name] = value if name == 'password' else value.strip()
    if values.get('theme') in ('light', 'dark'):
        result['theme'] = values['theme']
    return result


def load_settings(path=None):
    try:
        data = json.loads((path or settings_path()).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return dict(DEFAULTS)
    result = normalize(data)
    result['password'] = ''  # Never accept a plaintext password in the file.
    if isinstance(data, dict) and isinstance(data.get('password_protected'), str):
        try:
            result['password'] = password_bytes(base64.b64decode(data['password_protected'], validate=True), True).decode('utf-8')
        except (OSError, ValueError, AttributeError):
            pass  # A copied/corrupt password must not prevent opening the client.
    return result


def save_settings(values, path=None):
    path = path or settings_path()
    data = normalize(values)
    password = data.pop('password')
    if password:
        data['password_protected'] = base64.b64encode(password_bytes(password.encode('utf-8'))).decode('ascii')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement protects the last saved preferences if writing fails.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(data, stream, indent=2)
            stream.flush()
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
