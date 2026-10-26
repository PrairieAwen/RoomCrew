/* 全窗口工作空间相机；世界坐标与显示缩放相互独立。 */
"use strict";

class CrewCamera {
    /** 因为房间不应缩成浮岛，需要按实际视口填充场景并允许拖动查看局部。 */
    constructor(svg) {
        // 1、只绑定可见画布输入，不接触任务或数据库。
        this.svg = svg;
        this.center = [60, 225];
        this.zoom = 1;
        this.drag = null;
        this.onMoved = null;
        this.resizeObserver = new ResizeObserver(this.resize.bind(this));
        this.resizeObserver.observe(svg);
        svg.addEventListener("pointerdown", this.down.bind(this));
        svg.addEventListener("pointermove", this.move.bind(this));
        svg.addEventListener("pointerup", this.up.bind(this));
        svg.addEventListener("pointercancel", this.up.bind(this));
        svg.addEventListener("wheel", this.wheel.bind(this), {
            passive: false,
        });
        this.resize();
    }

    /** 因为窗口比例不同，需要按视口尺寸计算覆盖式投影而不露出画布外的背景。 */
    resize() {
        // 1、固定世界单位与客户端像素比例，默认只显示局部工作室。
        const box = this.svg.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const scale =
            Math.max(1.5, box.width / 1100, box.height / 650) * this.zoom;
        this.width = box.width / scale;
        this.height = box.height / scale;
        this.svg.setAttribute(
            "viewBox",
            `${this.center[0] - this.width / 2} ${this.center[1] - this.height / 2} ${this.width} ${this.height}`,
        );
        if (this.onView) this.onView(this);
    }

    /** 因为缩放应保持鼠标下的世界位置，需要围绕指针调整相机中心。 */
    change(factor, point = null) {
        // 1、有界缩放避免极小角色或无限放大，移动不改变布局格网。
        const previous = this.zoom;
        this.zoom = Math.max(0.8, Math.min(2.2, this.zoom * factor));
        if (point && previous !== this.zoom) {
            const ratio = previous / this.zoom;
            this.center[0] = point[0] + (this.center[0] - point[0]) * ratio;
            this.center[1] = point[1] + (this.center[1] - point[1]) * ratio;
        }
        this.clamp();
        this.resize();
    }

    /** 因为用户需要快速找到选中人物，需要只移动相机而不传送人物。 */
    focus(position) {
        // 1、留出人物头部和悬浮输入区，保持脚底坐标语义。
        const point = crewProject(position);
        this.center = [point[0], point[1] - 40];
        this.clamp();
        this.resize();
    }

    /** 因为相机不能无限离开会议室，需要限制中心位于工作空间的可浏览范围。 */
    clamp() {
        // 1、世界边缘外由连续地面覆盖，人物仍只在后端验证格网中移动。
        this.center[0] = Math.max(-340, Math.min(500, this.center[0]));
        this.center[1] = Math.max(120, Math.min(470, this.center[1]));
    }

    /** 因为人物和家具点击有独立含义，需要只在空地或中键开始平移。 */
    down(event) {
        // 1、避免拖动相机时意外下达人物换座命令。
        if (
            event.button !== 1 &&
            (event.button !== 0 ||
                event.target.closest(".crew-avatar,.room-object"))
        )
            return;
        this.drag = {
            x: event.clientX,
            y: event.clientY,
            center: [...this.center],
            moved: false,
        };
        this.svg.setPointerCapture(event.pointerId);
        this.svg.classList.add("panning");
    }

    /** 因为相机平移应保持真实世界尺度，需要将屏幕位移换算为当前 viewBox 位移。 */
    move(event) {
        // 1、局部拖动不写布局，不参与 Agent 状态或路径权限判断。
        if (!this.drag) return;
        const box = this.svg.getBoundingClientRect(),
            dx = event.clientX - this.drag.x,
            dy = event.clientY - this.drag.y;
        this.drag.moved = Math.hypot(dx, dy) > 4;
        this.center = [
            this.drag.center[0] - (dx / box.width) * this.width,
            this.drag.center[1] - (dy / box.height) * this.height,
        ];
        this.clamp();
        this.resize();
    }

    /** 因为指针可在画布外结束，需要结束拖动并恢复人物点击。 */
    up(event) {
        // 1、释放捕获仅影响输入，不取消已受理的任务。
        this.drag = null;
        this.svg.classList.remove("panning");
        if (this.svg.hasPointerCapture(event.pointerId))
            this.svg.releasePointerCapture(event.pointerId);
    }

    /** 因为用户习惯游戏地图滚轮缩放，需要以当前鼠标位置作为缩放锚点。 */
    wheel(event) {
        // 1、阻止页面滚动，位置换算不跨出本地 SVG。
        event.preventDefault();
        const box = this.svg.getBoundingClientRect();
        const point = [
            this.center[0] +
                ((event.clientX - box.left - box.width / 2) / box.width) *
                    this.width,
            this.center[1] +
                ((event.clientY - box.top - box.height / 2) / box.height) *
                    this.height,
        ];
        this.change(Math.exp(-event.deltaY * 0.001), point);
    }
}
