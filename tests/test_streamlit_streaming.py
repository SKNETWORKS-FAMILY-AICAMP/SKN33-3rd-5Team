from __future__ import annotations

import pytest

from streamlit_app.streaming import iter_text_chunks


def test_streaming_chunks_reconstruct_the_validated_answer() -> None:
    answer = "공식 문서에서 확인했습니다. [C1]\n\n`sudo raspi-config`를 실행하세요."

    chunks = list(iter_text_chunks(answer, words_per_chunk=2, delay_seconds=0))

    assert len(chunks) > 1
    assert "".join(chunks) == answer


@pytest.mark.parametrize(
    ("words_per_chunk", "delay_seconds"),
    [(0, 0), (1, -0.1)],
)
def test_streaming_rejects_invalid_options(
    words_per_chunk: int,
    delay_seconds: float,
) -> None:
    with pytest.raises(ValueError):
        list(
            iter_text_chunks(
                "answer",
                words_per_chunk=words_per_chunk,
                delay_seconds=delay_seconds,
            )
        )
