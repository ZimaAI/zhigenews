## CodeGraph

If a `.codegraph/` directory exists at the repository root, use CodeGraph before grep/find or reading source when locating or understanding code. Use `codegraph explore` / `codegraph node` or their MCP equivalents. If absent, skip CodeGraph; indexing is the user's decision.

## 前端视觉与交互规范

新增或修改前端页面、组件和样式前，按归属完整读取根目录规范：用户端读取 `design-user.md`，管理员端读取 `design.md`；同时影响双端的共享组件读取两份。再查看现有共享组件与各自全局样式，沿用对应设计变量、字体、间距、布局和状态，优先复用组件。

用户端使用浅冷灰外背景、白色画布、横向导航和绿色主题发现风格；管理员端保留暖白、深青绿及侧栏控制台。用户主题只在用户项目加载，不通过修改共享默认变量改变管理员风格。全局视觉变更先更新对应 design 文件，再同步实现。

页面须覆盖正常、加载、空、失败及关键交互状态。来源可追溯，移动端和键盘可用。原型的新闻、运行事件和发送结果必须标明模拟，不得冒充真实执行。

## 当前产品流程

当前版本和阶段以 `.project-flow/project.json`、目标版本 state 与 resume 输出为准。原型位于 `docs/releases/v1.0.0/draft/prototype/`，与正式应用实现隔离。
