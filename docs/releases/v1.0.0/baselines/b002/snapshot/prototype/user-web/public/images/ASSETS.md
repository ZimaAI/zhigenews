# 用户端主题封面资产

生成时间：2026-09-18 13:20–13:23 UTC（北京时间 21:20–21:23）。

使用内置 `image_gen` 工具生成；未调用 CLI/API 脚本。参考用户提供截图的纯色主题卡片、主体位于下部和顶部留白构图，没有复制截图图片、品牌或文字。所有图像均为原创 AI 主题示意，不代表真实新闻事件、真实人物或个人生物识别信息。

四张最终 PNG 为 1086 × 1448（3:4）竖图，可用 `object-fit: cover` 展示；卡片标题应由 HTML 呈现。已逐张目视检查：无文字或品牌标识，主体完整，顶部有可叠加标题的安静色面。玻璃脑初次生成出现透明渐隐边缘，已用同一内置工具修正为完整青蓝色不透明背景；只保留修正后的最终版本。

| 文件 | 用途 | 视觉内容 |
| --- | --- | --- |
| topic-agent.png | Agent 主题卡片 | 珊瑚红背景、黑色 VR 机器人雕塑 |
| topic-model.png | 大模型主题卡片 | 青蓝背景、透明玻璃脑静物 |
| topic-open.png | 开源主题卡片 | 明黄背景、互锁几何积木 |
| topic-security.png | AI 安全主题卡片 | 近黑背景、电蓝抽象指纹 |

## 最终提示词

### topic-agent.png

```text
Use case: stylized-concept. Asset type: original thematic cover for an AI news subscription card, portrait 3:4 image. Primary request: a glossy black sculptural generic robot head wearing a futuristic black VR visor, against a vivid solid coral red studio backdrop. Premium editorial still-life photography aesthetic, sculptural object not a real human. Head and visor sit in the lower two thirds of the frame; the upper third is calm uninterrupted coral color, suitable for an HTML title overlay. Dramatic red rim light, deep glossy blacks, close crop near the lower edge, bold simple composition. No text, no letters, no logos, no watermarks, no UI, no borders. This is thematic editorial art, not a photograph of a real news event.
```

### topic-model.png

```text
Use case: stylized-concept. Asset type: original thematic cover for an AI news subscription card, portrait 3:4 image. Primary request: a transparent sculptural glass brain as a minimal studio still life against a saturated fresh cyan blue backdrop. Premium editorial object photography aesthetic, intricate but clean glass folds and refracted aqua light. A single glass brain sits in the lower two thirds of the composition with a very subtle surface shadow; leave the upper third calm clear blue for an HTML title overlay. Simple, tactile, brilliant translucent glass, bold color, controlled studio lighting. No text, no letters, no logos, no watermark, no UI, no border. This is thematic conceptual art, not a photograph of a real news event.
```

### topic-open.png

```text
Use case: stylized-concept. Asset type: original thematic cover for an AI news subscription card, portrait 3:4 image. Primary request: a compact sculpture of modular interlocking geometric cubes and building blocks, against a warm saturated golden yellow studio backdrop. Premium editorial still-life photography with tactile satin-finish blocks in ivory, golden yellow and charcoal accents. The sculpture occupies the lower two thirds, upper third an uninterrupted yellow field for an HTML title overlay. Geometric architectural precision, playful modular structure, simple studio light and soft shadows, no other objects. No text, no letters, no logos, no watermarks, no UI, no borders. This is thematic art for open-source software, not an image of a real news event.
```

### topic-security.png

```text
Use case: stylized-concept. Asset type: original thematic cover for an AI news subscription card, portrait 3:4 image. Primary request: a large crisp electric-blue luminous fingerprint contour graphic on an almost black background. Contemporary premium technology editorial art, many smoothly flowing concentric fingerprint ridge lines, vivid cobalt and cyan blue light against matte near-black. Fingerprint occupies the lower two thirds, leave the upper third calm pure near-black for an HTML title overlay. Complete tall fingerprint silhouette with elegant clean line endings, centered composition, subtle glow only, minimal disciplined design. No text, no letters, no logos, no watermarks, no UI, no borders. Abstract security illustration, not biometric data from any real individual.
```

### topic-model.png 定向修正提示词

```text
Use case: precise-object-edit. Edit this portrait card artwork only to give it a fully opaque fresh cyan-blue studio background from edge to edge. Preserve the transparent glass brain object exactly, including its position, scale, refracted light and details. The upper third should be a calm bright cyan-blue field suitable for white HTML title overlay. Remove the dark/black-looking or transparent vignette at top and corners, use solid cyan (#39b7d3) all the way to all four edges. Keep the portrait 3:4 composition. Do not add text, letters, logos, watermarks, borders or UI. No alpha transparency in the final image: fully opaque background.
```

