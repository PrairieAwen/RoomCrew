/* 特殊行为顺序导演：消费持久表现队列，不控制 Agent 执行。 */
"use strict";
const CREW_PERFORMANCE_KINDS = new Set(["mcp", "archive", "handoff", "security"]);

class CrewActionDirector {
    /** 因为两个并行委派也需先后演示，需要为每个工作空间维护一个独立的顺序播放状态机。 */
    constructor(motion, navigator) {
        // 1、只使用视觉运动和地图；回执由控制层轮询提交，不在帧回调调用后端。
        this.motion = motion;
        this.navigator = navigator;
        this.queue = [];
        this.active = null;
        this.seen = new Set();
        this.through = 0;
        this.receipts = [];
        this.hints = new Map();
        this.participants = new Set();
        this.blocked = new Map();
    }

    /** 因为合并次数可在播放期间增长，需要按代表序号去重并更新计数，不重置动画进度。 */
    offer(actions) {
        // 1、忽略已播和重复项；不使用四秒过期或丢弃尾部的短动画队列。
        for (const action of actions || []) {
            if (!action.visual_only || !CREW_PERFORMANCE_KINDS.has(action.kind) ||
                !Number.isSafeInteger(action.source_seq) || action.source_seq <= this.through ||
                action.id !== String(action.source_seq) || typeof action.member_id !== "string") continue;
            const aggregate = crewPerformanceAggregation(action);
            if (this.seen.has(action.id)) {
                const current = this.active?.item.id === action.id ? this.active.item :
                    this.queue.find(crewPerformanceIdMatches, action.id);
                if (current && current.kind === action.kind && current.member_id === action.member_id &&
                    aggregate && aggregate.count >= (current.aggregation?.count || 1) &&
                    aggregate.last_seq >= (current.aggregation?.last_seq || current.source_seq))
                    current.aggregation = aggregate;
                continue;
            }
            this.seen.add(action.id);
            this.queue.push({...action, aggregation: aggregate});
        }
        this.queue.sort(crewPerformanceSequence);
    }

    /** 因为切换空间不能串播旧成员，需要彻底清理本地队列，未确认动作仍留在原空间数据库。 */
    reset() {
        // 1、释放当前临时移动，再丢弃只属于本窗口的缓存。
        this.clear();
        this.queue = [];
        this.seen.clear();
        this.receipts = [];
        this.through = 0;
        this.blocked.clear();
    }

    /** 因为隐藏窗口不应悄悄消费演出，需要把当前动作退回队首并恢复逻辑位置。 */
    clear() {
        // 1、原始 Run、通知和持久消费游标均不改变。
        if (this.active) {
            this.motion.returnVisual(this.active.item.member_id, this.navigator);
            this.queue.unshift(this.active.item);
            this.active = null;
        }
        this.hints.clear();
        this.participants.clear();
    }

    /** 因为人工拖动优先于自动表演，需要消费当前冲突动作并短暂让出该人物。 */
    engage(identifier, now) {
        // 1、用户只接管画面，不取消或重发后台任务。
        this.blocked.set(identifier, now + 30000);
        if (this.active && [this.active.item.member_id, this.active.item.target_member_id].includes(identifier))
            this.finish("skipped", "manual");
    }

    /** 因为特定动作完成后必须有回执，需要保留可幂等提交的结果而不直接写数据库。 */
    finish(result = "played", reason = "") {
        // 1、完成仅意味着动画消费完毕，不代表实际工具成功。
        const item = this.active?.item;
        if (!item) return;
        this.receipts.push({id: item.id, result, reason});
        this.through = Math.max(this.through, item.source_seq);
        this.seen.delete(item.id);
        this.active = null;
        this.hints.clear();
        this.participants.clear();
    }

    /** 因为已提交的回执不能在每次轮询重复发送，需要由控制层明确确认本地缓存。 */
    confirm(identifier) {
        // 1、网络失败不调用此方法，下次刷新继续提交，不影响后续真实执行。
        this.receipts = this.receipts.filter(crewPerformanceOtherReceipt, identifier);
    }

