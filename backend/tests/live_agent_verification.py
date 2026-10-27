"""显式启用的真实模型综合验收；不进入普通 pytest，不打印或复制模型秘密。"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import sys
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

project = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(project / "backend/src"), str(project / "backend/tests")]
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from mcp_fixture import mcp_server

from roomcrew.application.runtime import Runtime
from roomcrew.platform.paths import AppPaths


async def verify(
    config_root: Path,
    output: Path,
    mcp_url: str,
    mcp_calls: list[dict],
    file_lifecycle: bool = False,
) -> dict:
    """因为用户要求验证已配置模型，需要让生产框架自行规划、委派、运行代码并处理合成人工问题。"""
    # 1、测试产物和轨迹独立保存，私有连接只通过应用已有 ConfigStore / ModelFactory 使用。
    root = project / ".cache/live-agent-verification" / uuid4().hex
    paths = replace(AppPaths.create(root), private=config_root.resolve() / "private")
    runtime = Runtime(paths)
    await runtime.start()
    started = time.monotonic()
    report = {
        "live_model": True,
        "root": str(root),
        "production_loop": "deepagents",
        "scripted_model_responses": False,
    }
    try:
        if not runtime.config.path.is_file():
            raise RuntimeError("未找到已保存的模型连接；未读取其他目录")
        worker = await runtime.save_member(
            {
                "id": "verification_worker",
                "name": "验收同事",
                "description": "使用已配置的验收技能、数学 MCP 和隔离 Python 处理验证任务",
                "prompt": "你是通用数字同事。对执行结果保持诚实，通过真实工具完成委派并返回证据。",
                "skills": [
                    {
                        "name": "verification-record",
                        "description": "数值和文档交付前的证据核对",
                        "instructions": (
                            "交付前读取真实文件并核对数值。"
                            "用 Python 标准库完成计算，不凭心算冒充执行。"
                            "仅使用明确提供的模拟事实撰写日记，不杜撰用户经历。"
                        ),
                    }
                ],
                "mcp_servers": [{"name": "verification", "url": mcp_url}],
                "python_enabled": True,
            },
            0,
        )
        conversation = await runtime.new_conversation()
        files = paths.session_files(conversation["id"])
        numbers = [random.SystemRandom().randint(10, 999) for _ in range(23)]
        (files / "numbers.json").write_text(json.dumps(numbers), encoding="utf-8")
        expected = {
            "count": len(numbers),
            "sum": sum(numbers),
            "sum_squares": sum(value * value for value in numbers),
        }
        prompt = (
            "这是 RoomCrew 框架的合成功能验收，所有材料都是测试数据。"
            "先调用 list_agents 查看已有 Agent，再把计算和写作任务交给名为‘验收同事’的 Agent。"
            "同事需要按需阅读自己的 verification-record 技能，"
            "通过自己的 verification_add_numbers MCP 工具计算 37+58；"
            "读取 /numbers.json，自己编写 Python 脚本并实际调用 execute_python，"
            "计算 count、sum、sum_squares，"
            "将这三个字段作为 JSON 对象保存为 /verification-result.json，然后读取文件核对。"
            "再创建 /verification-diary.md：只根据三个模拟事实写一篇简短日记——"
            "整理了测试资料、调试了工作台、核对了计算结果。"
            "不要声称这些是用户的真实经历，日记应注明为模拟记录。"
            "你作为助手收到同事结果后，使用 ask_user 向验收操作者提一个 choice 类型问题，"
            "选项为‘通过’和‘继续检查’，"
            "允许其他补充；这是合成验收问题，不是系统安全授权。收到答复后读取产物并总结。"
            "必须真实执行上述工具，不可以仅描述计划、冒充已经执行或凭模型直接写入计算结果。"
        )
        if file_lifecycle:
            prompt += (
                "本轮还要让工作者验证默认文件管理工具：用 make_directory 创建 /archive，"
                "copy_file 把 /verification-diary.md 复制为 /archive/draft.md，"
                "再 move_file 移到 /archive/diary.md；file_info 查询该归档文件。"
                "用 write_file 新建 /temporary-note.txt，再用 delete_file 删除这个临时文件。"
                "请保留原始日记与最终归档，复制必须使用工具，不能重新生成不同内容。"
            )
        run = await runtime.submit(conversation["id"], prompt, uuid4().hex)
        print(
            json.dumps({"stage": "live_started", "conversation_id": conversation["id"]}), flush=True
        )
        answered = 0
        while True:
            if time.monotonic() - started > 600:
                await runtime.stop(run["run_id"])
                raise TimeoutError("真实验收超过本轮总时限")
            questions = await runtime.questions(conversation["id"])
            for question in questions:
                # 2、只答复本验收 Run 的合成问题；不读取或处理用户现有会话、审批或登录请求。
                if question["run_id"] != run["run_id"] or answered >= 3:
                    raise RuntimeError("收到非本验收的人工问题或重复问题过多")
                choices = question.get("choices", [])
                answer = (
                    "通过"
                    if "通过" in choices
                    else choices[0]
                    if choices
                    else "此为自动验收的合成答复，请继续按测试任务执行。"
                )
                await runtime.respond(question["id"], answer, uuid4().hex)
                answered += 1
                print(
                    json.dumps({"stage": "synthetic_human_answer", "count": answered}), flush=True
                )
            if not runtime.active and not questions:
                break
            await asyncio.sleep(0.25)
        # 3、检查真实产物与轨迹，预期值只在验证端计算，绝不替 Agent 生成缺失产物。
        events = []
        cursor = 0
        while batch := await runtime.events(conversation["id"], cursor):
            events.extend(batch)
            cursor = batch[-1]["seq"]
        started_tools = [event for event in events if event["kind"] == "tool.started"]
        names = [event["payload"]["name"] for event in started_tools]
        status = runtime.store.latest_status(conversation["id"])
        report.update(
            {
                "status": status,
                "conversation_id": conversation["id"],
                "tools": names,
                "mcp_calls": len(mcp_calls),
                "human_answers": answered,
                "worker_id": worker["id"],
                "seconds": round(time.monotonic() - started, 2),
            }
        )
        result_path = files / "verification-result.json"
        diary = files / "verification-diary.md"
        report["calculation_matches"] = (
            result_path.is_file() and json.loads(result_path.read_text("utf-8")) == expected
        )
        report["diary_exists"] = diary.is_file() and len(diary.read_text("utf-8")) > 50
        report["python_isolated"] = any(
            "windows-appcontainer" in event["payload"].get("output", "")
            for event in events
            if event["kind"] == "tool.completed"
        )
        report["skills_loaded"] = any(
            event["payload"].get("tool_kind") == "skill" for event in started_tools
        )
        report["delegated_to_configured_worker"] = any(
            event["kind"] == "task.assigned" and event["member_id"] == worker["id"]
            for event in events
        )
        report["ok"] = (
            status == "completed"
            and report["calculation_matches"]
            and report["diary_exists"]
            and report["python_isolated"]
            and report["skills_loaded"]
            and report["delegated_to_configured_worker"]
            and answered > 0
            and len(mcp_calls) > 0
            and "list_agents" in names
        )
        if file_lifecycle:
            archived = files / "archive/diary.md"
            report["default_file_tools"] = {
                "make_directory",
                "copy_file",
                "move_file",
                "file_info",
                "delete_file",
            } <= set(names)
            report["archive_matches_original"] = (
                archived.is_file()
                and diary.is_file()
                and archived.read_bytes() == diary.read_bytes()
            )
            report["temporary_file_removed"] = not (files / "temporary-note.txt").exists()
            report["ok"] = report["ok"] and all(
                report[key]
                for key in (
                    "default_file_tools",
                    "archive_matches_original",
                    "temporary_file_removed",
                )
            )
        report["artifact_sha256"] = (
            hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path.is_file() else None
        )
        return report
    finally:
        # 4、只写不含配置和秘密的验收摘要，并停止本验收自身的所有资源。
        report["seconds"] = round(time.monotonic() - started, 2)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        await runtime.close()


def main() -> None:
    """因为真实请求会消耗用户模型额度，需要显式命令参数启用而不纳入自动回归。"""
    # 1、参数只指定已存在的应用根，不接受明文 Key；日志禁止输出模型请求地址和底层异常。
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", required=True)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--files", action="store_true")
    options = parser.parse_args()
    logging.disable(logging.CRITICAL)
    with mcp_server() as (url, calls):
        logging.disable(logging.CRITICAL)
        result = asyncio.run(verify(options.config_root, options.report, url, calls, options.files))
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
