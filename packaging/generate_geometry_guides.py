"""生成家具制作底稿与作者坐标；输出是待绘制参考，不是可发布成品美术。"""

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "desktop/ui/studio/assets/scene-v2/source"
DIRECTIONS = {"s": 45, "se": 0, "e": 315, "ne": 270, "n": 225, "nw": 180, "w": 135, "sw": 90}
Z_SCALE = 12 * math.sqrt(6)


class Geometry:
    def __init__(self) -> None:
        """因为所有家具视角必须来自同一几何，需要在旋转前保存原始平面和法向。"""
        # 1、仅构建矢量底稿，不读取、拉伸或修改任何已有 PNG。
        self.faces: list[dict[str, Any]] = []

    def face(
        self,
        points: list[tuple[float, float, float]],
        normal: tuple[float, float, float],
        color: str,
    ) -> None:
        """因为固定相机需要筛选真正可见表面，需要记录面顶点、法向和底色。"""
        # 1、可编辑源保留三维坐标，不把截图中的二维倾斜误作新视角。
        self.faces.append({"points": points, "normal": normal, "color": color})

    def box(
        self, lo: tuple[float, float, float], hi: tuple[float, float, float], top: str, side: str
    ) -> None:
        """因为柜体、桌板和靠背应共用实体尺寸，需要由盒体一次产生五个外表面。"""
        # 1、底面不朝向上方相机，其他面随法向选择，不重复硬编码八张图片。
        x, y, z = lo
        a, b, c = hi
        self.face([(x, y, z), (x, b, z), (x, b, c), (x, y, c)], (-1, 0, 0), side)
        self.face([(a, y, z), (a, b, z), (a, b, c), (a, y, c)], (1, 0, 0), side)
        self.face([(x, y, z), (a, y, z), (a, y, c), (x, y, c)], (0, -1, 0), side)
        self.face([(x, b, z), (a, b, z), (a, b, c), (x, b, c)], (0, 1, 0), side)
        self.face([(x, y, c), (a, y, c), (a, b, c), (x, b, c)], (0, 0, 1), top)

    def column(
        self, center: tuple[float, float], radius: float, bottom: float, top: float, color: str
    ) -> None:
        """因为脚轮与立柱不能用倾斜矩形冒充，需要建立带圆周侧面的竖直柱体。"""
        # 1、十二边底稿足以约束绘画轮廓，成品材质可在轮廓内柔化边缘。
        ring = []
        for i in range(12):
            angle = i * math.pi / 6
            ring.append(
                (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))
            )
        for i, p in enumerate(ring):
            q = ring[(i + 1) % len(ring)]
            angle = (i + 0.5) * math.pi / 6
            self.face(
                [(p[0], p[1], bottom), (q[0], q[1], bottom), (q[0], q[1], top), (p[0], p[1], top)],
                (math.cos(angle), math.sin(angle), 0),
                color,
            )
        self.face([(x, y, top) for x, y in ring], (0, 0, 1), color)

    def rail(self, end: tuple[float, float], width: float, z: float, color: str) -> None:
        """因为脚轮底座是径向细杆而不是矩形平板，需要沿实际端点生成等宽支撑杆。"""
        # 1、杆从原点伸至脚轮，侧法向由每条边确定。
        length = math.hypot(*end)
        px, py = -end[1] / length * width / 2, end[0] / length * width / 2
        ring = [(px, py), (end[0] + px, end[1] + py), (end[0] - px, end[1] - py), (-px, -py)]
        for index, p in enumerate(ring):
            q = ring[(index + 1) % 4]
            dx, dy = q[0] - p[0], q[1] - p[1]
            span = math.hypot(dx, dy)
            self.face(
                [(p[0], p[1], z), (q[0], q[1], z), (q[0], q[1], z + 0.06), (p[0], p[1], z + 0.06)],
                (dy / span, -dx / span, 0),
                color,
            )
        self.face([(x, y, z + 0.06) for x, y in ring], (0, 0, 1), color)


