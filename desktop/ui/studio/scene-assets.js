/* 统一素材解析、方向关键帧与接触校准；不导入 Agent 类型。 */
"use strict";

/** 因为家具不能再按名字散落映射，需要从统一目录解析八方向的真实视图。 */
function crewSceneMaterial(type, direction = null) {
    // 1、只有随应用发布的素材目录可提供图片路径，方向不变成任意 URL。
    const catalog = window.ROOMCREW_SCENE_ASSETS;
    const definition = catalog?.definitions[type], material = catalog?.materials[type];
    if (!definition || !material) return null;
    const selected = direction || definition.default_direction;
    const view = material.views[selected];
    if (!view) return null;
    return { ...material, image: view.image || material.image,
        atlas_size: view.atlas_size || material.atlas_size,
        height: view.display_height || material.height,
        id: type, direction: selected, definition, view, frames: [view.rect] };
}

/** 因为每种家具的透视面和接触点不同，需要按素材元数据确定等比绘制位置，不能旋转平面图片。 */
function crewScenePicture(parent, material, ground, seat = null) {
    // 1、固定世界高度只产生等比缩放；臀部接触点与落地线使用同一份注册。
    const height = material.height, rect = material.frames[0];
    const width = height * rect[2] / rect[3];
    let left = ground[0] - width * material.view.ground[0];
    let top = ground[1] - height * material.view.ground[1];
    if (seat && material.view.seat) {
        left = seat[0] - width * material.view.seat[0];
        top = seat[1] - height * material.view.seat[1];
    }
    return crewEnvironmentPicture(parent, material, left, top, width);
}

/** 因为每个角色有不同身形，需要在已知内容 ID 上附加已登记臀部/脚底的八向坐姿，不改用户源文件。 */
function crewSceneCharacterSupplement(asset, sources, sizes) {
    // 1、仅替换显示补充页，旧文件、ID、帧号和两页用户导入合同保持不变。
    const entry = window.ROOMCREW_SCENE_ASSETS?.characters[asset.id];
    if (!entry || asset.manifest.version !== 3) return false;
    const manifest = structuredClone(asset.manifest), start = manifest.frame_rects.length;
    const page = sources.length;
    sources.push(entry.image);
    sizes.push(entry.size);
    manifest.frame_rects.push(...entry.frames.map(crewContactFrame, page));
    // 2、关键帧提供完整方向与接触，缺少手部逐帧动作时复用兼容坐姿，不能复用浮空旧坐姿。
    manifest.clips = manifest.clips.filter(crewStandingClip);
    for (let index = 0; index < entry.frames.length; index++)
        for (const action of Object.keys(CREW_CLIPS))
            if (!["walk", "run", "sit_down", "stand_up"].includes(action))
                manifest.clips.push({ action, direction: entry.frames[index].direction, posture: "seated", expression: "neutral", frames: [start + index], fps: 1, loop: true });
    asset.display_manifest = manifest;
    asset.contact_ready = true;
    asset.display_registration = structuredClone(asset.registration || { frames: [] });
    if (asset.display_registration.frames.length !== start) asset.display_registration.frames = [...asset.manifest.frame_rects];
    asset.display_registration.frames.push(...entry.frames);
    // 3、伸手打字有独立姿态；工作帧与待命帧共用头部尺度，不用膝上坐姿冒充操作电脑。
    if (entry.paired) {
        const work = entry.paired, workStart = manifest.frame_rects.length, workPage = sources.length;
        sources.push(work.image);
        sizes.push(work.size);
        manifest.frame_rects.push(...work.frames.map(crewContactFrame, workPage));
        asset.display_registration.frames.push(...work.frames);
        manifest.interaction_clips = [];
        for (const [direction, poses] of Object.entries(work.directions))
            for (const action of Object.keys(CREW_CLIPS)) {
                if (["walk", "run", "sit_down", "stand_up"].includes(action)) continue;
                const working = ["work", "type", "game", "read", "write"].includes(action);
                const indices = (working && poses.work) || poses.idle;
                manifest.interaction_clips.push({action,direction,posture:"seated",expression:"neutral",
                    frames:indices.map(crewWorkFrameIndex,workStart),fps:working?2:1,loop:true,
                    mirror:poses.mirror===true,includes_seat:true});
            }
        // 4、起坐使用完整配套姿势，椅脚原点固定；不能把坐姿直接替换成站姿冒充连续过程。
        const rise = entry.transition, riseStart=manifest.frame_rects.length, risePage=sources.length;
        sources.push(rise.image);sizes.push(rise.size);
        manifest.frame_rects.push(...rise.frames.map(crewContactFrame,risePage));
        asset.display_registration.frames.push(...rise.frames);
        for(const direction of ["nw","ne"])
            for(const action of ["stand_up","sit_down"])
                manifest.interaction_clips.push({action,direction,posture:"seated",expression:"neutral",
                    frames:rise.frames.map(crewTransitionFrameIndex,riseStart),fps:6,loop:false,
                    includes_seat:true,mirror:direction==="ne",transition:true});
    }
    return true;
}

