/* 完整素材总览：纯本地预览，不持有桌面桥、任务或模型配置。 */
"use strict";

/** 因为素材名称与描述不能变成 HTML，需要统一使用文本节点构造浏览界面。 */
function materialNode(tag, className = "", text = "") {
    // 1、内容一律作为纯文本，图片仅来自固定素材目录。
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
}

class MaterialGallery {
    /** 因为用户需要核查整套素材，需要维护类别、已解码图像和独立预览时钟。 */
    constructor(catalog) {
        // 1、素材数据来自随库分发的 catalog.js，不读取账号或运行日志。
        this.catalog = catalog;
        this.images = new Map();
        this.players = [];
        this.detail = null;
        this.time = 0;
        this.previous = 0;
        this.lastDraw = 0;
        this.paused = false;
        this.frameIndex = null;
        this.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
        document.addEventListener("keydown", this.keydown.bind(this));
        for (const button of document.querySelectorAll("nav button"))
            button.addEventListener("click", this.categoryClick.bind(this));
        document
            .getElementById("close-inspector")
            .addEventListener("click", this.close.bind(this));
        document
            .getElementById("toggle-play")
            .addEventListener("click", this.toggle.bind(this));
        document
            .getElementById("frame-slider")
            .addEventListener("input", this.scrub.bind(this));
        for (const key of ["action", "posture", "direction", "expression"])
            document
                .getElementById("detail-" + key)
                .addEventListener("change", this.change.bind(this));
        this.fillOptions("detail-action", CREW_ACTION_LABELS);
        this.fillOptions("detail-direction", CREW_DIRECTION_LABELS);
        this.fillOptions("detail-expression", CREW_EXPRESSION_LABELS);
        for (const [key, label] of [
            ["characters", "套角色"],
            ["character_frames", "人物姿态帧"],
            ["objects", "家具与装饰"],
            ["effects", "组状态特效"],
        ]) {
            const metric = materialNode("div", "metric");
            const value =
                key === "objects"
                    ? catalog.summary.furniture + catalog.summary.decor
                    : catalog.summary[key];
            metric.append(
                materialNode("strong", "", String(value)),
                materialNode("span", "", label),
            );
            document.getElementById("metrics").append(metric);
        }
        this.selectCategory("character");
        this.tick = this.tick.bind(this);
        requestAnimationFrame(this.tick);
    }

    /** 因为素材页位于隔离 iframe，需要在详情已关闭时将 Esc 转为有限的父窗口关闭请求。 */
    keydown(event) {
        // 1、详情弹窗优先使用浏览器自身关闭行为，独立浏览时不导航或关闭其他窗口。
        if (
            event.key === "Escape" &&
            !document.getElementById("inspector").open &&
            window.parent !== window
        )
            window.parent.postMessage({ type: "roomcrew.material.close" }, "*");
    }

    /** 因为动作、表情和朝向要沿用产品词表，需要从有限映射构造下拉菜单。 */
    fillOptions(identifier, values) {
        // 1、显示中文标签，保存英文语义标识。
        for (const [value, label] of Object.entries(values)) {
            const option = materialNode("option", "", label);
            option.value = value;
            document.getElementById(identifier).append(option);
        }
        document.getElementById("detail-direction").value = "se";
    }

    /** 因为类别切换不应新增文件或模型请求，需要只筛选已经登记的本地目录。 */
    categoryClick(event) {
        // 1、类别标识只来自固定导航按钮。
        this.selectCategory(event.currentTarget.dataset.category);
    }

    /** 因为素材种类不同需要不同说明，需要重建对应卡片或显示真实动作覆盖矩阵。 */
    selectCategory(category) {
        // 1、离开的卡片不再绘制，缓存仍可复用于随后打开的详情。
        this.players = [];
        document.getElementById("asset-grid").replaceChildren();
        for (const button of document.querySelectorAll("nav button"))
            button.classList.toggle(
                "selected",
                button.dataset.category === category,
            );
        document.getElementById("coverage").hidden = category !== "matrix";
        const titles = {
            character: [
                "会议室里的伙伴",
                "点击角色查看实际动作、姿态与朝向；关键帧预览的未覆盖能力会单独标明。",
            ],
            furniture: [
                "让工作发生的地方",
                "常用手绘家具已接入房间；各项具体用途与未接入项见详情。",
            ],
            decor: [
                "把空间布置成自己的样子",
                "窗、灯、门与日常小物。点击查看大图与原始来源。",
            ],
            effects: [
                "让每个状态都能被看见",
                "8 组、每组 4 帧；图标只是素材，不表示任务已通过核验或权限已授权。",
            ],
            matrix: [
                "实际绘制了哪些动作",
                "覆盖按真实清单计算；有动作不代表所有方向、姿态和表情组合都已绘制。",
            ],
        };
        document.getElementById("section-title").textContent =
            titles[category][0];
        document.getElementById("section-note").textContent =
            titles[category][1];
        if (category === "matrix") {
            this.matrix();
            document.getElementById("section-count").textContent = `20 × ${this.catalog.characters.length}`;
            return;
        }
        const entries =
            category === "character"
                ? this.catalog.characters
                : this.catalog.objects.filter(isMaterialCategory, category);
        document.getElementById("section-count").textContent =
            entries.length + " 项素材";
        for (const entry of entries) this.card(entry);
    }