def rotate(point: tuple[float, float, float], yaw: float) -> tuple[float, float, float]:
    """因为八向仅旋转物体，需要对所有角点与法向使用同一世界旋转。"""
    # 1、项目格网的正角度由规范定义；这里不使用图像平面旋转。
    c, s = math.cos(yaw), math.sin(yaw)
    return point[0] * c - point[1] * s, point[0] * s + point[1] * c, point[2]


def project(point: tuple[float, float, float]) -> tuple[float, float]:
    """因为底稿和运行地砖需使用同一相机，需要精确采用规范中的三维投影矩阵。"""
    # 1、视图单位与源像素密度分开，导出时不会逐帧改物体尺度。
    x, y, z = point
    return 24 * (x - y), 12 * (x + y) - Z_SCALE * z


def workstation() -> Geometry:
    """因为默认电脑桌已有精确单向样板，需要从同一实体继续生成其余视角，避免换方向又换相机。"""
    # 1、以桌面中心为原点；尺寸与单向样板一致，座位在 +X、键盘位于空腿区。
    mesh = Geometry()
    for x in (-0.62, 0.50):
        for y in (-1.32, 1.18):
            mesh.box((x, y, 0), (x + 0.15, y + 0.15, 1.38), "#b99566", "#89967b")
    mesh.box((-0.60, -1.24, 0.2), (-0.50, 1.22, 1.35), "#85917c", "#8e9b84")
    mesh.box((-0.54, 0.56, 0.10), (0.64, 1.24, 1.37), "#b49c73", "#9ca58d")
    for z in (0.34, 0.73, 1.12):
        mesh.box((0.64, 0.59, z - 0.15), (0.65, 1.20, z + 0.16), "#9ba68d", "#85917c")
        mesh.box((0.65, 0.78, z + 0.01), (0.67, 1.03, z + 0.05), "#b78a3f", "#b78a3f")
    # 2、显示器、底座和桌面参加同一世界旋转；键盘由运行时独立组件绘制，底稿不烘焙。
    mesh.box((-0.7, -1.4, 1.37), (0.7, 1.4, 1.44), "#d7b17b", "#c69d68")
    mesh.box((-0.44, -0.87, 1.44), (-0.16, -0.26, 1.47), "#555d61", "#404a50")
    mesh.box((-0.38, -0.62, 1.47), (-0.32, -0.54, 1.85), "#535c64", "#454c55")
    mesh.box((-0.41, -1.18, 1.79), (-0.34, 0.03, 2.53), "#3c4552", "#46505d")
    mesh.box((-0.339, -1.12, 1.85), (-0.335, -0.03, 2.47), "#b9ced5", "#b9ced5")
    return mesh


def chair() -> Geometry:
    """因为空椅八向应与现有坐姿配套，需要建立统一脚轮、座面、扶手和椅背。"""
    # 1、本轮保持旧人物兼容座高 22 视图单位，明确区别于尚待制作的 0.44 米新骨架规格。
    mesh = Geometry()
    seat = 22 / Z_SCALE
    mesh.column((0, 0), 0.09, 0.10, seat - 0.08, "#596157")
    for i in range(5):
        angle = i * 2 * math.pi / 5
        x, y = 0.45 * math.cos(angle), 0.45 * math.sin(angle)
        mesh.rail((x, y), 0.07, 0.10, "#4b534b")
        mesh.column((x, y), 0.085, 0, 0.14, "#424941")
    # 2、椅子正面为局部 +X，背面与扶手全部参加三维旋转。
    mesh.box((-0.48, -0.54, seat - 0.09), (0.48, 0.54, seat), "#aeb99d", "#829473")
    mesh.box((-0.49, -0.54, seat), (-0.38, 0.54, seat + 0.85), "#a9b797", "#8e9f7d")
    for sign in (-1, 1):
        y = sign * 0.58
        mesh.box(
            (-0.3, y - 0.045, seat + 0.03), (-0.22, y + 0.045, seat + 0.34), "#b69768", "#937a55"
        )
        mesh.box(
            (-0.35, y - 0.07, seat + 0.30), (0.30, y + 0.07, seat + 0.38), "#bac2aa", "#89997a"
        )
    return mesh


