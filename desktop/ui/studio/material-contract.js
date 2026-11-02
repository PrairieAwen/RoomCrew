/* 显示层统一素材语义、兼容校准与覆盖报告，不包含 Agent 配置。 */
"use strict";

const CREW_MATERIAL_CONTRACT = Object.freeze({
    version: 1,
    required: ["idle"],
    recommended: ["walk", "work", "phone", "read", "talk", "ask", "report", "sit_down", "stand_up"],
    humanoid: Object.freeze({id: "paired-standing-v1", runRatio: 0.91}),
});

/** 因为兼容图集不是同一骨架导出，需要按完整动作片段校准体量，禁止在播放时逐帧缩放。 */
function crewCalibrateStanding(asset) {
    // 1、只对已登记的四套人类内容生效；自定义形象和短体型吉祥物不强套人类身高。
    const entry = window.ROOMCREW_MATERIAL_LIBRARY?.characters.find(crewRegisteredCharacter, asset.id);
    if (!entry || entry.id === "hippo" || !asset.display_registration) return;
    const manifest = asset.manifest, frames = asset.display_registration.frames;
    const unit = manifest.display_height / manifest.frame_size[1];
    const idle = manifest.clips.filter(crewStandingNeutralIdle);
    const idleHeights = idle.flatMap(crewClipHeights, {manifest, frames, unit});
    if (!idleHeights.length) return;
    const profile = CREW_MATERIAL_CONTRACT.humanoid;
    const reference = crewStandingReference(window.ROOMCREW_SCENE_ASSETS.characters[asset.id], manifest);
    if (!reference) return;
    const base = reference / crewMaterialMedian(idleHeights);
    const factors = new Map();
    // 2、站立待命、行走与跑步各片段只有一个比例；保留片段内的步态起伏和原有腾空。
    for (const clip of manifest.clips) {
        if (clip.posture !== "standing" || clip.expression !== "neutral" ||
            !["idle", "walk", "run"].includes(clip.action)) continue;
        const heights = crewClipHeights.call({manifest, frames, unit}, clip);
        const target = clip.action === "run" ? reference * profile.runRatio : reference;
        const factor = target / crewMaterialMedian(heights);
        for (const index of clip.frames) factors.set(index, factor);
    }
    const standing = new Set(manifest.clips.filter(crewStandingClip).flatMap(crewClipFrames));
    for (const index of standing) {
        const frame = frames[index], rect = manifest.frame_rects[index];
        const factor = factors.get(index) ?? base, pivot = manifest.pivot;
        const flight = Math.max(0, pivot[1] - frame.offset[1] - rect.rect[3] * frame.scale);
        frame.offset = [pivot[0] - (pivot[0] - frame.offset[0]) * factor,
            pivot[1] - rect.rect[3] * frame.scale * factor - flight];
        frame.scale *= factor;
        frame.head_width *= factor;
    }
    // 3、头顶提示也使用这份静态校准；不在每帧追踪裁切框。
    asset.display_registration.sockets ||= {};
    asset.display_registration.sockets.standing = crewMaterialMedian(
        [...standing].map(crewFrameTop, {frames, pivot: manifest.pivot, unit}));
    asset.display_registration.profile = profile.id;
    asset.display_registration.standing_height = reference;
}

/** 因为独立行走与配套椅起身必须接上，需要以起身末帧的真实鞋底到头顶距离作为本角色基准。 */
function crewStandingReference(entry, manifest) {
    // 1、椅脚与鞋底分别登记，不能把椅轮的投影深度算成人物腿长。
    const transition = entry.transition, frame = transition?.frames.at(-1);
    if (!frame || !transition.standing_foot) return null;
    const top = (frame.offset[1] - manifest.pivot[1]) * manifest.display_height / manifest.frame_size[1];
    const height = transition.standing_foot[1] - top;
    return Number.isFinite(height) && height > 32 && height < 160 ? height : null;
}

/** 因为同名形象可以被用户重新绘制，需要按不可变内容 ID 匹配官方兼容校准。 */
function crewRegisteredCharacter(entry) {
    // 1、名称和路径都不构成受信身份。
    return entry.registered_id === String(this);
}

/** 因为表情会带来抬手和弯腰，需要仅用自然站立作为体量基准。 */
function crewStandingNeutralIdle(clip) {
    // 1、不用坐姿或椅子的包围框作为人物身高。
    return clip.action === "idle" && clip.posture === "standing" && clip.expression === "neutral";
}

/** 因为片段需要同一比例，需要读取整段已注册的显示高度而非逐帧自适应。 */
function crewClipHeights(clip) {
    // 1、只测量原始人体片段，固定配套椅补页不参与身高拟合。
    const values = [];
    for (const index of clip.frames) values.push(this.manifest.frame_rects[index].rect[3] * this.frames[index].scale * this.unit);
    return values;
}

/** 因为姿态校准需收集真实引用，需要保留帧号而不重新排列用户清单。 */
function crewClipFrames(clip) {
    // 1、调用方用集合去重。
    return clip.frames;
}

/** 因为提示挂点应稳定，需要在加载时计算同姿态的头顶中位值。 */
function crewFrameTop(index) {
    // 1、结果是人物局部世界坐标，不回算屏幕坐标。
    return (this.frames[index].offset[1] - this.pivot[1]) * this.unit;
}

/** 因为偶发边缘或道具不能主导尺度，需要使用不改变原数组的中位数。 */
function crewMaterialMedian(values) {
    // 1、空集合由调用方拒绝，偶数集合取中心两项的平均值。
    const sorted = [...values].sort(crewMaterialNumberOrder), middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/** 因为数值排序不能采用字符串顺序，需要显式比较尺度值。 */
function crewMaterialNumberOrder(left, right) {
    // 1、不修改任何素材对象。
    return left - right;
}

/** 因为可播放不等于全动作齐备，需要统一报告实际片段和缺失能力，不伪造完整动画。 */
function crewMaterialCoverage(asset) {
    // 1、合并正式播放器可见的片段，但逐项区分单帧关键姿势与多帧动画。
    const manifest = asset.display_manifest || asset.manifest;
    const clips = [...manifest.clips, ...(manifest.interaction_clips || []), ...(manifest.call_clips || [])];
    const lines = [];
    for (const action of [...CREW_MATERIAL_CONTRACT.required, ...CREW_MATERIAL_CONTRACT.recommended]) {
        const available = clips.filter(crewCoverageAction, action);
        const animated = available.some(crewAnimatedClip);
        const directions = new Set(available.map(crewClipDirection));
        lines.push(`${CREW_ACTION_LABELS[action]}：${available.length ? `${directions.size} 个方向 · ${animated ? "含多帧片段" : "关键帧"}` : "缺失，按播放器规则回退"}`);
    }
    // 2、估算和兼容预览不宣称美术或接触完整验收。
    return "动作合同 v1 · 兼容预览，非完整美术验收\n" + lines.join("\n");
}

/** 因为同一动作可有多个姿态和方向，需要按动作语义汇总覆盖。 */
function crewCoverageAction(clip) {
    // 1、不将缺失动作的回退计为原绘覆盖。
    return clip.action === String(this);
}

/** 因为复制同一帧不能算动画，需要至少存在两个不同帧号。 */
function crewAnimatedClip(clip) {
    // 1、仍只声明多帧片段，不等同于流畅逐帧动画。
    return new Set(clip.frames).size > 1;
}

/** 因为覆盖统计需要排除重复方向，需要提取明确登记的方向名。 */
function crewClipDirection(clip) {
    // 1、镜像方向仍由片段自己的声明标记。
    return clip.direction;
}
