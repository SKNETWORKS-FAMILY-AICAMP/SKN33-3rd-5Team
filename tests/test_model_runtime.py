from __future__ import annotations

import pytest

from src.model_runtime import InferenceDeviceError, resolve_inference_runtime


class FakeCuda:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available


class FakeMps:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available


class FakeTorch:
    bfloat16 = "bfloat16"
    float16 = "float16"
    float32 = "float32"

    def __init__(self, *, cuda: bool, mps: bool) -> None:
        self.cuda = FakeCuda(cuda)
        self.backends = type("Backends", (), {"mps": FakeMps(mps)})()


def test_auto_prefers_cuda_and_keeps_4bit() -> None:
    runtime = resolve_inference_runtime(FakeTorch(cuda=True, mps=True), load_in_4bit=True)

    assert runtime.device == "cuda"
    assert runtime.dtype == "bfloat16"
    assert runtime.load_in_4bit is True


def test_auto_uses_mps_and_disables_cuda_only_4bit() -> None:
    runtime = resolve_inference_runtime(FakeTorch(cuda=False, mps=True), load_in_4bit=True)

    assert runtime.device == "mps"
    assert runtime.dtype == "float16"
    assert runtime.load_in_4bit is False


def test_auto_falls_back_to_cpu() -> None:
    runtime = resolve_inference_runtime(
        FakeTorch(cuda=False, mps=False),
        requested_device="auto",
        load_in_4bit=True,
    )

    assert runtime.device == "cpu"
    assert runtime.dtype == "float32"
    assert runtime.load_in_4bit is False


def test_msp_alias_selects_mps_when_available() -> None:
    runtime = resolve_inference_runtime(
        FakeTorch(cuda=False, mps=True),
        requested_device="msp",
    )

    assert runtime.device == "mps"


@pytest.mark.parametrize(
    ("requested", "message"),
    [("cuda", "CUDA is unavailable"), ("mps", "Apple MPS is unavailable"), ("bad", "INFERENCE_DEVICE")],
)
def test_explicit_unavailable_or_invalid_device_is_rejected(requested, message) -> None:
    with pytest.raises(InferenceDeviceError, match=message):
        resolve_inference_runtime(
            FakeTorch(cuda=False, mps=False),
            requested_device=requested,
        )
