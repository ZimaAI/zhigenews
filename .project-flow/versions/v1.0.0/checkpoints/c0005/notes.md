# v1.0.0 · ITERATE r4 续接笔记

## 用户意图与起点

用户要求切换回最新版本，并沿用原方案的部分按钮和 icon，通过 icon、tag 增加美观度。已从 detached 72b512a 切回 main，HEAD 为 e7251f3（r3 极简用户端提交）。本轮改动未提交，保持 ITERATE，不冻结或转入正式实现。

## 已完成

- design-user.md 先更新为 3.1 / r4，明确在 r3 简约结构下使用 Lucide 线性图标、绿色主按钮、描边次按钮、浅色标签。
- 今日/历史主导航、设置页签、保存/退出/阅读/时间操作增加一致的图标。8 个话题各有图标底板和选择标记，显示实际已选数量；关键词采用 Hash 浅绿标签。
- 新闻来源增加字母块，话题使用浅绿标签；筛选为带图标的胶囊按钮，已读操作有描边和选中状态。历史日期卡片、数量与部分完成状态保持紧凑。
- 保留头像直达个人设置；订阅仍只有话题、背景、关键词；推送仍只每日时间、仅站内；首次引导与保存/未保存/错误交互沿用 r3。
- prototype README、spec 索引/UX/变更记录同步 r4。未修改管理员代码、共享模型、HTTP 契约、mock 匹配或领域字段。

## 实际验证

双端构建与 vue-tsc 通过。浏览器完成首次话题和关键词设置并开始阅读，Space 切换话题和新闻筛选，标记已读，头像进入设置并保存。成功标记与 aria-pressed 状态正确。320px 时话题名称曾换行，调整图标间距后 8 个话题均为单行。

/settings/preferences、/settings/schedule、/today 在 320/375/768/1024/1440/1920 的 18 组实际尺寸均无整页横向溢出；另检查 375px 历史日期卡片。桌面设置/阅读、手机引导/阅读/历史已目视检查。用户预览日志没有 error，尺寸覆盖已 reset，实际恢复 670px，停在个人设置。证据见 evidence/prototype-r4-validation.json。

## 检查点维护

切回 main 后 resume 曾报 Checkpoint manifest drift。只读审计确认 core.autocrlf=true 将 c0004 两份 JSON 的 LF 转成 CRLF，Git blob 内容与原记录哈希仍一致。已恢复这两份 JSON 的原始 LF 字节并通过 resume；新增 .gitattributes 仅固定检查点 JSON 为 LF、Markdown 为原有 CRLF，保留所有历史哈希和检查点语义。当前草稿和运行记录的预期变化由下一检查点记录。

## 续接

用户 http://127.0.0.1:5173/settings/preferences；管理员 http://127.0.0.1:5174/overview。停止后从 docs/releases/v1.0.0/draft/prototype 运行 npm run dev:user / npm run dev:admin。当前仍是 mock，没有真实 HTTP、模型、采集或定时发布。

下一步按反馈继续 ITERATE r4，无待确认阶段推进问题。续接先 resume，不重建原型。检查点目标 c0005，以 state 的实际记录为准。
