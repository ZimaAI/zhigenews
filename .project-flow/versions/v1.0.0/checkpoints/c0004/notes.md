# v1.0.0 · ITERATE r3 续接笔记

## 用户意图与起点

本轮用户要求先提交，然后精简用户端文字和界面；头像进入个人设置；订阅仅话题、背景、关键词；推送只保留每日时间，取消电子邮件，当前只支持站内；首次进入先引导偏好设置。

已在修改前提交 r2 全部成果：72b512a feat: redesign reader and split frontend design guides，未推送。r3 修改保留在工作区。保持 ITERATE，不冻结规范，不进入正式实现。

## 已完成

- 主导航收敛为今日/历史，头像直接到个人设置；移除账户中转弹窗、宣传段落和重复说明。白画布、灰背景、绿色强调继续由用户独立主题提供。
- 个人设置下设 /settings/preferences、/settings/schedule；旧 /preferences、/delivery 重定向。偏好只有话题/背景/关键词，8 个紧凑选择项；推送表单只有时间。
- 首次引导复用三字段编辑器。默认 seed 偏好为空、version 0、onboardingCompleted=false。有效保存持久化完成标志；刷新、后续登录不会重复引导。注册/全部重置重新引导，深链接不能绕过。
- 未按添加的关键词会随保存提交；保留校验、提交禁用、未保存离开和错误草稿。背景最多 500 字，关键词最多 20 个、每个 40 字。
- 简化今日、详情、历史、登录和运行页面；保留阅读状态、内容摘要、来源引用、搜索、生成/取消反馈，详情锚点定位。
- Preferences 与 DeliverySettings 实际字段和 OpenAPI 同步收缩，移除邮箱验证/测试发送方法及 3 个接口。站内通知 submitted 表示已发布，不等于已读；重试仅补发同份简报通知。管理员仅同步文案/图标/共享字段，布局色板不变。
- mock 固定 24 小时/最多 10 条/全部来源；任一话题或任一关键词匹配即可入选，背景保留供正式 Agent 使用，不冒充语义生成。localStorage 使用 r3 新键，不沿用旧邮箱设置。
- design-user.md 更新 r3；design.md 更新站内语义；候选需求/UX/领域/架构/验收/契约/追踪同步，新增 spec/07-changes.md 分类记录变化。历史决定保留并追加替代关系。

## 实际验证

npm run build：vue-tsc 与双端构建通过，用户 1632、管理员 1608 模块。npm run check:contract：14 样例、47 schemas、51 操作、48 实例，failures=[]。git diff --check 无错误；workflow doctor ok、problems=[]。

浏览器实际操作：首次空提交定位话题错误；Space 选择；背景与未添加关键词一起保存进入今日；刷新仍停留今日；头像直达三字段；未保存切换时间触发保留/放弃提示；时间 09:30 保存后刷新保持；error 场景保存失败保留草稿，重试加载后保存成功；生成 4 条匹配示例；键盘进入指定详情及来源，标记已读；历史无匹配搜索与清除；旧入口跳转；全部重置回引导，访问旧推送深链仍停留引导。管理员站内失败记录补发后沿用 brief-18、尝试 1→2、状态已发布。

三页 /settings/preferences、/settings/schedule、/today 在 320/375/768/1024/1440/1920 的 18 组实际宽度均无整页横向溢出。桌面 1440 设置、375 阅读与首次引导截图目视检查。两端最终 error 日志为空，管理员主色仍 #0F766E，无 ReaderShell。预览服务因 Windows 共享文件缓存曾读取旧 adapter，重启后上述流程通过。测试尺寸覆盖已清理：管理端恢复默认，带尺寸覆盖的旧用户测试标签页关闭，新的无覆盖预览保留在首次引导。

## 续接

原型用户 http://127.0.0.1:5173/，管理员 http://127.0.0.1:5174/overview。停止后从 prototype/ 运行 npm run dev:user / npm run dev:admin。当前仍为 mock，无真实 HTTP/模型/采集/定时发布；两端 localStorage 按 origin 独立。实际证据见 evidence/prototype-r3-validation.json。

下一步按用户反馈继续 ITERATE r3；没有待确认的阶段推进问题。续接先 resume，不重建现有原型。检查点目标 c0004，以 state 的实际记录为准。
