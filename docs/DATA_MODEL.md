# 数据约定（schema_version 1.0.0）

输出为 JSON 可序列化字典。读取方应允许附加字段并检查 `schema_version`；破坏兼容性的改动提升主版本。当前不提供运行时 JSON Schema 校验。

| 层级 | 主要字段 |
| --- | --- |
| 文档 | `document_id`、`source`、`metadata`、`page_count`、`pages_processed`、`truncated`、`status`、`coordinates`、`engine`、`options`、`pages` |
| 页面 | `number`、`width`、`height`、`original_rotation`、`cropbox`（读取成功时）、`type`、`status`、`blocks`、`images`、`quality`、`processing` |
| 内容块 | `id`、`page`、`type`、`text`、`bbox`、`source`、`reading_order`、`lines`、`quality`、`structure_method`；可选 `section_path`、`role` |
| 原始行 | `text`、`bbox`、`source`、`confidence`、`font_size`、`flags`；原生行可含 `bold`，OCR 行可含 `polygon` |
| 表格块 | 额外含 `rows`、`cells`，空/合并位置可为 `null`；不假定第一行为表头 |
| 图像 | `id`、`bbox`、`role`、`asset`；未导出时 `asset=null` |
| 分块 | `id`、`document_id`、`text`、`section_path`、`sources` |

`document_id` 为输入文件 SHA-256。块 ID 在相同版本与配置下按阅读顺序生成，如 `p0001-b0001`；算法升级后不保证不变。跨文件定位需结合 `document_id`。

块/行层的 `source` 为 `native` 或 `ocr`；文档层 `source` 则记录输入绝对路径和 SHA-256。分享输出时可按需移除本地路径。

## 坐标

页码从 1 开始，`reading_order` 从 0 开始。`bbox=[x0,y0,x1,y1]` 使用未旋转可见页左上原点，单位 pt（1/72 英寸）；宽高与 OCR 坐标在同一空间。`cropbox` 保留后端裁剪框，不能直接当作可见页原点。映射到旋转后的阅读器画面需应用页面旋转与缩放。

## 状态与质量

状态为 `success`、`partial_success`、`failure`。逐页异常不丢弃其他页。需要 OCR 却无法执行时保留原生内容并报告错误；没有内容可保留的失败页为 `failure`。

`quality.warnings` 与 `quality.errors` 带 `code` 和 `detail`。`needs_review` 是复核提示，不是概率。原生文字 `confidence=null`；OCR 分数不是校准的正确率。扫描页显式关闭 OCR 时可能流程成功但没有文本，须查看告警。

`truncated=true` 表示显式限制页数。耗时为转换时间，不含文件哈希与导出。CLI 峰值 RSS 为进程从启动以来的峰值，不是单页增量或系统内存。

## 分块溯源

每个 `sources` 项含 `page`、`block_id`、`bbox`、`start`、`end`。偏移是块 `text` 的 Python Unicode 字符索引，区间左闭右开。按 sources 顺序取原文切片，用两个换行连接，即得到分块 `text`。

`bbox` 指整个来源块，不是切片的精确几何框。分块按章节分隔，默认跳过已识别的重复页眉页脚，不重叠、不补写、不删除连字符。大小按字符而非 token 计；表格也可能切分，完整网格需读取文档 JSON。
