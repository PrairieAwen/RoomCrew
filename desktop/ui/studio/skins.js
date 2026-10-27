/* 注册图集缓存与动作变体选择；帧循环只读已加载数据。 */
"use strict";

class CrewSkins {
    /** 因为图片加载不能进入帧回调，需要注入独立的按需资源读取函数。 */
    constructor(loader) {
        // 1、缓存有界，失败素材使用内置骨架，不反复请求或执行外部代码。
        this.loader = loader;
        this.cache = new Map();
        this.pending = new Map();
        this.errors = new Set();
        this.active = new Set();
    }

    /** 因为场景更新可能多次出现同一素材，需要合并请求并限制同时保留的图集数量。 */
    ensure(identifier) {
        // 1、内置角色不需要网络或桥接，只有已注册 hash ID 才能请求图片。
        if (
            !identifier?.startsWith("avatar:") ||
            this.cache.has(identifier) ||
            this.pending.has(identifier) ||
            this.errors.has(identifier)
        )
            return;
        this.pending.set(identifier, this.load(identifier));
    }

    /** 因为损坏或加载失败不应阻止界面，需要读取和解码后再原子发布缓存。 */
    async load(identifier) {
        // 1、图片来源必须为后端规范化后的 PNG data URL。
        try {
            const value = await this.loader(identifier);
            const version = value.manifest?.version;
            const sources =
                version === 3 ? value.image_pages : [value.image_data];
            const sizes =
                version === 3
                    ? value.manifest.atlas_sizes
                    : [value.manifest?.atlas_size];
            if (
                value.id !== identifier ||
                value.manifest?.format !== "roomcrew.avatar" ||
                ![1, 2, 3].includes(version) ||
                !Array.isArray(sources) ||
                !Array.isArray(sizes) ||
                sources.length < 1 ||
                sources.length > 2 ||
                sources.length !== sizes.length
            )
                throw new Error("素材合同不兼容");
            value.decoded_pages = [];
            for (let index = 0; index < sources.length; index++) {
                if (
                    typeof sources[index] !== "string" ||
                    !sources[index].startsWith("data:image/png;base64,")
                )
                    throw new Error("素材图片来源无效");
                const image = new Image();
                image.src = sources[index];
                await image.decode();
                if (
                    image.naturalWidth !== sizes[index][0] ||
                    image.naturalHeight !== sizes[index][1]
                )
                    throw new Error("图集尺寸不一致");
                value.decoded_pages.push(image);
            }
            value.image_sources = sources;
            value.page_sizes = sizes;
            if (this.cache.size >= 9)
                for (const id of this.cache.keys()) {
                    if (!this.active.has(id)) {
                        this.cache.delete(id);
                        break;
                    }
                }
            if (this.cache.size >= 9) throw new Error("当前活动图集达到上限");
            this.cache.set(identifier, value);
        } catch (error) {
            this.errors.add(identifier);
        } finally {
            this.pending.delete(identifier);
        }
    }

    /** 因为图集只读部分状态时也要自然回退，需要按动作、姿态、表情及最近朝向选择变体。 */
    render(view, identifier, sample) {
        // 1、坐姿不能拿站立图集冒充，缺失整个姿态时回退到内置骨架。
        const asset = this.cache.get(identifier);
        if (!asset) {
            view.sprite?.remove();
            view.sprite = null;
            view.spriteFrame = null;
            return false;
        }
        const clip = crewSelectClip(asset.manifest, sample);
        if (!clip) {
            view.sprite?.remove();
            view.sprite = null;
            view.spriteFrame = null;
            return false;
        }
        if (!view.sprite || view.spriteId !== identifier) {
            view.sprite?.remove();
            const manifest = asset.manifest,
                scale = manifest.display_height / manifest.frame_size[1];
            const outer = crewSvg("svg", {
                x: -manifest.pivot[0] * scale,
                y: -manifest.pivot[1] * scale,
                width: manifest.frame_size[0] * scale,
                height: manifest.frame_size[1] * scale,
                overflow: "visible",
                class: manifest.pixel_art ? "sprite-pixel" : "sprite-smooth",
            });
            const images = [];
            for (let page = 0; page < asset.image_sources.length; page++)
                images.push(
                    crewSvg("image", {
                        width: asset.page_sizes[page][0],
                        height: asset.page_sizes[page][1],
                        href: asset.image_sources[page],
                        visibility: page === 0 ? "visible" : "hidden",
                    }),
                );
            view.spriteImages = images;
            view.spritePage = -1;
            if (manifest.version >= 2) {
                const crop = crewSvg("svg", { overflow: "hidden" });
                crop.append(...images);
                outer.append(crop);
                outer.setAttribute(
                    "viewBox",
                    `0 0 ${manifest.frame_size[0]} ${manifest.frame_size[1]}`,
                );
                view.spriteFrame = crop;
            } else {
                view.spriteFrame = null;
                outer.append(images[0]);
            }
            view.group.insertBefore(outer, view.badge);
            view.sprite = outer;
            view.spriteId = identifier;
        }
        // 2、只改变裁切矩形，禁止每帧重新加载或写入图片 URL。
        const [fw, fh] = asset.manifest.frame_size,
            columns = (asset.manifest.atlas_size?.[0] || 0) / fw;
        const index = sample.reduced ? 0 : Math.floor(sample.time * clip.fps);
        const frame =
            clip.frames[
                clip.loop
                    ? index % clip.frames.length
                    : Math.min(index, clip.frames.length - 1)
            ];
        if (asset.manifest.version >= 2) {
            const item = asset.manifest.frame_rects[frame],
                [x, y, width, height] = item.rect;
            const registration =
                view.member?.material_profile?.normalize !== false
                    ? asset.registration?.frames[frame]
                    : null;
            const offset = registration?.offset || item.offset;
            const scale = registration?.scale ?? item.scale ?? 1;
            const page = item.page || 0;
            if (view.spritePage !== page) {
                for (let index = 0; index < view.spriteImages.length; index++)
                    view.spriteImages[index].setAttribute(
                        "visibility",
                        index === page ? "visible" : "hidden",
                    );
                view.spritePage = page;
            }
            view.sprite.dataset.page = String(page);
            view.spriteFrame.setAttribute("x", offset[0]);
            view.spriteFrame.setAttribute("y", offset[1]);
            view.spriteFrame.setAttribute("width", width * scale);
            view.spriteFrame.setAttribute("height", height * scale);
            view.spriteFrame.setAttribute(
                "viewBox",
                `${x} ${y} ${width} ${height}`,
            );
        } else
            view.sprite.setAttribute(
                "viewBox",
                `${(frame % columns) * fw} ${Math.floor(frame / columns) * fh} ${fw} ${fh}`,
            );
        const mirrored =
            !sample.material_binding?.clip &&
            asset.manifest.mirror_west === true &&
            ["w", "nw", "sw"].includes(sample.direction);
        view.sprite.setAttribute(
            "transform",
            mirrored ? "scale(-1 1)" : "scale(1 1)",
        );
        view.sprite.dataset.mirrored = String(mirrored);
        view.sprite.dataset.frame = frame;
        view.sprite.dataset.variant = `${clip.action}.${clip.direction}.${clip.posture}.${clip.expression}`;
        return true;
    }
}

