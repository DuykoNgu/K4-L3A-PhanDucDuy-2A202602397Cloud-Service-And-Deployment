"""Đánh dấu shutdown và chuyển tiếp signal cho server đang chạy."""

import signal
from types import FrameType
from typing import Any


class Lifecycle:
    def __init__(self) -> None:
        self.shutting_down = False
        self._previous: dict[int, Any] = {}

    def request_shutdown(
        self, signum: int | None = None, frame: FrameType | None = None
    ) -> None:
        self.shutting_down = True
        previous = self._previous.get(signum)
        if callable(previous):
            previous(signum, frame)

    def install(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous = signal.getsignal(sig)
            if previous != self.request_shutdown:
                self._previous[sig] = previous
                signal.signal(sig, self.request_shutdown)


lifecycle = Lifecycle()