    /** 因为递文件和查档案都需走到实体旁，需要只从合法空格挑选可达站位。 */
    destination(item, scene) {
        // 1、目标人员和设施都来自当前会议室，不跨空间找替身。
        let focus;
        if (item.kind === "handoff") focus = this.motion.actors.get(item.target_member_id)?.position;
        else {
            const type = item.kind === "archive" ? "archive" : "security";
            const object = scene.room.objects.find(crewPerformanceObject, type);
            if (object) focus = [object.x + (object.footprint?.[0] || 1) / 2, object.y + (object.footprint?.[1] || 1) / 2];
        }
        if (!focus) return {error: "missing_target"};
        const actor = this.motion.actors.get(item.member_id), occupied = new Set();
        for (const [id, other] of this.motion.actors)
            if (id !== item.member_id) occupied.add(other.groundCell.join(","));
        // 2、靠近目标时保留社交距离，先近后远；无路时明确跳过，不能直线穿家具。
        for (let radius = 1; radius <= 3; radius++)
            for (const [dx, dy] of [[0, radius], [radius, 0], [-radius, 0], [0, -radius]]) {
                const point = [Math.floor(focus[0]) + dx, Math.floor(focus[1]) + dy];
                if (!this.navigator.free(point) || occupied.has(point.join(","))) continue;
                const route = this.navigator.route(actor.groundCell, point);
                if (!route.length) continue;
                return {route, anchor: {id: "performance:" + item.id, approach: point,
                    position: crewCellCenter(point), posture: "standing", purpose: "performance",
                    direction: crewDirection([focus[0] - point[0] - 0.5, focus[1] - point[1] - 0.5])}};
            }
        return {error: "unreachable"};
    }

