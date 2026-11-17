# 依赖与设计参考

Pai 自有源码沿用 Apache-2.0；依赖及模型分别适用自身许可。

| 组件 | 用途 | 上游许可 |
| --- | --- | --- |
| [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) | PDF、渲染、有线表格 | AGPL／商业双许可 |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | 可选 OCR | Apache-2.0，模型另查来源声明 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | 可选 CPU 推理 | MIT |

模型与字典不打包进 Pai，首次 OCR 可能下载；缓存应保留上游归属信息，具体以 [RapidOCR 文档](https://rapidai.github.io/RapidOCRDocs/main/) 与模型来源为准。OCR 安装另有传递依赖，本表不是完整 SBOM。

参考 [Docling 架构](https://docling-project.github.io/docling/concepts/architecture/) 的后端、流水线、统一文档与导出分层；没有复制其源码或打包模型，也不将其作为运行依赖。
