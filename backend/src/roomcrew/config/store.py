"""受保护模型配置的加载与原子保存。"""

import json
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from roomcrew.config.schema import ConfigurationError, ModelProfile
from roomcrew.config.validation import validate_profile
from roomcrew.security.windows_dpapi import protect_bytes


class ConfigStore:
    def __init__(self, private_dir: Path, filename: str = "model-config.dpapi") -> None:
        """因为密钥不属于任务资料，需要把配置仓库固定在独立私有目录。"""
        # 1、仅保存可信程序传入的路径，不允许 Agent 或前端更改配置文件位置。
        if filename not in {"model-config.dpapi", "presentation-model.dpapi"}:
            raise ValueError("未知模型配置域")
        self.path = private_dir / filename

    def require_profile(self) -> ModelProfile:
        """因为未配置时不能让 SDK 使用默认环境凭据，需要显式要求有效的人工配置。"""
        # 1、没有配置时给出明确提示，不创建默认模型。
        profile = self.load()
        if profile is None:
            raise ConfigurationError("请先在模型配置中填写并保存连接信息")
        return profile

    def summary(self) -> dict[str, Any]:
        """因为配置损坏也要允许用户修复，需要返回可编辑概况而不回传已保存的 Key。"""
        # 1、坏文件只影响连接配置，不阻止用户打开人工修复表单。
        try:
            profile = self.load()
        except ConfigurationError:
            return {"configured": False, "recovery_required": True}
        return profile.public() if profile else {"configured": False}

    def load(self) -> ModelProfile | None:
        """因为构建模型需要真实参数，需要由代码读取受保护文件；损坏文件不能静默忽略。"""
        # 1、未配置是合法状态；现有文件只能通过 DPAPI 读取。
        if not self.path.exists():
            return None
        try:
            value = json.loads(protect_bytes(self.path.read_bytes(), decrypt=True))
            return ModelProfile(**value)
        except (OSError, TypeError, ValueError) as error:
            raise ConfigurationError("本地模型配置无法读取，请重新保存配置") from error

    def save(self, values: dict[str, Any]) -> ModelProfile:
        """因为用户会反复保存或更换端点，需要校验完整配置，只在实际变更时原子替换保护文件。"""
        # 1、限定为首版已实现的 Chat Completions 协议，验证端点不包含认证片段。
        try:
            previous = self.load()
        except ConfigurationError:
            # 损坏配置允许用户用完整新输入修复，但不能沿用无法读取的旧凭据。
            previous = None
        profile = validate_profile(values, previous)
        # 2、内容完全相同时保留已有引用，避免重复保存使原会话的模型绑定失效。
        if previous and replace(profile, reference=previous.reference) == previous:
            return previous
        # 3、先加密完整配置再写临时文件，成功后原子替换；磁盘不出现明文中间文件。
        sealed = protect_bytes(json.dumps(asdict(profile), ensure_ascii=False).encode("utf-8"))
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(sealed)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return profile
