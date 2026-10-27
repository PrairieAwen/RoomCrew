"""有界本地素材导入：只接受校验后的 PNG 和 JSON，不保留源文件路径。"""

import base64
import hashlib
import io
import json
import re
import threading
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image, UnidentifiedImageError

from roomcrew_desktop.assets.paths import atlas_filenames
from roomcrew_desktop.assets.registration import register_frames
from roomcrew_desktop.assets.schema import validate_manifest

BUILTIN = "builtin:crew-v1"


def normalize_png(data: bytes) -> tuple[bytes, tuple[int, int]]:
    """因为图片可包含损坏数据、超大解码尺寸或元数据，需要严格验证后重编码为单帧 RGBA。"""
    # 1、解析前限制输入大小和格式；不用插件自动识别其他图片类型。
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("PNG 文件不能超过 4 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG"]) as picture:
                size = picture.size
                if max(size) > 2048 or min(size) < 32 or getattr(picture, "n_frames", 1) != 1:
                    raise ValueError("图集应为 32～2048 像素的单帧 PNG，不接受 APNG")
                picture.verify()
            # 2、解码边界确认后剥离文字、ICC 和其他元数据，避免外部信息随素材传播。
            with Image.open(io.BytesIO(data), formats=["PNG"]) as picture:
                clean = Image.frombytes("RGBA", size, picture.convert("RGBA").tobytes())
                output = io.BytesIO()
                clean.save(output, format="PNG", compress_level=6)
                encoded = output.getvalue()
                if len(encoded) > 8 * 1024 * 1024:
                    raise ValueError("规范化后的图集超过 8 MiB")
                return encoded, size
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as error:
        raise ValueError("PNG 无法安全解码，请检查素材文件") from error