    /** 因为图片应只解码一次，需要按相对路径缓存加载结果并把失败明确显示。 */
    async image(path) {
        // 1、路径来自固定目录，拒绝网络 URL 与越级目录。
        if (/^(?:[a-z]+:|\/)/i.test(path) || path.includes(".."))
            throw new Error("素材路径无效");
        if (this.images.has(path)) return this.images.get(path);
        const image = new Image();
        image.src = path;
        const promise = image.decode().then(this.loadedImage.bind(this, image));
        this.images.set(path, promise);
        return promise;
    }

    /** 因为缓存需要发布已解码图像，需要在同一具名回调中返回完成后的对象。 */
    loadedImage(image) {
        // 1、不改变原始图片像素或创建网络副本。
        return image;
    }

    /** 因为每张卡片要独立播放，需要准备真实图像后再登记到有界的当前页面播放器。 */
    async card(entry) {
        // 1、先显示文字与加载区域，不把加载失败说成没有素材。
        const card = materialNode("article", "asset-card"),
            stage = materialNode("div", "asset-stage");
        const canvas = materialNode("canvas");
        canvas.width = 420;
        canvas.height = 420;
        canvas.setAttribute("aria-label", entry.name + "预览");
        stage.append(
            canvas,
            materialNode(
                "span",
                "kind-badge",
                entry.kind === "character" ? "可导入角色" : "已制作 · 可预览",
            ),
        );
        const info = materialNode("div", "asset-info");
        const count =
            entry.kind === "character"
                ? `${entry.frame_count} 个姿态 · ${entry.action_count} 种动作${entry.coverage_level === "keyframe-preview" ? " · 关键帧预览" : " · 5 种闲置表情"}`
                : entry.kind === "effects"
                  ? "4 帧状态动画"
                  : "透明 PNG · 统一画风";
        info.append(
            materialNode("h3", "", entry.name),
            materialNode("p", "", count),
        );
        const button = materialNode(
            "button",
            "",
            entry.kind === "character" ? "查看全部动作 ↗" : "查看素材 ↗",
        );
        button.dataset.id = entry.id;
        button.addEventListener("click", this.openClick.bind(this));
        info.append(button);
        card.append(stage, info);
        document.getElementById("asset-grid").append(card);
        try {
            const paths =
                entry.kind === "character" ? entry.images : [entry.image];
            const images = [];
            for (const path of paths) images.push(await this.image(path));
            if (!card.isConnected) return;
            this.players.push({
                entry,
                canvas,
                images,
                action: "idle",
                posture: "standing",
                direction: "se",
                expression: "neutral",
                detail: false,
            });
        } catch (error) {
            info.append(materialNode("p", "", error.message || "素材加载失败"));
        }
    }

    /** 因为素材详情只能由明确点击打开，需要根据固定 ID 找到已登记项目。 */
    openClick(event) {
        // 1、不按用户文本构造资源地址。
        const id = event.currentTarget.dataset.id;
        const entry = [
            ...this.catalog.characters,
            ...this.catalog.objects,
        ].find(materialId, id);
        if (entry) this.open(entry);
    }

    /** 因为用户需要逐项检查动作与原始 PNG，需要展示可暂停、逐帧和切换变体的真实播放器。 */
    async open(entry) {
        // 1、先清理旧详情，防止异步图片覆盖随后选择的另一项。
        this.detail = null;
        this.paused = false;
        this.frameIndex = null;
        this.time = 0;
        document.getElementById("detail-name").textContent = entry.name;
        document.getElementById("detail-note").textContent =
            entry.kind === "character"
                ? entry.notes +
                  (entry.edge_frames.length
                      ? ` ${entry.edge_frames.length} 个边缘姿态建议继续精修。`
                      : "")
                : entry.integration;
        document.getElementById("character-controls").hidden =
            entry.kind !== "character";
        document.getElementById("detail-action").value = "idle";
        document.getElementById("detail-posture").value = "standing";
        document.getElementById("detail-direction").value = "se";
        document.getElementById("detail-expression").value = "neutral";
        document.getElementById("toggle-play").textContent = "暂停";
        const links = document.getElementById("source-links");
        links.replaceChildren();
        for (const path of entry.kind === "character"
            ? [`characters/${entry.id}/avatar.json`, ...entry.images]
            : [entry.image]) {
            const link = materialNode(
                "a",
                "",
                path.endsWith("json") ? "动作清单" : "原始 PNG",
            );
            link.href = path;
            link.target = "_blank";
            link.rel = "noopener";
            links.append(link);
        }
        const dialog = document.getElementById("inspector");
        if (!dialog.open) dialog.showModal();
        try {
            const images = [];
            for (const path of entry.kind === "character"
                ? entry.images
                : [entry.image])
                images.push(await this.image(path));
            if (
                document.getElementById("detail-name").textContent !==
                entry.name
            )
                return;
            this.detail = {
                entry,
                images,
                canvas: document.getElementById("detail-canvas"),
                detail: true,
            };
            this.change();
        } catch (error) {
            document.getElementById("fallback-note").textContent =
                error.message || "素材加载失败";
        }
    }

