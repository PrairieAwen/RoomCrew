/** 因为朝向、起坐与实际执行必须一致，需要在原生窗口检查四套素材和真实任务。 */
(async function verifyOfficeScene() {
    // 1、所有业务事件来自实际 SDK，测试只观察正式人物与 DOM。
    const phases = new Set();
    let previous = null,
        largestStep = 0,
        maxSprites = 0,
        unsafeFeet = 0;
    const poses = [];
    let desiredBoardDirection = "s";
    /** 因为工具执行和素材解码异步，需要等待真实条件并明确超时。 */
    async function until(check) {
        // 1、不通过篡改事实或隐藏节点让条件成立。
        for (let i = 0; i < 500; i++) {
            if (await check()) return;
            await new Promise(pause);
        }
        throw new Error("office condition timed out: " + window.__officeStage);
    }
    /** 因为原生帧循环应持续运行，需要异步让出测试线程。 */
    function pause(resolve) {
        /* 1、仅控制验收采样频率。 */ setTimeout(resolve, 100);
    }
    /** 因为初始素材可能尚未完成解码，需要等待四个角色都使用正式图集。 */
    function ready() {
        // 1、不允许几何占位被当作新素材验证成功。
        return (
            state.workspace &&
            !state.switching &&
            studio?.data &&
            studio.renderer.views.size === 4 &&
            [...studio.renderer.views.values()].every(hasSprite)
        );
    }
    /** 因为正在加载的形象不能证明已显示，需要检查实际 sprite。 */
    function hasSprite(view) {
        /* 1、角色资源加载失败也不算成功。 */ return Boolean(view.sprite);
    }
    /** 因为执行动作应由真实工具触发，需要观察 Python 调用期间的背向工作变体。 */
    async function working() {
        // 1、使用产品事实和实际图集变体共同判断，不根据模型自称工作。
        await studio.refresh();
        const fact = studio.renderer.facts.get("assistant"),
            view = studio.renderer.views.get("assistant");
        return (
            fact?.activity === "executing" &&
            fact?.tool_kind === "python" &&
            view.sprite.dataset.variant.includes(".nw.seated.") &&
            view.sprite.dataset.page === "3"
        );
    }
    /** 因为问题应面向用户且经过转身，需要等真实待办和正面素材同时出现。 */
    async function waiting() {
        // 1、暂停任务仍保留原 Run，不以泡泡出现代替后端问题。
        await studio.refresh();
        const view = studio.renderer.views.get("assistant");
        return (
            (await api("questions")).length === 1 &&
            view.sprite.dataset.variant.includes(".se.seated.")
        );
    }
    /** 因为截图需要保存当前阶段，需要等待原生导出而不操作系统桌面。 */
    function captured() {
        /* 1、不伪造已保存文件。 */ return (
            window.__officeCaptured === window.__officeStage
        );
    }
    /** 因为最终结果必须可核对，需要等待运行结束并检查实际文件。 */
    async function completed() {
        // 1、刷新权威运行状态，为后续用户操作解除界面发送锁。
        const overview = await api("overview");
        renderOverview(overview);
        await studio.refresh();
        return (
            !overview.active_run &&
            studio.renderer.facts.get("assistant")?.bubble_notice?.kind ===
                "result"
        );
    }
    /** 因为起坐不能滑动穿模，需要逐帧记录阶段、位移和临时混合层数。 */
    function observe() {
        // 1、这是只读验收采样，不替换生产运动插值器。
        const a = studio.renderer.motion.actors.get("assistant"),
            v = studio.renderer.views.get("assistant");
        const foot = crewActorFootPosition(a);
        phases.add(a.phase);
        if (previous)
            largestStep = Math.max(
                largestStep,
                Math.hypot(
                    foot[0] - previous[0],
                    foot[1] - previous[1],
                ),
            );
        previous = foot;
        maxSprites = Math.max(
            maxSprites,
            v.group.querySelectorAll(".sprite-smooth,.sprite-pixel").length,
        );
        // 2、检查真实连续位置与家具矩形的距离；只看路径节点会漏掉拐角切入和坐姿离座。
        if (a.phase === "moving")
            for (const obj of studio.data.scene.room.objects) {
                const [w, h] = obj.footprint || studio.data.scene.catalog[obj.type];
                const dx = Math.max(obj.x - a.position[0], 0, a.position[0] - obj.x - w);
                const dy = Math.max(obj.y - a.position[1], 0, a.position[1] - obj.y - h);
                if (Math.hypot(dx, dy) < 0.4) unsafeFeet++;
            }
        if (window.__officeWatching) requestAnimationFrame(observe);
    }
    /** 因为需要观察完成的落座，需要等待正式目标而不只判断路径队列为空。 */
    function seated() {
        // 1、包括转身与落座阶段必须已结束。
        const a = studio.renderer.motion.actors.get("assistant");
        return (
            a.phase === "settled" &&
            a.target.id === "sofa" &&
            a.posture === "seated"
        );
    }
    /** 因为直接驱动生产提交器仍应阻止导航，需要提供最小事件接口。 */
    function preventSubmit() {
        /* 1、此测试没有浏览器默认提交。 */
    }
    try {
        window.__officeStage = "loading";
        await until(ready);
        verifyFurnitureArt();
        // 2、复现现有用户的沙发/会议席配置，而不是只在默认工位验收工作朝向。
        for (const id of studio.renderer.views.keys()) studio.renderer.engage(id, true);
        const placement = await api("scene_move", "assistant", "sofa", studio.data.scene.room.revision);
        await studio.refresh();
        studio.renderer.motion.restore(placement, studio.data.scene.anchors, studio.data.scene.room.revision);
        const worker = [...studio.renderer.views.keys()].find(isWorker);
        await api("scene_move", worker, "conference:seat-1", studio.data.scene.room.revision);
        await studio.refresh();
        const originalManifests = [...studio.renderer.skins.cache.values()].map(
            manifestText,
        );
        if (originalManifests.some(hasThirdSavedPage))
            throw new Error("saved user contract changed");
        await newConversation();
        studio.roomMode();
        studio.renderer.cameraRig.center = [90, 310];
        studio.renderer.cameraRig.zoom = 0.8;
        studio.renderer.cameraRig.resize();
        el("prompt").value = "执行脚本后向我确认，最后报告实际产物";
        await sendTask({ preventDefault: preventSubmit });
        await until(working);
        window.__officeStage = "working";
        await until(captured);
        // 3、近景直接检查伸手工作与椅背，不能仅凭全景缩略图判断人物已经协调。
        studio.renderer.cameraRig.focus(studio.renderer.motion.actors.get("assistant").position);
        studio.renderer.cameraRig.zoom = 1.6;
        studio.renderer.cameraRig.resize();
        window.__officeStage = "working-close";
        await until(captured);
        studio.renderer.cameraRig.center = [90, 310];
        studio.renderer.cameraRig.zoom = 0.8;
        studio.renderer.cameraRig.resize();
        await until(waiting);
        await studio.showQuestions();
        window.__officeStage = "question";
        await until(captured);
        const form = el("questions-list").querySelector("form");
        form.querySelector(".question-choices button").click();
        form.requestSubmit();
        await until(completed);
        studio.closeQuestions();
        const file = await api(
            "read_artifact",
            state.conversation.id,
            "/proof.txt",
        );
        if (file.text !== "office verified")
            throw new Error("actual Python artifact missing");
        await studio.openConversation(
            "assistant",
            studio.renderer.facts.get("assistant").bubble_notice,
        );
        studio.roomMode();
        studio.selected = "assistant";
        window.__officeWatching = true;
        requestAnimationFrame(observe);
        for (const id of ["desk-3", "desk-4", "desk-1"]) {
            await studio.moveTo(id);
            if (id === "desk-4") await captureSeatSequence(id);
            else await until(atDestination.bind(null, id));
            window.__officeStage = id;
            await until(captured);
            poses.push({ id, position: [...studio.renderer.motion.actors.get("assistant").position] });
        }
        await studio.moveTo("sofa");
        await until(walking);
        // 3、冻结的只是测试窗口展示时钟，截图保留实际走到的帧，不改位置、素材或后台事实。
        studio.renderer.active = false;
        window.__officeStage = "walk-front";
        await until(captured);
        studio.renderer.active = true;
        await until(seated);
        window.__officeWatching = false;
        if (
            ![
                "stand_up",
                "moving",
                "turn_to_seat",
                "sit_down",
                "settled",
            ].every(hasPhase) ||
            largestStep > 0.4 ||
            maxSprites > 2 || unsafeFeet
        )
            throw new Error(
                "discontinuous movement or accumulating blend layers: " +
                    JSON.stringify({
                        phases: [...phases],
                        largestStep,
                        maxSprites,
                        unsafeFeet,
                    }),
            );
        window.__officeStage = "resting";
        await until(captured);
        // 4、用实际布置表单新建白板并轮转八向，检查保存、碰撞合同和渲染一起更新。
        studio.openFurniture(null);
        el("furniture-type").value = "screen";
        el("furniture-x").value = "25";
        el("furniture-y").value = "3";
        el("furniture-direction").value = "s";
        await studio.saveFurniture({ preventDefault: preventSubmit });
        await until(boardIsCurrent);
        const board = studio.data.scene.room.objects.find(isTestBoard);
        if (!board) throw new Error("furniture form did not save new whiteboard");
        for (const direction of CREW_DIRECTIONS) {
            desiredBoardDirection = direction;
            studio.openFurniture(board.id);
            el("furniture-direction").value = direction;
            await studio.saveFurniture({ preventDefault: preventSubmit });
            await until(boardIsCurrent);
            const current = studio.data.scene.room.objects.find(isTestBoard);
            if (current.direction !== direction) throw new Error("rotation not persisted: " + direction);
        }
        window.__officeStage = "rotation";
        await until(captured);
        // 5、保持生产 iframe 沙箱，实际导出素材总览，不能为了测试开启同源权限。
        studio.showAssetLibrary();
        for (let i = 0; i < 12; i++) await new Promise(pause);
        window.__officeStage = "assets";
        await until(captured);
        studio.closeAssetLibrary();
        window.__officeResult = {
            ok: true,
            variants: 4,
            python: true,
            human: true,
            phases: [...phases],
            largestStep,
            maxSprites,
            unsafeFeet,
            poses,
            furnitureArt: true,
            directionsEdited: 8,
            galleryOpened: true,
        };
    } catch (error) {
        window.__officeResult = {
            ok: false,
            error: error.message,
            stack: error.stack,
            stage: window.__officeStage,
        };
    }
    /** 因为已保存素材必须保持两页合同，需要提取原始目录供比较。 */
    function manifestText(asset) {
        /* 1、不把显示补丁混入用户配置。 */ return asset.manifest;
    }
    /** 因为显示补丁只能在内存中合并，需要拒绝原始清单多出页面。 */
    function hasThirdSavedPage(manifest) {
        /* 1、所有测试角色原本都是两页。 */ return manifest.images.length !== 2;
    }
    /** 因为完整起坐有明确的阶段，需要确认每个必要阶段都经过。 */
    function hasPhase(phase) {
        /* 1、阶段来自正式 motion 对象。 */ return phases.has(phase);
    }
    /** 因为新角色 ID 由正式保存入口生成，需要选择真实员工而不是硬编码一个不存在的 ID。 */
    function isWorker(id) {
        // 1、守卫和助手不作为会议席的第二位员工。
        return !["assistant", "guardian"].includes(id);
    }
    /** 因为测试白板由真实表单创建，需要按已设置的位置识别它而不是注入固定 ID。 */
    function isTestBoard(obj) {
        // 1、不会读取其他空间或修改用户布置。
        return obj.type === "screen" && obj.x === 25 && obj.y === 3;
    }
    /** 因为保存响应和后台轮询可能交错，需要等待真实新版本到达后再检查，不能把旧快照当成保存失败。 */
    function boardIsCurrent() {
        // 1、只观察真实持久化快照，不补写数据或放宽方向要求。
        return studio.data.scene.room.objects.find(isTestBoard)?.direction === desiredBoardDirection;
    }
    /** 因为每个桌子都应有正确落座位置，需要检查目标和完整坐下阶段。 */
    function atDestination(id) {
        // 1、不以计划已提交当作人已到位。
        const actor = studio.renderer.motion.actors.get("assistant");
        return actor.phase === "settled" && actor.target.id === id;
    }

    /** 因为静态工作截图无法证明起坐自然，需要导出生产播放器实际经过的每张过渡帧。 */
    async function captureSeatSequence(destination) {
        // 1、只暂停测试窗口的展示时钟以导出当前帧，不补写位置、选帧或任务事实。
        const recorded = new Set();
        for (let i = 0; i < 1000; i++) {
            const actor = studio.renderer.motion.actors.get("assistant");
            const sprite = studio.renderer.views.get("assistant").sprite;
            const key = `${actor.phase}-${sprite.dataset.frame}`;
            if (["stand_up", "sit_down"].includes(actor.phase) &&
                sprite.dataset.page === "4" && !recorded.has(key)) {
                recorded.add(key);
                studio.renderer.active = false;
                studio.renderer.cameraRig.focus(actor.position);
                studio.renderer.cameraRig.zoom = 1.5;
                studio.renderer.cameraRig.resize();
                window.__officeStage = "contact-" + key;
                await until(captured);
                studio.renderer.active = true;
            }
            if (atDestination(destination)) break;
            await new Promise(requestAnimationFrame);
        }
        // 2、离座和入座都必须真正显示过六种姿态，缺帧不能由多张相同截图代替。
        for (const phase of ["stand_up", "sit_down"])
            if ([...recorded].filter(key => key.startsWith(phase)).length !== 6)
                throw new Error("missing transition frames: " + phase);
        if (!atDestination(destination)) throw new Error("seat sequence timed out");
        studio.renderer.cameraRig.center = [90, 310];
        studio.renderer.cameraRig.zoom = 0.8;
        studio.renderer.cameraRig.resize();
    }
    /** 因为穿桌问题发生在途中，需要捕获真实走路阶段的客户区。 */
    function walking() {
        // 1、坐姿或起身不当作走路帧。
        const actor = studio.renderer.motion.actors.get("assistant");
        return actor.phase === "moving" && actor.elapsed > 1.2;
    }
    /** 因为更换原图不代表渲染未扭曲，需要检查实际 DOM 的图像比例、变换及监管员朝向。 */
    function verifyFurnitureArt() {
        // 1、每张桌子的源图比例必须原样显示，场景镜头不能给它单独加旋转或斜切。
        const renderer = studio.renderer;
        for (const obj of studio.data.scene.room.objects) {
            if (!["desk", "security"].includes(obj.type)) continue;
            const material = crewSceneMaterial(obj.type, obj.direction);
            const group = renderer.depth.querySelector(`[data-object="${obj.id}"]`);
            const picture = group.querySelector("svg");
            const rect = material.frames[0];
            const ratio = Number(picture.getAttribute("width")) / Number(picture.getAttribute("height"));
            const transform = picture.getCTM();
            if (Math.abs(ratio - rect[2] / rect[3]) > 0.00001 || Math.abs(transform.b) > 0.00001 || Math.abs(transform.c) > 0.00001 || Math.abs(transform.a - transform.d) > 0.00001)
                throw new Error("workstation distorted: " + obj.id);
        }
        // 2、监管员确实使用新页和与桌面相同的西北朝向，不能只更新预览图。
        const guardian = renderer.views.get("guardian");
        if (guardian.group.dataset.direction !== "nw" || !["2", "3"].includes(guardian.sprite.dataset.page) || guardian.sprite.dataset.mirrored !== "false")
            throw new Error("guardian orientation or supplement is stale");
    }
})();
