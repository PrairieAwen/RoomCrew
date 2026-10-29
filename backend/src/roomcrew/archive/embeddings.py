"""延迟加载的真实中文语义向量；无网络下载、无哈希伪向量或远程密钥兜底。"""

import asyncio
import json
from pathlib import Path
from typing import Any

from roomcrew.archive.text import fragments

MODEL = "BAAI/bge-small-zh-v1.5"
DIMENSIONS = 512


class LocalEmbeddings:
    def __init__(self, resources: Path) -> None:
        """因为向量模型不应拖慢应用启动，需要只登记随包资源并按第一次检索或索引加载。"""
        # 1、开发资源和发行资源位置固定，Agent 不能把任意文件路径作为模型来源。
        self.path = resources / (
            "archive-model" if (resources / "archive-model").is_dir() else ".cache/archive-model"
        )
        self._model: Any = None
        self._lock = asyncio.Lock()
        manifest = self.path / "roomcrew-model.json"
        revision = (
            json.loads(manifest.read_text("utf-8")).get("revision", "unknown")
            if manifest.is_file()
            else "missing"
        )
        self.identity = f"{MODEL}@{revision}:512"

    @property
    def available(self) -> bool:
        """因为缺少本地模型时必须明确降级，需要在不加载模型的情况下检查资源完整性。"""
        # 1、不会在查询失败后偷偷访问 Hugging Face 或向远程发送用户文本。
        return all(
            (self.path / name).is_file()
            for name in ("model_optimized.onnx", "tokenizer.json", "config.json")
        )

    def _embed(self, texts: list[str], query: bool) -> list[bytes]:
        """因为 ONNX 推理会占用 CPU，需要在工作线程串行加载和执行真实模型。"""
        import numpy as np
        from fastembed import TextEmbedding

        # 1、CPU 限制两个推理线程，只读固定本地模型，不自动下载或使用 GPU。
        if self._model is None:
            self._model = TextEmbedding(
                MODEL,
                specific_model_path=str(self.path),
                local_files_only=True,
                threads=2,
                providers=["CPUExecutionProvider"],
            )
        pieces = [fragments(text) or [""] for text in texts]
        flattened = [piece for group in pieces for piece in group]
        values = list(
            self._model.query_embed(flattened) if query else self._model.passage_embed(flattened)
        )
        result = []
        index = 0
        for group in pieces:
            vector = np.asarray(values[index : index + len(group)], dtype="<f4").mean(axis=0)
            index += len(group)
            if vector.shape != (DIMENSIONS,) or not np.isfinite(vector).all():
                raise ValueError("本地语义模型返回了无效向量")
            norm = float(np.linalg.norm(vector))
            if norm <= 0:
                raise ValueError("本地语义模型返回了空向量")
            result.append((vector / norm).astype("<f4").tobytes())
        return result

    async def embed(self, texts: list[str], query: bool = False) -> list[bytes]:
        """因为索引与查询可能同时发生，需要限制本地模型并发且不阻塞后端事件循环。"""
        # 1、失败显式报告，文本检索由调用方有说明地降级，不生成替代向量。
        if not self.available:
            raise ValueError("本地语义模型资源尚未准备，仍可使用文本和时间检索")
        async with self._lock:
            return await asyncio.to_thread(self._embed, texts, query)

    def close(self) -> None:
        """因为退出后不应保留模型占用，需要在后台作业停止后释放本地推理引用。"""
        # 1、推理由宿主先等待结束，再释放会话内存。
        self._model = None
