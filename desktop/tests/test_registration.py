"""真实透明图集的体型校准与原始素材不变约束。"""

import hashlib
import json
from pathlib import Path

from PIL import Image

from roomcrew_desktop.assets.registration import head_width, register_frames


def test_bundled_frames_keep_head_scale_and_sources_immutable() -> None:
    """因为人物各动作不能忽大忽小，需要用四套真实图集验证头部尺度与站坐基线。"""
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
        # 2、动作与站坐共享同一头部尺度；腾空差异保留，不能将整个坐姿拉成长站姿。
        widths = [frame["head_width"] for frame in result["frames"]]
        assert max(widths) / min(widths) < 1.025
        assert result["sockets"]["standing"] < result["sockets"]["seated"]
        assert hashes == [
            hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in manifest["images"]
        ]
        assert (folder / "avatar.json").read_bytes() == body
    # 3、不透明矩形不是可识别人物头部，不能强行套用人体校准。
    assert head_width(Image.new("L", (64, 128), 255)) is None
