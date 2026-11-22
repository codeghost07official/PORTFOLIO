"""Split long Markdown/text into overlapping, heading-aware chunks."""
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_text(text, size=900, overlap=150):
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    # split into blocks on blank lines, keeping fenced code blocks intact
    blocks, buf, in_code = [], [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if not line.strip() and not in_code:
            if buf:
                blocks.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        blocks.append("\n".join(buf))

    chunks, current, heading = [], "", ""
    for block in blocks:
        m = _HEADING.match(block.splitlines()[0])
        if m:
            heading = m.group(2).strip()
        while len(block) > size:  # hard-split giant blocks
            cut = block.rfind(" ", 0, size) if " " in block[:size] else size
            cut = cut if cut > size // 2 else size
            piece, block = block[:cut], block[cut - overlap if cut > overlap else cut:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(piece)
        if len(current) + len(block) + 2 > size and current:
            chunks.append(current)
            tail = current[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            prefix = f"[{heading}] " if heading and not block.startswith("#") else ""
            current = (prefix + tail + "\n\n" + block).strip()
        else:
            current = (current + "\n\n" + block).strip() if current else block
    if current:
        chunks.append(current)
    return chunks