    /** 因为关闭详情后不应继续绘制隐藏大画布，需要释放当前预览引用。 */
    close() {
        // 1、图像缓存仍可复用，关闭不删除素材或修改人物绑定。
        document.getElementById("inspector").close();
        this.detail = null;
    }

    /** 因为人工切换变体应从头检查，需要重置片段时间并读取有限控件值。 */
    change() {
        // 1、变体选择复用正式播放器的 crewSelectClip。
        if (!this.detail) return;
        for (const key of ["action", "posture", "direction", "expression"])
            this.detail[key] = document.getElementById("detail-" + key).value;
        this.time = 0;
        this.frameIndex = null;
    }

    /** 因为用户要观察关键姿态，需要暂停播放而不改变资源或执行状态。 */
    toggle() {
        // 1、这里只影响素材展台的时钟。
        this.paused = !this.paused;
        this.frameIndex = null;
        document.getElementById("toggle-play").textContent = this.paused
            ? "播放"
            : "暂停";
    }

    /** 因为逐帧检查应停在指定画面，需要暂停自动计时并使用有界滑块序号。 */
    scrub() {
        // 1、帧索引随后仍限制在实际片段长度内。
        this.paused = true;
        this.frameIndex = Number(document.getElementById("frame-slider").value);
        document.getElementById("toggle-play").textContent = "播放";
    }

    /** 因为总览不能把缺失变体冒充已绘制，需要按实际片段统计方向和姿态覆盖。 */
    matrix() {
        // 1、矩阵直接来自角色清单，不使用手写完成标记。
        const container = document.getElementById("coverage");
        container.replaceChildren();
        const table = materialNode("table"),
            head = materialNode("tr");
        head.append(materialNode("th", "", "动作"));
        for (const entry of this.catalog.characters)
            head.append(materialNode("th", "", entry.name));
        table.append(head);
        for (const action of Object.keys(CREW_ACTION_LABELS)) {
            const row = materialNode("tr");
            row.append(materialNode("td", "", CREW_ACTION_LABELS[action]));
            for (const entry of this.catalog.characters) {
                const matches = entry.manifest.clips.filter(
                    materialAction,
                    action,
                );
                const postures = new Set(),
                    directions = new Set();
                for (const clip of matches) {
                    postures.add(clip.posture);
                    directions.add(clip.direction);
                }
                row.append(
                    materialNode(
                        "td",
                        "",
                        matches.length
                            ? `✓ ${postures.size} 姿态 / ${directions.size} 原绘朝向`
                            : "待制作",
                    ),
                );
            }
            table.append(row);
        }
        container.append(
            table,
            materialNode(
                "p",
                "coverage-note",
                "西向可按声明镜像复用；未提供的姿态、朝向或表情会按播放器规则回退。五种基础表情目前在闲置姿态提供，尚未组合到每个动作。",
            ),
        );
    }

    /** 因为整库预览不应占满帧预算，需要限频绘制可见卡片并复用已解码纹理。 */
    tick(timestamp) {
        // 1、隐藏窗口停止推进，不调用桌面桥、模型或文件写入。
        const dt = this.previous
            ? Math.min(0.1, (timestamp - this.previous) / 1000)
            : 0;
        this.previous = timestamp;
        if (!document.hidden && !this.paused) this.time += dt;
        if (timestamp - this.lastDraw > 90 && !document.hidden) {
            this.lastDraw = timestamp;
            for (const player of this.players) {
                const rect = player.canvas.getBoundingClientRect();
                if (rect.bottom > 0 && rect.top < innerHeight)
                    this.draw(player, timestamp / 1000);
            }
            if (this.detail && document.getElementById("inspector").open)
                this.draw(this.detail, this.time);
        }
        requestAnimationFrame(this.tick);
    }

