"""时间规则适配；业务绑定与 Agent 调度不进入时间计算。"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]


def aware_datetime(value: Any) -> datetime:
    """因为本地字符串可能有歧义，需要只接受显式带 UTC 偏移的时间点。"""
    # 1、解析失败只返回稳定中文提示，不把外部内容拼入异常。
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        raise ValueError("时间点须为带时区的 ISO 格式，例如 2026-10-29T14:30:00+08:00") from None


def normalize_trigger(value: Any, now: datetime) -> dict[str, Any]:
    """因为模型生成的日程不能直接执行，需要校验有界结构并固定时区与间隔起点。"""
    # 1、只接受四种已实现规则，不接受 Python 回调、任意 Cron 字符串或未知字段。
    if not isinstance(value, dict):
        raise ValueError("trigger 必须是时间规则对象")
    kind = value.get("type")
    fields = {
        "once": {"at"},
        "interval": {"seconds", "start_at"},
        "daily": {"time"},
        "weekly": {"time", "weekdays"},
    }
    if (
        not isinstance(kind, str)
        or kind not in fields
        or set(value) - {"type", "timezone", *fields[kind]}
    ):
        raise ValueError("时间规则仅支持 once、interval、daily、weekly 的标准字段")
    zone = value.get("timezone", "Asia/Shanghai")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("请使用有效 IANA 时区，例如 Asia/Shanghai") from None
    result: dict[str, Any] = {"type": kind, "timezone": zone}
    # 2、一次性任务使用精确时间；间隔最少一分钟，锚点持久化以免重启后漂移。
    if kind == "once":
        result["at"] = aware_datetime(value.get("at")).isoformat()
    elif kind == "interval":
        seconds = value.get("seconds")
        if type(seconds) is not int or not 60 <= seconds <= 2678400:
            raise ValueError("间隔须为 60～2678400 秒的整数，例如五分钟填写 300")
        start = value.get("start_at")
        result.update(
            seconds=seconds,
            start_at=(
                aware_datetime(start) if start else now + timedelta(seconds=seconds)
            ).isoformat(),
        )
    else:
        clock = value.get("time", "")
        try:
            hour, minute = map(int, clock.split(":"))
            if not 0 <= hour <= 23 or not 0 <= minute <= 59 or len(clock) != 5:
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise ValueError("每天或每周的时间须为 HH:mm，例如 14:30") from None
        result["time"] = f"{hour:02d}:{minute:02d}"
        if kind == "weekly":
            days = value.get("weekdays")
            if (
                not isinstance(days, list)
                or not days
                or any(type(day) is not int or not 0 <= day <= 6 for day in days)
            ):
                raise ValueError("weekdays 使用 0～6 的数组，0 为周一，6 为周日")
            result["weekdays"] = sorted(set(days))
    return result


def next_fire(trigger: dict[str, Any], after: datetime) -> datetime | None:
    """因为重启与修改都需要相同的下一次时间，需要通过公开触发器求严格晚于指定时刻的结果。"""
    # 1、一次性规则不补造时间，间隔按已保存起点对齐；内部统一 UTC。
    after = after.astimezone(UTC)
    if trigger["type"] == "once":
        target = aware_datetime(trigger["at"])
        return target if target > after else None
    zone = ZoneInfo(trigger["timezone"])
    if trigger["type"] == "interval":
        clock = IntervalTrigger(
            seconds=trigger["seconds"],
            start_date=aware_datetime(trigger["start_at"]),
            timezone=zone,
        )
        return cast(
            datetime | None, clock.get_next_fire_time(None, after + timedelta(microseconds=1))
        )
    # 2、日历规则跳过不存在的本地时间和回拨的第二个相同时刻，避免一天重复两次。
    hour, minute = map(int, trigger["time"].split(":"))
    calendar = CronTrigger(
        hour=hour,
        minute=minute,
        second=0,
        timezone=zone,
        day_of_week=",".join(map(str, trigger["weekdays"])) if trigger["type"] == "weekly" else "*",
    )
    cursor = after
    for _ in range(4):
        target = calendar.get_next_fire_time(None, cursor + timedelta(microseconds=1))
        if target is None:
            return None
        actual = target.astimezone(UTC).astimezone(zone)
        if target.fold == 0 and actual.replace(tzinfo=None) == target.replace(tzinfo=None):
            return cast(datetime, target.astimezone(UTC))
        cursor = target.astimezone(UTC)
    raise ValueError("所选时区的日历时间无法计算，请调整时间")
