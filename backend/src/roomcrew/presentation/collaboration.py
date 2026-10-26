"""按真实委派作用域维护协作关系，只产生可丢弃的表现语义。"""

from typing import Any


def reduce_delegation(actors: dict[str, Any], event: dict[str, Any]) -> None:
    """因为已配置员工和临时外援的表现不同，需要按真实调用作用域建立与清理有界关系。

    同一 Run 合并会议，外援不创建人物；终态立即释放，不延迟真实工具执行。
    """
    # 1、终态先清理所有参与者的本 Run 关系，不借用人物 ID 共享任务上下文。
    kind, payload = event["kind"], event["payload"]
    run_id, scope = event["run_id"], event.get("scope", "main")
    if kind in {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}:
        for actor in actors.values():
            actor["delegations"] = {
                key: link
                for key, link in actor.get("delegations", {}).items()
                if link["run_id"] != run_id
            }
        return
    if kind in {"task.completed", "task.failed"}:
        for actor in actors.values():
            actor.get("delegations", {}).pop(run_id + ":" + scope, None)
        return
    # 2、仅明确适配出的委派元数据可以触发协作；旧事件不根据自然语言或名字猜外援。
    category = payload.get("delegation_kind")
    parent_id = payload.get("from_member_id")
    if (
        kind != "task.assigned"
        or category not in {"configured", "external"}
        or parent_id not in actors
    ):
        return
    links = actors[parent_id].setdefault("delegations", {})
    if len(links) >= 128:
        return
    links[run_id + ":" + scope] = {
        "run_id": run_id,
        "scope": scope,
        "kind": category,
        "parent": parent_id,
        "target": payload.get("target_member_id"),
        "source_seq": event["seq"],
    }


def meeting_groups(actors: list[dict[str, Any]], states: dict[str, Any]) -> list[dict[str, Any]]:
    """因为同一任务的多个委派要聚在一起，需要按 Run 合并稳定成员并保留真实人工等待优先级。"""
    # 1、这里只使用关系 ID 与已归约事实，不向场景广播任务或工具正文。
    facts = {actor["member_id"]: actor for actor in actors}
    groups: dict[str, dict[str, Any]] = {}
    for state in states.values():
        for link in state.get("delegations", {}).values():
            if (
                link["kind"] != "configured"
                or not link.get("target")
                or link["target"] == link["parent"]
            ):
                continue
            group = groups.setdefault(
                link["run_id"],
                {
                    "kind": "meeting",
                    "group_id": link["run_id"],
                    "source_seq": link["source_seq"],
                    "members": set(),
                },
            )
            group["members"].update((link["parent"], link["target"]))
            group["source_seq"] = min(group["source_seq"], link["source_seq"])
    # 2、疑问和错误人物不被会议盖住；同任务其他成员仍可保留真实协作关系。
    result = []
    for group in groups.values():
        members = sorted(
            member
            for member in group["members"]
            if member in facts
            and not facts[member]["requires_input"]
            and not facts[member]["warning_count"]
        )
        if len(members) >= 2:
            result.append({**group, "members": members})
    return sorted(result, key=group_sequence)


def group_sequence(group: dict[str, Any]) -> tuple[int, str]:
    """因为同一人物可能出现在多个并行关系中，需要用稳定排序决定当前可见会议。"""
    # 1、优先展示先建立的真实关系，避免轮询顺序改变导致反复换座。
    return group["source_seq"], group["group_id"]
