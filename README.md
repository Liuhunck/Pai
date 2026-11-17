# Pai — PDF extractor for AI

面向论文的轻量、本地 PDF 提取工具，输出 Markdown、结构化 JSON 和可追溯的 AI 文本分块。

**当前为 0.1.0 基础版本**：原生文字优先，扫描区域按需 OCR；默认不依赖 PyTorch、Docling 或大语言模型。论文结构使用几何与字体规则推断，尚未完成真实论文语料的质量基准，不宣称达到 Docling 的复杂版面识别效果。

## 安装与运行

Python 3.11+，在仓库根目录执行（项目尚未发布到 PyPI）：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# 电子论文：完全不使用 OCR 模型
pai paper.pdf --ocr off

# 可选 OCR：按需处理扫描页和嵌入图片
python -m pip install -e ".[ocr]"
pai paper.pdf --ocr auto

# 可重复运行的本地样例
python examples/make_sample.py
pai examples/sample.pdf --ocr off
```

原生提取只有 PyMuPDF 一个直接运行依赖。OCR 增加 RapidOCR、ONNX Runtime 及其传递依赖；模型延迟加载，首次使用可能下载。通过 `--models /path/to/models` 指定自有模型，默认缓存于 `$XDG_CACHE_HOME/pai/rapidocr` 或 `~/.cache/pai/rapidocr`。PDF 不会发送到远程服务。

默认处理所有页，每次创建独立的 `output/<文件名>-<随机后缀>/` 目录。`python -m pai_pdf` 与 `pai` 等价。

```bash
pai scan.pdf --ocr force --max-pages 5 --threads 2
pai paper.pdf --ocr off --no-images --no-tables --output results
pai --help
```

`auto` 优先原生文字，按需 OCR；`off` 不加载 OCR；`force` 对非空白页执行整页 OCR。未安装 OCR 时纯文字 PDF 仍可处理；需要 OCR 的区域会记录错误，保留已有文字并报告部分成功。

## Python API

```python
from pai_pdf import Options, convert
from pai_pdf.chunking import chunk_document

document = convert(
    "paper.pdf",
    "results/my-paper",  # 必须不存在或为空，防止覆盖既有输出
    options=Options(ocr="off", images=False),
)
chunks = chunk_document(document, max_chars=1200)
print(document["status"], len(chunks))
```

低层接口 `pai_pdf.parser.parse_document` 构建文档并按配置输出插图；`pai_pdf.export.write_outputs` 负责序列化。`convert` 支持注入实现 `OcrProvider` 协议的 `ocr_engine`。

## 输出

| 文件 | 用途 |
| --- | --- |
| `document.md` | 阅读与检索，含页码和内容块定位注释 |
| `document.json` | 原始行、内容块、章节路径、表格网格、位置和质量信息 |
| `chunks.jsonl` | 按章节分块，默认最多 1600 字符，保留来源块与字符偏移 |
| `report.json` | 状态、耗时、OCR 次数、逐页问题；CLI 另记录进程峰值 RSS |
| `assets/` | 嵌入位图区域的裁剪图，不重复导出整页扫描背景 |

页码从 1 开始；坐标为未旋转可见页左上原点，单位 pt。分块默认跳过已识别的重复页眉页脚，JSON 和 Markdown 仍保留它们。具体字段见 [数据约定](docs/DATA_MODEL.md)。

`status=success` 表示流程完成，不等于文字或结构完全正确；下游应检查 `quality.needs_review`。CLI 退出码：`0` 流程成功，`2` 部分成功/页面失败或参数错误，`1` 文件级失败。

## 能力与边界

| 已实现 | 边界 |
| --- | --- |
| 原生文字、原始行、坐标、异常字符标记 | 不自动改写或补全文字，断行连字符保留 |
| 简单双栏顺序、字体辅助标题、常见中英文章节 | 复杂跨栏、侧注和密集公式需复核 |
| 图表说明、参考文献章节标记 | 不解析作者/DOI 元数据，不关联图号与图像 |
| 有线原生表格、单元格定位、HTML 表格导出 | 不保证无框、扫描、合并单元格及跨页表格恢复 |
| 局部/整页 OCR、位置与文字去重 | 不提供公式 LaTeX 或扫描表格结构 |
| 位图区域导出 | 不检测完整矢量图、复合图和子图 |
| 逐页错误隔离、渲染像素上限 | 文档结果在内存累积，不保证恒定内存 |

## 开发

```bash
python -m pip install -e ".[dev]"
python examples/make_sample.py
ruff check .
ruff format --check .
pytest -q
python -m build
```

真实 OCR 测试需安装 `.[ocr]`，并设置 `PAI_OCR_MODELS` 为已有模型目录；普通 CI 明确跳过这一项，不下载模型。CI 配置覆盖 Python 3.11–3.13。

- [架构与路线](docs/ARCHITECTURE.md)
- [数据约定](docs/DATA_MODEL.md)
- [评估方式](docs/EVALUATION.md)
- [贡献规范](CONTRIBUTING.md)

## 设计参考与许可

参考 [Docling 的后端、流水线、统一文档和导出分层](https://docling-project.github.io/docling/concepts/architecture/)，按论文提取场景收敛依赖和功能。Pai 不调用 Docling，也不包含其模型或代码。

本仓库源码沿用 [Apache-2.0](LICENSE)。第三方依赖各自适用其许可：**PyMuPDF 为 AGPL／商业双许可**，不能将完整依赖栈视为 Apache-2.0；详见 [依赖与模型说明](THIRD_PARTY.md)。
