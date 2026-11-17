# 评估与验证

程序没有报错不等于提取质量达标。当前测试主要验证溯源、运行边界与规则，不代表真实论文准确率。

```bash
python -m pip install -e ".[dev]"
python examples/make_sample.py
pytest -q
```

样例由代码生成，无需下载 PDF。回归覆盖双栏、章节/图表说明、参考文献、分块上限与原文重建、有线表格、旋转裁剪、23 页完整处理、显式截断、OCR 异常保留、加密/损坏文件和 CLI 输出隔离。

真实 OCR 检查需安装 `.[ocr]`，将 `PAI_OCR_MODELS` 指向已有模型目录，再运行 `pytest -q tests/test_core.py -k mixed_ocr_region_coordinates`。本地模型文件为 `PP-OCRv6_det_small.onnx`、`PP-OCRv6_rec_small.onnx`、`ch_ppocr_mobile_v2.0_cls_mobile.onnx`；缺少依赖或模型时明确跳过。

## 待建立的论文基准

每份 PDF 记录来源、许可、SHA-256、语言、页数与版面类别。人工标注正文、阅读顺序、章节、图表、公式；调参集与保留测试集分开。真实论文未随仓库提供，尚未报告与 Docling 的对比数值。

| 维度 | 指标 |
| --- | --- |
| 文字 | 字符错误率、正文缺失率，中英文分开 |
| 顺序 | 块顺序成对正确率、跨栏错误数 |
| 结构 | 标题层级、图表说明 precision/recall/F1 |
| 表格 | 单元格内容与行列匹配，合并单元格单列 |
| 公式 | 符号保留与 LaTeX 结构；当前无 LaTeX 恢复 |
| 溯源 | 页码/坐标正确率、来源切片一致性 |
| 资源 | 冷/热启动、每页耗时、独立进程峰值 RSS、依赖与模型体积 |

对比 Docling 时固定版本、CPU/线程、OCR/表格开关、页范围和缓存；下载时间另报。分别比较原生与增强配置，公开失败样本；未经评测不宣称效果相当或性能更优。
