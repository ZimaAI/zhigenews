## CodeGraph

If a `.codegraph/` directory exists at the repository root, use CodeGraph before grep/find or reading source when locating or understanding code. Use `codegraph explore` / `codegraph node` or their MCP equivalents. If absent, skip CodeGraph; indexing is the user's decision.

## 前端视觉与交互规范

新增或修改前端页面、组件和样式前，完整读取根目录 `design.md`，再查看现有共享组件与全局样式。沿用其设计变量、字体、间距、布局和状态，优先复用组件。

页面须覆盖正常、加载、空、失败及关键交互状态。来源可追溯，移动端和键盘可用。原型的新闻、运行事件和发送结果必须标明模拟，不得冒充真实执行。

## 当前产品流程

当前版本和阶段以 `.project-flow/project.json`、目标版本 state 与 resume 输出为准。原型位于 `docs/releases/v1.0.0/draft/prototype/`，与正式应用实现隔离。
