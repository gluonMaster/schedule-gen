from __future__ import annotations

import argparse
import ctypes
import getpass
import importlib
import importlib.util
import json
import logging
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
import xml.etree.ElementTree as ET
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing.connection import Client, Listener
from urllib.request import urlopen

from gear_xls.runtime_paths import (
    HEALTH_MARKER,
    ProjectLayoutError,
    assert_valid_project_layout,
    ensure_runtime_dirs,
    get_project_root_id,
    get_runtime_dir,
    get_schedule_url,
    get_server_health_url,
    get_server_port,
    get_server_url_host,
    get_server_log_path,
    get_tray_launcher_path,
    get_tray_lock_path,
    get_tray_log_path,
    get_tray_state_path,
    load_server_config,
    normalize_project_root,
    resolve_project_root,
    set_project_root_env,
)


if os.name != "nt":
    raise RuntimeError("Windows tray runtime is supported only on Windows")


TASK_NAME = "SchedGen Flask Tray"
PROTOCOL_VERSION = 1
PIPE_AUTHKEY = b"SchedGenTrayControlV1"
CONNECT_TIMEOUT_MS = 3000
BOOTSTRAP_TIMEOUT_MS = 30000
DEFAULT_TIMEOUT_MS = 10000
START_TIMEOUT_MS = 60000
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
STILL_ACTIVE = 259
ERROR_ALREADY_EXISTS = 183
STATUS_STARTING = "starting"
STATUS_MANAGED = "managed_running"
STATUS_UNMANAGED = "unmanaged_compatible_running"
STATUS_STOPPED = "stopped"
STATUS_ERROR = "error"
OWNERSHIP_MANAGED = "managed"
OWNERSHIP_UNMANAGED = "unmanaged"
ERROR_NONE = "NONE"
ERROR_IPC_UNAVAILABLE = "IPC_UNAVAILABLE"
ERROR_IPC_TIMEOUT = "IPC_TIMEOUT"
ERROR_INVALID_REQUEST = "INVALID_REQUEST"
ERROR_OWNERSHIP_CONFLICT = "OWNERSHIP_CONFLICT"
ERROR_UNMANAGED_SERVER = "UNMANAGED_SERVER"
ERROR_START_FAILED = "START_FAILED"
ERROR_STOP_FAILED = "STOP_FAILED"
ERROR_RESTART_FAILED = "RESTART_FAILED"
ERROR_PORT_CONFLICT = "PORT_CONFLICT"
ERROR_LAYOUT_INVALID = "LAYOUT_INVALID"
ERROR_WRITE_ACCESS_DENIED = "WRITE_ACCESS_DENIED"
ERROR_AUTOSTART_FAILED = "AUTOSTART_FAILED"
ERROR_LAUNCHER_PREREQ = "LAUNCHER_PREREQUISITES_MISSING"
COMMANDS = {
    "ensure_running",
    "start_server",
    "stop_server",
    "restart_server",
    "open_web",
    "open_log",
    "status",
    "enable_autostart",
    "disable_autostart",
}
BOOTSTRAP_ALLOWED = {
    "ensure_running",
    "start_server",
    "open_web",
    "enable_autostart",
    "disable_autostart",
}
MB_OKCANCEL = 0x00000001
MB_YESNO = 0x00000004
MB_ICONERROR = 0x00000010
MB_ICONQUESTION = 0x00000020
MB_ICONWARNING = 0x00000030
MB_DEFBUTTON2 = 0x00000100
MESSAGEBOX_IDOK = 1
MESSAGEBOX_IDYES = 6


def _command_timeout(command: str) -> int:
    if command in {"ensure_running", "start_server", "restart_server"}:
        return START_TIMEOUT_MS
    return DEFAULT_TIMEOUT_MS


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16", sys.getfilesystemencoding(), "cp1251", "cp866"):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode(errors="replace")


def _hidden_subprocess_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "capture_output": True,
        "check": False,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return kwargs


def _run_subprocess(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, **_hidden_subprocess_kwargs())


def _is_task_not_found_output(output: str) -> bool:
    normalized = output.lower()
    known_fragments = (
        "cannot find",
        "the system cannot find the file specified",
        "не удается найти",
        "не удаётся найти",
        "das system kann die angegebene datei nicht finden",
        "angegebene datei nicht finden",
    )
    return any(fragment in normalized for fragment in known_fragments)


def _quote_arg(value: str) -> str:
    return subprocess.list2cmdline([value])


def _display_message(title: str, message: str, flags: int = MB_ICONERROR) -> int:
    return ctypes.windll.user32.MessageBoxW(None, message, title, flags)


def _current_windows_identity() -> str:
    domain = os.environ.get("USERDOMAIN")
    user = getpass.getuser()
    return f"{domain}\\{user}" if domain else user


def _current_session_id() -> int:
    session_id = wintypes.DWORD()
    kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(session_id))
    return int(session_id.value)


def _pipe_name(project_root: str) -> str:
    return rf"\\.\pipe\SchedGenTrayControl-{get_project_root_id(project_root)}"


def _mutex_name(project_root: str) -> str:
    return rf"Global\SchedGenTrayMutex-{get_project_root_id(project_root)}"


