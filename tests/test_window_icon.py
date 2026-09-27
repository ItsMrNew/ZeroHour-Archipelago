"""Verify native icon pixels rather than only checking the EXE resource."""
import ctypes as ct
from ctypes import wintypes as wt
import tkinter as tk

from zh.client_ui import icon_path
from zh.window_icon import WindowIcon


class IconInfo(ct.Structure):
    _fields_ = [('icon', wt.BOOL), ('x', wt.DWORD), ('y', wt.DWORD),
                ('mask', wt.HBITMAP), ('color', wt.HBITMAP)]


class Bitmap(ct.Structure):
    _fields_ = [('kind', wt.LONG), ('width', wt.LONG), ('height', wt.LONG),
                ('stride', wt.LONG), ('planes', wt.WORD), ('bits', wt.WORD), ('data', ct.c_void_p)]


def pixels(user, icon):
    user.GetIconInfo.argtypes = [wt.HICON, ct.POINTER(IconInfo)]
    gdi = ct.WinDLL('gdi32')
    gdi.GetObjectW.argtypes = [wt.HANDLE, ct.c_int, ct.c_void_p]
    gdi.GetBitmapBits.argtypes = [wt.HBITMAP, wt.LONG, ct.c_void_p]
    gdi.DeleteObject.argtypes = [wt.HANDLE]
    info, bitmap = IconInfo(), Bitmap()
    assert user.GetIconInfo(icon, ct.byref(info))
    try:
        assert gdi.GetObjectW(info.color, ct.sizeof(bitmap), ct.byref(bitmap))
        data = ct.create_string_buffer(bitmap.stride * bitmap.height)
        assert gdi.GetBitmapBits(info.color, len(data), data)
        return bitmap.width, bitmap.height, data.raw
    finally:
        gdi.DeleteObject(info.mask)
        gdi.DeleteObject(info.color)


def test_window_gets_native_pixels_and_reloads_for_display_scale():
    root = tk.Tk()
    root.withdraw()
    root.iconbitmap(default=str(icon_path()))
    icons = WindowIcon(root, icon_path())
    try:
        root.update_idletasks()
        root.deiconify()
        root.update()
        hwnd = icons.key[0]
        real_dpi = icons.user.GetDpiForWindow
        # Exercise physical sizes selected for 100%, 125%, 150%, and 200%.
        for dpi in (96, 120, 144, 192):
            icons.user.GetDpiForWindow = lambda hwnd: dpi
            icons.refresh()
            assert icons.key == (hwnd, dpi)
            for kind, cx, cy in ((1, 11, 12), (0, 49, 50)):
                width = icons.user.GetSystemMetricsForDpi(cx, dpi)
                height = icons.user.GetSystemMetricsForDpi(cy, dpi)
                handle = icons.user.SendMessageW(hwnd, 0x7f, kind, 0)
                expected = icons.user.LoadImageW(None, str(icon_path()), 1, width, height, 0x10)
                try:
                    actual = pixels(icons.user, handle)
                    assert actual[:2] == (width, height)
                    assert actual == pixels(icons.user, expected)
                finally:
                    icons.user.DestroyIcon(expected)
            before = list(icons.handles)
            icons.refresh()
            assert icons.handles == before  # Resize without a DPI change reuses handles.
        icons.user.GetDpiForWindow = real_dpi
    finally:
        root.destroy()
    assert icons.closed
    assert not icons.handles
