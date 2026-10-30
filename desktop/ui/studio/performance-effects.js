/* 演出道具：递文件、翻页与通话声波；不代表业务产物或审核结论。 */
"use strict";
class CrewPerformanceEffects {
    /** 因为工作角色使用不同图集，需要用独立道具层补充可识别交互并复用同一世界镜头。 */
    constructor() {
        // 1、图形只创建一次，帧循环只更新位置与透明度，不解析外部 SVG 或脚本。
        this.group = crewSvg("g", {"pointer-events":"none",class:"crew-performance-effects"});
        this.paper = crewSvg("g");
        this.paper.append(crewSvg("rect",{x:-8,y:-11,width:16,height:22,rx:2,fill:"#fffdf4",stroke:"#8a9aab","stroke-width":1}));
        this.paper.append(crewSvg("path",{d:"M-4,-6 H4 M-4,-2 H4 M-4,2 H2 M-4,6 H4",stroke:"#6d8cad","stroke-width":1.2,fill:"none"}));
        this.rings = crewSvg("path",{d:"M0,-6 Q7,0 0,6 M4,-10 Q15,0 4,10",fill:"none",stroke:"#6a91af","stroke-width":1.5,"stroke-linecap":"round"});
        this.group.append(this.paper,this.rings);
    }

    /** 因为道具必须随人物移动，需要每帧读取同一世界脚点，不回算屏幕坐标。 */
    paint(director, renderer) {
        // 1、只有实际处于互动阶段才显示道具；路上仍展示真实步行与起坐。
        const active = director.active, item = active?.item;
        const actor = item && renderer.motion.actors.get(item.member_id);
        const show = actor && active.stage === "perform" && director.hints.has(item.member_id);
        this.group.setAttribute("display",show?"inline":"none");
        if (!show) return;
        this.group.dataset.kind = item.kind;
        this.paper.setAttribute("display",item.kind === "mcp" ? "none":"inline");
        this.rings.setAttribute("display",item.kind === "mcp" ? "inline":"none");
        const origin = crewProject(actor.position), age = active.elapsed;
        const source = renderer.views.get(item.member_id)?.member;
        const asset = renderer.skins.cache.get(source?.avatar_id);
        const sockets = asset?.display_registration?.sockets || asset?.registration?.sockets;
        const hand = (sockets?.[actor.posture] || -90) * 0.48;
        let x = origin[0]+10, y=origin[1]+hand;
        // 2、派发纸张从主角手边移向接收者，查档则翻动纸页；任何动作都不创建真实文件。
        if(item.kind === "handoff") {
            const target = renderer.motion.actors.get(item.target_member_id);
            if(target) {
                const destination = crewProject(target.position), t=crewEase(Math.min(1,age/1.8));
                x += (destination[0]-origin[0]-20)*t;
                y += (destination[1]-origin[1])*t;
            }
        }
        const flutter = item.kind === "archive" ? Math.sin(age*8)*9 : -10+age*6;
        this.paper.setAttribute("transform",`translate(${x},${y}) rotate(${flutter})`);
        this.rings.setAttribute("transform",`translate(${origin[0]+24},${origin[1]+hand*1.75})`);
        this.rings.setAttribute("opacity",0.45+Math.sin(age*7)*0.25);
    }
}
