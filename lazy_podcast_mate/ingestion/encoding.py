"""Text decoding with a UTF-8 preference and safe fallback.

We keep this hand-rolled (no `chardet` dependency) because the vast majority
of modern articles are UTF-8 and the fallback list covers the realistic
non-UTF-8 cases our target audience will see.
"""

from __future__ import annotations

from .errors import IngestionError

_FALLBACK_ENCODINGS = ("utf-8-sig", "gbk", "gb18030", "big5", "latin-1")


def decode_bytes(data: bytes, source_path: str) -> tuple[str, str]:
    """Return (decoded_text, encoding_used). Raise `IngestionError` on failure.

    Tries UTF-8 first (strict), then a short list of common fallbacks.
    `latin-1` never fails to decode, so we only accept it when the resulting
    text contains predominantly printable characters.
    """
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    for enc in _FALLBACK_ENCODINGS:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc == "latin-1" and not _looks_like_text(text):
            continue
        return text, enc

    raise IngestionError(
        f"cannot decode {source_path!r}: not valid UTF-8 and no fallback encoding matched"
    )


def _looks_like_text(text: str) -> bool:
    if not text:
        return False
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t ")
    return printable / len(text) > 0.9