def sofa() -> Geometry:
    """因为四张沙发需在相同地砖中相向摆放，需要从同一主体产生各向靠背与扶手。"""
    # 1、保留旧人物兼容座高；沙发的真实坐席与前景遮挡后续仍由桌面锚点约束。
    mesh = Geometry()
    seat = 22 / Z_SCALE
    for x in (-0.54, 0.55):
        for y in (-1.25, 1.25):
            mesh.box((x - 0.05, y - 0.05, 0), (x + 0.05, y + 0.05, 0.28), "#b99566", "#9b7b52")
    mesh.box((-0.70, -1.45, 0.22), (0.70, 1.45, seat - 0.10), "#98a48c", "#7d8c73")
    mesh.box((-0.70, -1.45, seat - 0.08), (-0.50, 1.45, seat + 0.80), "#a7b095", "#87987c")
    for y in (-1.15, 0.03):
        mesh.box((-0.43, y, seat - 0.1), (0.64, y + 1.12, seat), "#b3bea1", "#95a487")
    # 2、两个座垫与枕头属于同一实体，转向时不重新设计款式。
    for sign in (-1, 1):
        y = sign * 1.32
        mesh.box(
            (-0.62, y - 0.12, seat - 0.05), (0.69, y + 0.12, seat + 0.42), "#b6bfa3", "#93a185"
        )
        py = sign * 0.84
        mesh.box(
            (-0.47, py - 0.25, seat + 0.08), (-0.28, py + 0.25, seat + 0.61), "#eddfbd", "#dacbaa"
        )
    return mesh


def meeting() -> Geometry:
    """因为会议桌的长边不能再与地板有不同透视，需要用统一高度和四角制作八向桌面。"""
    # 1、桌面参考宽 1.8 米、深 0.9 米、高 0.72 米。
    mesh = Geometry()
    for x in (-0.72, 0.72):
        for y in (-1.50, 1.50):
            mesh.box((x - 0.07, y - 0.07, 0), (x + 0.07, y + 0.07, 1.36), "#bd9766", "#987749")
    mesh.box((-0.90, -1.80, 1.36), (0.90, 1.80, 1.44), "#d6b47f", "#b68d59")
    # 2、一本绿色记录本固定在桌面，不添加人物和椅子到桌子原画。
    mesh.box((-0.26, -0.30, 1.44), (0.17, 0.25, 1.47), "#6f7f61", "#4f6047")
    return mesh


def tea_table() -> Geometry:
    """因为茶几需与四沙发共享比例和透视，需要保存低桌的同一组实体尺寸。"""
    # 1、低桌保持 0.4 米高，原画不烘焙地毯和周围沙发。
    mesh = Geometry()
    for x in (-0.42, 0.42):
        for y in (-0.72, 0.72):
            mesh.box((x - 0.045, y - 0.045, 0), (x + 0.045, y + 0.045, 0.75), "#c6a373", "#9e7c4e")
    mesh.box((-0.47, -0.79, 0.20), (0.47, 0.79, 0.25), "#cba777", "#ae8957")
    mesh.box((-0.50, -0.85, 0.75), (0.50, 0.85, 0.80), "#dbb684", "#b58c59")
    mesh.box((-0.15, -0.25, 0.8), (0.12, 0.17, 0.83), "#6e7f60", "#52654a")
    return mesh


