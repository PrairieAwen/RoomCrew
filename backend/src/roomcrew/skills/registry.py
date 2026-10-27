"""显式 Skill 来源校验；正文渐进加载由 Deep Agents 执行。"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from roomcrew.contracts.errors import ExecutionError
from roomcrew.security.paths import resolve_task_path


@dataclass(frozen=True)
class SkillPolicy:
    sources: tuple[str, ...] = ()


def resolve_skill_sources(root: Path, policy: SkillPolicy) -> list[str]:
    """因为技能只能从可信代码声明的任务路径加载，需要先检查来源而不提前读取全部正文。"""
    # 1、未声明时不自动扫描用户磁盘；同一来源只注册一次。
    sources = []
    for source in dict.fromkeys(policy.sources):
        try:
            folder = resolve_task_path(root, source)
            # 2、显式声明的来源必须存在并包含技能，避免框架静默跳过造成用户误判。
            if not source.startswith("/skills/") or not folder.is_dir():
                raise ValueError("无效技能来源")
            if not any(path.is_file() for path in folder.glob("*/SKILL.md")):
                raise ValueError("技能来源为空")
        except ValueError:
            raise ExecutionError("SKILL_SOURCE_INVALID") from None
        sources.append(source)
    return sources


def materialize_skills(home: Path, configuration: dict[str, Any]) -> str | None:
    """因为技能正文需要渐进读取且不能混入可写任务目录，需要按内容哈希创建只读挂载源。"""
    # 1、只从已经验证的运行快照生成文本包；名称和文件路径已由配置入口校验。
    skills = configuration.get("skills", [])
    if not skills:
        return None
    digest = hashlib.sha256(
        json.dumps(skills, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    destination = home / digest
    if not destination.is_dir():
        for skill in skills:
            folder = destination / skill["name"]
            folder.mkdir(parents=True, exist_ok=True)
            header = (
                "---\nname: "
                + skill["name"]
                + "\ndescription: "
                + json.dumps(skill["description"], ensure_ascii=False)
                + "\n---\n\n"
            )
            (folder / "SKILL.md").write_text(header + skill["instructions"], encoding="utf-8")
            for relative, text in skill.get("files", {}).items():
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
    # 2、返回 SDK 虚拟路径，宿主绝对路径不会进入提示词。
    return "/skills/configured/" + digest + "/"
