/* 已有透明美术的环境接入与视口前景；背景皮肤不参与导航。 */
"use strict";

/** 因为人物和环境需要统一手绘画风，需要复用正式素材库的固定原图与裁切描述。 */
function crewEnvironmentMaterial(id) {
    // 1、只从随程序分发的有限目录取图，不接受用户路径或远程 URL。
    for (const item of [
        ...(window.ROOMCREW_MATERIAL_LIBRARY?.objects || []),
    ])
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
            crewWallGradient("crew-wall-left", "#fbf3e5", "#e4d6bd"),
            crewWallGradient("crew-wall-right", "#fff9ee", "#eee1cb"),
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

    /** 因为单个家具的灰色椭圆不能形成统一光照，需要在世界地面登记柔光、织纹和小接触阴影。 */
    drawLighting(parent) {
        // 1、所有定义只在重建静态场景时建立，不在帧循环做滤镜计算或随机闪动。
        const defs = crewSvg("defs");
        const shadow = crewSvg("filter", {id:"crew-contact-shadow",x:"-30%",y:"-150%",width:"160%",height:"400%"});
        shadow.append(crewSvg("feGaussianBlur", {stdDeviation:1.8}));
        const glow = crewSvg("radialGradient", {id:"crew-daylight",cx:"22%",cy:"35%",r:"75%"});
        glow.append(crewSvg("stop",{offset:0,"stop-color":"#fff4cc","stop-opacity":0.60}),
            crewSvg("stop",{offset:1,"stop-color":"#fff7e8","stop-opacity":0}));
        const weave = crewSvg("pattern",{id:"crew-rug-weave",width:5,height:4,patternUnits:"userSpaceOnUse"});
        weave.append(crewSvg("path",{d:"M0,1 L5,1 M1,0 L1,4",stroke:"#fff8e8","stroke-width":0.3,opacity:0.7}));
        defs.append(shadow,glow,weave);
        parent.append(defs,crewSvg("rect",{x:-1200,y:-200,width:2400,height:1800,fill:"url(#crew-daylight)","pointer-events":"none"}));
        // 2、窗格投射在固定地面坐标上，人物和家具在其上，不能把整张效果盖到人物脸上。
        const light = crewSvg("g",{opacity:0.38,"pointer-events":"none"});
        for(let i=0;i<7;i++) {
            const p=crewProject([0.2,3+i*3.1]);
            for(let pane=0;pane<2;pane++)
                light.append(crewSvg("path",{d:`M${p[0]-58},${p[1]+pane*22} l54,-27 l145,92 l-54,27Z`,fill:"#fff9d8"}));
        }
        parent.append(light);
    }

    /** 因为参考图的窗外树影和窗框具有层次，需要在现有墙面几何上绘制同透视的温暖窗景。 */
    drawWindows(parent) {
        // 1、每扇窗使用局部裁切，树影不能越过窗框或侵入地面。
        for(let i=0;i<12;i++) {
            const p=crewProject([0.1,3+i*3.1]);
            const pane=crewSvg("g",{transform:`translate(${p[0]},${p[1]-160})`,"pointer-events":"none"});
            const id="crew-window-"+i, defs=crewSvg("defs"),clip=crewSvg("clipPath",{id});
            const outline="M0,0 L-62,31 L-62,94 L0,63Z";
            clip.append(crewSvg("path",{d:outline}));
            defs.append(clip);
            const scenery=crewSvg("g",{"clip-path":`url(#${id})`});
            scenery.append(crewSvg("path",{d:outline,fill:"#dbe6d4"}));
            // 2、平面窗景纹理贴合墙面，只有建筑表面投影，不改变设备八向选图的规则。
            scenery.append(crewSvg("image",{href:"studio/assets/scene-v1/window-garden-v2.png",
                x:-62,y:0,width:62,height:63,preserveAspectRatio:"none",
                transform:"matrix(1 -0.5 0 1 0 0)",opacity:0.84}));
            pane.append(defs,crewSvg("path",{d:outline,transform:"translate(-2,3)",fill:"#a69579",opacity:0.35}),scenery,
                crewSvg("path",{d:outline,fill:"none",stroke:"#9b896c","stroke-width":3}),
                crewSvg("path",{d:"M-30,15 L-30,78 M0,32 L-62,63",stroke:"#fff8e5","stroke-width":3}),
                crewSvg("path",{d:"M-60,36 L-1,7 L-1,18 L-60,47Z",fill:"#fffbe8",opacity:0.35}),
                crewSvg("path",{d:"M-63,96 L1,64 L5,67 L-59,99Z",fill:"#dec8a2",stroke:"#b49e79","stroke-width":0.8}));
            parent.append(pane);
        }
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
