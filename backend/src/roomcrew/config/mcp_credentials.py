"""MCP Bearer 凭据的可信本地仓库；公开定义仅保存不可变引用。"""

import ipaddress
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from roomcrew.security.windows_dpapi import protect_bytes


class MCPCredentials:
    def __init__(self, private: Path, scope: str) -> None:
        """因为多个会议室共用私有目录，需要将每份不可变凭据绑定到所属空间和完整端点。"""
        # 1、路径和作用域由可信装配代码指定，不接受模型或界面提供文件路径。
        self._path = private / "mcp-credentials.dpapi"
        self._scope = scope

    def _load(self) -> dict[str, Any]:
        """因为凭据文件损坏不能触发环境变量兜底，需要明确失败并只在内存中解密。"""
        # 1、未保存是合法空仓库；损坏文件不自动覆盖，避免丢失其他空间的凭据。
        if not self._path.exists():
            return {}
        try:
            entries = json.loads(protect_bytes(self._path.read_bytes(), decrypt=True))
            if not isinstance(entries, dict):
                raise ValueError
            return entries
        except (OSError, TypeError, ValueError):
            raise ValueError("MCP 保护配置无法读取，请检查本地配置文件") from None

    def _write(self, entries: dict[str, Any]) -> None:
        """因为配置写入可能中断，需要先加密再原子替换，磁盘上不生成明文临时文件。"""
        # 1、使用同目录临时文件，所有操作在应用事件循环内同步完成且不包含 await。
        sealed = protect_bytes(json.dumps(entries, ensure_ascii=False).encode("utf-8"))
        temporary = self._path.with_suffix(".tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(sealed)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)

    def key(self, server: dict[str, Any]) -> str:
        """因为引用本身不能授权向新地址发送旧 Key，需要同时验证空间和端点绑定。"""
        # 1、无引用就是无认证；有引用时严格检查归属，禁止跨会议室复用或改地址后沿用。
        reference = server.get("auth_ref")
        if not reference:
            return ""
        entry = self._load().get(reference, {})
        if entry.get("scope") != self._scope or entry.get("url") != server["url"]:
            raise ValueError("MCP 凭据与当前空间或地址不匹配，请重新填写 Key")
        return self.validate_key(server["url"], entry.get("key", ""))

    @staticmethod
    def validate_key(url: str, key: Any) -> str:
        """因为认证 Header 需要防注入且不能经公网明文传送，需要验证 Key 和认证端点。"""
        # 1、Bearer 只接受有限可打印 ASCII；不接收已经拼接的 Header 或换行。
        if not isinstance(key, str) or not 1 <= len(key) <= 4096:
            raise ValueError("请填写 MCP API Key")
        if any(ord(char) < 33 or ord(char) > 126 for char in key):
            raise ValueError("MCP API Key 不得包含空格、换行或非 ASCII 字符")
        # 2、只有本机回环地址可使用 HTTP，其他认证服务必须使用 HTTPS。
        parsed = urlsplit(url)
        loopback = parsed.hostname == "localhost"
        with suppress(ValueError):
            loopback = loopback or ipaddress.ip_address(parsed.hostname or "").is_loopback
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("带 API Key 的 MCP 服务必须使用 HTTPS；本机回环测试除外")
        return key

    def resolve(self, server: dict[str, Any], auth: dict[str, Any] | None = None) -> str:
        """因为测试和保存应使用同一表单语义，需要统一处理无认证、替换 Key 和留空保留。"""
        # 1、未提交鉴权编辑时保留旧引用；字段白名单防止用户误填任意认证 Header。
        if auth is None:
            return self.key(server)
        if not isinstance(auth, dict) or set(auth) - {"mode", "api_key"}:
            raise ValueError("MCP 鉴权只支持无认证或 Bearer API Key")
        if auth.get("mode") == "none":
            return ""
        if auth.get("mode") != "bearer":
            raise ValueError("未知 MCP 鉴权方式")
        # 2、留空只允许复用匹配当前端点的凭据，测试不改变原配置。
        key = auth.get("api_key", "")
        if key == "":
            key = self.key(server)
        return self.validate_key(server["url"], key)

    @contextmanager
    def prepare(
        self, servers: list[dict[str, Any]], updates: dict[str, Any]
    ) -> Iterator[list[dict[str, Any]]]:
        """因为业务配置使用 SQLite 版本校验，需要先保存不可变引用并在业务失败时清理新凭据。

        旧引用保留以支持历史 checkpoint；本方法上下文内禁止 await，不修改其他运行的凭据。
        """
        # 1、先验证所有编辑内容，再写入；秘密绝不成为业务回调的输入。
        if not isinstance(updates, dict) or set(updates) - {item["name"] for item in servers}:
            raise ValueError("MCP 鉴权编辑与服务列表不一致")
        entries = self._load()
        added = []
        public = []
        for server in servers:
            item = dict(server)
            key = self.resolve(server, updates.get(server["name"]))
            if not key:
                item.pop("auth_ref", None)
            elif entries.get(server.get("auth_ref", ""), {}) != {
                "scope": self._scope,
                "url": server["url"],
                "key": key,
            }:
                reference = uuid4().hex
                entries[reference] = {"scope": self._scope, "url": server["url"], "key": key}
                item["auth_ref"] = reference
                added.append(reference)
            public.append(item)
        # 2、新 Key 先加密落地，SQLite CAS 或其他业务校验失败时只删除本次新增的引用。
        if added:
            self._write(entries)
        try:
            yield public
        except BaseException:
            if added:
                for reference in added:
                    entries.pop(reference)
                self._write(entries)
            raise
