"""按元数据先过滤的文本和向量检索；没有独立数据库服务。"""

import heapq
import sqlite3
from pathlib import Path
from typing import Any

from roomcrew.storage.archives import ArchiveRepository


def filters(values: dict[str, Any], prefix: str = "d") -> tuple[str, list[Any]]:
    """因为检索不能先搜全库再隐藏未授权结果，需要在 SQL 中先限定空间、成员与日期。"""
    # 1、列名前缀只由本模块常量传入，所有用户值均使用占位参数。
    terms, parameters = [f"{prefix}.workspace_id=?"], [values["workspace_id"]]
    for name, operator in (
        ("member_id", "="),
        ("agent_id", "="),
        ("from_time", ">="),
        ("to_time", "<="),
    ):
        if values.get(name):
            column = "at" if name.endswith("time") else name
            terms.append(f"{prefix}.{column}{operator}?")
            parameters.append(values[name])
    if values.get("kind"):
        terms.append(f"{prefix}.kind=?")
        parameters.append(values["kind"])
    return " AND ".join(terms), parameters


class ArchiveSearch:
    def __init__(self, repository: ArchiveRepository) -> None:
        """因为文字和向量应返回同一来源合同，需要共用档案元数据和过滤规则。"""
        # 1、不持有模型配置，向量编码由外层异步服务提供。
        self.repository = repository

    def text(self, query: str, values: dict[str, Any], limit: int = 30) -> list[dict[str, Any]]:
        """因为中文短词与长词索引能力不同，需要支持精确子串并对长词使用 FTS5 索引。"""
        # 1、FTS 表达式由转义的字面词构造，模型不能提交 SQL 或查询运算符。
        where, parameters = filters(values)
        words = query.split()
        if words and all(len(word) >= 3 for word in words):
            match = " AND ".join('"' + word.replace('"', '""') + '"' for word in words)
            statement = (
                "SELECT d.*,bm25(archive_fts) relevance FROM archive_fts "
                "JOIN archive_documents d ON d.id=archive_fts.rowid "
                "WHERE archive_fts MATCH ? AND " + where + " ORDER BY relevance,d.at DESC LIMIT ?"
            )
            parameters = [match, *parameters, limit]
        else:
            for word in words:
                where += " AND instr(lower(d.text),lower(?))>0"
                parameters.append(word)
            statement = (
                "SELECT d.* FROM archive_documents d WHERE " + where + " ORDER BY d.at DESC LIMIT ?"
            )
            parameters.append(limit)
        return [dict(row) for row in self.repository.db.execute(statement, parameters)]

    @staticmethod
    def vector(
        path: Path,
        query: bytes,
        values: dict[str, Any],
        model: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """因为个人档案可在 SQLite 内轻量计算，需要在工作线程分批读取已授权向量并保留有限候选。"""
        import numpy as np

        # 1、每次独立只读连接属于当前线程，不跨线程使用宿主的写连接。
        where, parameters = filters(values)
        vector = np.frombuffer(query, dtype="<f4")
        best: list[tuple[float, int, dict[str, Any]]] = []
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT d.* FROM archive_documents d WHERE "
                + where
                + " AND d.model=? AND d.vector IS NOT NULL",
                [*parameters, model],
            )
            while batch := rows.fetchmany(256):
                for row in batch:
                    candidate = np.frombuffer(row["vector"], dtype="<f4")
                    if candidate.shape != vector.shape:
                        continue
                    score = float(np.dot(vector, candidate))
                    item = (score, row["id"], {**dict(row), "similarity": score})
                    if len(best) < limit:
                        heapq.heappush(best, item)
                    elif score > best[0][0]:
                        heapq.heapreplace(best, item)
        # 2、只返回已通过数据库范围过滤的候选，内部向量不会暴露给模型或界面。
        return [item[2] for item in sorted(best, reverse=True)]

    def recent(self, values: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
        """因为用户通常只关心上次对话，需要优先按会话日期读取有限目录和摘要进度。"""
        # 1、目录仍限定来源空间，时间按会话结束时间，成员按会话入口所有者。
        compatible = {**values}
        member = compatible.pop("member_id", "")
        where, parameters = filters(compatible, "d")
        where = where.replace("d.at", "d.ended_at")
        if member:
            where += " AND (d.member_id=? OR EXISTS(SELECT 1 FROM archive_documents own "
            where += "WHERE own.archive_id=d.id AND own.member_id=?))"
            parameters.extend([member, member])
        rows = self.repository.db.execute(
            "SELECT d.*,(SELECT count(*) FROM archive_messages m WHERE m.archive_id=d.id) messages,"
            "(SELECT count(*) FROM archive_parts p WHERE p.archive_id=d.id) parts,"
            "(SELECT count(*) FROM archive_parts p WHERE p.archive_id=d.id AND result IS NOT NULL) "
            "completed_parts FROM archives d WHERE " + where + " ORDER BY ended_at DESC LIMIT ?",
            [*parameters, limit],
        )
        return [dict(row) for row in rows]