/** 因为起坐原图可能有不同帧数，需要将每帧局部索引转入显示副本。 */
function crewTransitionFrameIndex(_frame, index) {
    // 1、按登记的完整过渡帧数装配，不把四帧假定写死到播放器。
    return Number(this) + index;
}

/** 因为工作片段共享一个内部显示页，需要把局部帧号转换为显示清单索引。 */
function crewWorkFrameIndex(index) {
    // 1、不改变原用户素材的持久化帧号。
    return Number(this) + index;
}

/** 因为页号由播放器装配时决定，需要复制源帧并附加本次显示页索引。 */
function crewContactFrame(frame) {
    // 1、保留源像素坐标与明确的接触标记。
    return { ...frame, page: Number(this) };
}

/** 因为旧坐姿没有可靠接触点，需要保留站姿动作并使用新版坐姿关键帧。 */
function crewStandingClip(clip) {
    // 1、这只修改显示副本，用户原清单不受影响。
    return clip.posture !== "seated";
}

/** 因为坐姿不该统一抬高，需要按当前方向的臀部高度匹配座面，脚底仍落在地面或明确脚踏上。 */
function crewSeatContact(asset, actor, sample) {
    // 1、在格心运动之外只求解局部接触，不改变任务、路线或人物逻辑位置。
    const manifest = asset?.display_manifest || asset?.manifest;
    const empty = { elevation: 0, offsetX:0, support: 0, pad: 0, soleX: 0, soleY:0, hipError: null, verified: false };
    if (!manifest) return empty;
    const clip = crewSelectClip(manifest, { ...sample, posture: "seated" });
    if (clip?.includes_seat) return {...empty,verified:true,composite:true,hipError:null};
    if(!sample.seatMix || sample.posture !== "seated") return empty;
    const frame = clip?.frames[Math.min(clip.frames.length - 1, Math.floor((sample.time || 0) * clip.fps) % clip.frames.length)];
    let contact = (asset.display_registration || asset.registration)?.frames[frame]?.contact || manifest.frame_rects[frame]?.contact;
    if (!contact) return empty;
    if (!Number.isFinite(contact.seat_height)) {
        // 2、自制图集未做头部归一时，接触标记直接从虚拟帧换算为世界单位。
        const unit = manifest.display_height / manifest.frame_size[1];
        contact = { hip: [(contact.hip[0] - manifest.pivot[0]) * unit, (contact.hip[1] - manifest.pivot[1]) * unit], soles: [(contact.soles[0] - manifest.pivot[0]) * unit, (contact.soles[1] - manifest.pivot[1]) * unit], seat_height: (contact.soles[1] - contact.hip[1]) * unit };
    }
    const attached = crewAttachedSeat(actor);
    const seat = attached?.contact?.seat_height || 22;
    // 3、臀部对应椅面，鞋底落在其向前伸出的地面点；透视纵向差不能误当成悬空高度并塞入脚踏。
    const elevation = (seat + contact.hip[1]) * sample.seatMix;
    const offsetX = -contact.hip[0] * sample.seatMix;
    return { elevation, offsetX, support:0, pad:0,
        soleX:contact.soles[0]+offsetX, soleY:contact.soles[1]-elevation,
        hipError:Math.abs(contact.hip[1]-elevation+seat), verified:true,
        poseSeat:contact.seat_height, targetSeat:seat };
}
