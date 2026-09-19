# Domain Docs

## 布局

采用 single-context：

- 根目录 CONTEXT.md：业务概念与术语。
- docs/adr/：架构决策记录。

## 阅读规则

探索代码前，阅读已有 CONTEXT.md 及与当前任务相关的 ADR。
文件不存在时直接继续，不提示缺失，也不预先创建占位文件。
由 domain-modeling 技能在概念或决策明确后按需创建。

## 术语与决策

命名业务概念时沿用 CONTEXT.md 的术语，避免使用其明确排除的同义词。
发现术语缺口时，先检查是否引入了不必要的新概念；
确有缺口则留待 domain-modeling 补充。

建议与现有 ADR 冲突时，明确指出冲突及重新考虑的理由，不默默覆盖。
