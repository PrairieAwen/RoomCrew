"""表现协议的有限词表；动作只能展示事实，不能执行命令。"""

from typing import Any

GESTURES = frozenset(
    {
        "idle",
        "think",
        "read",
        "type",
        "write",
        "work",
        "talk",
        "ask",
        "report",
        "alert",
        "listen",
        "walk",
        "run",
        "sit_down",
        "stand_up",
        "sit",
        "phone",
        "game",
        "water",
        "relax",
    }
)
EXPRESSIONS = frozenset({"neutral", "focused", "curious", "concerned", "smile"})
DIRECTIONS = ("s", "sw", "w", "nw", "n", "ne", "e", "se")
POSTURES = frozenset({"standing", "seated"})
LEISURE_ACTIONS = frozenset({"none", "phone", "game", "water", "relax"})
IDLE_ACTIVITIES = frozenset({"phone", "game", "wander", "chat", "water", "relax"})
DEFAULT_IDLE_ACTIVITIES = ["phone", "game", "wander", "chat"]


def leisure_profile(member: dict[str, Any]) -> dict[str, Any]:
    """因为同一 Agent 的不同形象可以有各自的空闲习惯，需要规范化只属于人物的摸鱼配置。

    返回最多四项活动及兼容的单动作字段；轮换固定为 300—600 秒，不解析脚本或路径。
    """
    # 1、旧账号没有这些字段时按人物身份提供默认值，不修改已有数据库版本。
    role = member.get("role", "employee")
    default = "none" if role == "guardian" else "game" if role == "employee" else "phone"
    action = member.get("leisure_action", default)
    delay = member.get("leisure_delay", 5)
    # 2、监管员不能通过生活动画冒充安全服务的运行状态。
    if not isinstance(action, str) or action not in LEISURE_ACTIONS:
        raise ValueError("空闲动作不在支持的词表中")
    if type(delay) is not int or not 0 <= delay <= 120:
        raise ValueError("空闲等待时间必须是 0—120 秒整数")
    if role == "guardian" and action != "none":
        raise ValueError("监管员保持值守，不配置摸鱼动作")
    # 3、新活动池优先；旧版保持待命继续禁用，旧自定义动作保留在最多四项的池中。
    defaults = list(DEFAULT_IDLE_ACTIVITIES)
    if action in {"water", "relax"}:
        defaults = [action, *defaults[:3]]
    activities = member.get("leisure_actions", [] if action == "none" else defaults)
    if (
        not isinstance(activities, list)
        or len(activities) > 4
        or any(not isinstance(item, str) or item not in IDLE_ACTIVITIES for item in activities)
        or len(set(activities)) != len(activities)
    ):
        raise ValueError("空闲活动最多四项，且必须是不同的注册活动")
    if role == "guardian" and activities:
        raise ValueError("监管员保持值守，不配置摸鱼活动")
    return {"leisure_action": action, "leisure_delay": delay, "leisure_actions": list(activities)}
