/* 人物局部空间中的稳定挂点，不读取屏幕边界或逐帧裁切框。 */
"use strict";
const CREW_BUBBLE_SOCKET_CACHE = new WeakMap();

/** 因为人物移动和镜头变化应由同一个父变换带动，需要只计算角色局部挂点。 */
function crewBubbleAnchor(manifest, seatMix = 0, registration = null) {
    // 1、起坐使用连续姿态插值；行走帧和相机信息不能改变局部挂点。
    const seat = Math.max(0, Math.min(1, seatMix));
    if (!manifest) return { x: 0, y: -116 + seat * 13 };
    if (registration?.sockets)
        return {
            x: 0,
            y:
                registration.sockets.standing +
                (registration.sockets.seated - registration.sockets.standing) *
                    seat,
        };
    let sockets = CREW_BUBBLE_SOCKET_CACHE.get(manifest);
    if (!sockets) {
        sockets = crewAtlasBubbleSockets(manifest);
        CREW_BUBBLE_SOCKET_CACHE.set(manifest, sockets);
    }
    return {
        x: 0,
        y: sockets.standing + (sockets.seated - sockets.standing) * seat,
    };
}

/** 因为图集各帧裁切留白不同，需要按整套姿态生成一次稳定挂点而不是追逐每帧边界。 */
function crewAtlasBubbleSockets(manifest) {
    // 1、先使用统一虚拟画布与脚底锚点，缺失姿态沿用画布挂点。
    const scale = manifest.display_height / manifest.frame_size[1];
    const result = {
        standing: -manifest.pivot[1] * scale,
        seated: -manifest.pivot[1] * scale,
    };
    // 2、裁切素材按整套姿态最上沿定位，切帧、转向和道具变化不改变挂点。
    if (manifest.frame_rects)
        for (const posture of ["standing", "seated"]) {
            let top = Infinity;
            for (const clip of manifest.clips)
                if (clip.posture === posture)
                    for (const frame of clip.frames)
                        top = Math.min(
                            top,
                            manifest.frame_rects[frame].offset[1],
                        );
            if (Number.isFinite(top))
                result[posture] = (top - manifest.pivot[1]) * scale;
        }
    return result;
}
