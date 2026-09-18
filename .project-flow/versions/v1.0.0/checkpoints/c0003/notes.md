# v1.0.0 · ITERATE r2 续接笔记

## 用户意图与本轮起点

用户要求：“先提交一次。然后参考所给的图片中的设计，创建一个新的 Design 文件。记录用户端的界面风格。”并明确将根 design 文件改为管理员端规范，最终两份规范。

已在任何改版前提交原型 r1 全部成果：`2bfb26d feat: add dual Vue prototypes and draft API contracts`。未推送。本轮视觉修改留在工作区。恢复 c0002 时无 drift/warnings，保持 ITERATE，无基线或正式实现批准。

## 已完成

- 根 design-user.md 新增用户端规范；根 design.md 收敛为管理员端，保留原 85 个 CSS token。
- AGENTS.md 按用户/管理员/共享范围读取对应规范。同步需求、UX、架构、AC、traceability、索引及启动文档。
- 用户端新增 ReaderShell.vue / user-tokens.css，顶部横向导航、浅冷灰外围、1120px 白色画布、绿色下划线、小圆角与独立主题。其他阅读/历史/推送/登录/首次配置/运行页继承该主题。
- Preferences.vue + TopicDiscovery.vue 实现参考图式主题发现：分类、本地搜索、四张原创主题封面、四张小主题卡及已选摘要。搜索只筛候选；选择只改草稿；显式保存生效。保留关键词、排除词、参数、来源类型、记忆、失败保留与离开提醒。
- 内置 image_gen 生成四张本地原创主题封面；模型封面透明边缘经同工具修正。最终资产和完整提示词在 user-web/public/images/ASSETS.md。封面不是新闻照片。
- 管理员应用源码与共享执行/样式代码未改；shared/API.md 仅更新壳的开发说明。无 API schema 或交换字段变化。

## 真实验证

npm run build 成功（含 vue-tsc --noEmit）；用户端1631模块，管理员1608模块。git diff --check 无空白错误。

浏览器真实检查：搜索“芯片”仅返回相关小卡且不改变已保存版本/已选；选中后草稿计数3→4、版本仍3；未保存跳转触发提示；空搜索不丢选择；保存后版本4，离开再回来仍4主题；Space可选择主题；error场景保存失败保留4主题，重试加载/保存成功；账户弹窗Escape关闭后焦点回触发按钮；页顶重置恢复seed。最终双端error日志为空。

/preferences、/today、/delivery 在320/375/768/1024/1440/1920共18个组合无整页横向溢出。桌面与手机截图已目视检查，未导出PNG。管理员浏览器仍为#0F766E、暖白rgb(247,248,245)与侧栏，无ReaderShell。弱文字颜色调整为#697075，在白/浅灰三背景上对比度最低4.56。实际证据见 evidence/prototype-r2-validation.json。

## 下一动作

保持 v1.0.0 / ITERATE / r2，继续按用户反馈迭代，不冻结规范、不进入SPECIFY或正式实现。无未修复的已观察阻塞。原型仍为mock，双端localStorage独立，未接真实后端/模型/新闻/邮件。

入口：用户 http://127.0.0.1:5173/preferences，管理员 http://127.0.0.1:5174/overview。服务若退出，按prototype/README.md重启。续接先运行resume，再查看design-user.md或design.md及本轮文件；不要回滚现有修改或重建原型。检查点目标c0003，以state实际记录为准。
