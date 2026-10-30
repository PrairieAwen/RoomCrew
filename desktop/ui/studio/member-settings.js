/* 人物属性的两个独立编辑模型：执行配置与素材表现。 */
"use strict";

const CREW_BINDING_LABELS = {
    tool: "普通工具调用",
    python: "Python 脚本",
    mcp: "MCP 调用",
    skill: "查阅 Skills",
    human: "咨询人工",
    completed: "任务完成",
    security: "安全审核（预留）",
    directory: "发现团队成员",
    archive: "查阅档案库",
    delegation: "向成员递交任务",
};
const CREW_BINDING_DEFAULTS = {
    tool: "type",
    python: "type",
    mcp: "phone",
    skill: "type",
    human: "ask",
    completed: "report",
    security: "talk",
    directory: "type",
    archive: "read",
    delegation: "talk",
};

class CrewMemberConfiguration {
    /** 因为执行定义与员工外观独立变化，需要把编辑页和数据收集职责分开。 */
    constructor(materials) {
        // 1、页签仅控制编辑状态，素材设置从不写入 Agent 能力字段。
        this.actions = new CrewActionEditor(materials);
        this.mcp = new CrewMCPEditor();
        for (const key of ["agent", "material"])
            el(`member-tab-${key}`).addEventListener(
                "click",
                this.tabClick.bind(this),
            );
    }

    /** 因为人物属性需要先区分执行和显示，需要按用户选择切换独立页签。 */
    tabClick(event) {
        // 1、仅显示相应面板，不触发保存或模型请求。
        this.show(event.currentTarget.dataset.panel);
    }

    /** 因为新建和编辑需要一致的初始视图，需要集中设置页签状态与隐藏属性。 */
    show(panel = "agent") {
        // 1、只接受本地注册的两个页签，保留另一页尚未保存的内容。
        for (const key of ["agent", "material"]) {
            const active = key === panel;
            el(`member-panel-${key}`).hidden = !active;
            el(`member-tab-${key}`).setAttribute(
                "aria-selected",
                String(active),
            );
        }
    }

    /** 因为 Agent 配置可能被多个形象复用，需要只从执行定义填入这一组字段。 */
    loadAgent(member) {
        // 1、完整能力配置只在人工编辑时读取，不混入外观与动作帧。
        el("member-description").value =
            member.description || "通用文件与资料处理";
        el("member-prompt").value = member.prompt || "";
        el("member-skills").value = JSON.stringify(
            member.skills || [],
            null,
            2,
        );
        this.mcp.load(member.mcp_servers || []);
        el("member-python").checked = member.python_enabled !== false;
        el("member-abilities").hidden = member.role === "guardian";
        this.show();
    }

    /** 因为复用已有定义时不能覆盖其能力，需要只收集当前可编辑的执行字段。 */
    readAgent() {
        // 1、禁用字段不提交；JSON 解析失败由表单错误反馈处理。
        if (el("member-prompt").disabled) return {};
        return {
            prompt: el("member-prompt").value,
            description: el("member-description").value,
            ...(el("member-skills").disabled
                ? {}
                : {
                      skills: JSON.parse(el("member-skills").value || "[]"),
                      mcp_servers: this.mcp.read(),
                      python_enabled: el("member-python").checked,
                  }),
        };
    }

    /** 因为每个员工形象都有自己的泡泡和素材，需要只恢复人物级显示配置。 */
    loadMaterial(member) {
        // 1、旧版动作覆盖读入新编辑器，保存时统一为素材绑定。
        const profile = member.interaction_profile || {};
        el("member-normalize").checked =
            member.material_profile?.normalize !== false;
        el("member-question-bubble").value =
            profile.question_bubble || "老板，我有问题想问你。";
        el("member-completed-bubble").value =
            profile.completed_bubble || "老板，本轮回复已就绪，请查看。";
        this.actions.load(member);
    }

    /** 因为显示配置不得变成 Agent 提示，需要用独立字段保存素材和短泡泡。 */
    readMaterial() {
        // 1、旧覆盖字段归并到 material_profile，不并存两套可编辑映射。
        return {
            material_profile: {
                ...this.actions.read(),
                normalize: el("member-normalize").checked,
            },
            interaction_profile: {
                question_bubble: el("member-question-bubble").value,
                completed_bubble: el("member-completed-bubble").value,
                action_overrides: {},
            },
        };
    }
}