    /** 因为画面允许滞后于任务，需要逐项完成前往、互动和返回，再消费下一个事件。 */
    tick(scene, views, facts, healthy, now, dt, reduced = false) {
        // 1、断线和人工问题暂停消费，待命导演不会抢走正在表演的参与者。
        this.hints.clear();
        this.participants.clear();
        if (!healthy || !scene) return;
        if (!this.active && this.queue.length) {
            const item = this.queue[0];
            if ((this.blocked.get(item.member_id) || 0) > now) return;
            this.active = {item: this.queue.shift(), stage: "prepare", elapsed: 0, age: 0};
        }
        const current = this.active;
        if (!current) return;
        const item = current.item, actor = this.motion.actors.get(item.member_id);
        if (!actor || !views.has(item.member_id)) { this.finish("skipped", "missing_actor"); return; }
        if (reduced) { this.finish("skipped", "reduced_motion"); return; }
        if (current.revision != null && (current.revision !== this.navigator.revision || current.generation !== actor.generation)) {
            this.finish("skipped", "layout_changed"); return;
        }
        this.participants.add(item.member_id);
        if (item.target_member_id) this.participants.add(item.target_member_id);
        if (facts.get(item.member_id)?.requires_input || facts.get(item.target_member_id)?.requires_input) return;
        current.age += Math.min(0.05, Math.max(0, dt));
        if (current.age > 60) { this.motion.returnVisual(item.member_id, this.navigator); this.finish("skipped", "unreachable"); return; }
        // 2、MCP 原地通话；委派、查档和未来安全审核才产生快速的场景移动。
        if (current.stage === "prepare") {
            if (actor.phase !== "settled") return;
            if (item.kind === "handoff") {
                const recipient = this.motion.actors.get(item.target_member_id);
                if (!recipient) { this.finish("skipped", "missing_target"); return; }
                if (recipient.visualKind === "leisure") this.motion.returnVisual(item.target_member_id, this.navigator);
                if (recipient.phase !== "settled") return;
            }
            current.revision = this.navigator.revision;
            current.generation = actor.generation;
            if (item.kind === "mcp") current.stage = "perform";
            else {
                const destination = this.destination(item, scene);
                if (destination.error) { this.finish("skipped", destination.error); return; }
                if (!this.motion.visualMove(item.member_id, destination.route, destination.anchor, "performance")) return;
                current.stage = "travel";
            }
        }
        if (current.stage === "travel" && actor.phase === "settled") current.stage = "perform";
        if (current.stage === "perform") {
            const action = {mcp: "phone", archive: "read", handoff: "talk", security: "talk"}[item.kind];
            const category = {mcp: "mcp", archive: "archive", handoff: "delegation", security: "security"}[item.kind];
            const target = views.get(item.target_member_id)?.member.name || "成员";
            const caption = {mcp: "联系外部服务 · 打电话", archive: "档案库 · 翻查历史", handoff: `递交文件 · 给${target}派任务`, security: "安全服务台 · 请求审核"}[item.kind];
            const override = views.get(item.member_id).member.interaction_profile?.action_overrides?.[category];
            const count = item.aggregation?.count || 1;
            this.hints.set(item.member_id, {kind: "performance", performance_kind: item.kind, category,
                action: override || action, aggregation_count: count,
                caption: "动作演示 · " + caption + (count > 1 ? ` · 60秒内${count}次调用合并` : ""),
                direction: item.kind === "mcp" ? "se" : actor.target.direction});
            if (item.kind === "handoff" && views.has(item.target_member_id))
                this.hints.set(item.target_member_id, {kind: "performance", performance_kind: "receive", action: "listen",
                    caption: "接收派发文件 · 动作演示", direction: crewDirection([actor.position[0] - this.motion.actors.get(item.target_member_id).position[0], actor.position[1] - this.motion.actors.get(item.target_member_id).position[1]])});
            current.elapsed += Math.min(0.05, Math.max(0, dt));
            if (current.elapsed >= 2.4) {
                if (actor.visualKind === "performance") {
                    this.motion.returnVisual(item.member_id, this.navigator);
                    current.stage = "return";
                } else this.finish();
            }
        }
        // 3、返回工位完成后再启动下一项；即便对应 Run 已结束也可继续消费，不伪造新执行。
        if (current.stage === "return" && actor.phase === "settled" && actor.visualKind !== "return") this.finish();
    }
}

/** 因为桌面协议要兼容旧单条动作，需要只接纳有版本、单调序号和有效计数的聚合摘要。 */
function crewPerformanceAggregation(action) {
    // 1、聚合只作用于 MCP 与查档，不能把委派或安全请求悄悄合并。
    const value = action.aggregation;
    if (!value || value.version !== 1 || !Number.isSafeInteger(value.count) || value.count < 1 ||
        value.first_seq !== action.source_seq || !Number.isSafeInteger(value.last_seq) ||
        value.last_seq < value.first_seq || value.count > value.last_seq - value.first_seq + 1 ||
        ![0, 60000].includes(value.window_ms) ||
        (value.count > 1 && !["mcp", "archive"].includes(action.kind))) return null;
    return {...value};
}

/** 因为新快照只更新同一代表项，需要按稳定 ID 找到仍在队列中的对应对象。 */
function crewPerformanceIdMatches(item) {
    // 1、不按人物名称、共享 Agent 定义或事件正文匹配。
    return item.id === String(this);
}

/** 因为不同 Run 的委派也要有稳定演示顺序，需要只按来源序号排序。 */
function crewPerformanceSequence(a, b) {
    // 1、序号来自当前工作空间的正式事件日志。
    return a.source_seq - b.source_seq;
}
/** 因为回执需要幂等重试，需要只移除已经成功提交的那一条。 */
function crewPerformanceOtherReceipt(receipt) {
    // 1、其他尚未提交的回执继续保留。
    return receipt.id !== String(this);
}
/** 因为设施可以自定义名称，需要按固定类型而非名称查找档案库或安全服务台。 */
function crewPerformanceObject(object) {
    // 1、目标不会成为任意脚本或后端权限。
    return object.type === String(this);
}
