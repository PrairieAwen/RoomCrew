/* 人物素材与动作预览；所有预览都是人工编辑，不提交 Agent 任务。 */
"use strict";

const CREW_PORTRAIT_PREVIEW = [
    { action: "idle", posture: "standing", direction: "se", duration: 2 },
    { action: "walk", posture: "standing", direction: "se", duration: 2.4 },
    { action: "run", posture: "standing", direction: "se", duration: 2.4 },
    { action: "walk", posture: "standing", direction: "ne", duration: 2.4 },
    { action: "run", posture: "standing", direction: "ne", duration: 2.4 },
    { action: "sit_down", posture: "standing", direction: "se", duration: 0.4 },
    { action: "phone", posture: "seated", direction: "se", duration: 5 },
    { action: "stand_up", posture: "standing", direction: "se", duration: 0.4 },
    { action: "phone", posture: "standing", direction: "se", duration: 4 },
    { action: "ask", posture: "standing", direction: "se", duration: 2 },
];

class CrewMaterialPanel {
    /** 因为用户需要在绑定前检验动作，需要复用正式播放器而非另写一套假动画。 */
    constructor(skins) {
        // 1、预览与正式场景共用已验证图集缓存及骨架。
        this.skins = skins;
        this.rig = new CrewRig();
        this.clock = 0;
        this.previous = 0;
        this.lastDraw = 0;
        this.token = 0;
        this.view = null;
        this.sequence = null;
        for (const key of [
            "member-color",
            "member-skin",
            "member-hair",
            "member-glasses",
            "member-normalize",
        ])
            el(key).addEventListener("input", this.appearance.bind(this));
        for (const key of [
            "preview-action",
            "preview-expression",
            "preview-direction",
            "preview-posture",
        ])
            el(key).addEventListener("change", this.changePreview.bind(this));
        el("member-avatar").addEventListener(
            "change",
            this.changeAvatar.bind(this),
        );
        el("import-avatar").addEventListener(
            "click",
            this.importAvatar.bind(this),
        );
        el("example-avatar").addEventListener(
            "click",
            this.importExample.bind(this),
        );
        el("portrait-avatar").addEventListener(
            "click",
            this.importPortrait.bind(this),
        );
        el("bundle-avatar").addEventListener(
            "click",
            this.importBundle.bind(this),
        );
        el("preview-sequence").addEventListener(
            "click",
            this.toggleSequence.bind(this),
        );
        el("reload-avatar").addEventListener("click", this.reload.bind(this));
        el("member-leisure-action").addEventListener(
            "change",
            this.previewLeisure.bind(this),
        );
        for (const action of Object.keys(CREW_CLIPS)) {
            const option = node(
                "option",
                "",
                `${CREW_ACTION_LABELS[action]} · ${action}`,
            );
            option.value = action;
            el("preview-action").append(option);
        }
        for (const expression of CREW_EXPRESSIONS) {
            const option = node(
                "option",
                "",
                `${CREW_EXPRESSION_LABELS[expression]} · ${expression}`,
            );
            option.value = expression;
            el("preview-expression").append(option);
        }
        for (const direction of CREW_DIRECTIONS) {
            const option = node(
                "option",
                "",
                `${CREW_DIRECTION_LABELS[direction]} · ${direction}`,
            );
            option.value = direction;
            el("preview-direction").append(option);
        }
        el("preview-direction").value = "se";
        this.tick = this.tick.bind(this);
        requestAnimationFrame(this.tick);
    }

    /** 因为表单可能连续切换人物，需要带代次恢复当前素材并丢弃旧目录请求。 */
    async open(member) {
        // 1、立即提供当前引用，目录慢或损坏也不阻止编辑普通属性。
        const token = ++this.token,
            identifier = member.avatar_id || "builtin:crew-v1";
        this.stopSequence();
        el("member-avatar").replaceChildren();
        const current = node("option", "", identifier);
        current.value = identifier;
        el("member-avatar").append(current);
        el("preview-action").value = "idle";
        el("preview-expression").value = "neutral";
        el("preview-posture").value = "standing";
        this.clock = 0;
        this.appearance();
        this.changeAvatar();
        try {
            const catalog = await api("avatar_catalog");
            if (token !== this.token) return;
            el("member-avatar").replaceChildren();
            for (const asset of catalog) {
                const option = node("option", "", asset.name);
                option.value = asset.id;
                el("member-avatar").append(option);
            }
            el("member-avatar").value = identifier;
            if (!el("member-avatar").value) {
                el("member-avatar").value = "builtin:crew-v1";
                el("avatar-feedback").textContent =
                    "原素材缺失，可保存为内置外观或重新导入。";
            }
        } catch (error) {
            el("avatar-feedback").textContent =
                "素材目录暂不可用，已有角色仍可编辑。";
        }
    }