class CrewActionEditor {
    /** 因为用户应能直接选择动作帧而非手写协议，需要用统一编辑器维护人物触发映射。 */
    constructor(materials) {
        // 1、复用正式素材缓存和播放器，预览不制造任何 Agent 轨迹。
        this.materials = materials;
        this.bindings = {};
        this.manifest = null;
        this.token = 0;
        this.dirty = false;
        for (const [key, label] of Object.entries(CREW_BINDING_LABELS))
            el("binding-category").append(new Option(label, key));
        for (const [key, label] of Object.entries(CREW_ACTION_LABELS))
            el("binding-action").append(new Option(`${label} · ${key}`, key));
        el("binding-category").addEventListener(
            "change",
            this.selectCategory.bind(this),
        );
        el("binding-action").addEventListener(
            "change",
            this.selectAction.bind(this),
        );
        el("binding-clip").addEventListener(
            "change",
            this.selectClip.bind(this),
        );
        for (const key of ["binding-frames", "binding-fps", "binding-loop"])
            el(key).addEventListener("input", this.changed.bind(this));
        el("binding-apply").addEventListener(
            "click",
            this.applyClick.bind(this),
        );
        el("binding-reset").addEventListener("click", this.reset.bind(this));
        el("member-avatar").addEventListener(
            "crew-avatar-change",
            this.assetChanged.bind(this),
        );
    }

    /** 因为不同人物的帧覆盖不能相互串用，需要在打开表单时恢复各自绑定副本。 */
    load(member) {
        // 1、旧动作映射转为同语义绑定；新字段优先，编辑不修改原始快照。
        this.bindings = {};
        for (const [key, action] of Object.entries(
            member.interaction_profile?.action_overrides || {},
        ))
            this.bindings[key] = { action };
        Object.assign(
            this.bindings,
            structuredClone(member.material_profile?.bindings || {}),
        );
        this.avatarId = member.avatar_id || "builtin:crew-v1";
        el("binding-category").value = "tool";
        this.dirty = false;
        this.assetChanged();
    }

    /** 因为图集加载可能晚于人物切换，需要按代次刷新可选帧并丢弃旧请求结果。 */
    async assetChanged() {
        // 1、更换图集保留动作语义，丢弃只属于旧图集的精确变体和帧号。
        const token = ++this.token,
            identifier = el("member-avatar").value;
        if (identifier !== this.avatarId) {
            for (const [key, value] of Object.entries(this.bindings))
                this.bindings[key] = { action: value.action };
            this.avatarId = identifier;
        }
        this.materials.skins.ensure(identifier);
        await this.materials.skins.pending.get(identifier);
        if (token !== this.token) return;
        this.manifest =
            this.materials.skins.cache.get(identifier)?.manifest || null;
        this.dirty = false;
        this.selectCategory();
        this.summary();
    }

    /** 因为用户可能编辑完一个类型后切换，需要先保存当前草稿再显示目标绑定。 */
    selectCategory() {
        // 1、切换前保存原类型草稿；非法输入保持原类型并展示错误。
        if (this.dirty) {
            try {
                this.commit();
            } catch (error) {
                el("binding-category").value = this.category;
                showError(error);
                return;
            }
        }
        const category = el("binding-category").value;
        this.category = category;
        this.dirty = false;
        const value = this.bindings[category] || {
            action: CREW_BINDING_DEFAULTS[category],
        };
        el("binding-action").value = value.action;
        this.fillClips(value);
    }

    /** 因为更换动作会改变合法变体，需要同步重建帧选择并标记待保存。 */
    selectAction() {
        // 1、先回到自动方向/姿态，用户再明确指定某一图集变体。
        this.fillClips({ action: el("binding-action").value });
        this.changed();
    }

    /** 因为所有帧必须来自当前动作素材，需要用已导入清单建立明确变体列表。 */
    fillClips(binding) {
        // 1、自动选帧保留方向与坐姿适配；固定变体表示用户明确覆盖这一组合。
        el("binding-clip").replaceChildren(
            new Option("自动适配方向和姿态", ""),
        );
        for (const clip of this.manifest?.clips || [])
            if (clip.action === binding.action)
                el("binding-clip").append(
                    new Option(
                        `${CREW_DIRECTION_LABELS[clip.direction]} / ${clip.posture === "seated" ? "坐姿" : "站姿"} / ${CREW_EXPRESSION_LABELS[clip.expression]}`,
                        crewClipKey(clip),
                    ),
                );
        el("binding-clip").value = binding.clip || "";
        if (!el("binding-clip").value) el("binding-clip").value = "";
        this.fillFrames(binding);
    }

    /** 因为选定图集变体后需要看到原始帧序列，需要将其数据填入可编辑控件。 */
    selectClip() {
        // 1、使用清单原始序列作起点，不推测未制作的帧。
        this.fillFrames({});
        this.changed();
    }

