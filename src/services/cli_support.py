"""Shared terminal presentation helpers for service CLI entry points."""

from __future__ import annotations

from contextlib import contextmanager
from itertools import cycle
from threading import Event, Thread
from time import sleep
from typing import Iterator, TextIO


@contextmanager
def loading_indicator(message: str, *, stream: TextIO) -> Iterator[None]:
    """Show progress without corrupting JSON or piped command output."""

    if not stream.isatty():
        print(f"[loading] {message}", file=stream, flush=True)
        yield
        return

    stopped = Event()

    def render() -> None:
        for symbol in cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if stopped.is_set():
                break
            stream.write(f"\r{symbol} {message}")
            stream.flush()
            sleep(0.1)

    thread = Thread(target=render, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=0.2)
        stream.write(f"\r{' ' * (len(message) + 3)}\r")
        stream.flush()


__all__ = ["loading_indicator"]
