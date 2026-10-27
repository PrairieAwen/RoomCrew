/* 气泡只选择相对人物的位置，不钉在屏幕边缘。 */
"use strict";

/** 因为泡泡应与实际素材同步移动，需要只在人物头部附近选择相对位置而不夹紧屏幕坐标。 */
function crewBubbleLayout(anchor, viewport) {
    // 1、候选位置全部锚定同一个头部，无法完全放入视口时也不把泡泡移到无关位置。
    const width = 224,
        height = 70,
        gap = 16;
    const positions = [
        { left: anchor.x - width / 2, top: anchor.y - height - gap },
        { left: anchor.x + 24, top: anchor.y - height / 2 },
        { left: anchor.x - width - 24, top: anchor.y - height / 2 },
        { left: anchor.x + 24, top: anchor.y + gap },
        { left: anchor.x - width - 24, top: anchor.y + gap },
    ];
    let selected = positions[0],
        best = Infinity;
    for (const position of positions) {
        let score =
            Math.max(0, viewport.left - position.left) +
            Math.max(0, position.left + width - viewport.right) +
            Math.max(0, viewport.top - position.top) +
            Math.max(0, position.top + height - viewport.bottom);
        for (const obstacle of viewport.obstacles || [])
            if (crewBubbleIntersects({ ...position, width, height }, obstacle))
                score += width;
        if (score < best) {
            selected = position;
            best = score;
        }
    }
    // 2、尾线始终连接实际素材锚点，平移或缩放不会改为另一个人物的坐标。
    const { left, top } = selected;
    const tailX = Math.max(left + 12, Math.min(anchor.x, left + width - 12));
    const tailY =
        anchor.y >= top + height
            ? top + height - 4
            : anchor.y < top
              ? top + 4
              : Math.max(top + 10, Math.min(anchor.y, top + height - 10));
    return { left, top, width, height, tailX, tailY };
}

/** 因为场景按钮可能接近人物，需要给相对位置选择提供轻量遮挡判断。 */
function crewBubbleIntersects(rect, region) {
    // 1、仅用于比较人物附近候选位置，不能把气泡固定到按钮边缘。
    return (
        rect.left < region.right + 8 &&
        rect.left + rect.width > region.left - 8 &&
        rect.top < region.bottom + 8 &&
        rect.top + rect.height > region.top - 8
    );
}
