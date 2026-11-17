import re

FIXED_SIZE = 500
FIXED_OVERLAP = 50
MAX_SECTION_CHARS = 900


def chunk_fixed(doc, text):
    chunks = []
    step = FIXED_SIZE - FIXED_OVERLAP
    for n, start in enumerate(range(0, len(text), step)):
        piece = text[start:start + FIXED_SIZE].strip()
        if piece:
            chunks.append({"id": f"{doc}#{n}", "source": doc, "heading": "", "text": piece})
    return chunks


def _split_long(body):
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        if current and len(current) + len(para) > MAX_SECTION_CHARS:
            parts.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        parts.append(current.strip())
    return parts


def chunk_by_heading(doc, text):
    title, section, buf = doc, "", []
    sections = []
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((section, "\n".join(buf)))
            section, buf = line[3:].strip(), []
        else:
            buf.append(line)
    sections.append((section, "\n".join(buf)))

    chunks = []
    for heading, body in sections:
        body = body.strip()
        if not body:
            continue
        for part in _split_long(body):
            label = f"{title} > {heading}" if heading else title
            chunks.append({
                "id": f"{doc}#{len(chunks)}",
                "source": doc,
                "heading": heading or title,
                "text": f"{label}\n{part}",
            })
    return chunks


def make_chunks(doc, text, mode):
    if mode == "fixed":
        return chunk_fixed(doc, text)
    if mode == "heading":
        return chunk_by_heading(doc, text)
    raise ValueError(f"unknown chunking mode: {mode}")
