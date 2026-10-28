/* 有界场景导航：只读取服务端障碍合同，不写人物位置或执行状态。 */
"use strict";

class CrewNavigator {
    /** 因为散步和会议要复用相同障碍，需要缓存有限网格而不在帧循环重建。 */
    constructor() {
        // 1、未取得合法地图时不生成路线。
        this.revision = -1;
        this.width = 0;
        this.height = 0;
        this.blocked = new Set();
        this.seats = new Set();
    }

    /** 因为场景可能降级或跨版本，需要严格验证导航合同并按布局版本更新缓存。 */
    update(value) {
        // 1、限制网格与障碍数量，拒绝非整数和越界坐标。
        if (
            !value ||
            value.version !== 1 ||
            !Number.isSafeInteger(value.revision) ||
            !Number.isInteger(value.width) ||
            !Number.isInteger(value.height) ||
            value.width < 1 ||
            value.height < 1 ||
            value.width > 64 ||
            value.height > 64 ||
            !Array.isArray(value.blocked) ||
            value.blocked.length > 4096
        )
            return false;
        if (value.revision === this.revision) return true;
        const blocked = new Set();
        for (const point of value.blocked) {
            if (
                !Array.isArray(point) ||
                point.length !== 2 ||
                !point.every(Number.isInteger) ||
                point[0] < 0 ||
                point[1] < 0 ||
                point[0] >= value.width ||
                point[1] >= value.height
            )
                return false;
            blocked.add(point.join(","));
        }
        // 2、椅子不是家具主体的一部分，但不能被散步路线当作可穿越的空格。
        const seats = new Set();
        if (value.seats != null && (!Array.isArray(value.seats) || value.seats.length > 512)) return false;
        for (const point of value.seats || []) {
            if (!Array.isArray(point) || point.length !== 2 || !point.every(Number.isInteger) || point[0] < 0 || point[1] < 0 || point[0] >= value.width || point[1] >= value.height) return false;
            seats.add(point.join(","));
        }
        this.seats = seats;
        this.width = value.width;
        this.height = value.height;
        this.blocked = blocked;
        this.revision = value.revision;
        return true;
    }

    /** 因为视觉目的地不能穿过家具，需要统一判断固定格网是否可通行。 */
    free(point, includeSeats = true) {
        // 1、只接受地图内整数格，不接受世界像素或外部路径。
        return (
            Array.isArray(point) &&
            point.length === 2 &&
            point.every(Number.isInteger) &&
            point[0] >= 0 &&
            point[1] >= 0 &&
            point[0] < this.width &&
            point[1] < this.height &&
            !this.blocked.has(point.join(",")) &&
            (!includeSeats || !this.seats.has(point.join(",")))
        );
    }

    /** 因为本地视觉移动也必须避障，需要用有界四邻域搜索生成独立路线。 */
    route(start, end) {
        // 1、不可达时返回空数组，不回退直线穿越或请求 Agent。
        if (!this.free(start, false) || !this.free(end, false)) return [];
        const queue = [[...start]],
            previous = new Map([[start.join(","), null]]);
        let cursor = 0;
        while (cursor < queue.length) {
            const point = queue[cursor++],
                key = point.join(",");
            if (key === end.join(",")) {
                const path = [];
                let current = point;
                while (current) {
                    path.push(current);
                    current = previous.get(current.join(","));
                }
                return path.reverse();
            }
            for (const [dx, dy] of [
                [1, 0],
                [-1, 0],
                [0, 1],
                [0, -1],
            ]) {
                const next = [point[0] + dx, point[1] + dy],
                    nextKey = next.join(",");
                const endpoint = nextKey === end.join(",") || nextKey === start.join(",");
                if (this.free(next, !endpoint) && !previous.has(nextKey)) {
                    previous.set(nextKey, point);
                    queue.push(next);
                }
            }
        }
        return [];
    }

    /** 因为散步不应钻到画布角落，需要只返回当前位置附近且保持一格边距的空地。 */
    nearby(point, occupied = new Set()) {
        // 1、候选有界；最终仍需 route 验证实际连通性。
        const result = [];
        for (let y = 1; y < this.height - 1; y++)
            for (let x = 1; x < this.width - 1; x++) {
                const distance =
                    Math.abs(x - point[0]) + Math.abs(y - point[1]);
                if (
                    distance >= 3 &&
                    distance <= 7 &&
                    this.free([x, y]) &&
                    !occupied.has([x, y].join(","))
                )
                    result.push([x, y]);
            }
        return result;
    }
}
