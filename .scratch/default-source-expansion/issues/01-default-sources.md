# 扩充默认来源

Type: task
Status: resolved
Blocked by: 无

提取两个指定页面的清单，更新默认配置和说明，验证条目完整性及初始化兼容性。

## Answer

- `catalog.py` 固定默认启用「更多」菜单中的 47 个 NewsNow 规范来源 ID。
- `default-rss-sources.json` 保存文章全部 340 个不同 URL，加原有中国新闻网共 341 个。
- 浏览器表格与下载 HTML 独立提取结果一致（340 行，JSON 22571 字符，FNV-1a 483413151）。
- 3 个空名称用 URL 补齐；同名不同地址保留；已有 3 个默认来源 ID 不变。
- 原有采集与运行配置测试：37 passed。Ruff 与 git diff --check 通过。
- `verify_defaults.py` 验证 388 个来源 ID/URL 唯一、自定义 NewsNow 基础地址、上游周期、重复初始化保留已有编辑和禁用状态。
- 仅配置导入验证，未执行所有外部源的采集，未写入运行数据库。
- 初始化命令与清单来源记录于 ingestion/README.md。
