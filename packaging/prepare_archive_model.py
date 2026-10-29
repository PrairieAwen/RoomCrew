"""准备可随应用离线分发的中文语义模型；不处理用户文本或配置。"""

import json
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> None:
    """因为用户无需另配 embedding 服务，需要在构建时取得固定的公开 ONNX 模型和许可。"""
    # 1、下载只发生在明确的制作步骤，应用运行时不会自动访问模型站点。
    root = Path(__file__).resolve().parents[1]
    target = root / ".cache/archive-model"
    target.mkdir(parents=True, exist_ok=True)
    snapshot = Path(
        snapshot_download(
            "Qdrant/bge-small-zh-v1.5",
            allow_patterns=["*.json", "*.txt", "model_optimized.onnx", "LICENSE*", "README.md"],
            cache_dir=str(root / ".cache/embedding-download"),
        )
    )
    # 2、复制真实文件而非缓存符号链接，固定实际下载版本以便后续核对和离线打包。
    for source in snapshot.iterdir():
        if source.is_file():
            shutil.copyfile(source, target / source.name)
    (target / "roomcrew-model.json").write_text(
        json.dumps(
            {
                "model": "BAAI/bge-small-zh-v1.5",
                "repository": "Qdrant/bge-small-zh-v1.5",
                "revision": snapshot.name,
                "dimensions": 512,
                "license": "MIT",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(target)


if __name__ == "__main__":
    main()