    /** 因为配色与眼镜应即时预览，需要只重建本地骨架而不更改已保存的成员。 */
    appearance() {
        // 1、字段仍由保存接口校验，预览不读数据库或模型配置。
        const member = {
            color: el("member-color").value,
            skin: el("member-skin").value,
            hair: el("member-hair").value,
            glasses: el("member-glasses").checked,
        };
        const group = crewSvg("g"),
            rig = this.rig.create(member),
            badge = crewSvg("text");
        group.append(
            crewSvg("ellipse", {
                cx: 0,
                cy: 3,
                rx: 21,
                ry: 7,
                fill: "#0b1615",
                opacity: 0.2,
            }),
            rig.root,
            badge,
        );
        el("avatar-preview").replaceChildren(group);
        this.view = { group, rig, badge };
        this.view.member = {
            material_profile: { normalize: el("member-normalize").checked },
        };
    }

    /** 因为预览切换不能继承旧片段进度，需要从新动作起点播放。 */
    changePreview() {
        // 1、跑步和坐姿互斥，与实际场景保持同一约束。
        this.stopSequence();
        this.binding = null;
        if (["walk", "run", "stand_up"].includes(el("preview-action").value))
            el("preview-posture").value = "standing";
        this.clock = 0;
    }

    /** 因为验收需要连续观察完整步态和生活动作，需要提供明确标注的纯素材连播。 */
    toggleSequence() {
        // 1、播放只切换现有预览控件，不读取或改写任务事实。
        if (this.sequence) {
            this.stopSequence();
            return;
        }
        this.sequence = { index: 0, elapsed: 0 };
        el("preview-sequence").textContent = "停止连播";
        this.applySequenceStep();
    }

    /** 因为连播与手工选择应共用同一播放器，需要将当前片段写入预览控件。 */
    applySequenceStep() {
        // 1、姿态与朝向来自固定样板列表，不能触发走动命令或模型请求。
        const step = CREW_PORTRAIT_PREVIEW[this.sequence.index];
        el("preview-action").value = step.action;
        el("preview-posture").value = step.posture;
        el("preview-direction").value = step.direction;
        el("preview-expression").value = "neutral";
        el("preview-mode").textContent =
            `原地连播 · ${CREW_ACTION_LABELS[step.action]} · 不提交任务`;
        this.clock = 0;
    }

    /** 因为用户手动选择或关闭编辑时不应继续覆盖控件，需要清理本地连播状态。 */
    stopSequence() {
        // 1、只清理预览播放器，不触碰正式场景的动作时钟。
        this.sequence = null;
        el("preview-sequence").textContent = "连播核心动作";
        el("preview-mode").textContent = "素材预览 · 不提交任务";
    }

    /** 因为用户选择空闲习惯后需要立即看到效果，需要只在素材预览中切换动作而不提交任务。 */
    previewLeisure() {
        // 1、生活动作使用同一播放器；保持待命时使用普通 idle。
        const action = el("member-leisure-action").value;
        el("preview-action").value = CREW_LEISURE_ACTIONS.has(action)
            ? action
            : "idle";
        el("preview-expression").value =
            action === "none" ? "neutral" : "smile";
        this.changePreview();
    }

    /** 因为更换素材只改变显示引用，需要按需请求已注册图片并保留原执行定义。 */
    changeAvatar() {
        // 1、不发送人物提示、模型参数或工作日志。
        this.view?.sprite?.remove();
        if (this.view) this.view.sprite = null;
        const imported = el("member-avatar").value.startsWith("avatar:");
        for (const key of [
            "member-color",
            "member-skin",
            "member-hair",
            "member-glasses",
        ])
            el(key).disabled = imported;
        this.skins.ensure(el("member-avatar").value);
        this.binding = null;
        el("member-avatar").dispatchEvent(new Event("crew-avatar-change"));
        this.clock = 0;
        el("avatar-feedback").textContent =
            "缺少工作动作回退到同姿态 idle；缺少摸鱼动作或姿态则使用内置骨架。";
    }

    /** 因为用户需要先试用完整素材，需要导入随程序提供的可编辑样例。 */
    async importExample() {
        // 1、来源是固定样例，不接受模型生成的路径。
        await this.importSource("import_avatar_example");
    }

    /** 因为新角色美术应可独立试用，需要通过正式素材导入入口展示而不替换用户原绑定。 */
    async importPortrait() {
        // 1、来源固定为随应用分发的手绘样板，不发送任务或模型请求。
        await this.importSource("import_avatar_portrait");
    }

