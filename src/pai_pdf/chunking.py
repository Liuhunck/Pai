"""Deterministic character-bounded chunks with exact source text offsets."""


def chunk_document(document, max_chars=1600, *, include_furniture=False):
    """Split within sections; offsets refer to block text, not PDF byte offsets.

    Character bounds avoid a tokenizer dependency. Tables may span multiple chunks;
    their complete grid remains in document.json. No overlap or text rewriting.
    """
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    chunks = []
    text, sources, section = "", [], None

    def flush():
        nonlocal text, sources
        if sources:
            chunks.append(
                {
                    "id": f"chunk-{len(chunks) + 1:05d}",
                    "document_id": document["document_id"],
                    "text": text,
                    "section_path": section or [],
                    "sources": sources,
                }
            )
            text, sources = "", []

    for page in document["pages"]:
        for block in page["blocks"]:
            if not include_furniture and block.get("role") in {"header", "footer"}:
                continue
            path = block.get("section_path", [])
            if section != path:
                flush()
                section = path
            value = block["text"]
            offset = 0
            while offset < len(value):
                separator = "\n\n" if text else ""
                available = max_chars - len(text) - len(separator)
                if available <= 0:
                    flush()
                    continue
                end = min(len(value), offset + available)
                # Prefer a word boundary when splitting a long block.
                if end < len(value):
                    boundary = value.rfind(" ", offset, end)
                    if boundary > offset:
                        end = boundary + 1
                text += separator + value[offset:end]
                sources.append(
                    {
                        "page": page["number"],
                        "block_id": block["id"],
                        "bbox": block["bbox"],
                        "start": offset,
                        "end": end,
                    }
                )
                offset = end
                if offset < len(value):
                    flush()
    flush()
    return chunks