def screen() -> Geometry:
    """因为白板应与会议桌同向且脚架真实落地，需要建立板面与底轮的统一三维结构。"""
    # 1、面板正面为 +X；旋转时同时转动板面、支架与轮子。
    mesh = Geometry()
    for y in (-1.27, 1.27):
        mesh.box((-0.055, y - 0.055, 0.12), (0.055, y + 0.055, 2.95), "#706a5a", "#55584e")
        mesh.box((-0.47, y - 0.055, 0.12), (0.47, y + 0.055, 0.20), "#6b705e", "#4c5347")
        for x in (-0.43, 0.43):
            mesh.column((x, y), 0.09, 0, 0.14, "#4e5349")
    mesh.box((-0.06, -1.38, 1.25), (0.06, 1.38, 3.05), "#736c59", "#655f50")
    mesh.box((0.065, -1.32, 1.31), (0.075, 1.32, 2.99), "#f2e8cb", "#f2e8cb")
    mesh.box((-0.075, -1.32, 1.31), (-0.065, 1.32, 2.99), "#e6dcc1", "#e6dcc1")
    mesh.box((0.04, -1.16, 1.19), (0.25, 1.16, 1.25), "#8d846d", "#696553")
    return mesh


def archive() -> Geometry:
    """因为档案柜不能沿另一套相机倾斜，需要从统一柜体、门板与抽屉生成八向底稿。"""
    # 1、档案室仍是规划入口，这里只制作外观，不新增归档业务。
    mesh = Geometry()
    mesh.box((-0.35, -0.9, 0.08), (0.35, 0.9, 1.65), "#d4b180", "#bc9c72")
    for y in (-0.85, 0.43):
        for z in (0.30, 0.69, 1.08):
            mesh.box((0.352, y, z - 0.14), (0.37, y + 0.40, z + 0.17), "#e6d2a6", "#e6d2a6")
    for y in (-0.38, 0.04):
        mesh.box((0.352, y, 0.14), (0.37, y + 0.34, 1.52), "#b59665", "#b59665")
    # 2、固定几本绿色卷宗作为识别道具，款式不随方向重生。
    for y in (-0.50, -0.30, -0.10):
        mesh.box((-0.10, y, 1.65), (0.15, y + 0.12, 2.12), "#9b9d78", "#718060")
    return mesh


def bookcase() -> Geometry:
    """因为书柜的顶边和搁板也须与地轴一致，需要用同一实体相机制作可见的书架。"""
    # 1、正面沿局部 +X，书本和搁板属于同一模型，转向时不会改变层数和方向。
    mesh = Geometry()
    mesh.box((-0.35, -0.82, 0.08), (-0.28, 0.82, 3.4), "#c5a06d", "#ae885a")
    for y in (-0.82, 0.75):
        mesh.box((-0.35, y, 0.08), (0.35, y + 0.07, 3.4), "#d1ae7a", "#ad8656")
    colors = ("#7e8c67", "#bca77d", "#8f9b79", "#c6bb9a")
    for level, z in enumerate((0.14, 1.0, 1.86, 2.72, 3.34)):
        mesh.box((-0.35, -0.82, z), (0.35, 0.82, z + 0.06), "#d6b580", "#ad8758")
        if level == 4:
            continue
        for index in range(8):
            y = -0.66 + index * 0.165
            mesh.box(
                (-0.18, y, z + 0.06),
                (0.24, y + 0.13, z + 0.68 + (index % 3) * 0.04),
                colors[index % 4],
                colors[index % 4],
            )
    return mesh


