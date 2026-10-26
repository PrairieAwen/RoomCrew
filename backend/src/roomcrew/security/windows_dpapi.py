"""Windows 用户级保护 API，不依赖配置或 Agent。"""

import ctypes
import os
from ctypes import wintypes


class ProtectionError(ValueError):
    """操作系统保护失败；调用方禁止回退明文。"""


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect_bytes(payload: bytes, *, decrypt: bool = False) -> bytes:
    """因为配置不能明文落盘，需要使用当前 Windows 用户的 DPAPI 加解密；失败不回退明文。"""
    # 1、该版本明确面向 Windows；保护 API 的失败必须显式向调用方报告。
    if os.name != "nt":
        raise ProtectionError("此版本需要 Windows 的本地配置保护服务")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_string_buffer(payload)
    source = DataBlob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = DataBlob()
    # 2、固定参数类型，避免 64 位指针截断；禁止弹出系统凭据交互窗口。
    if decrypt:
        operation = crypt.CryptUnprotectData
        operation.argtypes = [
            ctypes.POINTER(DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DataBlob),
        ]
        success = operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        operation = crypt.CryptProtectData
        operation.argtypes = [
            ctypes.POINTER(DataBlob),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(DataBlob),
        ]
        success = operation(
            ctypes.byref(source),
            "RoomCrew model configuration",
            None,
            None,
            None,
            1,
            ctypes.byref(output),
        )
    if not success:
        raise ProtectionError("无法保护或读取本地模型配置，请确认当前 Windows 用户")
    # 3、复制系统分配的结果并释放系统缓冲区，避免长期运行时泄漏。
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)
