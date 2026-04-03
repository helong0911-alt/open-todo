"""
Base class for outbox-style polling workers.

Extracts the common poll-loop, exponential-backoff retry, and graceful
shutdown logic shared by :mod:`outbox` (webhook delivery) and
:mod:`email_worker` (SMTP delivery).

Subclasses override ``_poll_batch`` to implement task-specific query
and delivery logic.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional


class BaseOutboxWorker(ABC):
    """
    Abstract polling worker with exponential-backoff retry.

    Parameters
    ----------
    name : str
        Human-readable worker name (used in log messages).
    poll_interval : int
        Seconds between poll cycles (default 5).
    max_retries : int
        Maximum delivery attempts before marking a task ``failed`` (default 5).
    """

    def __init__(
        self,
        name: str,
        poll_interval: int = 5,
        max_retries: int = 5,
    ) -> None:
        self.name = name
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.logger = logging.getLogger(f"otd.{name}")
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    @abstractmethod
    async def _poll_batch(self) -> None:
        """
        Query for deliverable tasks and attempt delivery.

        Called once per poll cycle.  Implementations should:
        1. Open a DB session, query for pending tasks (with ``.limit(100)``).
        2. Filter by ``next_retry_at <= now`` or ``next_retry_at IS NULL``.
        3. Attempt delivery for each task.
        4. On success/failure, update the task record accordingly.
        """
        ...

    # ------------------------------------------------------------------
    # Retry math
    # ------------------------------------------------------------------

    @staticmethod
    def backoff_next_retry(retry_count: int) -> datetime:
        """
        Calculate the next retry timestamp using exponential backoff
        (2^n minutes from now).
        """
        delay_minutes = 2 ** retry_count
        return datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Continuously call ``_poll_batch`` until shutdown is signalled."""
        self.logger.info(
            "%s started (poll every %ds)", self.name, self.poll_interval
        )

        while not self._shutdown_event.is_set():
            try:
                await self._poll_batch()
            except Exception:
                self.logger.exception(
                    "%s encountered an error during poll", self.name
                )

            # Wait for next poll or shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=self.poll_interval
                )
                break
            except asyncio.TimeoutError:
                pass

        self.logger.info("%s stopped", self.name)

    # ------------------------------------------------------------------
    # Public start / stop API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the polling loop as a background asyncio task."""
        self._shutdown_event = asyncio.Event()
        self._worker_task = asyncio.create_task(self._poll_loop())
        self.logger.info("%s task created", self.name)

    async def stop(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        if self._worker_task is not None:
            self._shutdown_event.set()
            await self._worker_task
            self._worker_task = None
            self.logger.info("%s task joined", self.name)
