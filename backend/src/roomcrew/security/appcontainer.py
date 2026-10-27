"""Windows AppContainer 进程边界；只允许显式目录，不回退宿主执行。"""

import ctypes
import os
import shutil
import subprocess
import threading
import time
from contextlib import suppress
from ctypes import wintypes as wt
from pathlib import Path
from typing import Any
from uuid import uuid4

from roomcrew.contracts.errors import ExecutionError


class SecurityCapabilities(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", wt.LPVOID),
        ("Capabilities", wt.LPVOID),
        ("CapabilityCount", wt.DWORD),
        ("Reserved", wt.DWORD),
    ]


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("lpReserved", wt.LPWSTR),
        ("lpDesktop", wt.LPWSTR),
        ("lpTitle", wt.LPWSTR),
        ("dwX", wt.DWORD),
        ("dwY", wt.DWORD),
        ("dwXSize", wt.DWORD),
        ("dwYSize", wt.DWORD),
        ("dwXCountChars", wt.DWORD),
        ("dwYCountChars", wt.DWORD),
        ("dwFillAttribute", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("wShowWindow", wt.WORD),
        ("cbReserved2", wt.WORD),
        ("lpReserved2", wt.LPVOID),
        ("hStdInput", wt.HANDLE),
        ("hStdOutput", wt.HANDLE),
        ("hStdError", wt.HANDLE),
    ]


class StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", StartupInfo), ("lpAttributeList", wt.LPVOID)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("hProcess", wt.HANDLE),
        ("hThread", wt.HANDLE),
        ("dwProcessId", wt.DWORD),
        ("dwThreadId", wt.DWORD),
    ]


class JobBasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wt.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wt.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wt.DWORD),
        ("SchedulingClass", wt.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (key, ctypes.c_ulonglong)
        for key in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class JobLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JobBasicLimits),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def windows_api() -> tuple[Any, Any, Any]:
    """因为 Win32 指针不能使用默认整数截断，需要统一声明隔离进程所需的原生函数签名。"""
    # 1、仅在 Windows 加载系统 DLL，不从用户素材或任务目录导入库。
    if os.name != "nt":
        raise ExecutionError("PYTHON_UNAVAILABLE")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    signatures = {
        "InitializeProcThreadAttributeList": (
            [wt.LPVOID, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_size_t)],
            wt.BOOL,
        ),
        "UpdateProcThreadAttribute": (
            [
                wt.LPVOID,
                wt.DWORD,
                ctypes.c_size_t,
                wt.LPVOID,
                ctypes.c_size_t,
                wt.LPVOID,
                wt.LPVOID,
            ],
            wt.BOOL,
        ),
        "DeleteProcThreadAttributeList": ([wt.LPVOID], None),
        "CreateProcessW": (
            [
                wt.LPCWSTR,
                wt.LPWSTR,
                wt.LPVOID,
                wt.LPVOID,
                wt.BOOL,
                wt.DWORD,
                wt.LPVOID,
                wt.LPCWSTR,
                wt.LPVOID,
                ctypes.POINTER(ProcessInfo),
            ],
            wt.BOOL,
        ),
        "CreateJobObjectW": ([wt.LPVOID, wt.LPCWSTR], wt.HANDLE),
        "SetInformationJobObject": ([wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD], wt.BOOL),
        "AssignProcessToJobObject": ([wt.HANDLE, wt.HANDLE], wt.BOOL),
        "TerminateJobObject": ([wt.HANDLE, wt.UINT], wt.BOOL),
        "TerminateProcess": ([wt.HANDLE, wt.UINT], wt.BOOL),
        "ResumeThread": ([wt.HANDLE], wt.DWORD),
        "WaitForSingleObject": ([wt.HANDLE, wt.DWORD], wt.DWORD),
        "GetExitCodeProcess": ([wt.HANDLE, ctypes.POINTER(wt.DWORD)], wt.BOOL),
        "CloseHandle": ([wt.HANDLE], wt.BOOL),
        "LocalFree": ([wt.LPVOID], wt.LPVOID),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    # 2、AppContainer 不申请网络、设备或其他能力，权限仅靠专属 SID 的目录授权。
    userenv.CreateAppContainerProfile.argtypes = [
        wt.LPCWSTR,
        wt.LPCWSTR,
        wt.LPCWSTR,
        wt.LPVOID,
        wt.DWORD,
        ctypes.POINTER(wt.LPVOID),
    ]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [wt.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    userenv.GetAppContainerFolderPath.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.LPWSTR)]
    userenv.GetAppContainerFolderPath.restype = ctypes.c_long
    advapi.ConvertSidToStringSidW.argtypes = [wt.LPVOID, ctypes.POINTER(wt.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wt.BOOL
    advapi.FreeSid.argtypes, advapi.FreeSid.restype = [wt.LPVOID], wt.LPVOID
    return kernel, userenv, advapi


def directory_access(path: Path, sid: str, grant: bool) -> None:
    """因为 AppContainer 默认不能读取应用目录，需要只向专属 SID 授权隔离副本或撤销该授权。"""
    # 1、使用参数数组调用系统 ACL 工具，不拼接 Shell 或执行模型命令。
    executable = Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32/icacls.exe"
    arguments = (
        [
            str(executable),
            str(path),
            "/grant:r",
            "*" + sid + ":(OI)(CI)(RX)",
        ]
        if grant
        else [str(executable), str(path), "/remove:g", "*" + sid, "/T", "/Q"]
    )
    completed = subprocess.run(
        arguments, capture_output=True, timeout=30, creationflags=0x08000000, check=False
    )
    if completed.returncode:
        raise ExecutionError("PYTHON_UNAVAILABLE")


def run_container(
    executable: Path, script: Path, folder: Path, timeout: int, cancelled: threading.Event
) -> dict[str, Any]:
    """因为 Agent 生成的 Python 可以任意访问系统，需要在无网络 AppContainer 与受限 Job 中执行。"""
    # 1、每次调用拥有独立 SID；只授权解释器副本和本次输入输出目录。
    import msvcrt

    kernel, userenv, advapi = windows_api()
    profile = "RoomCrew.Script." + uuid4().hex
    sid_pointer = wt.LPVOID()
    sid_text = wt.LPWSTR()
    process, attributes, job = ProcessInfo(), None, None
    attributes_initialized = False
    granted: list[Path] = []
    original_folder = folder
    container_folder = wt.LPWSTR()
    created = False
    sid = ""
    try:
        if userenv.CreateAppContainerProfile(
            profile,
            "RoomCrew isolated Python",
            "No network capabilities",
            None,
            0,
            ctypes.byref(sid_pointer),
        ):
            raise ExecutionError("PYTHON_UNAVAILABLE")
        created = True
        if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid_text)):
            raise ExecutionError("PYTHON_UNAVAILABLE")
        sid = sid_text.value or ""
        directory_access(executable.parent, sid, True)
        granted.append(executable.parent)
        if userenv.GetAppContainerFolderPath(sid, ctypes.byref(container_folder)):
            raise ExecutionError("PYTHON_UNAVAILABLE")
        # 使用系统创建的低完整性容器目录，普通用户无需降低宿主目录完整性或提权。
        folder = Path(container_folder.value or "") / "Temp/work"
        folder.mkdir(parents=True)
        relative_script = script.relative_to(original_folder)
        for source in original_folder.rglob("*"):
            if source.is_symlink() or source.is_junction():
                raise ExecutionError("PYTHON_FAILED")
            target = folder / source.relative_to(original_folder)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        script = folder / relative_script
        # 2、标准句柄限定为三个日志句柄，清空父进程环境，避免继承配置与 Python 搜索路径。
        logs = folder / ".roomcrew-output"
        logs.mkdir(exist_ok=True)
        with (
            open(os.devnull, "rb") as stdin,
            (logs / "stdout.txt").open("wb") as stdout,
            (logs / "stderr.txt").open("wb") as stderr,
        ):
            handles = [msvcrt.get_osfhandle(stream.fileno()) for stream in (stdin, stdout, stderr)]
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            handle_array = (wt.HANDLE * len(handles))(*handles)
            size = ctypes.c_size_t()
            kernel.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            attributes = ctypes.create_string_buffer(size.value)
            if not kernel.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size)):
                raise ExecutionError("PYTHON_FAILED")
            attributes_initialized = True
            capabilities = SecurityCapabilities(sid_pointer, None, 0, 0)
            if not kernel.UpdateProcThreadAttribute(
                attributes,
                0,
                0x20009,
                ctypes.byref(capabilities),
                ctypes.sizeof(capabilities),
                None,
                None,
            ):
                raise ExecutionError("PYTHON_FAILED")
            if not kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x20002, handle_array, ctypes.sizeof(handle_array), None, None
            ):
                raise ExecutionError("PYTHON_FAILED")
            startup = StartupInfoEx()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100
            (
                startup.StartupInfo.hStdInput,
                startup.StartupInfo.hStdOutput,
                startup.StartupInfo.hStdError,
            ) = handles
            startup.lpAttributeList = ctypes.cast(attributes, wt.LPVOID)
            environment = {
                "SystemRoot": os.environ.get("SYSTEMROOT", "C:/Windows"),
                "WINDIR": os.environ.get("SYSTEMROOT", "C:/Windows"),
                "TEMP": str(folder),
                "TMP": str(folder),
                "PATH": str(executable.parent),
                "PYTHONUTF8": "1",
            }
            environment.update(
                {
                    "USERPROFILE": os.environ.get("USERPROFILE", str(Path.home())),
                    "LOCALAPPDATA": str(folder.parent),
                    "APPDATA": str(folder.parent),
                }
            )
            block = ctypes.create_unicode_buffer(
                "\0".join(key + "=" + value for key, value in sorted(environment.items())) + "\0\0"
            )
            command = ctypes.create_unicode_buffer(
                subprocess.list2cmdline(
                    [str(executable), "-I", "-S", "-B", "-X", "utf8", str(script)]
                )
            )
            if not kernel.CreateProcessW(
                str(executable),
                command,
                None,
                None,
                True,
                0x00000004 | 0x00080000 | 0x00000400 | 0x08000000,
                block,
                str(folder),
                ctypes.byref(startup),
                ctypes.byref(process),
            ):
                raise OSError(ctypes.get_last_error(), "AppContainer process creation failed")
            # 3、挂起创建后先施加进程数、内存和退出限制，再允许脚本开始，避免子进程逃出生命周期。
            job = kernel.CreateJobObjectW(None, None)
            limits = JobLimits()
            limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x8 | 0x100
            limits.BasicLimitInformation.ActiveProcessLimit = 1
            limits.ProcessMemoryLimit = 512 * 1024 * 1024
            ui_limits = wt.DWORD(0xFF)
            if (
                not job
                or not kernel.SetInformationJobObject(
                    job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                )
                or not kernel.SetInformationJobObject(
                    job, 4, ctypes.byref(ui_limits), ctypes.sizeof(ui_limits)
                )
                or not kernel.AssignProcessToJobObject(job, process.hProcess)
            ):
                raise ExecutionError("PYTHON_FAILED")
            if kernel.ResumeThread(process.hThread) == 0xFFFFFFFF:
                raise ExecutionError("PYTHON_FAILED")
            deadline, reason = time.monotonic() + timeout, ""
            while True:
                wait_result = kernel.WaitForSingleObject(process.hProcess, 100)
                if wait_result == 0:
                    break
                if wait_result != 0x102:
                    raise ExecutionError("PYTHON_FAILED")
                if cancelled.is_set() or time.monotonic() >= deadline:
                    reason = "cancelled" if cancelled.is_set() else "timeout"
                elif (logs / "stdout.txt").stat().st_size + (
                    logs / "stderr.txt"
                ).stat().st_size > 1024 * 1024:
                    reason = "output_limit"
                if reason:
                    kernel.TerminateJobObject(job, 1)
                    kernel.WaitForSingleObject(process.hProcess, 5000)
                    break
            code = wt.DWORD()
            if not kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code)):
                raise ExecutionError("PYTHON_FAILED")
        # 4、只读取有限日志；运行失败仍真实返回错误，不能伪造文件或成功结果。
        output: dict[str, Any] = {
            "exit_code": code.value,
            "reason": reason,
            "isolation": "windows-appcontainer",
            "network": False,
        }
        for name in ("stdout", "stderr"):
            with (logs / (name + ".txt")).open("rb") as stream:
                output[name] = stream.read(32000).decode("utf-8", errors="replace")
        files = list(folder.rglob("*"))
        if any(path.is_symlink() or path.is_junction() for path in files):
            raise ValueError("Python 输出不能包含符号链接或目录联接")
        ordinary = [
            path
            for path in files
            if path.is_file() and ".roomcrew-output" not in path.relative_to(folder).parts
        ]
        if len(ordinary) > 256 or sum(path.stat().st_size for path in ordinary) > 32 * 1024 * 1024:
            raise ValueError("Python 输出超过大小限制")
        for path in ordinary:
            destination = original_folder / path.relative_to(folder)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        return output
    finally:
        # 5、先结束所有执行，再释放句柄、撤销专属目录授权并删除临时容器身份。
        if job:
            kernel.TerminateJobObject(job, 1)
            kernel.CloseHandle(job)
        if process.hProcess:
            kernel.TerminateProcess(process.hProcess, 1)
            kernel.CloseHandle(process.hProcess)
        if process.hThread:
            kernel.CloseHandle(process.hThread)
        if attributes_initialized:
            kernel.DeleteProcThreadAttributeList(attributes)
        for path in granted:
            with suppress(Exception):
                directory_access(path, sid, False)
        if sid_text:
            kernel.LocalFree(ctypes.cast(sid_text, wt.LPVOID))
        if sid_pointer:
            advapi.FreeSid(sid_pointer)
        if container_folder:
            ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(container_folder, wt.LPVOID))
        if created:
            userenv.DeleteAppContainerProfile(profile)
