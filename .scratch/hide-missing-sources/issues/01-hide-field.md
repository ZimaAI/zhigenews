# 移除公开字段和前端展示

Type: task
Status: resolved
Blocked by: 无

## 验收

- 今日页和详情页移除对应提示块。
- 公开 Brief DTO 不包含 missingSources，内部数据保持不变。
- 前端契约、类型检查及公开投影回归验证通过。

## Answer

已移除两个用户页面的提示块和公开 Brief 契约中的 missingSources，并重新生成前端类型。已有 public_brief 根据公开契约过滤响应，无需修改业务逻辑；内部字段和处理保持原样。

验证通过：公开投影回归测试（1 passed）、npm run check、npm run check:contract、npm run build:user、git diff --check。未执行浏览器视觉检查。
