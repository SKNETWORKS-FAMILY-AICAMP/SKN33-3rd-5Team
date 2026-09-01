"""Safe presentation streaming for already validated chatbot responses."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator


WORD_WITH_SPACE = re.compile(r"\S+\s*|\s+")


def iter_text_chunks(
    text: str,
    *,
    words_per_chunk: int = 2,
    delay_seconds: float = 0.012,
) -> Iterator[str]:
    """Yield a validated answer in small chunks for a typewriter-style UI.

    The service completes grounding and citation validation before this helper is
    called.  This prevents an unverified partial answer from reaching the user.
    """

    if words_per_chunk < 1:
        raise ValueError("words_per_chunk must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must not be negative")

    tokens = WORD_WITH_SPACE.findall(text)
    for index in range(0, len(tokens), words_per_chunk):
        yield "".join(tokens[index : index + words_per_chunk])
        if delay_seconds:
            time.sleep(delay_seconds)


__all__ = ["iter_text_chunks"]
