"""真实透明图集的体型校准与原始素材不变约束。"""

import hashlib
import json
from pathlib import Path

from PIL import Image

from roomcrew_desktop.assets.registration import head_width, register_frames


def test_bundled_frames_keep_clip_scale_and_sources_immutable() -> None:
    """因为逐帧估算头宽会产生呼吸式缩放，需要验证五套真实图集按整段校准且源文件不变。"""
    # 1、读取真实随包图集，原图与帧号必须完全不变，校准只生成显示元数据。
    root = Path(__file__).resolve().parents[1] / "ui/studio/assets/library-v1/characters"
    for folder in root.iterdir():
        body = (folder / "avatar.json").read_bytes()
        manifest = json.loads(body)
        manifest["display_height"] = 128
        pages = [(folder / name).read_bytes() for name in manifest["images"]]
        hashes = [hashlib.sha256(page).hexdigest() for page in pages]
        result = register_frames(manifest, pages)
        assert result and len(result["frames"]) == len(manifest["frame_rects"])
        # 2、走路和跑步保留原步态起伏，但同一个方向的片段不能逐帧改变相对作者的倍率。
        assert result["strategy"] == "clip-median"
        for clip in manifest["clips"]:
            if clip["action"] not in {"walk", "run"}:
                continue
            factors = [
                result["frames"][index]["scale"]
                / manifest["frame_rects"][index].get("scale", 1)
                for index in clip["frames"]
            ]
            assert max(factors) - min(factors) < 0.000001
        if folder.name == "hippo":
            # 短腿吉祥物坐到带脚踏的高椅后头部反而高于站立，不能强套人类身高关系。
            assert result["sockets"]["standing"] > result["sockets"]["seated"]
        else:
            assert result["sockets"]["standing"] < result["sockets"]["seated"]
        assert hashes == [
            hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in manifest["images"]
        ]
        assert (folder / "avatar.json").read_bytes() == body
    # 3、不透明矩形不是可识别人物头部，不能强行套用人体校准。
    assert head_width(Image.new("L", (64, 128), 255)) is None
