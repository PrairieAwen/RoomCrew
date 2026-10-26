/* 统一格网的矢量素材渲染器；不依赖模型、数据库或任务调度。 */
"use strict";

/** 因为所有空间节点需要安全构造，需要用 SVG 属性创建本地注册的几何素材。 */
function crewSvg(tag, attributes = {}, text = "") {
    // 1、外部名字只作为纯文本，禁止通过 innerHTML 加载素材脚本。
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes))
        element.setAttribute(key, value);
    element.textContent = text;
    return element;
}

/** 因为用户本人不是场景员工，需要在渲染边界再次过滤旧版 User 形象。 */
function crewVisibleMember(member) {
    // 1、旧账号仍可保留历史身份记录，画面不创建老板替身。
    return member.role !== "user";
}

class CrewRenderer {
    /** 因为场景需要独立生命周期，需要只注入人物选择与家具点击两个用户回调。 */
    constructor(svg, selectMember, selectObject, assetLoader) {
        // 1、渲染器没有桌面桥；帧循环不能发模型请求或写业务状态。
        this.svg = svg;
        this.selectMember = selectMember;
        this.selectObject = selectObject;
        this.motion = new CrewMotion();
        this.navigator = new CrewNavigator();
        this.idle = new CrewIdleDirector(this.motion, this.navigator);
        this.collaboration = new CrewCollaborationDirector(
            this.motion,
            this.navigator,
        );
        this.interactions = [];
        this.animator = new CrewAnimator();
        this.rig = new CrewRig();
        this.skins = new CrewSkins(assetLoader);
        this.furniture = new CrewFurniture(this);
        this.active = true;
        this.depth = crewSvg("g");
        this.views = new Map();
        this.facts = new Map();
        this.scene = null;
        this.revision = 0;
        this.zoom = 1;
        this.previous = 0;
        this.factsHealthy = false;
        this.feedTime = 0;
        this.lastDraw = 0;
        this.reducedMotion = window.matchMedia(
            "(prefers-reduced-motion: reduce)",
        ).matches;
        this.selected = null;
        this.world = crewSvg("g");
        this.svg.append(this.world);
        this.cameraRig = new CrewCamera(svg);
        this.environment = new CrewEnvironment(svg, this.world);
        this.cameraRig.onView = this.environment.frame.bind(this.environment);
        this.environment.frame(this.cameraRig);
        this.tick = this.tick.bind(this);
        document.addEventListener(
            "visibilitychange",
            this.visibility.bind(this),
        );
        requestAnimationFrame(this.tick);
    }

    /** 因为新会议室的版本和人物 ID 可与旧房间相同，需要彻底释放可丢弃的场景表现。 */
    resetWorkspace() {
        // 1、先释放临时走动，再清空事实与显示节点；不操作任何执行器。
        this.idle.clear();
        this.idle.blocked.clear();
        this.collaboration.clear();
        this.collaboration.blocked.clear();
        this.collaboration.retryAt.clear();
        this.motion.actors.clear();
        this.animator.clear();
        this.navigator.revision = -1;
        this.facts.clear();
        this.views.clear();
        this.interactions = [];
        this.scene = null;
        this.revision = 0;
        this.factsHealthy = false;
        this.selected = null;
        this.world.replaceChildren();
        // 2、旧异步图片完成后只落在旧缓存，不进入新空间的素材目录。
        this.skins = new CrewSkins(this.skins.loader);
    }

