/* 家具实例只消费统一素材合同；方向、接触与图层不进入 Agent。 */
"use strict";

class CrewFurniture {
    /** 因为家具要随布局和素材一起变化，需要只引用场景渲染能力。 */
    constructor(renderer) {
        // 1、不持有模型、工具或任务执行接口。
        this.renderer = renderer;
    }

    /** 因为所有设备都需支持方向配置，需要从同一目录绘制独立关键帧，而非按类型堆偏移。 */
    draw(obj) {
        // 1、占地来自原生端旋转后的合同，显示方向与碰撞方向一致。
        const r = this.renderer, material = crewSceneMaterial(obj.type, obj.direction);
        if (!material) return;
        const [w, d] = obj.footprint || r.scene.catalog[obj.type];
        const p = crewProject([obj.x + w / 2, obj.y + d / 2]);
        const group = crewSvg("g", { class: "room-object", "data-object": obj.id,
            tabindex: 0, role: "button", "aria-label": material.definition.label });
        group.dataset.depth = obj.x + obj.y + (w + d) / 2;
        group.dataset.entity = "object:" + obj.id;
        group.dataset.material = obj.type;
        group.dataset.direction = material.direction;
        group.dataset.coverage = material.view.coverage;
        group.addEventListener("click", r.objectClick.bind(r));
        group.addEventListener("keydown", r.objectKey.bind(r));
        const shadow = crewSvg("ellipse", { fill:"#76624b", opacity:0.12,
            filter:"url(#crew-contact-shadow)", "data-contact-shadow":"true" });
        group.append(shadow);
        const anchor = r.scene.anchors.find(crewObjectAnchor, obj.id);
        let picture;
        // 2、坐席以座面和地面两个标记注册；桌子的操作侧与人物座位共用同一地面基线。
        if (anchor && ["desk", "security"].includes(obj.type)) {
            const floor = crewProject(anchor.furniture_position || anchor.position);
            const desk = { ...material, view: { ...material.view, ground: material.view.operator_ground } };
            picture = crewScenePicture(group, desk, floor);
        } else if (anchor && ["sofa", "chair"].includes(obj.type)) {
            const floor = crewProject(anchor.position);
            picture = crewScenePicture(group, material, floor, [floor[0], floor[1] - anchor.contact.seat_height]);
        } else picture = crewScenePicture(group, material,
            [p[0], p[1] + (material.view.world_origin_at_center ? 0 : 12)]);
        // 3、接触阴影跟随实际图片脚线，不能按占地中心画出远离家具的大椭圆。
        const px = Number(picture.getAttribute("x")), py = Number(picture.getAttribute("y"));
        const pw = Number(picture.getAttribute("width")), ph = Number(picture.getAttribute("height"));
        if (["desk", "security"].includes(obj.type)) {
            const keyboard = window.ROOMCREW_SCENE_ASSETS.attachments?.keyboard;
            const direction = anchor.direction;
            const view = keyboard?.views[direction];
            if (view) {
                const keyPicture = { ...keyboard, frames:[view.rect] };
                const keyHeight = keyboard.width * view.rect[3] / view.rect[2];
                crewEnvironmentPicture(group,keyPicture,px+pw*material.view.keyboard[0]-keyboard.width/2,
                    py+ph*material.view.keyboard[1]-keyHeight/2,keyboard.width);
            }
        }
        shadow.setAttribute("cx", px + pw * 0.5);
        shadow.setAttribute("cy", py + ph - 2);
        shadow.setAttribute("rx", pw * 0.37);
        shadow.setAttribute("ry", Math.max(3, Math.min(8, pw * 0.065)));
        if (obj.type === "tea_table") {
            const point = material.view.plant_attachment || [0.48, 0.30];
            const pot = crewEnvironmentMaterial("furniture-12");
            const height = 23 * pot.frames[0][3] / pot.frames[0][2];
            crewEnvironmentPicture(group, pot, px + pw * point[0] - 11.5,
                py + ph * point[1] - height, 23);
        }
        if (["archive", "security"].includes(obj.type))
            group.append(crewSvg("text", { x: px + pw * 0.5, y: py - 9,
                "text-anchor": "middle", "font-size": 9, fill: "#526174", stroke: "#fff",
                "paint-order": "stroke", "stroke-width": 3 },
                obj.type === "archive" ? "档案室 · 规划中" : "安全服务台 · 未接入"));
        r.depth.append(group);
        // 4、工作椅和会议椅也是同一个八向素材，不使用另一套前后朝向图片规则。
        if (["desk", "security", "meeting"].includes(obj.type))
            for (const seat of r.scene.anchors)
                if (seat.object_id === obj.id) this.chair(seat);
    }