def export(kind: str, mesh: Geometry) -> None:
    """因为成品原图需可复核像素与坐标，需要同时导出八向 SVG 和每格作者原点。"""
    # 1、固定源密度四像素每视图单位；每向仅平移构图，不缩放物体。
    density, cell = 4.0, 640
    body = []
    views = {}
    triangles = []
    edges = []
    for index, (direction, angle) in enumerate(DIRECTIONS.items()):
        yaw = math.radians(angle)
        all_points = [
            project(rotate(point, yaw)) for face in mesh.faces for point in face["points"]
        ]
        minx, miny = min(p[0] for p in all_points), min(p[1] for p in all_points)
        maxx, maxy = max(p[0] for p in all_points), max(p[1] for p in all_points)
        cx, cy = (index % 4) * cell, (index // 4) * cell
        origin = (
            cx + cell / 2 - density * (minx + maxx) / 2,
            cy + cell / 2 - density * (miny + maxy) / 2,
        )
        drawn = []
        for face in mesh.faces:
            normal = rotate(face["normal"], yaw)
            if normal[0] + normal[1] + normal[2] * math.sqrt(2 / 3) <= 0.001:
                continue
            world = [rotate(point, yaw) for point in face["points"]]
            # 2、另存真正逐像素深度测试的数据；平面平均深度不足以正确遮住桌腿和枕头。
            positions = []
            for p in world:
                view_x, view_y = project(p)
                positions.append(
                    [
                        (origin[0] + density * view_x) / 2560 * 2 - 1,
                        1 - (origin[1] + density * view_y) / 1280 * 2,
                        -(p[0] + p[1] + p[2] * math.sqrt(2 / 3)) / 20,
                    ]
                )
            color = [int(face["color"][i : i + 2], 16) / 255 for i in (1, 3, 5)]
            for i in range(1, len(positions) - 1):
                for vertex in (positions[0], positions[i], positions[i + 1]):
                    triangles.extend(vertex + color)
            for i, vertex in enumerate(positions):
                edges.extend(vertex + positions[(i + 1) % len(positions)])
            depth = sum(x + y + z * math.sqrt(2 / 3) for x, y, z in world) / len(world)
            coords = " ".join(
                f"{origin[0] + density * project(p)[0]:.3f},"
                f"{origin[1] + density * project(p)[1]:.3f}"
                for p in world
            )
            drawn.append(
                (
                    depth,
                    f'<polygon points="{coords}" fill="{face["color"]}" '
                    'stroke="#6d5a42" stroke-width="1.8" stroke-linejoin="round"/>',
                )
            )
        body.extend(item[1] for item in sorted(drawn, key=face_depth))
        views[direction] = {
            "cell": [cx, cy, cell, cell],
            "origin_px": list(origin),
            "projected_bounds": [minx, miny, maxx, maxy],
            "yaw_degrees": angle,
        }
    # 3、保存底稿和实际坐标，不能只留下提示词却没有几何依据。
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="2560" height="1280" '
        'viewBox="0 0 2560 1280">' + "".join(body) + "</svg>"
    )
    (DEST / f"{kind}-guide.svg").write_text(svg, "utf-8")
    (DEST / f"{kind}-mesh.json").write_text(
        json.dumps({"triangles": triangles, "edges": edges}), "utf-8"
    )
    (DEST / f"{kind}-guide.json").write_text(
        json.dumps(
            {
                "camera_profile_id": "rc-ortho-2to1-v1",
                "source_pixels_per_view_unit": density,
                "size": [2560, 1280],
                "views": views,
                "status": "geometry_guide_only",
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )


def face_depth(value: tuple[float, str]) -> float:
    """因为同向多个面需要按实体深度绘制，需要提供确定性的排序键。"""
    # 1、此排序只用于底稿，不决定实际 Agent 状态或运行时遮挡权限。
    return value[0]


def main() -> None:
    """因为同一制作规范要复用到多类家具，需要统一生成各类的八向底稿与来源记录。"""
    # 1、目录仅保存本项目制图参考，成品 PNG 必须另经美术制作和实测验收。
    DEST.mkdir(parents=True, exist_ok=True)
    for kind, builder in {
        "workstation": workstation,
        "chair": chair,
        "sofa": sofa,
        "meeting": meeting,
        "tea_table": tea_table,
        "screen": screen,
        "archive": archive,
        "bookcase": bookcase,
    }.items():
        export(kind, builder())
    print("已生成八类家具的固定相机八向底稿")


if __name__ == "__main__":
    main()