    /** 因为快照可能乱序，需要按布局版本、成员身份和事实序号独立更新。 */
    update(data) {
        // 1、布局变化才重建静态家具；相同布局只更新人物与语义状态。
        if (data.scene.room.revision < this.revision) return;
        this.scene = data.scene;
        const navigationHealthy = this.navigator.update(data.scene.navigation);
        this.interactions = data.interactions || [];
        this.factsHealthy =
            !data.degraded && !data.catching_up && navigationHealthy;
        this.feedTime = performance.now();
        if (data.scene.room.revision !== this.revision) {
            this.revision = data.scene.room.revision;
            this.world.replaceChildren();
            this.views.clear();
            this.depth = crewSvg("g");
            this.drawRoom(data.scene.room);
        }
        const members = data.members.filter(crewVisibleMember);
        this.skins.active = new Set(members.map(crewMemberSkin));
        for (const member of members) {
            this.skins.ensure(member.avatar_id);
            const signature = JSON.stringify([
                member.name,
                member.color,
                member.skin,
                member.hair,
                member.glasses,
                member.avatar_id,
            ]);
            if (this.views.get(member.id)?.signature !== signature) {
                this.views.get(member.id)?.group.remove();
                this.views.set(member.id, this.drawMember(member, signature));
            }
            this.views.get(member.id).member = member;
        }
        // 2、归档人物释放本地绘制，历史轨迹仍由后端保留。
        const live = new Set(members.map(crewMemberId));
        for (const [identifier, view] of this.views) {
            if (!live.has(identifier)) {
                view.group.remove();
                this.views.delete(identifier);
                this.motion.actors.delete(identifier);
            }
        }
        for (const place of data.scene.placements)
            this.motion.restore(place, data.scene.anchors, this.revision);
        for (const raw of data.actors) {
            const value = crewState(raw),
                old = this.facts.get(raw.member_id);
            if (value && (!old || value.source_seq >= old.source_seq))
                this.facts.set(value.member_id, value);
        }
    }

    /** 因为所有美术都要遵守同一透视，需要通过格网顶点绘制家具立体盒。 */
    box(
        parent,
        x,
        y,
        width,
        depth,
        height,
        color,
        side = "#9c826b",
        elevation = 0,
    ) {
        // 1、顶面与立面共用脚底投影，避免素材看似错位或悬浮。
        const points = [
            [x, y],
            [x + width, y],
            [x + width, y + depth],
            [x, y + depth],
        ]
            .map(crewProject)
            .map(crewRaised, elevation);
        const top = points.map(crewRaised, height);
        parent.append(
            crewSvg("polygon", {
                points: top.map(crewPoint).join(" "),
                fill: color,
                stroke: "#665c50",
                "stroke-width": 1,
            }),
        );
        for (const pair of [
            [1, 2],
            [2, 3],
        ]) {
            const p = [
                top[pair[0]],
                top[pair[1]],
                points[pair[1]],
                points[pair[0]],
            ];
            parent.append(
                crewSvg("polygon", {
                    points: p.map(crewPoint).join(" "),
                    fill: side,
                    stroke: "#665c50",
                    "stroke-width": 1,
                }),
            );
        }
    }

    /** 因为空间应铺满应用而不是悬浮小岛，需要用连续材质和局部相机绘制办公室。 */
    drawRoom(room) {
        // 1、连续地板覆盖视口外，不因缩放或窗口比例露出黑色边界。
        const floor = crewSvg("g", { class: "scene-floor" }),
            defs = crewSvg("defs");
        const pattern = crewSvg("pattern", {
            id: "crew-floor",
            width: 96,
            height: 48,
            patternUnits: "userSpaceOnUse",
        });
        pattern.append(
            crewSvg("rect", { width: 96, height: 48, fill: "#e5dbc8" }),
            crewSvg("path", {
                d: "M0,24 L48,0 L96,24 L48,48Z M-48,0 L0,24 L48,0 M48,48 L96,24 L144,48",
                fill: "none",
                stroke: "#c8bba2",
                "stroke-width": 0.6,
            }),
            crewSvg("path", {
                d: "M0,25 L48,49 M49,1 L95,24",
                stroke: "#f8efdc",
                "stroke-width": 0.7,
            }),
        );
        defs.append(pattern);
        floor.append(
            defs,
            crewSvg("rect", {
                x: -4000,
                y: -4000,
                width: 8000,
                height: 8000,
                fill: "url(#crew-floor)",
            }),
        );
        // 2、软装保持原格网，高墙单独延伸到镜头外，窗户与标识随新墙面抬高。
        this.rug(floor, [2, 7], 11, 5, "#b2b9a4");
        this.rug(floor, [15, 2], 8, 7, "#aebdbc");
        this.rug(floor, [1, 14], 6, 4, "#c9ad85");
        this.environment.drawWalls(floor);
        for (let i = 0; i < 12; i++) {
            const p = crewProject([0.1, 3 + i * 3.1]),
                window = crewSvg("g", {
                    transform: `translate(${p[0]},${p[1] - 154})`,
                });
            window.append(
                crewSvg("path", {
                    d: "M0,0 L-62,31 L-62,88 L0,57Z",
                    fill: "#bdd0bc",
                    stroke: "#8f927b",
                    "stroke-width": 3,
                }),
                crewSvg("path", {
                    d: "M-30,15 L-30,72 M0,29 L-62,60",
                    stroke: "#f6edda",
                    "stroke-width": 3,
                }),
                crewSvg("path", {
                    d: "M-60,34 L-1,5 L-1,16 L-60,45Z",
                    fill: "#ffffff44",
                }),
            );
            floor.append(window);
        }
        this.label(floor, [6, 1], "RoomCrew", -170);
        this.label(floor, [19, 8], "MEETING · 会议区", 12);
        this.label(floor, [6, 12], "WORK · 团队工位", 10);
        this.world.append(floor, this.depth);
        for (const obj of room.objects) this.drawObject(obj);
    }