class AvatarLibrary:
    def __init__(self, root: Path) -> None:
        """因为素材库异常不能阻止 Agent 启动，需要只保存路径并按需读取本地素材。"""
        # 1、库目录在会话文件视图之外；不打开网络或扫描用户磁盘。
        self.root = root
        self._lock = threading.Lock()
        self._clip_catalog: dict[str, dict[str, Any]] = {}
        self._registrations: dict[str, dict[str, Any] | None] = {}

    def clip_catalog(self, identifier: str) -> dict[str, Any] | None:
        """因为保存帧绑定只需要图集清单，需要缓存不可变素材元数据而不反复编码 PNG。"""
        # 1、内置骨架没有外部帧号；内容寻址图集的清单只在首次引用时读取。
        if identifier == BUILTIN:
            return None
        if identifier not in self._clip_catalog:
            path = self._path(identifier) / "avatar.json"
            if path.stat().st_size > 128 * 1024:
                raise ValueError("素材描述文件过大")
            self._clip_catalog[identifier] = json.loads(path.read_text("utf-8"))
        return self._clip_catalog[identifier]

    def import_manifest(self, path: Path) -> dict[str, Any]:
        """因为同时导入会争用内容目录和配额，需要串行化导入而不锁住 Agent 存储。"""
        # 1、锁只用于用户素材操作，普通执行和素材读取不等待这把锁。
        with self._lock:
            return self._import_manifest(path)

    def _import_manifest(self, path: Path) -> dict[str, Any]:
        """因为用户选择的素材需要在升级后继续存在，需要校验并原子复制到独立内容寻址目录。"""
        # 1、文件由人工文件选择器指定，只读取同目录的 JSON 和 PNG。
        source = path.resolve(strict=True)
        if source.suffix.lower() != ".json" or source.stat().st_size > 128 * 1024:
            raise ValueError("请选择小于 128 KiB 的素材 JSON 描述文件")
        try:
            value = json.loads(source.read_text("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("素材 JSON 无法读取") from error
        if not isinstance(value, dict):
            raise ValueError("素材清单必须是对象")
        filenames = atlas_filenames(value)
        # 2、先在内存校验，失败时不写半成品或改变现有绑定。
        pages, sizes = [], []
        for filename in filenames:
            encoded, size = normalize_png(
                self._image_bytes(source.parent, filename, 4 * 1024 * 1024)
            )
            pages.append(encoded)
            sizes.append(size)
        paged = value.get("version") == 3
        manifest = validate_manifest(value, sizes if paged else sizes[0])
        stored_names = [f"atlas-{i}.png" for i in range(len(pages))] if paged else ["atlas.png"]
        if paged:
            manifest["images"] = stored_names
        else:
            manifest["image"] = stored_names[0]
        body = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
        identifier = hashlib.sha256(body + b"".join(pages)).hexdigest()[:32]
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / identifier
        if target.exists():
            return self.summary("avatar:" + identifier)
        if len(list(self.root.glob("*/avatar.json"))) >= 32:
            raise ValueError("本地库最多保存 32 套自定义素材")
        # 3、暂存目录完成后同目录原子改名；不保留原始用户路径。
        with TemporaryDirectory(prefix=".import-", dir=self.root) as staging:
            temporary = Path(staging)
            (temporary / "avatar.json").write_bytes(body)
            for filename, encoded in zip(stored_names, pages, strict=True):
                (temporary / filename).write_bytes(encoded)
            temporary.rename(target)
        return self.summary("avatar:" + identifier)

    def _image_bytes(self, folder: Path, filename: str, limit: int) -> bytes:
        """因为源图与已存图都不能跨目录，需要共用路径、大小和普通文件检查后才读取。"""
        # 1、文件名已经过有限合同检查，解析后仍拒绝链接到目录外或系统设备。
        image = (folder / filename).resolve(strict=True)
        if (
            image.parent != folder.resolve()
            or not image.is_file()
            or image.suffix.lower() != ".png"
            or image.stat().st_size > limit
        ):
            raise ValueError("图集路径越界或文件过大")
        return image.read_bytes()

    def _path(self, identifier: str) -> Path:
        """因为外部 ID 不能变成本机任意路径，需要只接受内容寻址的固定格式。"""
        # 1、路径解析后仍需在库内，拒绝手工植入的目录链接。
        if not re.fullmatch(r"avatar:[0-9a-f]{32}", identifier):
            raise ValueError("素材标识无效")
        path = (self.root / identifier.split(":")[1]).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_dir():
            raise ValueError("素材不存在或路径越界")
        return path

    def require_id(self, identifier: str) -> None:
        """因为人物只应绑定已导入素材，需要验证引用存在，不接受远程 URL 或脚本。"""
        # 1、内置骨架始终可用，损坏自定义素材保留显式报错。
        if identifier != BUILTIN:
            self.summary(identifier)

    def summary(self, identifier: str) -> dict[str, Any]:
        """因为列表不需要传输完整图集，需要只返回固定名称和素材能力概况。"""
        # 1、大小边界在导入时校验；读取时再次限制本地文件，不回传源路径。
        if identifier == BUILTIN:
            return {"id": BUILTIN, "name": "RoomCrew · 精细骨架", "kind": "rig", "actions": []}
        path = self._path(identifier) / "avatar.json"
        if path.stat().st_size > 128 * 1024 or not path.resolve().is_relative_to(
            self.root.resolve()
        ):
            raise ValueError("素材描述文件无效")
        value = json.loads(path.read_text("utf-8"))
        return {
            "id": identifier,
            "name": value["name"],
            "kind": "atlas",
            "actions": sorted({clip["action"] for clip in value["clips"]}),
        }

    def catalog(self) -> list[dict[str, Any]]:
        """因为导入列表可能包含被手工损坏的文件，需要跳过坏素材并保留可用内置角色。"""
        # 1、只扫描应用自己的素材库，普通轮询不读取图集像素。
        result = [self.summary(BUILTIN)]
        if self.root.exists():
            for path in sorted(self.root.glob("*/avatar.json"))[:32]:
                try:
                    result.append(self.summary("avatar:" + path.parent.name))
                except (ValueError, OSError, KeyError, TypeError):
                    continue
        return result

    def asset(self, identifier: str) -> dict[str, Any]:
        """因为 WebView 不应获得任意 file URL，需要只返回已导入 PNG 的有限 data URL 与清单。"""
        # 1、图集按需读取一次，界面缓存；不在每次场景订阅中广播图片。
        path = self._path(identifier)
        manifest_path = path / "avatar.json"
        if not manifest_path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("素材文件路径越界")
        if manifest_path.stat().st_size > 128 * 1024:
            raise ValueError("素材文件大小无效")
        body = manifest_path.read_bytes()
        manifest = json.loads(body)
        pages = [
            self._image_bytes(path, filename, 8 * 1024 * 1024)
            for filename in atlas_filenames(manifest)
        ]
        digest = hashlib.sha256(body + b"".join(pages)).hexdigest()[:32]
        if identifier != "avatar:" + digest:
            raise ValueError("素材已被修改，请重新导入")
        encoded_pages = [
            "data:image/png;base64," + base64.b64encode(encoded).decode("ascii")
            for encoded in pages
        ]
        if identifier not in self._registrations:
            if len(self._registrations) >= 32:
                self._registrations.clear()
            self._registrations[identifier] = register_frames(manifest, pages)
        return {
            "id": identifier,
            "manifest": manifest,
            "registration": self._registrations[identifier],
            **(
                {"image_pages": encoded_pages}
                if manifest["version"] == 3
                else {"image_data": encoded_pages[0]}
            ),
        }
