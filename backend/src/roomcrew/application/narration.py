"""可选的低优先级表现模型；超时、无效或过期结果直接丢弃。"""

import asyncio
import json
import time
from typing import Any

from roomcrew.config.store import ConfigStore
from roomcrew.models.factory import create_model

ALLOWED = {
    "idle": {"idle"},
    "thinking": {"think", "read"},
    "executing": {"work", "read"},
    "delegating": {"talk"},
    "receiving": {"listen"},
    "question": {"ask"},
    "warning": {"alert"},
    "reporting": {"report"},
    "waiting": {"idle"},
    "stopped": {"idle"},
}


def validate_decoration(value: Any, state: dict[str, Any]) -> dict[str, str]:
    """因为模型输出不能直接控制素材或事实状态，需要只接收兼容动作和有限旁白。"""
    # 1、禁止任意帧、URL、脚本或权限字段，权威 activity 不在输出合同里。
    if not isinstance(value, dict) or set(value) != {"action_id", "summary"}:
        raise ValueError("旁白合同不匹配")
    text = value["summary"]
    if (
        value["action_id"] not in ALLOWED.get(state["activity"], {"idle"})
        or not isinstance(text, str)
        or not 1 <= len(text) <= 60
    ):
        raise ValueError("旁白动作或长度无效")
    if any(
        word in text.lower()
        for word in ("http", "<", ">", "已授权", "批准", "任务成功", "已经完成", "\n")
    ):
        raise ValueError("旁白包含不允许的声明")
    return {"action_id": value["action_id"], "summary": text}


class NarrationService:
    def __init__(self, config: ConfigStore) -> None:
        """因为旁白不能占据主执行链，需要使用独立配置、独立队列和独立故障预算。"""
        # 1、默认不调用任何模型，只有人工开启后才接收安全事实摘要。
        self.config = config
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._latest: dict[str, int] = {}
        self._started: dict[str, float] = {}
        self._decorations: dict[str, dict[str, Any]] = {}
        self._slot = asyncio.Semaphore(1)
        self._failures = 0
        self._retry_at = 0.0

    def decorate(self, actors: list[dict[str, Any]], enabled: bool) -> list[dict[str, Any]]:
        """因为场景不能等待额外模型，需要立即返回规则结果，只异步补充同一版本的装饰。"""
        # 1、只有有限的当前状态进入任务，不发送对话、工具输出、账号名或模型配置。
        result = []
        for state in actors:
            member = state["member_id"]
            self._latest[member] = state["source_seq"]
            decoration = self._decorations.get(member)
            if enabled and decoration and decoration["source_seq"] == state["source_seq"]:
                result.append(
                    {
                        **state,
                        **decoration["value"],
                        "origin": "model",
                        "rule_summary": state["summary"],
                    }
                )
            else:
                result.append(state)
            # 2、队列有界、每人十秒至多一次，故障冷却不影响 Agent 或基础交互。
            if (
                enabled
                and state["active_contexts"]
                and member not in self._tasks
                and not (decoration and decoration["source_seq"] == state["source_seq"])
                and len(self._tasks) < 4
                and time.monotonic() >= self._retry_at
                and time.monotonic() - self._started.get(member, -100) >= 10
            ):
                self._started[member] = time.monotonic()
                self._tasks[member] = asyncio.create_task(self._run(state))
        return result

    async def _run(self, state: dict[str, Any]) -> None:
        """因为辅助模型可能慢或幻觉，需要有界调用并在当前事实版本仍一致时才采用结果。"""
        # 1、所有网络请求使用旁白域的受保护模型配置，不借用执行模型 Key。
        model = None
        member = state["member_id"]
        try:
            async with self._slot, asyncio.timeout(2):
                if (
                    self._latest.get(member) != state["source_seq"]
                    or time.monotonic() - self._started[member] >= 2
                ):
                    return
                model = create_model(self.config.require_profile())
                facts = {
                    key: state[key]
                    for key in ("activity", "active_contexts", "question_count", "warning_count")
                }
                reply = await model.ainvoke(
                    "只输出 JSON，字段 action_id 与 summary。只描述这些事实，不宣称完成或授权。"
                    + "允许动作："
                    + json.dumps(sorted(ALLOWED[state["activity"]]))
                    + "。事实："
                    + json.dumps(facts),
                    max_tokens=160,
                )
                content = reply.content
                if not isinstance(content, str) or len(content) > 1000:
                    raise ValueError("旁白响应过长")
                value = validate_decoration(json.loads(content), state)
                if self._latest.get(member) == state["source_seq"]:
                    self._decorations[member] = {"source_seq": state["source_seq"], "value": value}
                self._failures = 0
        except Exception:
            # 2、无效输出和超时退回既有规则，三次失败后冷却一分钟。
            self._failures += 1
            if self._failures >= 3:
                self._retry_at = time.monotonic() + 60
        finally:
            try:
                if model is not None:
                    await model.close()
            except Exception:
                pass
            finally:
                self._tasks.pop(member, None)

    async def close(self) -> None:
        """因为关闭或禁用时不能遗留额外请求，需要取消辅助任务而不触碰主执行器。"""
        # 1、取消只影响表现模型，规则结果始终可用。
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._decorations.clear()