    /** 因为地毯应随家具格网一致透视，需要从同一占地顶点生成软装区域。 */
    rug(parent, position, width, depth, color) {
        // 1、纯装饰不加入后端碰撞地图。
        const [x, y] = position,
            points = [
                [x, y],
                [x + width, y],
                [x + width, y + depth],
                [x, y + depth],
            ].map(crewProject);
        parent.append(
            crewSvg("polygon", {
                points: points.map(crewPoint).join(" "),
                fill: color,
                opacity: 0.62,
                stroke: "#8a9381",
                "stroke-width": 2,
            }),
        );
    }

    /** 因为空间名称只提供方向信息，需要使用纯文本地面标识。 */
    label(parent, position, text, offset = 0) {
        // 1、标签不接受 HTML 或可点击的外部链接。
        const point = crewProject(position);
        parent.append(
            crewSvg(
                "text",
                {
                    x: point[0],
                    y: point[1] + offset,
                    "text-anchor": "middle",
                    fill: "#7e7568",
                    "font-size": 10,
                    "letter-spacing": 1,
                },
                text,
            ),
        );
    }

    /** 因为家具需要同一占地与设计语言，需要交给独立素材绘制器处理。 */
    drawObject(obj) {
        // 1、渲染器只负责组装，不更改实际布局规则。
        this.furniture.draw(obj);
    }

    /** 因为内置和自定义人物应共享点击及脚底坐标，需要创建统一人物容器。 */
    drawMember(member, signature) {
        // 1、容器保留稳定身份，骨架和图集只是可替换的显示对象。
        const group = crewSvg("g", {
            class: "crew-avatar",
            "data-member": member.id,
            tabindex: 0,
            role: "button",
            "aria-label": member.name,
        });
        group.dataset.entity = "member:" + member.id;
        group.addEventListener("click", this.memberClick.bind(this));
        group.addEventListener("keydown", this.memberKey.bind(this));
        const shadow = crewSvg("ellipse", {
            cx: 0,
            cy: 2,
            rx: 18,
            ry: 7,
            fill: "#625746",
            opacity: 0.18,
        });
        const rig = this.rig.create(member),
            badge = crewSvg("text", {
                x: 0,
                y: -127,
                "text-anchor": "middle",
                "font-size": 17,
                fill: "#4b6e5a",
            });
        const name = crewSvg(
            "text",
            {
                x: 0,
                y: 21,
                "text-anchor": "middle",
                "font-size": 10,
                fill: "#465348",
                "paint-order": "stroke",
                stroke: "#f5eddc",
                "stroke-width": 3,
            },
            member.name,
        );
        const leisureLabel = crewSvg("text", {
            x: 0,
            y: 34,
            "text-anchor": "middle",
            "font-size": 8,
            fill: "#4b735b",
            "paint-order": "stroke",
            stroke: "#f5eddc",
            "stroke-width": 2.5,
            visibility: "hidden",
        });
        group.append(shadow, rig.root, badge, name, leisureLabel);
        this.depth.append(group);
        return {
            group,
            rig,
            badge,
            name,
            shadow,
            signature,
            member,
            leisureLabel,
        };
    }

