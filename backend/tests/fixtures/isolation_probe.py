"""合成隔离探针；OUTSIDE_FILE 和 LOCAL_PORT 由测试注入，不访问真实用户配置。"""

import ctypes
import json
import os
import socket
import subprocess
import sys
from ctypes import wintypes as w
from pathlib import Path

try:
    Path(OUTSIDE_FILE).read_text()  # noqa: F821
    outside_read = True
except PermissionError:
    outside_read = False

try:
    connection = socket.create_connection(("127.0.0.1", LOCAL_PORT), timeout=1)  # noqa: F821
    connection.close()
    network = True
except OSError:
    network = False

try:
    subprocess.run([sys.executable, "-I", "-c", "print('child')"], check=True, capture_output=True)
    child_process = True
except (OSError, subprocess.CalledProcessError):
    child_process = False

kernel = ctypes.WinDLL("kernel32")
advapi = ctypes.WinDLL("advapi32")
kernel.GetCurrentProcess.restype = w.HANDLE
advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
advapi.GetTokenInformation.argtypes = [
    w.HANDLE,
    ctypes.c_int,
    w.LPVOID,
    w.DWORD,
    ctypes.POINTER(w.DWORD),
]
token = w.HANDLE()
advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token))
flag, size = w.DWORD(), w.DWORD()
advapi.GetTokenInformation(token, 29, ctypes.byref(flag), 4, ctypes.byref(size))
Path("proof.json").write_text(
    json.dumps(
        {
            "container": flag.value,
            "outside_read": outside_read,
            "env": os.getenv("ROOMCREW_TEST_SECRET"),
            "network": network,
            "child_process": child_process,
        }
    ),
    encoding="utf-8",
)
