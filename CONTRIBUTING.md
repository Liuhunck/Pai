# 贡献规范

使用 Python 3.11+、`src/` 布局和 `pip install -e ".[dev]"` 开发环境。提交前运行：

```bash
python examples/make_sample.py
ruff check .
ruff format --check .
pytest -q
python -m build
```

版面/文字规则修改需增加体现文字丢失、顺序或定位偏差的回归样例，优先现场生成 PDF。真实样本需有再分发许可，不提交私人文档、输出、模型、缓存或环境。

后端放在 `backends/`，编排放在 `parser.py`，论文语义与 PDF 库解耦。新模型采用可选依赖与延迟加载；异常必须进入报告，不得静默丢弃内容。API、坐标和序列化变化同步文档。

PR 写清问题、变化后的行为、验证结果与边界。质量提升附固定语料评测，性能提升附环境与配置。