    /** 因为移动、表情、姿态与工作动作应连续组合，需要用正交播放器驱动每个人物。 */
    tick(timestamp) {
        // 1、帧循环不发桥接请求，资源和真实状态均在独立查询阶段准备。
        const interval = 1000 / 60;
        if (timestamp - this.lastDraw < interval) {
            requestAnimationFrame(this.tick);
            return;
        }
        this.lastDraw = timestamp - ((timestamp - this.lastDraw) % interval);
        const dt = Math.min(
            0.05,
            this.previous ? (timestamp - this.previous) / 1000 : 0,
        );
        this.previous = timestamp;
        if (!document.hidden && this.active) {
            if (this.reducedMotion) this.motion.settle();
            const healthy =
                this.factsHealthy &&
                timestamp - this.feedTime < 4000 &&
                !this.reducedMotion;
            this.collaboration.tick(
                this.interactions,
                this.scene,
                this.views,
                this.facts,
                healthy,
                timestamp,
            );
            this.idle.tick(
                this.views,
                this.facts,
                healthy,
                timestamp,
                this.collaboration.participants,
            );
            this.motion.step(dt);
            for (const [id, view] of this.views) {
                const actor = this.motion.actors.get(id);
                if (!actor) continue;
                const fact = this.facts.get(id),
                    sample = this.animator.sample(
                        id,
                        fact,
                        actor,
                        dt,
                        this.reducedMotion,
                        null,
                        timestamp,
                        this.collaboration.hints.get(id) ||
                            this.idle.hints.get(id),
                    );
                const p = crewProject(actor.position);
                view.group.setAttribute(
                    "transform",
                    `translate(${p[0]},${p[1]})`,
                );
                view.group.dataset.depth =
                    actor.position[0] + actor.position[1] + 0.1;
                view.group.classList.toggle(
                    "is-selected",
                    id === this.selected,
                );
                view.group.dataset.clip = sample.action;
                view.group.dataset.frame = sample.frame;
                view.group.dataset.posture = sample.posture;
                view.group.dataset.locomotion = sample.locomotion;
                view.group.dataset.expression = sample.expression;
                view.group.dataset.direction = sample.direction;
                view.group.dataset.phase = sample.phase;
                view.group.dataset.leisure = String(sample.leisure);
                view.group.dataset.idleActivity = sample.idleActivity || "";
                view.group.dataset.meeting = String(sample.meeting);
                view.group.dataset.externalCall = String(sample.externalCall);
                view.leisureLabel.textContent =
                    sample.caption ||
                    (sample.leisure
                        ? `摸鱼 · ${CREW_ACTION_LABELS[sample.action]}`
                        : "");
                view.leisureLabel.setAttribute(
                    "visibility",
                    sample.leisure || sample.caption ? "visible" : "hidden",
                );
                const custom = this.skins.render(
                    view,
                    view.member.avatar_id,
                    sample,
                );
                view.rig.root.setAttribute(
                    "visibility",
                    custom ? "hidden" : "visible",
                );
                if (!custom) this.rig.paint(view.rig, sample, dt);
                view.badge.textContent = fact?.question_count
                    ? "?"
                    : fact?.warning_count
                      ? "!"
                      : sample.externalCall
                        ? "☎"
                        : sample.meeting
                          ? "↔"
                          : {
                                think: "···",
                                talk: "↔",
                                report: "▤",
                                ask: "?",
                                alert: "!",
                            }[sample.action] || "";
            }
            // 2、按脚底深度排序，仅在顺序变化时移动节点，避免人物穿过前景家具。
            const ordered = [...this.depth.children].sort(crewEntityDepth),
                signature = ordered.map(crewEntityId).join("|");
            if (signature !== this.depthSignature) {
                this.depth.append(...ordered);
                this.depthSignature = signature;
            }
        }
        requestAnimationFrame(this.tick);
    }

