"""分析原始图集的留白分界与人物脚底，仅输出元数据，不修改 PNG 像素。"""

from pathlib import Path
from typing import Any

from PIL import Image


def find_seams(profile: list[int], count: int, search: float = 0.22) -> list[int]:
    """因为生成素材的行列并非精确等分，需要在预计分界附近寻找透明谷值，避免裁断人物。"""
    # 1、用有效内容区估算间距，忽略外缘的零星低密度噪声。
    threshold = max(2, max(profile) // 40)
    active = [index for index, value in enumerate(profile) if value >= threshold]
    if not active:
        raise ValueError("素材区域没有有效像素")
    start, end = active[0], active[-1] + 1
    stride = (end - start) / count
    seams = [0]
    # 2、在透明谷值内优先选择接近预期的位置，保持排序和每块的有效宽度。
    for index in range(1, count):
        expected = start + stride * index
        lo = max(seams[-1] + 4, round(expected - stride * search))
        hi = min(len(profile) - 4, round(expected + stride * search))
        candidates = [
            (sum(profile[max(0, pos - 2) : pos + 3]), abs(pos - expected), pos)
            for pos in range(lo, hi + 1)
        ]
        if not candidates:
            raise ValueError("素材分界不足")
        seams.append(min(candidates)[2])
    return [*seams, len(profile)]


def grid_regions(
    path: Path, rows: int, columns: int, search: float = 0.22, trim_fragments: bool = False
) -> tuple[list[dict[str, Any]], tuple[int, int]]:
    """因为多张角色图集需要共用登记方式，需要分析分界、裁切与脚底位置，同时保留原图。"""
    # 1、只分析单页的高透明度遮罩，不重画或重编码源图片。
    frames = []
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode != "RGBA" or max(image.size) > 2048:
            raise ValueError("需要有界的 RGBA PNG")
        width, height = image.size
        mask = image.getchannel("A").point([0] * 96 + [1] * 160)
        pixels = mask.tobytes()
        y_profile = [sum(pixels[y * width : (y + 1) * width]) for y in range(height)]
        ys = find_seams(y_profile, rows, search)
        for row in range(rows):
            row_pixels = pixels[ys[row] * width : ys[row + 1] * width]
            xs = find_seams([sum(row_pixels[x::width]) for x in range(width)], columns, search)
            for col in range(columns):
                cell = mask.crop((xs[col], ys[row], xs[col + 1], ys[row + 1]))
                bounds = cell.getbbox()
                if bounds is None:
                    raise ValueError(f"素材第 {row + 1} 行第 {col + 1} 列为空")
                left, top, right, bottom = bounds
                if trim_fragments:
                    left, top, right, bottom = body_bounds(cell)
                left, top = max(0, left - 1), max(0, top - 1)
                right, bottom = min(cell.width, right + 1), min(cell.height, bottom + 1)
                # 2、从头部中心附近寻找鞋底，降低水壶和花盆对人物根节点的影响。
                head = cell.crop((left, top, right, top + max(1, (bottom - top) // 3))).getbbox()
                center = left + (head[0] + head[2]) / 2 if head else (left + right) / 2
                radius = max(12, (right - left) // 4)
                foot_left, foot_right = (
                    max(left, round(center - radius)),
                    min(right, round(center + radius)),
                )
                foot = cell.crop((foot_left, max(top, bottom - 10), foot_right, bottom)).getbbox()
                root_x = foot_left + (foot[0] + foot[2]) / 2 if foot else center
                frames.append(
                    {
                        "rect": [xs[col] + left, ys[row] + top, right - left, bottom - top],
                        "root": root_x - left,
                        "edge": top + ys[row] == 0 or bottom + ys[row] == height,
                        "row": row,
                        "column": col,
                    }
                )
    return frames, (width, height)


def connected_regions(mask: Image.Image) -> list[tuple[int, int, int, int, int]]:
    """因为人物残片与不等高家具都需要区分独立图形，需要复用透明遮罩的八邻接区域分析。"""
    # 1、八邻接分析只修改内存遮罩副本，原始 PNG 和透明度均保留。
    pixels = bytearray(mask.tobytes())
    width, height = mask.size
    components = []
    for start, active in enumerate(pixels):
        if not active:
            continue
        pixels[start] = 0
        stack = [start]
        left = right = start % width
        top = bottom = start // width
        area = 0
        while stack:
            index = stack.pop()
            x, y = index % width, index // width
            area += 1
            left, top = min(left, x), min(top, y)
            right, bottom = max(right, x), max(bottom, y)
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if pixels[neighbor]:
                        pixels[neighbor] = 0
                        stack.append(neighbor)
        components.append((area, left, top, right + 1, bottom + 1))
    return components


def body_bounds(mask: Image.Image) -> tuple[int, int, int, int]:
    """因为相邻行鞋尖可能与头部重叠在同一高度，需要用主身体连通区域限定裁切元数据。

    返回主体及有意义道具的包围矩形，不修改原图；家具与特效不使用此人物专用规则。
    """
    # 1、分析遮罩副本，不改变源图像素。
    components = connected_regions(mask)
    if not components:
        raise ValueError("人物主体为空")
    # 2、主体最大区域决定裁切，保留足够大的离散道具，剔除明显位于边界的邻帧碎片。
    main = max(components)
    _, left, top, right, bottom = main
    body_height = bottom - top
    for area, x0, y0, x1, y1 in components:
        above = y0 <= 1 and y1 < top + body_height * 0.25
        below = y1 >= mask.height - 1 and y0 > bottom - body_height * 0.25
        if area < main[0] * 0.05 or above or below:
            continue
        left, top, right, bottom = min(left, x0), min(top, y0), max(right, x1), max(bottom, y1)
    return left, top, right, bottom


def object_regions(
    path: Path, rows: int, columns: int
) -> tuple[list[dict[str, Any]], tuple[int, int]]:
    """因为家具高度不等且跨越统一行分界，需要按完整独立物件分析后再按行列登记。

    只返回裁切元数据；区域不足时明确失败，不把边角当成完整素材。
    """
    # 1、主要连通区域对应完整家具；低透明度噪声不参与物件排序。
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode != "RGBA" or max(image.size) > 2048:
            raise ValueError("需要有界的 RGBA PNG")
        mask = image.getchannel("A").point([0] * 96 + [1] * 160)
        regions = sorted(connected_regions(mask), reverse=True)[: rows * columns]
        if len(regions) != rows * columns:
            raise ValueError("独立家具数量不足")
        regions.sort(key=region_center_y)
        result = []
        # 2、按各物件中心分行、再按横坐标排序，不裁断跨越名义网格的边缘。
        for row in range(rows):
            band = sorted(regions[row * columns : (row + 1) * columns], key=region_center_x)
            for _, x0, y0, x1, y1 in band:
                x0, y0 = max(0, x0 - 1), max(0, y0 - 1)
                x1, y1 = min(image.width, x1 + 1), min(image.height, y1 + 1)
                result.append({"rect": [x0, y0, x1 - x0, y1 - y0]})
        return result, image.size


def region_center_y(region: tuple[int, int, int, int, int]) -> int:
    """因为不等高物件不能按顶部排序，需要以纵向中心建立稳定的素材行。"""
    # 1、比较双倍中心坐标，避免不必要的浮点计算。
    return region[2] + region[4]


def region_center_x(region: tuple[int, int, int, int, int]) -> int:
    """因为同一行物件宽度不同，需要以横向中心恢复从左到右的登记顺序。"""
    # 1、排序只影响目录元数据，不修改图片。
    return region[1] + region[3]
