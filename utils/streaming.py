"""把整段文本切成小块，供 A2A/SSE 流式输出使用。"""


def chunk_text(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i:i + size]
