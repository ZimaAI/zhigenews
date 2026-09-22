# 重写项目 README

Type: task
Status: resolved
Blocked by: none

## Scope

参考 Alibaba 开源项目的 README 编排，补齐品牌头部、主题与技术徽章、目录和已有海报。正文依次为项目简介、核心特性、项目结构与架构图、快速开始、许可证。采用 MIT，保留原开发与运维内容到独立文档。

## References

- https://github.com/alibaba/spring-ai-alibaba/blob/main/README.md
- https://github.com/alibaba/nacos/blob/develop/README.md
- https://choosealicense.com/licenses/mit/

## Verification

核对功能与源码、技术栈与依赖清单、启动命令与 Compose 配置，检查本地链接、章节锚点和 diff。

## Answer

已重写 README，引用工作区已有海报，加入五个章节、目录树、Mermaid 架构图和完整启动步骤；新增 MIT LICENSE。旧 README 的开发、调试与运维内容移至 docs/development.md，并修正相对链接。

验证通过：23 个本地链接与锚点、五个章节顺序、代码围栏、git diff --check、docker compose --profile app config --quiet。本次为文档修改，未启动服务或调用外部模型。
