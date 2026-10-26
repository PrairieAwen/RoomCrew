/** 因为元数据正确不代表素材可看可播，需要在真实 WebView2 运行正式展厅并检查可观察结果。 */
(async function verifyMaterialGallery() {
    /** 因为图像解码与绘制异步完成，需要有界等待真实 DOM 与画布状态。 */
    async function until(check) {
        // 1、最多等待二十秒，不改写播放器或素材。
        for (let index = 0; index < 200; index++) {
            if (check()) return;
            await new Promise(pause);
        }
        throw new Error("material gallery condition timed out");
    }
    /** 因为不能阻塞动画线程，需要把测试采样让回浏览器事件循环。 */
    function pause(resolve) {
        // 1、只控制检查频率。
        setTimeout(resolve, 100);
    }
    /** 因为所有角色都应实际解码，需要等待正式卡片播放器达到四套。 */
    function ready() {
        // 1、不通过替代图片或注册数据绕过资源加载。
        return window.materialGallery?.players.length === 4;
    }
    /** 因为工作动作位于第二页，需要检查真实画布已绘制所选帧。 */
    function workPage() {
        // 1、读取正式绘制器每帧写入的观测标签。
        return document.getElementById("detail-canvas").dataset.page === "1";
    }
    /** 因为走跑在基础页，需要观察真实跨页切换。 */
    function corePage() {
        // 1、不直接调用 draw 或修改播放器时间。
        return document.getElementById("detail-canvas").dataset.page === "0";
    }
    /** 因为逐帧应暂停在指定帧，需要检查可见标题而非只读滑块输入。 */
    function scrubbed() {
        // 1、正式控件决定帧序号。
        return document
            .getElementById("frame-caption")
            .textContent.includes("第 3 / 8");
    }
    /** 因为每个类别要实际加载，需要等待登记与已绘制卡片数量一致。 */
    function categoryReady() {
        // 1、目标数量由当前固定类别取得。
        return (
            window.materialGallery.players.length ===
            Number(
                document
                    .getElementById("section-count")
                    .textContent.split(" ")[0],
            )
        );
    }
    try {
        // 1、通过真实卡片与控件跨页、暂停和切换动作，不向模型发送请求。
        window.__materialStage = "cards";
        await until(ready);
        document.querySelector('[data-id="assistant"]').click();
        window.__materialStage = "detail";
        await until(workReady);
        /** 因为详情异步解码，需要先确认正式播放器已准备当前角色。 */
        function workReady() {
            // 1、只观察正式详情状态。
            return window.materialGallery.detail?.entry.id === "assistant";
        }
        const action = document.getElementById("detail-action");
        action.value = "read";
        document.getElementById("detail-posture").value = "seated";
        action.dispatchEvent(new Event("change"));
        window.__materialStage = "work-page";
        await until(workPage);
        action.value = "run";
        document.getElementById("detail-posture").value = "standing";
        action.dispatchEvent(new Event("change"));
        window.__materialStage = "core-page";
        await until(corePage);
        const slider = document.getElementById("frame-slider");
        slider.value = "2";
        slider.dispatchEvent(new Event("input"));
        window.__materialStage = "scrub";
        await until(scrubbed);
        const pixels = document
            .getElementById("detail-canvas")
            .getContext("2d")
            .getImageData(0, 0, 800, 800).data;
        let opaque = 0;
        for (let index = 3; index < pixels.length; index += 4)
            if (pixels[index]) opaque++;
        if (opaque < 5000) throw new Error("character canvas blank");
        document.getElementById("close-inspector").click();
        // 2、每类数量与覆盖矩阵必须来自实际登记，全部图片应能在原生页面显示。
        for (const category of ["furniture", "decor", "effects"]) {
            window.__materialStage = category;
            document.querySelector(`[data-category="${category}"]`).click();
            await until(categoryReady);
            if (
                document.querySelectorAll(".asset-card").length !==
                (category === "furniture" ? 12 : category === "decor" ? 16 : 8)
            )
                throw new Error("wrong category count");
        }
        document.querySelector('[data-category="matrix"]').click();
        if (document.querySelectorAll("#coverage tr").length !== 21)
            throw new Error("coverage matrix missing");
        if (document.body.scrollWidth > innerWidth + 1)
            throw new Error("gallery horizontal overflow");
        window.__materialResult = {
            ok: true,
            characters: 4,
            furniture: 12,
            decor: 16,
            effects: 8,
            pageSwitch: true,
            scrub: true,
            matrix: true,
            opaquePixels: opaque,
        };
    } catch (error) {
        window.__materialResult = {
            ok: false,
            error: error.message,
            stage: window.__materialStage,
            players: window.materialGallery?.players.length,
            page: document.getElementById("detail-canvas")?.dataset.page,
            text: document.getElementById("frame-caption")?.textContent,
        };
    }
})();