    /** 因为坐着的人可以转向用户，需要预先创建八向椅子和有限遮挡层，帧循环只切换可见性。 */
    chair(anchor) {
        // 1、椅子脚底和人物根节点位于同一地面点，座面高度从交互合同读取。
        const floor = crewProject(anchor.position), r = this.renderer;
        const root = crewSvg("g", { "data-depth": anchor.position[0] + anchor.position[1] - 0.2,
            "data-entity": "chair:" + anchor.id, "pointer-events": "none" });
        const front = crewSvg("g", { "data-depth": anchor.position[0] + anchor.position[1] + 0.2,
            "data-entity": "chair-front:" + anchor.id, "pointer-events": "none" });
        const variants = new Map(), overlays = new Map();
        const id = "seat-clip-" + r.revision + "-" + r.seats.size;
        const clip = crewSvg("clipPath", { id });
        clip.append(crewSvg("rect", { x: floor[0] - 50,
            y: floor[1] - 35, width: 100, height: 49 }));
        front.append(clip);
        // 2、每向都使用真实关键帧，背部椅背仅在腰线以下形成前景遮挡。
        for (const direction of CREW_DIRECTIONS) {
            const material = crewSceneMaterial("chair", direction);
            const base = crewSvg("g"), overlay = crewSvg("g", { "clip-path": "url(#" + id + ")" });
            crewScenePicture(base, material, floor, [floor[0], floor[1] - anchor.contact.seat_height]);
            overlay.append(...[...base.children].map(crewCloneNode));
            variants.set(direction, base);
            overlays.set(direction, overlay);
            root.append(base);
            front.append(overlay);
        }
        r.depth.append(root, front);
        r.seats.set(anchor.id, { root, front, variants, overlays, anchor, floor });
        this.faceSeat({ target: anchor, phase: "settled" }, { direction: anchor.direction });
    }

    /** 因为椅子应跟随实际人物而不是屏幕镜像，需要切换方向对应的原绘关键帧。 */
    faceSeat(actor, sample) {
        // 1、离座后不让空椅跟随走远的人转向；固定方向时不重复改 DOM。
        const attached = crewAttachedSeat(actor);
        const seat = this.renderer.seats.get(attached?.id);
        if (!seat || actor.phase === "moving" || seat.direction === sample.direction) return;
        seat.direction = sample.direction;
        for (const [direction, variant] of seat.variants)
            variant.setAttribute("display", direction === sample.direction ? "inline" : "none");
        for (const [direction, overlay] of seat.overlays)
            overlay.setAttribute("display", direction === sample.direction && ["n", "ne", "nw"].includes(direction) ? "inline" : "none");
    }

    /** 因为配套交互帧已包含整张椅子，需要在同一帧隐藏空椅，并在人物起身后恢复。 */
    occupy(view, actor, sample, custom) {
        // 1、起身属于离开的椅子，行走不绑定任何椅子；不能远程隐藏目的地的椅子。
        const anchor = crewAttachedSeat(actor);
        const paired = custom && view.sprite?.dataset.includesSeat === "true";
        const identifier = paired ? anchor?.id : null;
        if (view.pairedSeat && view.pairedSeat !== identifier) {
            const old = this.renderer.seats.get(view.pairedSeat);
            old?.root.setAttribute("visibility","visible");
            old?.front.setAttribute("visibility","visible");
        }
        // 2、始终最多一张真实可见椅子，交互结束时不保留隐藏的空座。
        const seat = this.renderer.seats.get(identifier);
        if (seat) {
            seat.root.setAttribute("visibility","hidden");
            seat.front.setAttribute("visibility","hidden");
        }
        view.pairedSeat = identifier;
    }

    /** 因为离座后空椅应留在被拉出的位置，需要同步确定性的座椅轨迹，不在人物消失后弹回桌下。 */
    frameChairs() {
        // 1、位置来自同一动画状态机；不持久化到用户布局，也不触发 Agent。
        for(const [id,seat] of this.renderer.seats) {
            const position=this.renderer.motion.chairs.get(id)||seat.anchor.position;
            const p=crewProject(position),transform=`translate(${p[0]-seat.floor[0]},${p[1]-seat.floor[1]})`;
            seat.root.setAttribute("transform",transform);seat.front.setAttribute("transform",transform);
            seat.root.dataset.depth=position[0]+position[1]-0.2;
            seat.front.dataset.depth=position[0]+position[1]+0.2;
        }
    }


}

/** 因为同一椅子需要前景遮挡副本，需要克隆已注册图像而不重新解码像素。 */
function crewCloneNode(element) {
    // 1、克隆只用于有限八向家具节点。
    return element.cloneNode(true);
}