def _schedule_url(project_root: str) -> str:
    return get_schedule_url(project_root)


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=os.path.dirname(path),
            delete=False,
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = handle.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _read_json_file(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_port_open(project_root: str, timeout: float = 0.5) -> bool:
    host = get_server_url_host(project_root)
    port = get_server_port(project_root)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_compatible_server_running(project_root: str, timeout: float = 1.0) -> bool:
    try:
        with urlopen(get_server_health_url(project_root), timeout=timeout) as response:
            body = response.read(2048).decode("utf-8", errors="replace")
        data = json.loads(body)
        return (
            isinstance(data, dict)
            and data.get("ok") is True
            and data.get("marker") == HEALTH_MARKER
            and data.get("project_root_id") == get_project_root_id(project_root)
        )
    except Exception:
        return False


kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32
UINT_PTR = ctypes.c_size_t
ATOM = wintypes.WORD
HGDIOBJ = wintypes.HANDLE
HCURSOR = getattr(wintypes, "HCURSOR", wintypes.HANDLE)

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
kernel32.GetCurrentProcessId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyIcon.restype = wintypes.BOOL


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class BITMAPV5HEADER(ctypes.Structure):
    _fields_ = [
        ("bV5Size", wintypes.DWORD),
        ("bV5Width", ctypes.c_long),
        ("bV5Height", ctypes.c_long),
        ("bV5Planes", wintypes.WORD),
        ("bV5BitCount", wintypes.WORD),
        ("bV5Compression", wintypes.DWORD),
        ("bV5SizeImage", wintypes.DWORD),
        ("bV5XPelsPerMeter", ctypes.c_long),
        ("bV5YPelsPerMeter", ctypes.c_long),
        ("bV5ClrUsed", wintypes.DWORD),
        ("bV5ClrImportant", wintypes.DWORD),
        ("bV5RedMask", wintypes.DWORD),
        ("bV5GreenMask", wintypes.DWORD),
        ("bV5BlueMask", wintypes.DWORD),
        ("bV5AlphaMask", wintypes.DWORD),
        ("bV5CSType", wintypes.DWORD),
        ("bV5Endpoints", ctypes.c_byte * 36),
        ("bV5GammaRed", wintypes.DWORD),
        ("bV5GammaGreen", wintypes.DWORD),
        ("bV5GammaBlue", wintypes.DWORD),
        ("bV5Intent", wintypes.DWORD),
        ("bV5ProfileData", wintypes.DWORD),
        ("bV5ProfileSize", wintypes.DWORD),
        ("bV5Reserved", wintypes.DWORD),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    ctypes.c_void_p,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_long
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.SetTimer.argtypes = [wintypes.HWND, UINT_PTR, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = UINT_PTR
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = ctypes.c_long
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadCursorW.restype = HCURSOR
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.CreateIconIndirect.restype = wintypes.HICON
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, UINT_PTR, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BITMAPV5HEADER),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.UINT, ctypes.c_void_p]
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.DeleteObject.argtypes = [HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int


def _make_int_resource(value: int) -> ctypes.c_void_p:
    return ctypes.c_void_p(value & 0xFFFF)


def _filetime_to_iso(filetime: FILETIME) -> str | None:
    ticks = (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime
    if ticks <= 0:
        return None
    timestamp = (ticks - 116444736000000000) / 10000000
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0)
    return dt.isoformat()


def _open_process_handle(pid: int, access: int) -> wintypes.HANDLE | None:
    handle = kernel32.OpenProcess(access, False, int(pid))
    if not handle:
        return None
    return handle


def is_pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    handle = _open_process_handle(pid, PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def get_process_executable(pid: int | None) -> str | None:
    if not pid:
        return None
    handle = _open_process_handle(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return normalize_project_root(buffer.value)
    finally:
        kernel32.CloseHandle(handle)


def get_process_create_time_utc(pid: int | None) -> str | None:
    if not pid:
        return None
    handle = _open_process_handle(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if not handle:
        return None
    try:
        created = FILETIME()
        exited = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return _filetime_to_iso(created)
    finally:
        kernel32.CloseHandle(handle)


def wait_for_pid_exit(pid: int | None, timeout_ms: int) -> bool:
    if not pid:
        return True
    handle = _open_process_handle(pid, SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION)
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(handle, timeout_ms) == WAIT_OBJECT_0
    finally:
        kernel32.CloseHandle(handle)


def terminate_pid(pid: int | None) -> bool:
    if not pid:
        return True
    handle = _open_process_handle(pid, PROCESS_TERMINATE | SYNCHRONIZE)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)


def _find_pythonw() -> str:
    required_modules = ("flask", "flask_cors", "bcrypt")

    def _candidate_pairs() -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        executable = normalize_project_root(sys.executable or "")
        if executable:
            lower = executable.lower()
            if lower.endswith("pythonw.exe"):
                pythonw = executable
                python = os.path.join(os.path.dirname(executable), "python.exe")
                pairs.append((python, pythonw))
            elif lower.endswith("python.exe"):
                python = executable
                pythonw = os.path.join(os.path.dirname(executable), "pythonw.exe")
                pairs.append((python, pythonw))

        for command_name in ("python.exe", "python", "pythonw.exe"):
            resolved = shutil.which(command_name)
            if not resolved:
                continue
            resolved = normalize_project_root(resolved)
            lower = resolved.lower()
            if lower.endswith("pythonw.exe"):
                pairs.append(
                    (os.path.join(os.path.dirname(resolved), "python.exe"), resolved)
                )
            elif lower.endswith("python.exe"):
                pairs.append(
                    (resolved, os.path.join(os.path.dirname(resolved), "pythonw.exe"))
                )

        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for python, pythonw in pairs:
            normalized_pair = (
                normalize_project_root(python),
                normalize_project_root(pythonw),
            )
            if normalized_pair in seen:
                continue
            seen.add(normalized_pair)
            deduped.append(normalized_pair)
        return deduped

    def _python_has_required_modules(python_executable: str) -> bool:
        if not os.path.exists(python_executable):
            return False
        normalized = normalize_project_root(python_executable)
        if normalized == normalize_project_root(sys.executable or ""):
            return all(importlib.util.find_spec(module) is not None for module in required_modules)
        probe = (
            "import importlib.util, sys; "
            "missing=[m for m in sys.argv[1:] if importlib.util.find_spec(m) is None]; "
            "raise SystemExit(1 if missing else 0)"
        )
        try:
            completed = subprocess.run(
                [python_executable, "-c", probe, *required_modules],
                timeout=15,
                **_hidden_subprocess_kwargs(),
            )
        except Exception:
            return False
        return completed.returncode == 0

    fallback_pythonw = None
    for python, pythonw in _candidate_pairs():
        if not os.path.exists(pythonw):
            continue
        if fallback_pythonw is None:
            fallback_pythonw = pythonw
        if _python_has_required_modules(python):
            return pythonw

    if fallback_pythonw:
        return fallback_pythonw
    raise ProjectLayoutError("pythonw.exe not found in any available Python runtime")


def resolve_tray_launcher_command(project_root: str | None = None) -> dict[str, object]:
    root = assert_valid_project_layout(project_root)
    launcher_path = get_tray_launcher_path(root)
    if not os.path.isfile(launcher_path):
        raise ProjectLayoutError(f"Tray launcher not found: {launcher_path}")
    pythonw = _find_pythonw()
    return {
        "program": pythonw,
        "arguments": [launcher_path, "--mode", "tray", "--project-root", root],
        "start_in": root,
        "mode": "python_runtime",
    }


def resolve_server_child_command(project_root: str | None = None) -> dict[str, object]:
    root = assert_valid_project_layout(project_root)
    launcher_path = get_tray_launcher_path(root)
    if not os.path.isfile(launcher_path):
        raise ProjectLayoutError(f"Tray launcher not found: {launcher_path}")
    pythonw = _find_pythonw()
    return {
        "program": pythonw,
        "arguments": [launcher_path, "--mode", "server", "--project-root", root],
        "start_in": root,
        "mode": "python_runtime",
    }


def _launch_detached_process(
    command: dict[str, object],
    project_root: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    ensure_runtime_dirs(project_root)
    stderr_stream = open(get_tray_log_path(project_root), "ab")
    try:
        return subprocess.Popen(
            [command["program"], *command["arguments"]],
            cwd=command["start_in"],
            env=env,
            close_fds=True,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=stderr_stream,
        )
    finally:
        stderr_stream.close()


@dataclass
class AutostartStatus:
    enabled: bool
    stale: bool = False
    message: str = ""


@dataclass
class ControlResponse:
    ok: bool
    status: str
    message: str
    error_code: str = ERROR_NONE
    ownership_mode: str = OWNERSHIP_MANAGED
    autostart_enabled: bool = False
    server_pid: int | None = None
    controller_windows_identity: str | None = None
    controller_session_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "error_code": self.error_code,
            "ownership_mode": self.ownership_mode,
            "autostart_enabled": self.autostart_enabled,
            "server_pid": self.server_pid,
            "controller_windows_identity": self.controller_windows_identity,
            "controller_session_id": self.controller_session_id,
        }


class ControlPlaneError(RuntimeError):
    def __init__(self, response: ControlResponse):
        super().__init__(response.message)
        self.response = response


def _task_xml(identity: str, program: str, arguments: str, start_in: str) -> str:
    from xml.sax.saxutils import escape

    escaped_identity = escape(identity)
    escaped_program = escape(program)
    escaped_arguments = escape(arguments)
    escaped_start_in = escape(start_in)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{escaped_identity}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escaped_identity}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escaped_program}</Command>
      <Arguments>{escaped_arguments}</Arguments>
      <WorkingDirectory>{escaped_start_in}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _query_task_xml() -> str | None:
    completed = _run_subprocess(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"])
    if completed.returncode != 0:
        output = _decode_bytes(completed.stderr or completed.stdout or b"").lower()
        if _is_task_not_found_output(output):
            return None
        raise RuntimeError(output.strip() or "Failed to query scheduled task")
    return _decode_bytes(completed.stdout)


def query_autostart_status(project_root: str | None = None) -> AutostartStatus:
    root = resolve_project_root(project_root)
    try:
        expected = resolve_tray_launcher_command(root)
    except Exception as exc:
        return AutostartStatus(False, False, str(exc))

    xml_text = _query_task_xml()
    if not xml_text:
        return AutostartStatus(False, False, "")

    try:
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        root_xml = ET.fromstring(xml_text)
        command = root_xml.findtext(".//t:Exec/t:Command", default="", namespaces=ns)
        arguments = root_xml.findtext(".//t:Exec/t:Arguments", default="", namespaces=ns)
        working_directory = root_xml.findtext(
            ".//t:Exec/t:WorkingDirectory", default="", namespaces=ns
        )
        logon_type = root_xml.findtext(".//t:LogonType", default="", namespaces=ns)
        user_id = root_xml.findtext(".//t:LogonTrigger/t:UserId", default="", namespaces=ns)
        expected_arguments = subprocess.list2cmdline(expected["arguments"])
        stale = any(
            [
                normalize_project_root(command) != normalize_project_root(expected["program"]),
                arguments != expected_arguments,
                normalize_project_root(working_directory) != normalize_project_root(expected["start_in"]),
                logon_type != "InteractiveToken",
                user_id != _current_windows_identity(),
            ]
        )
        message = "Autostart task registered"
        if stale:
            message = "Autostart task points to a stale or non-canonical path"
        return AutostartStatus(True, stale, message)
    except Exception as exc:
        return AutostartStatus(True, True, f"Autostart task could not be parsed: {exc}")


def enable_autostart(project_root: str | None = None) -> AutostartStatus:
    root = assert_valid_project_layout(project_root)
    launcher = resolve_tray_launcher_command(root)
    arguments = subprocess.list2cmdline(launcher["arguments"])
    xml = _task_xml(_current_windows_identity(), launcher["program"], arguments, launcher["start_in"])
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml", mode="w", encoding="utf-16") as temp:
            temp.write(xml)
            temp_path = temp.name
        completed = _run_subprocess(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", temp_path, "/F"])
        if completed.returncode != 0:
            output = _decode_bytes(completed.stderr or completed.stdout or b"")
            raise RuntimeError(output.strip() or "Failed to register scheduled task")
        return query_autostart_status(root)
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def disable_autostart() -> AutostartStatus:
    completed = _run_subprocess(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if completed.returncode != 0:
        output = _decode_bytes(completed.stderr or completed.stdout or b"").lower()
        if not _is_task_not_found_output(output):
            raise RuntimeError(output.strip() or "Failed to delete scheduled task")
    return AutostartStatus(False, False, "Autostart disabled")


def _default_state(project_root: str) -> dict:
    return {
        "project_root": project_root,
        "data_root": project_root,
        "controller_pid": os.getpid(),
        "controller_started_at": _utc_now_iso(),
        "controller_executable": normalize_project_root(sys.executable),
        "deployment_mode": "python_runtime",
        "project_root_id": get_project_root_id(project_root),
        "controller_windows_identity": _current_windows_identity(),
        "controller_session_id": _current_session_id(),
        "server_pid": None,
        "server_started_at": None,
        "server_create_time_utc": None,
        "server_executable": None,
        "ownership_mode": OWNERSHIP_MANAGED,
        "status": STATUS_STOPPED,
        "status_reason": "Tray initialized",
        "last_error": "",
        "autostart_enabled": False,
        "launcher_path": get_tray_launcher_path(project_root),
        "ipc_endpoint_name": _pipe_name(project_root),
    }


def _create_lock_file(project_root: str) -> None:
    with open(get_tray_lock_path(project_root), "w", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n")


def _remove_lock_file(project_root: str) -> None:
    lock_path = get_tray_lock_path(project_root)
    if os.path.exists(lock_path):
        try:
            os.unlink(lock_path)
        except OSError:
            pass


class TrayController:
    def __init__(self, project_root: str):
        self.project_root = assert_valid_project_layout(project_root)
        set_project_root_env(self.project_root)
        ensure_runtime_dirs(self.project_root)
        _create_lock_file(self.project_root)
        self.pipe_name = _pipe_name(self.project_root)
        self.identity = _current_windows_identity()
        self.session_id = _current_session_id()
        self.state_path = get_tray_state_path(self.project_root)
        self.log = self._configure_logging()
        self.state = _default_state(self.project_root)
        self.state_lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.shutdown_event = threading.Event()
        self.listener: Listener | None = None
        self.listener_thread: threading.Thread | None = None
        self.monitor_thread: threading.Thread | None = None
        self.server_process: subprocess.Popen | None = None
        self.start_deadline = 0.0
        self.window: TrayWindow | None = None
        self._refresh_autostart_status()
        self._recover_state()
        self._persist_state()

    def _configure_logging(self) -> logging.Logger:
        logger = logging.getLogger(f"tray.{get_project_root_id(self.project_root)}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler(get_tray_log_path(self.project_root), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        if getattr(sys, "stdout", None) is not None:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
        logger.propagate = False
        return logger

    def _refresh_autostart_status(self) -> None:
        try:
            status = query_autostart_status(self.project_root)
        except Exception as exc:
            self.log.warning("Autostart status query failed: %s", exc)
            self.state["autostart_enabled"] = False
            return
        self.state["autostart_enabled"] = status.enabled
        if status.stale:
            self.state["status_reason"] = status.message

    def _recover_state(self) -> None:
        existing = _read_json_file(self.state_path)
        if not existing:
            return
        other_identity = existing.get("controller_windows_identity")
        other_session = existing.get("controller_session_id")
        other_pid = existing.get("controller_pid")
        if other_pid and is_pid_running(other_pid):
            if other_identity != self.identity or other_session != self.session_id:
                raise ControlPlaneError(
                    ControlResponse(
                        False,
                        STATUS_ERROR,
                        "Tray already belongs to another Windows session",
                        ERROR_OWNERSHIP_CONFLICT,
                        OWNERSHIP_UNMANAGED,
                        bool(existing.get("autostart_enabled")),
                        existing.get("server_pid"),
                        other_identity,
                        other_session,
                    )
                )
        if existing.get("server_pid") and is_pid_running(existing.get("server_pid")):
            self.state["status"] = STATUS_UNMANAGED
            self.state["status_reason"] = "Detected compatible server without live controller"
            self.state["ownership_mode"] = OWNERSHIP_UNMANAGED
            self.state["server_pid"] = existing.get("server_pid")
        self.log.info("Recovered runtime state from %s", self.state_path)

    def _persist_state(self) -> None:
        with self.state_lock:
            payload = dict(self.state)
            payload["autostart_enabled"] = bool(self.state.get("autostart_enabled"))
            _write_json_atomic(self.state_path, payload)

    def _set_state(
        self,
        status: str,
        reason: str,
        *,
        error_code: str = ERROR_NONE,
        ownership_mode: str | None = None,
        server_pid: int | None = None,
        server_started_at: str | None = None,
        server_create_time_utc: str | None = None,
        server_executable: str | None = None,
    ) -> None:
        with self.state_lock:
            clear_server_metadata = status in {STATUS_STOPPED, STATUS_ERROR, STATUS_UNMANAGED}
            self.state["status"] = status
            self.state["status_reason"] = reason
            self.state["last_error"] = "" if error_code == ERROR_NONE else error_code
            if ownership_mode is not None:
                self.state["ownership_mode"] = ownership_mode
            if server_pid is not None or status in {STATUS_STOPPED, STATUS_ERROR, STATUS_UNMANAGED}:
                self.state["server_pid"] = server_pid
            if server_started_at is not None or clear_server_metadata:
                self.state["server_started_at"] = server_started_at
            if server_create_time_utc is not None or clear_server_metadata:
                self.state["server_create_time_utc"] = server_create_time_utc
            if server_executable is not None or clear_server_metadata:
                self.state["server_executable"] = server_executable
            self.state["controller_pid"] = os.getpid()
            self.state["controller_windows_identity"] = self.identity
            self.state["controller_session_id"] = self.session_id
            self.state["ipc_endpoint_name"] = self.pipe_name
            self._refresh_autostart_status()
            self._persist_state()
        if self.window is not None:
            self.window.refresh_icon()

    def _managed_process_matches(self) -> bool:
        pid = self.state.get("server_pid")
        if not pid or not is_pid_running(pid):
            return False
        if self.state.get("controller_windows_identity") != self.identity:
            return False
        if self.state.get("controller_session_id") != self.session_id:
            return False
        if self.state.get("ownership_mode") != OWNERSHIP_MANAGED:
            return False
        create_time = get_process_create_time_utc(pid)
        executable = get_process_executable(pid)
        expected_create_time = self.state.get("server_create_time_utc")
        expected_executable = self.state.get("server_executable")
        if (
            create_time
            and executable
            and create_time == expected_create_time
            and executable == expected_executable
        ):
            return True
        if self.server_process and self.server_process.pid == pid and self.server_process.poll() is None:
            if expected_executable and executable and executable != expected_executable:
                return False
            return True
        return False

    def _inspect_runtime(self) -> tuple[str, str, str, int | None]:
        managed_pid = None
        if self.server_process and self.server_process.poll() is None:
            managed_pid = self.server_process.pid
        if _is_compatible_server_running(self.project_root):
            if managed_pid is not None:
                return STATUS_MANAGED, OWNERSHIP_MANAGED, ERROR_NONE, managed_pid
            if self._managed_process_matches():
                return STATUS_MANAGED, OWNERSHIP_MANAGED, ERROR_NONE, self.state.get("server_pid")
            return STATUS_UNMANAGED, OWNERSHIP_UNMANAGED, ERROR_NONE, self.state.get("server_pid")
        if managed_pid is not None:
            if self.state.get("status") == STATUS_MANAGED or _is_port_open(self.project_root):
                return STATUS_MANAGED, OWNERSHIP_MANAGED, ERROR_NONE, managed_pid
        if self.start_deadline and time.time() < self.start_deadline and self.state.get("server_pid"):
            if is_pid_running(self.state.get("server_pid")):
                return STATUS_STARTING, OWNERSHIP_MANAGED, ERROR_NONE, self.state.get("server_pid")
        if _is_port_open(self.project_root):
            return STATUS_ERROR, OWNERSHIP_MANAGED, ERROR_PORT_CONFLICT, None
        return STATUS_STOPPED, OWNERSHIP_MANAGED, ERROR_NONE, None

    def _response(self, ok: bool, message: str, error_code: str = ERROR_NONE) -> ControlResponse:
        status, ownership, detected_error_code, detected_pid = self._inspect_runtime()
        effective_error_code = error_code if error_code != ERROR_NONE else detected_error_code
        if status != self.state.get("status"):
            reason = self.state.get("status_reason") or message
            self._set_state(
                status,
                reason,
                error_code=effective_error_code or ERROR_NONE,
                ownership_mode=ownership,
                server_pid=detected_pid,
            )
        return ControlResponse(
            ok=ok,
            status=self.state.get("status"),
            message=message,
            error_code=effective_error_code,
            ownership_mode=self.state.get("ownership_mode"),
            autostart_enabled=bool(self.state.get("autostart_enabled")),
            server_pid=self.state.get("server_pid"),
            controller_windows_identity=self.identity,
            controller_session_id=self.session_id,
        )

    def start_listener(self) -> None:
        self.listener = Listener(address=self.pipe_name, family="AF_PIPE", authkey=PIPE_AUTHKEY)
        self.listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
        self.listener_thread.start()

    def _listener_loop(self) -> None:
        assert self.listener is not None
        while not self.shutdown_event.is_set():
            try:
                conn = self.listener.accept()
            except Exception:
                if self.shutdown_event.is_set():
                    break
                self.log.exception("IPC accept failed")
                time.sleep(0.2)
                continue
            try:
                with conn:
                    try:
                        request = json.loads(_decode_bytes(conn.recv_bytes()))
                        response = self.handle_request(request)
                    except Exception as exc:
                        self.log.exception("IPC request failed")
                        response = ControlResponse(
                            False,
                            STATUS_ERROR,
                            str(exc),
                            ERROR_INVALID_REQUEST,
                            self.state.get("ownership_mode", OWNERSHIP_MANAGED),
                            bool(self.state.get("autostart_enabled")),
                            self.state.get("server_pid"),
                            self.identity,
                            self.session_id,
                        )
                    try:
                        conn.send_bytes(
                            json.dumps(response.to_dict(), ensure_ascii=False).encode("utf-8")
                        )
                    except Exception:
                        self.log.exception("IPC response send failed")
            except Exception:
                self.log.exception("IPC connection lifecycle failed")

    def start_monitor(self) -> None:
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def _monitor_loop(self) -> None:
        autostart_refresh_at = 0.0
        while not self.shutdown_event.is_set():
            try:
                status, ownership, error_code, pid = self._inspect_runtime()
                if status == STATUS_ERROR and error_code == ERROR_PORT_CONFLICT:
                    self._set_state(status, f"Port {get_server_port(self.project_root)} is occupied by another process", error_code=error_code, ownership_mode=ownership, server_pid=pid)
                elif status == STATUS_UNMANAGED:
                    self._set_state(status, "Compatible server is running without tray ownership", ownership_mode=ownership, server_pid=pid)
                elif status == STATUS_STOPPED and self.state.get("status") not in {STATUS_STOPPED, STATUS_STARTING}:
                    self._set_state(status, "Server stopped", ownership_mode=ownership, server_pid=None)
                elif status == STATUS_MANAGED and (
                    self.state.get("status") != STATUS_MANAGED
                    or self.state.get("server_pid") != pid
                    or self.state.get("status_reason") != "Managed server is running"
                    or self.state.get("ownership_mode") != ownership
                ):
                    self._set_state(
                        status,
                        "Managed server is running",
                        ownership_mode=ownership,
                        server_pid=pid,
                        server_started_at=self.state.get("server_started_at"),
                        server_create_time_utc=self.state.get("server_create_time_utc"),
                        server_executable=self.state.get("server_executable"),
                    )
                if self.server_process and self.server_process.poll() is not None and self.state.get("status") == STATUS_MANAGED:
                    self._set_state(STATUS_ERROR, f"Managed child exited with code {self.server_process.returncode}", error_code=ERROR_START_FAILED, ownership_mode=OWNERSHIP_MANAGED, server_pid=None)
                    self.server_process = None
                if time.time() >= autostart_refresh_at:
                    self._refresh_autostart_status()
                    self._persist_state()
                    autostart_refresh_at = time.time() + 30
            except Exception:
                self.log.exception("Monitor loop failure")
            time.sleep(2)

    def handle_request(self, request: dict) -> ControlResponse:
        if request.get("protocol_version") != PROTOCOL_VERSION:
            return self._response(False, "Unsupported protocol version", ERROR_INVALID_REQUEST)
        if request.get("project_root_id") != get_project_root_id(self.project_root):
            return self._response(False, "Project root mismatch", ERROR_INVALID_REQUEST)
        command = request.get("command")
        if command not in COMMANDS:
            return self._response(False, f"Unsupported command: {command}", ERROR_INVALID_REQUEST)
        caller_identity = request.get("caller_windows_identity")
        caller_session = request.get("caller_session_id")
        if (
            command in {"start_server", "stop_server", "restart_server", "enable_autostart", "disable_autostart"}
            and (caller_identity != self.identity or caller_session != self.session_id)
        ):
            return self._response(False, "Command rejected for another Windows session", ERROR_OWNERSHIP_CONFLICT)
        if command == "status":
            return self._response(True, "Status refreshed")
        if command == "open_log":
            return self.open_log()
        if command == "open_web":
            return self.open_web()
        if command == "enable_autostart":
            return self.enable_autostart()
        if command == "disable_autostart":
            return self.disable_autostart()
        if command == "ensure_running":
            return self.ensure_running()
        if command == "start_server":
            return self.start_server()
        if command == "stop_server":
            return self.stop_server()
        if command == "restart_server":
            return self.restart_server()
        return self._response(False, "Unsupported command", ERROR_INVALID_REQUEST)

    def _launch_server_child(self) -> subprocess.Popen:
        command = resolve_server_child_command(self.project_root)
        environment = os.environ.copy()
        environment["SCHEDGEN_PROJECT_ROOT"] = self.project_root
        server_config = load_server_config(self.project_root)
        environment["HOST"] = str(server_config["host"])
        environment["PORT"] = str(server_config["port"])
        return _launch_detached_process(command, self.project_root, env=environment)

    def _wait_for_managed_start(self) -> bool:
        deadline = time.time() + (START_TIMEOUT_MS / 1000)
        self.start_deadline = deadline
        while time.time() < deadline:
            if _is_compatible_server_running(self.project_root) and self._managed_process_matches():
                self.start_deadline = 0.0
                return True
            if self.server_process and self.server_process.poll() is not None:
                self.start_deadline = 0.0
                return False
            time.sleep(0.3)
        self.start_deadline = 0.0
        return False

    def ensure_running(self) -> ControlResponse:
        with self.operation_lock:
            status, ownership, error_code, _ = self._inspect_runtime()
            if status == STATUS_MANAGED:
                return self._response(True, "Server already running")
            if status == STATUS_UNMANAGED:
                return self._response(True, "Compatible server is running without tray ownership")
            if status == STATUS_ERROR and error_code == ERROR_PORT_CONFLICT:
                return self._response(False, f"Port {get_server_port(self.project_root)} is occupied by another process", ERROR_PORT_CONFLICT)
            return self._start_managed_server("Server started")

    def start_server(self) -> ControlResponse:
        with self.operation_lock:
            status, ownership, error_code, _ = self._inspect_runtime()
            if status == STATUS_MANAGED:
                return self._response(True, "Server already running")
            if status == STATUS_UNMANAGED:
                return self._response(False, "Tray cannot take ownership of an external compatible server", ERROR_UNMANAGED_SERVER)
            if status == STATUS_ERROR and error_code == ERROR_PORT_CONFLICT:
                return self._response(False, f"Port {get_server_port(self.project_root)} is occupied by another process", ERROR_PORT_CONFLICT)
            return self._start_managed_server("Server started")

    def _start_managed_server(self, success_message: str) -> ControlResponse:
        try:
            self.server_process = self._launch_server_child()
            pid = self.server_process.pid
            time.sleep(0.2)
            create_time = get_process_create_time_utc(pid)
            executable = get_process_executable(pid)
            self._set_state(
                STATUS_STARTING,
                "Launching managed server",
                ownership_mode=OWNERSHIP_MANAGED,
                server_pid=pid,
                server_started_at=_utc_now_iso(),
                server_create_time_utc=create_time,
                server_executable=executable,
            )
            self.log.info("Managed server child started with PID %s", pid)
            if not self._wait_for_managed_start():
                self.log.error("Managed server failed to become healthy")
                self._set_state(STATUS_ERROR, "Managed server failed to become healthy", error_code=ERROR_START_FAILED, ownership_mode=OWNERSHIP_MANAGED, server_pid=None)
                return self._response(False, "Server startup failed", ERROR_START_FAILED)
            self._set_state(
                STATUS_MANAGED,
                "Managed server is running",
                ownership_mode=OWNERSHIP_MANAGED,
                server_pid=pid,
                server_started_at=self.state.get("server_started_at"),
                server_create_time_utc=create_time,
                server_executable=executable,
            )
            return self._response(True, success_message)
        except ProjectLayoutError as exc:
            return self._response(False, str(exc), ERROR_LAUNCHER_PREREQ)
        except PermissionError as exc:
            return self._response(False, str(exc), ERROR_WRITE_ACCESS_DENIED)
        except Exception as exc:
            self.log.exception("Managed server launch failed")
            self._set_state(STATUS_ERROR, str(exc), error_code=ERROR_START_FAILED, ownership_mode=OWNERSHIP_MANAGED, server_pid=None)
            return self._response(False, str(exc), ERROR_START_FAILED)

    def stop_server(self) -> ControlResponse:
        with self.operation_lock:
            status, ownership, _, pid = self._inspect_runtime()
            if status != STATUS_MANAGED or not self._managed_process_matches():
                if status == STATUS_UNMANAGED:
                    return self._response(False, "Tray cannot stop an external compatible server", ERROR_UNMANAGED_SERVER)
                return self._response(False, "No managed server is running", ERROR_STOP_FAILED)
            self.log.warning("Stopping managed server PID %s via forceful Windows termination; active requests may be interrupted", pid)
            # Windows has no graceful console-free shutdown path here; both attempts use TerminateProcess.
            if self.server_process and self.server_process.pid == pid:
                self.server_process.terminate()
            else:
                terminate_pid(pid)
            if not wait_for_pid_exit(pid, 5000):
                self.log.warning("Managed server PID %s did not exit after the first forceful termination attempt; retrying", pid)
                terminate_pid(pid)
                wait_for_pid_exit(pid, 5000)
            self.server_process = None
            if _is_compatible_server_running(self.project_root):
                self._set_state(STATUS_ERROR, "Managed server stop did not clear health-check", error_code=ERROR_STOP_FAILED, ownership_mode=OWNERSHIP_MANAGED, server_pid=None)
                return self._response(False, "Server stop failed", ERROR_STOP_FAILED)
            self._set_state(STATUS_STOPPED, "Server stopped", ownership_mode=OWNERSHIP_MANAGED, server_pid=None)
            return self._response(True, "Server stopped")

    def restart_server(self) -> ControlResponse:
        with self.operation_lock:
            status, _, _, _ = self._inspect_runtime()
            if status != STATUS_MANAGED:
                if status == STATUS_UNMANAGED:
                    return self._response(False, "Tray cannot restart an external compatible server", ERROR_UNMANAGED_SERVER)
                return self._response(False, "Restart is available only for a managed running server", ERROR_RESTART_FAILED)
            stop_response = self.stop_server()
            if not stop_response.ok:
                return self._response(False, stop_response.message, ERROR_RESTART_FAILED)
            return self._start_managed_server("Server restarted")

    def open_web(self) -> ControlResponse:
        response = self.ensure_running()
        if not response.ok and response.status != STATUS_UNMANAGED:
            return response
        if response.status in {STATUS_MANAGED, STATUS_UNMANAGED} or response.ok:
            webbrowser.open(_schedule_url(self.project_root))
            return self._response(True, "Web interface opened")
        return response

    def open_log(self) -> ControlResponse:
        target = get_server_log_path(self.project_root)
        if not os.path.exists(target):
            target = get_tray_log_path(self.project_root)
        os.startfile(target)
        return self._response(True, "Log opened")

    def enable_autostart(self) -> ControlResponse:
        try:
            status = enable_autostart(self.project_root)
            self.state["autostart_enabled"] = status.enabled
            self._persist_state()
            return self._response(True, status.message or "Autostart enabled")
        except Exception as exc:
            self.log.exception("Enabling autostart failed")
            return self._response(False, str(exc), ERROR_AUTOSTART_FAILED if "pythonw" not in str(exc).lower() else ERROR_LAUNCHER_PREREQ)

    def disable_autostart(self) -> ControlResponse:
        try:
            status = disable_autostart()
            self.state["autostart_enabled"] = status.enabled
            self._persist_state()
            return self._response(True, status.message or "Autostart disabled")
        except Exception as exc:
            self.log.exception("Disabling autostart failed")
            return self._response(False, str(exc), ERROR_AUTOSTART_FAILED)

    def get_local_lock_state(self) -> dict:
        try:
            if self.project_root not in sys.path:
                sys.path.insert(0, self.project_root)
            set_project_root_env(self.project_root)
            lock_manager = importlib.import_module("gear_xls.lock_manager")
            return lock_manager.get_lock_status()
        except Exception as exc:
            return {"error": str(exc)}

    def shutdown(self, stop_managed: bool) -> None:
        self.shutdown_event.set()
        if stop_managed:
            try:
                self.stop_server()
            except Exception:
                self.log.exception("Failed to stop managed server during shutdown")
        try:
            Client(self.pipe_name, family="AF_PIPE", authkey=PIPE_AUTHKEY).close()
        except Exception:
            pass
        if self.listener:
            try:
                self.listener.close()
            except Exception:
                pass
        _remove_lock_file(self.project_root)


def _color_to_bgra(color: tuple[int, int, int, int]) -> bytes:
    red, green, blue, alpha = color
    return bytes((blue, green, red, alpha))


def _state_color(status: str) -> tuple[int, int, int, int]:
    mapping = {
        STATUS_MANAGED: (46, 160, 67, 255),
        STATUS_STARTING: (227, 177, 48, 255),
        STATUS_ERROR: (198, 56, 55, 255),
        STATUS_STOPPED: (128, 128, 128, 255),
        STATUS_UNMANAGED: (52, 120, 246, 255),
    }
    return mapping.get(status, (128, 128, 128, 255))


def _create_icon_pixels(color: tuple[int, int, int, int], size: int = 64) -> bytes:
    outer = size / 2 - 4
    inner = outer - 6
    center = size / 2 - 0.5
    fill = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            dx = x - center
            dy = y - center
            dist = math.sqrt(dx * dx + dy * dy)
            offset = (y * size + x) * 4
            if dist <= outer:
                pixel = color
                if dist >= inner:
                    pixel = (30, 30, 30, 255)
                fill[offset : offset + 4] = _color_to_bgra(pixel)
            else:
                fill[offset : offset + 4] = b"\x00\x00\x00\x00"
    return bytes(fill)


def _create_hicon(status: str) -> wintypes.HICON:
    size = 64
    pixels = _create_icon_pixels(_state_color(status), size=size)
    bi = BITMAPV5HEADER()
    bi.bV5Size = ctypes.sizeof(BITMAPV5HEADER)
    bi.bV5Width = size
    bi.bV5Height = -size
    bi.bV5Planes = 1
    bi.bV5BitCount = 32
    bi.bV5Compression = 3
    bi.bV5RedMask = 0x00FF0000
    bi.bV5GreenMask = 0x0000FF00
    bi.bV5BlueMask = 0x000000FF
    bi.bV5AlphaMask = 0xFF000000
    bits = ctypes.c_void_p()
    hdc = user32.GetDC(None)
    hbitmap = gdi32.CreateDIBSection(hdc, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    user32.ReleaseDC(None, hdc)
    ctypes.memmove(bits, pixels, len(pixels))
    mask = gdi32.CreateBitmap(size, size, 1, 1, None)
    iconinfo = ICONINFO(True, 0, 0, mask, hbitmap)
    hicon = user32.CreateIconIndirect(ctypes.byref(iconinfo))
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteObject(mask)
    return hicon


WM_USER = 0x0400
WM_APP_NOTIFY = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_NULL = 0x0000
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
MF_STRING = 0x00000000
MF_GRAYED = 0x00000001
MF_DISABLED = 0x00000002
MF_SEPARATOR = 0x00000800
TPM_BOTTOMALIGN = 0x0020
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
IDI_APPLICATION = 32512
IDC_ARROW = 32512
ID_STATUS = 1001
ID_OPEN_WEB = 1002
ID_START = 1003
ID_RESTART = 1004
ID_STOP = 1005
ID_OPEN_LOG = 1006
ID_AUTOSTART = 1007
ID_EXIT = 1008
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class TrayWindow:
    def __init__(self, controller: TrayController):
        self.controller = controller
        self.controller.window = self
        self.class_name = f"SchedGenTrayWindow-{get_project_root_id(controller.project_root)}"
        self.instance = kernel32.GetModuleHandleW(None)
        self.icons = {status: _create_hicon(status) for status in {STATUS_MANAGED, STATUS_STARTING, STATUS_ERROR, STATUS_STOPPED, STATUS_UNMANAGED}}
        self._wnd_proc_ref = WNDPROC(self._wnd_proc)
        self.hwnd = self._create_window()
        self._add_icon()
        user32.SetTimer(self.hwnd, 1, 2000, None)

    def _create_window(self) -> wintypes.HWND:
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = ctypes.cast(self._wnd_proc_ref, ctypes.c_void_p).value
        window_class.lpszClassName = self.class_name
        window_class.hInstance = self.instance
        window_class.hCursor = user32.LoadCursorW(None, _make_int_resource(IDC_ARROW))
        atom = user32.RegisterClassW(ctypes.byref(window_class))
        if not atom:
            atom = 1
        return user32.CreateWindowExW(0, self.class_name, "SchedGen Flask Tray", 0, 0, 0, 0, 0, None, None, self.instance, None)

    def _notify_data(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_APP_NOTIFY
        data.hIcon = self.icons.get(self.controller.state.get("status"), self.icons[STATUS_STOPPED])
        data.szTip = "SchedGen Flask Tray"
        return data

    def _add_icon(self) -> None:
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._notify_data()))

    def refresh_icon(self) -> None:
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._notify_data()))

    def _remove_icon(self) -> None:
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._notify_data()))

    def _menu_label_for_status(self) -> str:
        status = self.controller.state.get("status")
        reason = self.controller.state.get("status_reason") or ""
        return f"Статус: {status} | {reason}"[:120]

    def _append_menu_item(self, menu, item_id: int, text: str, enabled: bool = True) -> None:
        flags = MF_STRING if enabled else (MF_STRING | MF_GRAYED)
        user32.AppendMenuW(menu, flags, item_id, text)

    def _show_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        status = self.controller.state.get("status")
        user32.AppendMenuW(menu, MF_STRING | MF_DISABLED, ID_STATUS, self._menu_label_for_status())
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        self._append_menu_item(menu, ID_OPEN_WEB, "Открыть веб-интерфейс", status in {STATUS_MANAGED, STATUS_UNMANAGED, STATUS_STOPPED, STATUS_ERROR})
        self._append_menu_item(menu, ID_START, "Запустить сервер", status in {STATUS_STOPPED, STATUS_ERROR})
        self._append_menu_item(menu, ID_RESTART, "Перезапустить сервер", status == STATUS_MANAGED)
        self._append_menu_item(menu, ID_STOP, "Остановить сервер", status == STATUS_MANAGED)
        self._append_menu_item(menu, ID_OPEN_LOG, "Открыть лог", True)
        autostart_label = "Выключить автозапуск" if self.controller.state.get("autostart_enabled") else "Включить автозапуск"
        self._append_menu_item(menu, ID_AUTOSTART, autostart_label, True)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        self._append_menu_item(menu, ID_EXIT, "Выход", True)
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RIGHTBUTTON, point.x, point.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)

    def _confirm_destructive_action(self, action_name: str) -> bool:
        lock_state = self.controller.get_local_lock_state()
        if lock_state.get("error"):
            result = _display_message(
                "Состояние lock неизвестно",
                "Не удалось прочитать локальный lock-state.\n"
                f"Ошибка: {lock_state.get('error')}\n\n"
                "Продолжение может прервать активную сессию сохранения.\n\n"
                "Продолжить несмотря на неизвестное состояние?",
                MB_OKCANCEL | MB_ICONWARNING | MB_DEFBUTTON2,
            )
            if result != MESSAGEBOX_IDOK:
                return False
        extra = ""
        if lock_state.get("holder"):
            extra = f"\n\nАктивен lock редактора: {lock_state.get('holder')}. Действие может прервать текущую сессию."
        result = _display_message(
            "Подтверждение",
            f"{action_name} может прервать активный запрос или окно сохранения.{extra}\n\nПродолжить?",
            MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2,
        )
        return result == MESSAGEBOX_IDYES

    def _run_async(self, handler) -> None:
        threading.Thread(target=handler, daemon=True).start()

    def _handle_command(self, command_id: int) -> None:
        if command_id == ID_OPEN_WEB:
            self._run_async(lambda: self.controller.open_web())
        elif command_id == ID_START:
            self._run_async(lambda: self.controller.start_server())
        elif command_id == ID_RESTART:
            if self._confirm_destructive_action("Перезапуск сервера"):
                self._run_async(lambda: self.controller.restart_server())
        elif command_id == ID_STOP:
            if self._confirm_destructive_action("Остановка сервера"):
                self._run_async(lambda: self.controller.stop_server())
        elif command_id == ID_OPEN_LOG:
            self._run_async(lambda: self.controller.open_log())
        elif command_id == ID_AUTOSTART:
            if self.controller.state.get("autostart_enabled"):
                self._run_async(lambda: self.controller.disable_autostart())
            else:
                self._run_async(lambda: self.controller.enable_autostart())
        elif command_id == ID_EXIT:
            stop_managed = self.controller.state.get("status") == STATUS_MANAGED
            if stop_managed and not self._confirm_destructive_action("Закрытие tray и остановка сервера"):
                return
            self._run_async(lambda: self._shutdown(stop_managed))

    def _shutdown(self, stop_managed: bool) -> None:
        self.controller.shutdown(stop_managed=stop_managed)
        user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _wnd_proc(self, hwnd, message, wparam, lparam):
        if message == WM_APP_NOTIFY and lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
            self._show_menu()
            return 0
        if message == WM_COMMAND:
            self._handle_command(int(wparam) & 0xFFFF)
            return 0
        if message == WM_TIMER:
            self.refresh_icon()
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            self._remove_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def run(self) -> int:
        message = MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        for icon in self.icons.values():
            user32.DestroyIcon(icon)
        return 0


def _connect_pipe(pipe_name: str, timeout_ms: int):
    deadline = time.time() + (timeout_ms / 1000)
    last_error = None
    while time.time() < deadline:
        try:
            return Client(pipe_name, family="AF_PIPE", authkey=PIPE_AUTHKEY)
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(str(last_error) if last_error else "Pipe unavailable")


def _bootstrap_primary_tray(project_root: str) -> None:
    launcher = resolve_tray_launcher_command(project_root)
    _launch_detached_process(launcher, project_root)


def send_control_command(
    command: str,
    project_root: str | None = None,
    timeout_ms: int | None = None,
    *,
    bootstrap_if_missing: bool = True,
) -> ControlResponse:
    root = assert_valid_project_layout(project_root)
    pipe_name = _pipe_name(root)
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "project_root": root,
        "project_root_id": get_project_root_id(root),
        "command": command,
        "request_id": f"{os.getpid()}-{time.time_ns()}",
        "caller_pid": os.getpid(),
        "caller_windows_identity": _current_windows_identity(),
        "caller_session_id": _current_session_id(),
        "timeout_ms": timeout_ms or _command_timeout(command),
    }
    try:
        connection = _connect_pipe(pipe_name, CONNECT_TIMEOUT_MS)
    except TimeoutError:
        if not bootstrap_if_missing or command not in BOOTSTRAP_ALLOWED:
            return ControlResponse(False, STATUS_ERROR, "Active tray instance not available", ERROR_IPC_UNAVAILABLE)
        try:
            _bootstrap_primary_tray(root)
        except Exception as exc:
            return ControlResponse(False, STATUS_ERROR, str(exc), ERROR_LAUNCHER_PREREQ)
        try:
            connection = _connect_pipe(pipe_name, BOOTSTRAP_TIMEOUT_MS)
        except TimeoutError:
            return ControlResponse(False, STATUS_ERROR, "Timed out waiting for tray bootstrap", ERROR_IPC_UNAVAILABLE)

    with connection:
        try:
            connection.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            if not connection.poll((timeout_ms or _command_timeout(command)) / 1000):
                return ControlResponse(False, STATUS_ERROR, "Control command timed out", ERROR_IPC_TIMEOUT)
            response_data = json.loads(_decode_bytes(connection.recv_bytes()))
        except (EOFError, OSError):
            return ControlResponse(
                False,
                STATUS_ERROR,
                "Active tray instance exited before replying",
                ERROR_IPC_UNAVAILABLE,
            )
        except json.JSONDecodeError:
            return ControlResponse(
                False,
                STATUS_ERROR,
                "Tray returned an invalid response payload",
                ERROR_INVALID_REQUEST,
            )
    return ControlResponse(**response_data)


def send_control_command_or_raise(command: str, project_root: str | None = None, timeout_ms: int | None = None) -> ControlResponse:
    response = send_control_command(command, project_root, timeout_ms)
    if not response.ok:
        raise ControlPlaneError(response)
    return response


def _response_exit_code(response: ControlResponse) -> int:
    if response.ok:
        return 0
    if response.error_code == ERROR_IPC_UNAVAILABLE:
        return 20
    if response.error_code == ERROR_IPC_TIMEOUT:
        return 21
    if response.error_code in {ERROR_OWNERSHIP_CONFLICT, ERROR_UNMANAGED_SERVER}:
        return 22
    if response.error_code in {ERROR_START_FAILED, ERROR_RESTART_FAILED, ERROR_PORT_CONFLICT}:
        return 23
    return 24


def run_server_mode(project_root: str) -> int:
    set_project_root_env(project_root)
    try:
        from gear_xls.server_routes import run_server
    except Exception:
        traceback.print_exc()
        return 23
    try:
        run_server(project_root=project_root)
    except Exception:
        traceback.print_exc()
        return 23
    return 0


def run_tray_mode(project_root: str) -> int:
    project_root = assert_valid_project_layout(project_root)
    existing_state = _read_json_file(get_tray_state_path(project_root))
    if existing_state.get("controller_pid") and is_pid_running(existing_state.get("controller_pid")):
        if existing_state.get("controller_windows_identity") not in {None, _current_windows_identity()} or existing_state.get("controller_session_id") not in {None, _current_session_id()}:
            _display_message("SchedGen Tray", "Tray уже запущен в другой Windows-сессии.", 0x00000010)
            return 22

    mutex = kernel32.CreateMutexW(None, False, _mutex_name(project_root))
    if not mutex:
        _display_message("SchedGen Tray", "Не удалось создать single-instance mutex.", 0x00000010)
        return 20
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        try:
            response = send_control_command("status", project_root, bootstrap_if_missing=False)
            if response.ok or response.error_code == ERROR_IPC_UNAVAILABLE:
                return 0 if response.ok else 20
        finally:
            kernel32.CloseHandle(mutex)

    try:
        controller = TrayController(project_root)
    except ControlPlaneError as exc:
        kernel32.CloseHandle(mutex)
        _display_message("SchedGen Tray", exc.response.message, 0x00000010)
        return _response_exit_code(exc.response)
    except ProjectLayoutError as exc:
        kernel32.CloseHandle(mutex)
        _display_message("SchedGen Tray", str(exc), 0x00000010)
        return 24
    except PermissionError as exc:
        kernel32.CloseHandle(mutex)
        _display_message("SchedGen Tray", str(exc), 0x00000010)
        return 24

    controller.start_listener()
    controller.start_monitor()
    threading.Thread(target=controller.ensure_running, daemon=True).start()
    tray = TrayWindow(controller)
    try:
        return tray.run()
    finally:
        controller.shutdown(stop_managed=False)
        kernel32.CloseHandle(mutex)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SchedGen Windows tray/runtime launcher")
    parser.add_argument("--mode", choices=["tray", "server"])
    parser.add_argument("--control", choices=sorted(COMMANDS))
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--timeout-ms", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    project_root = resolve_project_root(args.project_root)
    if args.control:
        response = send_control_command(args.control, project_root, args.timeout_ms)
        if getattr(sys, "stdout", None) is not None:
            print(json.dumps(response.to_dict(), ensure_ascii=False))
        return _response_exit_code(response)
    if args.mode == "server":
        return run_server_mode(project_root)
    if args.mode == "tray":
        return run_tray_mode(project_root)
    parser.error("Either --mode or --control is required")
    return 24
