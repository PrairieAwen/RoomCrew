"""封存后完整历史的不可变压缩副本与完整公开消息投影。"""

import gzip
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from roomcrew.archive.text import visible_messages


def write_lines(path: Path, rows: Any) -> dict[str, Any]:
    """因为官方轨迹可能很大，需要流式压缩每条原记录并计算文件完整性校验值。"""
    # 1、写入的是公开持久记录，不增加模型配置、运行对象或隐藏推理。
    count = 0
    with (
        path.open("wb") as output,
        gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0) as zipped,
    ):
        for value in rows:
            zipped.write((json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode())
            count += 1
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return {"rows": count, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def native_rows(cursor: sqlite3.Cursor) -> Any:
    """因为原生轨迹正文是 JSON，需要逐行展开而不把整份重复上下文加载到内存。"""
    # 1、保留收到时间、产品 Run、SDK 调用树与原生内容，不借压缩截断字段。
    for row in cursor:
        yield {**dict(row), "body": json.loads(row["body"])}


def snapshot(
    database: Path,
    folder: Path,
    record: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """因为两种 SQLite 记录和文件副本需要同一高水位，需要在线程内取得一致只读快照再原子发布。"""
    # 1、固定会话与事件范围；单独连接属于当前工作线程，不跨线程使用宿主连接。
    temporary = folder.parent / (".partial-" + uuid4().hex)
    temporary.mkdir(parents=True)
    try:
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            events = [
                {**dict(row), "payload": json.loads(row["payload"])}
                for row in db.execute(
                    "SELECT * FROM events WHERE conversation_id=? AND seq<=? ORDER BY seq",
                    (record["conversation_id"], record["event_seq"]),
                )
            ]
            messages = visible_messages(events)
            manifest = {
                "version": 1,
                "archive_id": record["id"],
                "workspace_id": record["workspace_id"],
                "conversation_id": record["conversation_id"],
                "event_seq": record["event_seq"],
                "native_seq": record["native_seq"],
                "files": {},
            }
            manifest["files"]["events.jsonl.gz"] = write_lines(
                temporary / "events.jsonl.gz", events
            )
            manifest["files"]["messages.jsonl.gz"] = write_lines(
                temporary / "messages.jsonl.gz", messages
            )
            manifest["files"]["native.jsonl.gz"] = write_lines(
                temporary / "native.jsonl.gz",
                native_rows(
                    db.execute(
                        "SELECT * FROM native_events WHERE conversation_id=? "
                        "AND seq<=? ORDER BY seq",
                        (record["conversation_id"], record["native_seq"]),
                    ),
                ),
            )
        # 2、只发布全部成功的目录；跨介质回执丢失时校验复用，不覆盖原始已发布副本。
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8"
        )
        if folder.exists():
            existing = json.loads((folder / "manifest.json").read_text("utf-8"))
            if existing != manifest:
                raise ValueError("档案副本校验不一致，请人工检查原始记录")
            for name, info in manifest["files"].items():
                with (folder / name).open("rb") as original:
                    if hashlib.file_digest(original, "sha256").hexdigest() != info["sha256"]:
                        raise ValueError("既有档案文件完整性校验失败，原文件未被覆盖")
        else:
            temporary.rename(folder)
        return messages, manifest
    finally:
        # 3、仅清理本方法刚建立且仍位于档案根内的临时目录，不触及原会话或已发布文件。
        if temporary.exists() and temporary.resolve().parent == folder.parent.resolve():
            shutil.rmtree(temporary)
