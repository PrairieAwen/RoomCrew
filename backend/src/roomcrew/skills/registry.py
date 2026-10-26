"""显式 Skill 来源校验；正文渐进加载由 Deep Agents 执行。"""

from dataclasses import dataclass
from pathlib import Path

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
