"""PyTorch 추론 백엔드를 CUDA, Apple MPS, CPU 사이에서 일관되게 선택한다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


DeviceName = Literal["cuda", "mps", "cpu"]


class InferenceDeviceError(ValueError):
    """요청한 추론 백엔드를 현재 환경에서 사용할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class InferenceRuntime:
    """모델 로더가 사용할 장치·dtype·유효 양자화 설정이다."""

    device: DeviceName
    dtype: object
    load_in_4bit: bool


def _mps_available(torch: object) -> bool:
    backend = getattr(getattr(torch, "backends", None), "mps", None)
    checker = getattr(backend, "is_available", None)
    return bool(checker()) if callable(checker) else False


def normalize_inference_device(value: str) -> str:
    """환경변수의 장치값을 검증하고 `msp` 오타는 `mps`로 정규화한다."""

    normalized = value.strip().lower()
    # 사용자가 흔히 쓰는 오타도 MPS로 해석해 Apple Silicon 로컬 실행을 막지 않는다.
    if normalized == "msp":
        normalized = "mps"
    if normalized not in {"auto", "cuda", "mps", "cpu"}:
        raise InferenceDeviceError(
            "INFERENCE_DEVICE must be one of 'auto', 'cuda', 'mps', or 'cpu'."
        )
    return normalized


def resolve_inference_runtime(
    torch: object,
    *,
    requested_device: str = "auto",
    load_in_4bit: bool = True,
) -> InferenceRuntime:
    """현재 PyTorch 환경과 요청값에서 안전한 모델 로딩 설정을 만든다.

    ``auto``는 CUDA, MPS, CPU 순으로 선택한다. BitsAndBytes 4-bit 양자화는 CUDA에서만
    지원하므로 MPS·CPU에서는 전체 정밀도 로딩으로 자동 전환한다.
    """

    requested = normalize_inference_device(requested_device)
    cuda_available = bool(getattr(getattr(torch, "cuda", None), "is_available", lambda: False)())
    mps_available = _mps_available(torch)

    if requested == "auto":
        device: DeviceName = "cuda" if cuda_available else "mps" if mps_available else "cpu"
    else:
        device = requested  # type: ignore[assignment]
        if device == "cuda" and not cuda_available:
            raise InferenceDeviceError(
                "INFERENCE_DEVICE=cuda was requested, but CUDA is unavailable. "
                "Use auto, mps, or cpu instead."
            )
        if device == "mps" and not mps_available:
            raise InferenceDeviceError(
                "INFERENCE_DEVICE=mps was requested, but Apple MPS is unavailable. "
                "Use auto, cuda, or cpu instead."
            )

    dtype = (
        getattr(torch, "bfloat16")
        if device == "cuda"
        else getattr(torch, "float16")
        if device == "mps"
        else getattr(torch, "float32")
    )
    return InferenceRuntime(
        device=device,
        dtype=dtype,
        load_in_4bit=load_in_4bit and device == "cuda",
    )


__all__ = [
    "DeviceName",
    "InferenceDeviceError",
    "InferenceRuntime",
    "normalize_inference_device",
    "resolve_inference_runtime",
]