    /** 因为自动骨架与图集帧编辑有不同能力，需要明确启用或禁用精确帧字段。 */
    fillFrames(binding) {
        // 1、只有明确选择真实图集变体才允许修改帧序列与速度。
        const clip = this.manifest?.clips.find(
            crewClipKeyMatches,
            el("binding-clip").value,
        );
        for (const key of ["binding-frames", "binding-fps", "binding-loop"])
            el(key).disabled = !clip;
        el("binding-frames").value = (
            binding.frames ||
            clip?.frames ||
            []
        ).join(", ");
        el("binding-fps").value = binding.fps || clip?.fps || 8;
        el("binding-loop").checked = binding.loop ?? clip?.loop ?? true;
    }

    /** 因为编辑不能立刻修改已保存人物，需要仅记录本地草稿发生变化。 */
    changed() {
        // 1、实际持久化仍统一由人物保存入口完成。
        this.dirty = true;
    }

    /** 因为帧编辑需要即时确认效果，需要应用到表单预览并反馈非法输入。 */
    applyClick() {
        // 1、只播放本地素材，不调用模型或启动任务。
        try {
            this.commit();
        } catch (error) {
            showError(error);
        }
    }

    /** 因为预览和最终保存必须使用同一数据，需要统一解析当前类型的动作与帧草稿。 */
    commit() {
        // 1、空变体使用自动适配；显式帧只允许有限整数序列。
        const binding = { action: el("binding-action").value };
        if (el("binding-clip").value) {
            const frames = el("binding-frames")
                .value.split(",")
                .map(crewFrameNumber);
            const count =
                this.manifest.frame_rects?.length ||
                (this.manifest.atlas_size[0] / this.manifest.frame_size[0]) *
                    (this.manifest.atlas_size[1] / this.manifest.frame_size[1]);
            const fps = Number(el("binding-fps").value);
            if (
                !frames.length ||
                frames.length > 120 ||
                frames.some(crewInvalidFrame, count) ||
                !Number.isInteger(fps) ||
                fps < 1 ||
                fps > 60
            )
                throw new Error(
                    "请填写图集范围内的帧号（最多 120 个）和 1–60 帧/秒。",
                );
            Object.assign(binding, {
                clip: el("binding-clip").value,
                frames,
                fps,
                loop: el("binding-loop").checked,
            });
        }
        this.bindings[this.category] = binding;
        this.dirty = false;
        this.summary();
        // 2、复用正式图集播放器，明确预览的是哪一执行触发类型。
        this.materials.stopSequence();
        el("preview-action").value = binding.action;
        this.materials.binding = binding;
        this.materials.clock = 0;
        el("preview-mode").textContent =
            `${CREW_BINDING_LABELS[this.category]} · 素材预览，不提交任务`;
    }

    /** 因为用户需要回到产品默认动作，需要只删除当前人物该类型的覆盖。 */
    reset() {
        // 1、不改变其他类型、其他员工或 Agent 能力。
        delete this.bindings[el("binding-category").value];
        this.materials.binding = null;
        this.selectCategory();
        this.summary();
    }

    /** 因为用户需要确认已配置哪些类型，需要显示简明绑定清单。 */
    summary() {
        // 1、只作为纯文本显示，不解析动作脚本。
        const items = [];
        for (const [key, value] of Object.entries(this.bindings))
            items.push(
                `${CREW_BINDING_LABELS[key]}：${CREW_ACTION_LABELS[value.action]}${value.frames ? ` · ${value.frames.length} 帧 / ${value.fps} fps` : " · 自动选帧"}`,
            );
        el("binding-summary").textContent =
            items.join("\n") || "尚无覆盖，使用默认动作映射。";
    }

    /** 因为用户可能未点击预览就保存，需要合并当前未应用草稿再提交人物素材配置。 */
    read() {
        // 1、返回独立副本，防止保存请求与继续编辑共享同一个可变对象。
        if (this.dirty) this.commit();
        return {
            version: 1,
            avatar_id: el("member-avatar").value,
            bindings: structuredClone(this.bindings),
        };
    }
}

/** 因为逗号序列可能包含空项，需要把空白转为无效值供统一校验。 */
function crewFrameNumber(text) {
    // 1、允许空格，不把空字符串当作第零帧。
    return text.trim() ? Number(text.trim()) : NaN;
}
/** 因为帧不能离开导入图集，需要同时检查整数和当前图集范围。 */
function crewInvalidFrame(frame) {
    // 1、thisArg 是清单提供的帧总数。
    return !Number.isInteger(frame) || frame < 0 || frame >= Number(this);
}