    /** 因为人物与家具都需要真实裁切预览，需要在画布中按清单坐标绘制已制作像素。 */
    draw(player, time) {
        // 1、人物选帧沿用产品语义选择器，物件使用已登记的静态或四帧区域。
        const { entry, canvas, images } = player,
            ctx = canvas.getContext("2d"),
            w = canvas.width,
            h = canvas.height;
        ctx.clearRect(0, 0, w, h);
        let frames,
            clip = null,
            manifest = entry.manifest;
        if (entry.kind === "character") {
            clip = crewSelectClip(manifest, player);
            if (!clip) {
                if (player.detail) {
                    document.getElementById("frame-caption").textContent =
                        "此组合未绘制";
                    document.getElementById("fallback-note").textContent =
                        "此姿态无可用变体；会议室内将使用内置骨架回退。";
                }
                return;
            }
            frames = clip.frames;
        } else frames = entry.frames;
        const raw =
            player.detail && this.frameIndex !== null
                ? this.frameIndex
                : this.reduced
                  ? 0
                  : Math.floor(time * (clip?.fps || entry.fps));
        const ordinal = Math.max(
            0,
            Math.min(
                frames.length - 1,
                clip?.loop === false ? raw : raw % frames.length,
            ),
        );
        if (entry.kind === "character") {
            const frame = manifest.frame_rects[frames[ordinal]],
                [x, y, rw, rh] = frame.rect,
                scale =
                    Math.min(
                        w / manifest.frame_size[0],
                        h / manifest.frame_size[1],
                    ) * 0.86;
            ctx.save();
            ctx.translate(w / 2, h * 0.9);
            ctx.fillStyle = "#596c431b";
            ctx.beginPath();
            ctx.ellipse(0, 2, w * 0.09, h * 0.025, 0, 0, Math.PI * 2);
            ctx.fill();
            if (
                manifest.mirror_west &&
                ["w", "nw", "sw"].includes(player.direction)
            )
                ctx.scale(-1, 1);
            ctx.drawImage(
                images[frame.page],
                x,
                y,
                rw,
                rh,
                (frame.offset[0] - manifest.pivot[0]) * scale,
                (frame.offset[1] - manifest.pivot[1]) * scale,
                rw * frame.scale * scale,
                rh * frame.scale * scale,
            );
            ctx.restore();
            canvas.dataset.page = String(frame.page);
            canvas.dataset.sourceFrame = String(frames[ordinal]);
        } else {
            const [x, y, rw, rh] = frames[ordinal],
                scale = Math.min(w / rw, h / rh) * 0.84;
            ctx.drawImage(
                images[0],
                x,
                y,
                rw,
                rh,
                (w - rw * scale) / 2,
                (h - rh * scale) / 2,
                rw * scale,
                rh * scale,
            );
        }
        // 2、详情始终标明实际片段和回退，不能把通用 idle 说成专用动作。
        if (player.detail) {
            const slider = document.getElementById("frame-slider");
            slider.max = String(frames.length - 1);
            slider.value = String(ordinal);
            document.getElementById("frame-caption").textContent =
                `片段第 ${ordinal + 1} / ${frames.length} 帧 · 仅素材预览`;
            const fallbacks = [];
            if (clip && clip.action !== player.action)
                fallbacks.push("动作缺失，回退待命");
            if (clip && clip.expression !== player.expression)
                fallbacks.push("表情未绘制，使用现有表情");
            if (
                clip &&
                clip.direction !==
                    crewAtlasDirection(manifest, player.direction)
            )
                fallbacks.push("方向使用最近已有朝向");
            if (
                clip &&
                manifest.mirror_west &&
                ["w", "nw", "sw"].includes(player.direction)
            )
                fallbacks.push("西向镜像复用");
            document.getElementById("fallback-note").textContent = clip
                ? `${CREW_ACTION_LABELS[clip.action]} · ${clip.posture === "seated" ? "坐姿" : "站姿"} · ${CREW_EXPRESSION_LABELS[clip.expression]} · 原绘 ${clip.direction}${fallbacks.length ? "；" + fallbacks.join("；") : ""}`
                : "图集裁切预览 · 场景接入见说明";
        }
    }
}

/** 因为筛选不使用模糊名称，需要按固定类别比较登记条目。 */
function isMaterialCategory(entry) {
    /* 1、thisArg 来自固定导航。 */ return entry.kind === String(this);
}
/** 因为人物和物件名称可以重复，需要用稳定 ID 选择详情。 */
function materialId(entry) {
    /* 1、不按文本推断路径。 */ return entry.id === String(this);
}
/** 因为覆盖矩阵需反映真实动作，需要按精确语义筛选片段。 */
function materialAction(clip) {
    /* 1、未知动作不计入覆盖。 */ return clip.action === String(this);
}

window.materialGallery = new MaterialGallery(window.ROOMCREW_MATERIAL_LIBRARY);
