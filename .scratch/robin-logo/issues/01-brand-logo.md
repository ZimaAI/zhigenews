# 统一知更鸟 Logo

Type: task
Status: resolved
Blocked by: none

## 范围

设计 SVG，接入双端品牌入口和 favicon，核对布局与构建。

## Answer

- 已接入用户欢迎页、阅读器共用页头、管理员登录、侧栏、手机顶栏及双端 favicon。按照用户反馈改为浅薄荷绿飞翔造型。
- 两端 Vite 使用同一素材目录作为 publicDir，页面和 favicon 引用同一 SVG，支持 BASE_URL。
- `npm run build` 通过（契约检查、Vue 类型检查、双端生产构建）；两端开发服务返回正确 SVG MIME 与内容，生产目录均包含同一素材。
- 临时视觉页面挂载真实 ReaderShell、Auth、Admin App 与 Login，使用标明模拟的页面内容和内存会话，不调用管理登录或生成简报。四类布局在 320、375、768、1024、1440、1920px 下 Logo 全部加载成功、无横向溢出。实际用户首次引导和管理员登录也完成浏览器检查。
- 手机管理员品牌链接为 44×44px，Tab 可聚焦且显示焦点轮廓。浏览器尺寸已恢复，临时验证页面已删除。
- 本次验证仅针对品牌与布局，不代替业务流程验收。
