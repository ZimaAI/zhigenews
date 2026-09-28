# 修复 Linux 镜像契约检查失败

Type: task
Status: resolved
Blocked by: none

本地 Windows 的 OpenAPI 文件为 CRLF，生成器对原始字节生成 SHA-256；Git 提交中的文件为 LF，导致 Linux Docker 构建报 Generated frontend contract is stale。

## Comments

- 从 HEAD 提取契约、生成器和生成文件到临时目录后复现相同错误；本地与提交文件仅换行符不同。
- 增加 Linux LF 检出回归测试，修复前已确认失败。
- 固定契约及生成文件使用 LF，重新生成；保留严格契约检查。

## Answer

`.gitattributes` 对 OpenAPI 与生成的 TypeScript 固定 LF，重新生成与 Git 提交字节一致的哈希。新增回归用例在 Windows 也按 Linux LF 输入执行真实生成器检查，修复后 11 项 API 测试通过。

完整 `docker build -f infra/deploy/web.Dockerfile -t zhigenews-web:contract-check .` 通过：契约校验、双端类型检查/构建、11 项 API 测试及 Caddy 镜像输出均成功。
