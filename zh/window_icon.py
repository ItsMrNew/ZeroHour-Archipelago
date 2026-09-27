"""Load Windows icon frames at their native size, bypassing Tk's ICO decoder."""
import ctypes as ct
from ctypes import wintypes as wt
import os


def enable_display_scaling():
    """Must run before Tk creates its first window."""
    if os.name == 'nt':
        user = ct.WinDLL('user32', use_last_error=True)
        user.SetProcessDpiAwarenessContext.argtypes = [ct.c_void_p]
        user.SetProcessDpiAwarenessContext.restype = wt.BOOL
        # Per-monitor V2. If a manifest/host already chose awareness, leave it.
        user.SetProcessDpiAwarenessContext(ct.c_void_p(-4))


class WindowIcon:
    def __init__(self, root, path):
        self.root, self.path = root, str(path)
        self.handles = []
        self.key = None
        self.closed = False
        self.pending = None
        self.user = ct.WinDLL('user32', use_last_error=True)
        self.user.GetAncestor.argtypes = [wt.HWND, wt.UINT]
        self.user.GetAncestor.restype = wt.HWND
        self.user.GetDpiForWindow.argtypes = [wt.HWND]
        self.user.GetDpiForWindow.restype = wt.UINT
        self.user.GetSystemMetricsForDpi.argtypes = [ct.c_int, wt.UINT]
        self.user.GetSystemMetricsForDpi.restype = ct.c_int
        self.user.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ct.c_int, ct.c_int, wt.UINT]
        self.user.LoadImageW.restype = wt.HANDLE
        self.user.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        self.user.SendMessageW.restype = wt.LPARAM
        self.user.DestroyIcon.argtypes = [wt.HICON]
        self.user.DestroyIcon.restype = wt.BOOL
        root.bind('<Map>', self.schedule, add='+')
        root.bind('<Configure>', self.schedule, add='+')
        root.bind('<Destroy>', self.destroy, add='+')
        self.schedule()

    def schedule(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if not self.closed and self.pending is None:
            self.pending = self.root.after_idle(self.refresh)

    def refresh(self):
        self.pending = None
        if self.closed:
            return
        hwnd = self.user.GetAncestor(self.root.winfo_id(), 2)  # Tk wrapper, GA_ROOT
        dpi = self.user.GetDpiForWindow(hwnd) or 96
        key = (hwnd, dpi)
        if self.key == key:
            return
        # Windows selects the matching ICO frame without the extra resampling
        # introduced by the bundled Tk iconbitmap path.
        new = []
        for cx, cy in ((11, 12), (49, 50)):  # SM_CX/YICON, SM_CX/YSMICON
            width = self.user.GetSystemMetricsForDpi(cx, dpi)
            height = self.user.GetSystemMetricsForDpi(cy, dpi)
            icon = self.user.LoadImageW(None, self.path, 1, width, height, 0x10)  # LR_LOADFROMFILE
            if not icon:
                for handle in new:
                    self.user.DestroyIcon(handle)
                raise ct.WinError(ct.get_last_error())
            new.append(icon)
        for kind, handle in zip((1, 0), new):  # WM_SETICON: ICON_BIG, ICON_SMALL
            self.user.SendMessageW(hwnd, 0x80, kind, handle)
        old, self.handles = self.handles, new
        self.key = key
        for handle in old:
            self.user.DestroyIcon(handle)

    def destroy(self, event):
        if event.widget is not self.root:
            return
        self.closed = True
        if self.pending is not None:
            self.root.after_cancel(self.pending)
            self.pending = None
        for handle in self.handles:
            self.user.DestroyIcon(handle)
        self.handles = []