    /** 因为窗口后台可能累积旧动作，需要在可见性变化时丢弃移动补帧。 */
    visibility() {
        // 1、不恢复工具或重新发起用户任务。
        this.motion.settle();
        this.idle.clear();
        this.collaboration.clear();
        this.animator.clear();
        this.previous = 0;
    }

    /** 因为点击人物表示用户开始安排工作，需要立即结束生活动作并按真实轨迹保持待命。 */
    engage(identifier, manualMove = false) {
        // 1、点击不创建任务，手动换座另行暂停会议接管。
        this.idle.engage(identifier, performance.now());
        if (manualMove)
            this.collaboration.engage(identifier, performance.now());
    }

    /** 因为人物点击用于展开轨迹，需要把稳定身份交给界面控制层。 */
    memberClick(event) {
        // 1、只改变观察对象，默认不发任何任务。
        this.selected = event.currentTarget.dataset.member;
        this.engage(this.selected);
        this.selectMember(this.selected);
    }

    /** 因为键盘用户也需要选择人物，需要支持与鼠标相同的明确选择。 */
    memberKey(event) {
        // 1、只处理 Enter，不吞掉其他导航键。
        if (event.key === "Enter") this.memberClick(event);
    }

    /** 因为家具点击既可能换座也可能编辑，需要由控制层根据当前模式决定。 */
    objectClick(event) {
        // 1、渲染层不自行调用移动或布局接口。
        this.selectObject(event.currentTarget.dataset.object);
    }

    /** 因为家具操作需要键盘可达，需要提供与点击一致的入口。 */
    objectKey(event) {
        // 1、只在明确提交键触发。
        if (event.key === "Enter") this.objectClick(event);
    }

    /** 因为缩放只影响观察，需要交给相机而不修改任何世界位置。 */
    camera(factor) {
        // 1、世界格网、家具和人物的任务状态都保持原值。
        this.cameraRig.change(factor);
    }

    /** 因为人物可能走到视口之外，需要提供纯观察的定位能力。 */
    focusMember(identifier) {
        // 1、只移动相机，角色位置和任务都不随之改变。
        const actor = this.motion.actors.get(identifier);
        if (actor) this.cameraRig.focus(actor.position);
    }
}

/** 因为排序要与所有家具一致，需要按占地位置生成稳定深度顺序。 */
function crewObjectDepth(a, b) {
    // 1、相同深度保持原始顺序。
    return a.x + a.y - b.x - b.y;
}
/** 因为顶面相对脚底抬高，需要统一用高度变换局部顶点。 */
function crewRaised(point) {
    // 1、高度仅用于美术投影，不改变导航格网。
    return [point[0], point[1] - Number(this)];
}
/** 因为 SVG 多边形需要坐标字符串，需要集中格式化本地有限坐标。 */
function crewPoint(point) {
    // 1、此函数不接受模型或外部文件输入。
    return point.join(",");
}
/** 因为人物列表需检查归档变化，需要统一提取稳定成员 ID。 */
function crewMemberId(member) {
    // 1、显示名称不承担身份关联。
    return member.id;
}

/** 因为深度排序必须统一比较所有素材，需要使用脚底世界深度而非 DOM 创建顺序。 */
function crewEntityDepth(a, b) {
    // 1、同深度保持当前稳定顺序。
    return Number(a.dataset.depth) - Number(b.dataset.depth);
}
/** 因为深度顺序不变时无需重新插入节点，需要提取稳定素材身份。 */
function crewEntityId(element) {
    // 1、此标识不承担权限或执行身份。
    return element.dataset.entity;
}
/** 因为图集缓存需要知道哪些资源仍被使用，需要从人物配置提取注册引用。 */
function crewMemberSkin(member) {
    // 1、引用不是本机路径或任意 URL。
    return member.avatar_id;
}