    /** 因为四套角色需要共用安全导入和反馈，需要只传递有限角色标识来选择整套动作素材。 */
    async importBundle() {
        // 1、选择形象不改变人物身份或 Agent 能力；保存前只预览。
        await this.importSource(
            "import_avatar_bundle",
            el("bundle-character").value,
        );
    }

    /** 因为用户自制素材需选择来源，需要调用同一导入工作流维护反馈和表单代次。 */
    async importAvatar() {
        // 1、实际来源由原生文件选择器决定。
        await this.importSource("import_avatar");
    }

    /** 因为用户自制素材需显式选择来源，需要调用原生文件选择器后再显示校验结果。 */
    async importSource(method, role = null) {
        // 1、只接受本地 PNG 图集与 JSON 清单，不向网页传文件路径或执行脚本。
        const token = ++this.token;
        el("import-avatar").disabled = true;
        el("example-avatar").disabled = true;
        el("portrait-avatar").disabled = true;
        el("bundle-avatar").disabled = true;
        el("avatar-feedback").textContent =
            method !== "import_avatar"
                ? "正在导入并校验随附动作样例…"
                : "选择 JSON 描述文件；PNG 图集放在同一文件夹。";
        try {
            const result =
                role === null ? await api(method) : await api(method, role);
            if (result.cancelled) return;
            if (token !== this.token || !el("member-dialog").open) return;
            const catalog = await api("avatar_catalog");
            el("member-avatar").replaceChildren();
            for (const asset of catalog) {
                const option = node("option", "", asset.name);
                option.value = asset.id;
                el("member-avatar").append(option);
            }
            el("member-avatar").value = result.id;
            this.changeAvatar();
            if (method === "import_avatar_portrait") {
                el("preview-action").value = "phone";
                el("preview-posture").value = "seated";
                el("preview-direction").value = "se";
            }
            el("avatar-feedback").textContent =
                "已校验并复制到本地素材库。点击保存后绑定到人物。";
        } catch (error) {
            if (!error.stale && token === this.token)
                el("avatar-feedback").textContent =
                    error.message || "素材导入失败";
        } finally {
            if (token === this.token) {
                el("import-avatar").disabled = false;
                el("example-avatar").disabled = false;
                el("portrait-avatar").disabled = false;
                el("bundle-avatar").disabled = false;
            }
        }
    }

    /** 因为暂时读取失败不应永久锁住素材，需要提供人工重新加载而不自动无限重试。 */
    reload() {
        // 1、只刷新当前注册引用，不接受任意 URL。
        const id = el("member-avatar").value;
        this.skins.errors.delete(id);
        this.skins.cache.delete(id);
        this.changeAvatar();
    }

    /** 因为预览应体现正式播放器的真实能力，需要使用相同骨架与图集选帧接口。 */
    tick(timestamp) {
        // 1、仅在编辑窗口打开时绘制，预览绝不提交任务或伪造轨迹。
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
        if (el("member-dialog").open && !document.hidden && this.view) {
            if (this.sequence) {
                this.sequence.elapsed += dt;
                if (
                    this.sequence.elapsed >=
                    CREW_PORTRAIT_PREVIEW[this.sequence.index].duration
                ) {
                    this.sequence.index =
                        (this.sequence.index + 1) %
                        CREW_PORTRAIT_PREVIEW.length;
                    this.sequence.elapsed = 0;
                    this.applySequenceStep();
                }
            }
            this.clock += dt;
            const action = el("preview-action").value;
            let seat = el("preview-posture").value === "seated" ? 1 : 0;
            if (action === "sit_down")
                seat = crewEase(Math.min(1, this.clock / 0.38));
            if (action === "stand_up")
                seat = 1 - crewEase(Math.min(1, this.clock / 0.32));
            const sample = {
                action,
                material_binding: this.binding,
                expression: el("preview-expression").value,
                direction: el("preview-direction").value,
                posture: seat === 1 ? "seated" : "standing",
                seatMix: seat,
                time: this.clock,
                clock: this.clock,
                reduced: false,
            };
            const custom = this.skins.render(
                this.view,
                el("member-avatar").value,
                sample,
            );
            this.view.rig.root.setAttribute(
                "display",
                custom ? "none" : "inline",
            );
            if (!custom) this.rig.paint(this.view.rig, sample, dt);
            el("avatar-preview").dataset.action = action;
            el("avatar-preview").dataset.expression = sample.expression;
        }
        requestAnimationFrame(this.tick);
    }
}
