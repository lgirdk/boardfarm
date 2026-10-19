"""A controllable SessionMode for agent tests."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, ClassVar

from boardfarm3.api.modes import ModeRequestError, SessionMode

if TYPE_CHECKING:
    from boardfarm3.api.modes import ModeContext


class FakeMode(SessionMode):
    """Runs nothing; the test decides when it ends.

    ``run`` keys steer it: ``bad`` fails validation, ``explode`` fails start.
    """

    stream_name = "fake"
    instances: ClassVar[list[FakeMode]] = []

    def __init__(self, context: ModeContext) -> None:
        """Remember the context and register this instance.

        :param context: what the session hands the mode
        :type context: ModeContext
        """
        super().__init__(context)
        self.cancel_calls = 0
        self._since: float | None = None
        self._ended = False
        FakeMode.instances.append(self)

    def validate(self) -> None:
        """Refuse a run carrying ``bad``."""
        if self.context.run.get("bad"):
            msg = "bad run"
            raise ModeRequestError(msg)

    async def start(self) -> None:
        """Start, or fail like a missing binary when the run carries ``explode``."""
        if self.context.run.get("explode"):
            msg = "cannot spawn"
            raise OSError(msg)
        self._since = time.time()

    def status(self) -> dict[str, Any]:
        """Report the fake run."""
        return {"state": "finished" if self._ended else "running", "fake": True}

    def running_since(self) -> float | None:
        """Return the start time while running."""
        return None if self._ended else self._since

    async def cancel(self) -> bool:
        """End the run if it is still going."""
        self.cancel_calls += 1
        if self._ended or self._since is None:
            return False
        self.end()
        return True

    async def wait(self) -> None:
        """Nothing to wait for."""

    def end(self) -> None:
        """Finish the run the way a real mode does."""
        self._ended = True
        self.context.finished()
