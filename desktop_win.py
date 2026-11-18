"""Windows-spezifisches Desktop-Verhalten über ctypes (ohne Zusatzpakete).

- pin_to_bottom: Fenster hinter alle anderen legen (HWND_BOTTOM), nicht in der Taskleiste
  (WS_EX_TOOLWINDOW) und ohne Fokus-Klau (WS_EX_NOACTIVATE).
- lower_to_bottom: legt das Fenster regelmäßig wieder nach hinten (main.py, alle 2 s).
- attach_to_workerw: Alternative, die das Fenster in die Desktop-Ebene (WorkerW) hängt.
  Dann bleibt es auch bei Win+D sichtbar. Experimentell, Windows ändert das Verhalten gelegentlich.
- Autostart über HKCU\\...\\Run.

Auf anderen Systemen sind alle Funktionen wirkungslos, damit die Vorschau überall läuft.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)
IS_WINDOWS = sys.platform == "win32"

HWND_BOTTOM = 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = 0x00000080, 0x00040000, 0x08000000
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Tomatenplan"

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                           wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def pin_to_bottom(hwnd: int) -> None:
    if not IS_WINDOWS:
        return
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style = (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def lower_to_bottom(hwnd: int) -> None:
    """Legt das Fenster wieder hinter alle anderen, ohne es zu aktivieren."""
    if not IS_WINDOWS:
        return
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def attach_to_workerw(hwnd: int) -> bool:
    """Hängt das Fenster hinter die Desktop-Symbole. Gibt False zurück, wenn es nicht klappt."""
    if not IS_WINDOWS:
        return False
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return False
    result = ctypes.c_size_t()
    # 0x052C veranlasst Explorer, ein WorkerW-Fenster hinter den Symbolen zu erzeugen.
    user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(result))

    found: list[int] = []

    @WNDENUMPROC
    def callback(top, _lparam):
        if user32.FindWindowExW(top, None, "SHELLDLL_DefView", None):
            worker = user32.FindWindowExW(None, top, "WorkerW", None)
            if worker:
                found.append(worker)
        return True

    user32.EnumWindows(callback, 0)
    workerw = found[0] if found else user32.FindWindowExW(progman, None, "WorkerW", None)  # Windows 11 24H2+
    if not workerw:
        log.warning("WorkerW nicht gefunden, nutze HWND_BOTTOM.")
        return False
    user32.SetParent(hwnd, workerw)
    return True


# --- Autostart ----------------------------------------------------------------

def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{Path(__file__).resolve().with_name("main.py")}"'


def autostart_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def system_uses_dark_mode() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False
