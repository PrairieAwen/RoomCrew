"""所有图集版本共用的有限文件名合同。"""

from typing import Any


def atlas_filenames(value: dict[str, Any]) -> list[str]:
    """因为多页图集不能变成任意文件读取器，需要统一验证有限的同目录 PNG 名称。

    返回一至两个源文件名；旧版仍只接收 image，v3 只接收 images。
    """
    # 1、页数有界且不能重复，避免引用数量放大图片解码与内存开销。
    pages = value.get("images") if value.get("version") == 3 else [value.get("image")]
    if not isinstance(pages, list) or not 1 <= len(pages) <= 2:
        raise ValueError("人物素材只能包含一至两页 PNG")
    names: list[str] = []
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *{f"COM{i}" for i in range(10)},
        *{f"LPT{i}" for i in range(10)},
    }
    for filename in pages:
        if not isinstance(filename, str) or not 1 <= len(filename) <= 120:
            raise ValueError("图集需要有效的 PNG 文件名")
        # 2、拒绝 URL、目录、设备名和 Windows 尾空格规范化歧义。
        if (
            any(char in filename for char in ("/", "\\", ":", "\0"))
            or not filename.lower().endswith(".png")
            or filename.endswith((" ", "."))
        ):
            raise ValueError("图集只能引用同目录 PNG 文件名")
        if filename.split(".")[0].rstrip(" .").upper() in reserved:
            raise ValueError("图集不能引用系统设备名")
        if filename.casefold() in {name.casefold() for name in names}:
            raise ValueError("图集页不能重复")
        names.append(filename)
    return names
