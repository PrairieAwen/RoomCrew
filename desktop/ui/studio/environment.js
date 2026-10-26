/* 已有透明美术的环境接入与视口前景；背景皮肤不参与导航。 */
"use strict";

/** 因为人物和环境需要统一手绘画风，需要复用正式素材库的固定原图与裁切描述。 */
function crewEnvironmentMaterial(id) {
    // 1、只从随程序分发的有限目录取图，不接受用户路径或远程 URL。
    for (const item of window.ROOMCREW_MATERIAL_LIBRARY?.objects || [])
        if (item.id === id) return item;
    return null;
}

/** 因为家具与前景都需要使用同一裁切逻辑，需要按原始比例创建一次性 SVG 图像。 */
function crewEnvironmentPicture(parent, material, x, y, width) {
    // 1、图像原像素保持不变；一次建立 URL，帧循环只改变人物与相机。
    if (!material) return null;
    const [sx, sy, sw, sh] = material.frames[0],
        height = (width * sh) / sw;
    const crop = crewSvg("svg", {
        x,
        y,
        width,
        height,
        viewBox: `${sx} ${sy} ${sw} ${sh}`,
        overflow: "hidden",
        "pointer-events": "none",
    });
    crop.append(
        crewSvg("image", {
            href: "studio/assets/library-v1/" + material.image,
            width: material.atlas_size[0],
            height: material.atlas_size[1],
        }),
    );
    parent.append(crop);
    return crop;
}

/** 因为墙面与踢脚线需要共用等距投影，需要从同一墙脚端点生成竖直平面。 */
function crewWallPoints(endpoint, height) {
    // 1、墙脚始终贴合格网原点，增加高度不改变人物和家具的地面坐标。
    return [[0, -height], [endpoint[0], endpoint[1] - height], endpoint, [0, 0]]
        .map(crewPoint)
        .join(" ");
}

/** 因为两面墙需要柔和的受光差异，需要复用固定世界坐标的竖向材质渐变。 */
function crewWallGradient(id, light, shade) {
    // 1、渐变不随墙面裁切高度改变，缩放时不会出现颜色跳变。
    const gradient = crewSvg("linearGradient", {
        id,
        gradientUnits: "userSpaceOnUse",
        x1: 0,
        y1: -400,
        x2: 0,
        y2: 500,
    });
    gradient.append(
        crewSvg("stop", { offset: 0, "stop-color": light }),
        crewSvg("stop", { offset: 1, "stop-color": shade }),
    );
    return gradient;
}

class CrewEnvironment {
    /** 因为矩形屏幕两侧不能只露出大片空地，需要使用轻量前景与光照形成延伸空间。 */
    constructor(svg, world) {
        // 1、装饰没有角色、碰撞或点击行为，和可编辑家具保持独立。
        this.front = crewSvg("g", {
            class: "scene-foreground",
            "pointer-events": "none",
        });
        this.left = crewSvg("g");
        this.right = crewSvg("g");
        this.front.append(this.left, this.right);
        svg.append(this.front);
        crewEnvironmentPicture(
            this.left,
            crewEnvironmentMaterial("furniture-11"),
            -66,
            -230,
            175,
        );
        crewEnvironmentPicture(
            this.right,
            crewEnvironmentMaterial("furniture-12"),
            -55,
            -205,
            155,
        );
        this.world = world;
        this.walls = [];
        this.wallHeight = 0;
        this.camera = null;
    }

    /** 因为矮墙会露出墙外地砖，需要用连续高墙、墙角与踢脚线围合当前办公室。 */
    drawWalls(parent) {
        // 1、墙面只作为装饰背景，放在人物与家具之后，不参与碰撞或任务权限。
        const shell = crewSvg("g", {
                class: "scene-walls",
                "pointer-events": "none",
            }),
            defs = crewSvg("defs"),
            left = crewProject([0, 96]),
            right = crewProject([96, 0]);
        defs.append(
            crewWallGradient("crew-wall-left", "#e6dcc7", "#c7b89e"),
            crewWallGradient("crew-wall-right", "#f3ead8", "#dbcbae"),
        );
        shell.append(defs);
        this.walls = [];
        this.wallHeight = 0;
        for (const [side, endpoint] of [
            ["left", left],
            ["right", right],
        ]) {
            const wall = crewSvg("polygon", {
                class: "scene-wall",
                "data-side": side,
                fill: `url(#crew-wall-${side})`,
            });
            shell.append(wall);
            this.walls.push({ wall, endpoint });
        }
        // 2、窄墙角与低踢脚线提供体积感，墙脚柔影衔接原来的地板材质。
        this.corner = crewSvg("path", {
            stroke: "#96866f",
            "stroke-width": 1.5,
            opacity: 0.32,
        });
        shell.append(this.corner);
        for (const endpoint of [left, right]) {
            shell.append(
                crewSvg("path", {
                    d: `M0,2 L${endpoint[0]},${endpoint[1] + 2}`,
                    stroke: "#6f5e48",
                    "stroke-width": 8,
                    opacity: 0.09,
                }),
                crewSvg("polygon", {
                    points: crewWallPoints(endpoint, 12),
                    fill: "#eee5d3",
                    stroke: "#b9aa90",
                    "stroke-width": 0.7,
                }),
            );
        }
        parent.append(shell);
        // 3、首次绘制与切换空间都按当前镜头补齐墙面；上沿始终留在可见区之外。
        if (this.camera) this.frame(this.camera);
    }

    /** 因为窗口大小和缩放会改变边缘，需要只在相机变化时重定位前景，避免出现硬画布边。 */
    frame(camera) {
        // 1、最低墙高提高到 320；按两侧最远可见墙脚补足上沿，避免宽屏和平移露出墙外地面。
        this.camera = camera;
        if (!Number.isFinite(camera.width) || !Number.isFinite(camera.height))
            return;
        const extent = Math.max(
            Math.abs(camera.center[0] - camera.width / 2),
            Math.abs(camera.center[0] + camera.width / 2),
        );
        const height = Math.ceil(
            Math.max(
                320,
                extent / 2 - (camera.center[1] - camera.height / 2) + 64,
            ),
        );
        if (this.walls.length && height !== this.wallHeight) {
            this.wallHeight = height;
            for (const { wall, endpoint } of this.walls) {
                wall.setAttribute("points", crewWallPoints(endpoint, height));
                wall.setAttribute("data-height", height);
            }
            this.corner.setAttribute("d", `M0,${-height} L0,-12`);
        }
        // 2、前景如窗边植物，只占屏幕底角；不遮挡中心工位或更改可走格网。
        const x = camera.center[0] - camera.width / 2,
            y = camera.center[1] + camera.height / 2;
        this.left.setAttribute("transform", `translate(${x},${y + 55})`);
        this.right.setAttribute(
            "transform",
            `translate(${x + camera.width - 35},${y + 50})`,
        );
    }
}