/** 因为自制素材不一定覆盖所有变体，需要只选择兼容姿态并明确按优先级回退。 */
function crewSelectClip(manifest, sample) {
    // 1、人物显式选择的帧序列优先；帧引用由桌面配置入口校验，预览与正式场景共用。
    if (sample.material_binding?.clip) {
        const selected = manifest.clips.find(
            crewClipKeyMatches,
            sample.material_binding.clip,
        );
        if (selected) return { ...selected, ...sample.material_binding };
    }
    // 2、自动选帧匹配实际动作；摸鱼缺帧回退内置，工作缺帧回退同姿态 idle。
    const posture = sample.posture;
    let matches = manifest.clips.filter(crewClipPosture, posture);
    const exact = matches.filter(crewClipAction, sample.action);
    matches = exact.length ? exact : matches.filter(crewClipAction, "idle");
    if (!matches.length)
        matches = manifest.clips.filter(crewClipAction, "idle");
    // 3、表情优先于近邻朝向，中性是合法回退；有限数组比较不加载额外资源。
    let selected = null,
        best = Infinity;
    for (const clip of matches) {
        const wanted = CREW_DIRECTIONS.indexOf(
                crewAtlasDirection(manifest, sample.direction),
            ),
            actual = CREW_DIRECTIONS.indexOf(clip.direction);
        const delta = Math.abs(wanted - actual),
            distance = Math.min(delta, 8 - delta);
        const score =
            (clip.expression === sample.expression
                ? 0
                : clip.expression === "neutral"
                  ? 10
                  : 20) + distance;
        if (score < best) {
            best = score;
            selected = clip;
        }
    }
    return selected;
}

/** 因为美术可以明确授权西向镜像，需要先映射到实际制作的朝向以保留真正的侧背面。 */
function crewAtlasDirection(manifest, direction) {
    // 1、默认不镜像；只有显式布尔开关才复用另一侧的手绘帧。
    if (manifest.mirror_west !== true) return direction;
    return { w: "e", nw: "ne", sw: "se" }[direction] || direction;
}
/** 因为姿态兼容是安全回退条件，需要用具名谓词筛选图集变体。 */
function crewClipPosture(clip) {
    // 1、坐姿和站姿不能相互代用。
    return clip.posture === String(this);
}
/** 因为动作名不允许自由文本推断，需要按注册的固定词表精确匹配。 */
function crewClipAction(clip) {
    // 1、缺失动作的回退由选择器统一处理。
    return clip.action === String(this);
}

/** 因为素材变体需要可保存的稳定引用，需要使用与桌面校验一致的组合键。 */
function crewClipKey(clip) {
    // 1、组成字段来自已验证素材词表。
    return [clip.action, clip.direction, clip.posture, clip.expression].join(
        ".",
    );
}
/** 因为清单查找不能依赖数组位置，需要精确比较稳定变体键。 */
function crewClipKeyMatches(clip) {
    // 1、thisArg 是当前编辑器选择的键。
    return crewClipKey(clip) === String(this);
}
