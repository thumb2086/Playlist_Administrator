import os
import time
import signal
import threading
from abc import ABC, abstractmethod


class PipelineState:
    """Shared state flowing through all pipeline steps.

    Attributes
    ----------
    config : dict
        The application config.
    log_func : callable
        ``log_func(message)`` — called for every progress / status message.
    progress_cb : callable or None
        ``progress_cb(step_name, current, total, message)`` — called after
        every meaningful amount of work within a step.  *current* and *total*
        are integers (0‑based); *step_name* is the human‑readable step label.
    pause_event : threading.Event
        When cleared, the pipeline should pause.  Set to resume.
    stop_event : threading.Event
        When set, the pipeline should abort asap.
    status_cb : callable or None
        ``status_cb(index, status, name)`` — fine‑grained item‑level status.
    killed_pids : list[int]
        List of subprocess PIDs that were forcibly killed on cancel.
    """
    def __init__(self, config, log_func, progress_cb=None,
                 pause_event=None, stop_event=None, status_cb=None):
        self.config = config
        self.log_func = log_func
        self.progress_cb = progress_cb or (lambda *a: None)
        self.pause_event = pause_event or threading.Event()
        self.pause_event.set()
        self.stop_event = stop_event or threading.Event()
        self.status_cb = status_cb
        self.killed_pids = []

    def is_cancelled(self):
        return self.stop_event.is_set()

    def is_paused(self):
        return not self.pause_event.is_set()

    def wait_if_paused(self):
        while not self.pause_event.is_set():
            if self.stop_event.is_set():
                return False
            self.pause_event.wait(0.2)
        return not self.stop_event.is_set()


class PipelineStep(ABC):
    """Base class for a single, cancellable pipeline step."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human‑readable name (e.g. \"Convert M4A → MP3\")."""

    @property
    @abstractmethod
    def weight(self) -> float:
        """Relative weight of this step in the overall progress (0‑100)."""

    @abstractmethod
    def run(self, state: PipelineState) -> bool:
        """Execute the step.  Return False if cancelled."""


class PipelineOrchestrator:
    """Runs a sequence of PipelineStep instances with shared state.

    Usage::

        orch = PipelineOrchestrator(config)
        orch.run(state)

    or for a single step::

        orch.run_step(2, state)          # run step index 2 only
        orch.run_step("scrape", state)   # run step named "scrape"
    """

    def __init__(self, config):
        self.config = config
        self.steps = []  # filled by _build_steps()

    def _build_steps(self):
        """Return the ordered list of PipelineStep instances."""
        from core.steps.step_convert import StepConvert
        from core.steps.step_scrape import StepScrape
        from core.steps.step_prune import StepPrune
        from core.steps.step_unsorted import StepUnsorted
        from core.steps.step_metadata import StepMetadata

        return [
            StepConvert(),
            StepScrape(),
            StepPrune(),
            StepUnsorted(),
            StepMetadata(),
        ]

    def _reset_killed_pids(self, state):
        state.killed_pids.clear()

    def run(self, state: PipelineState, from_step: int = 0):
        """Run all steps starting at *from_step*."""
        self.steps = self._build_steps()
        self._reset_killed_pids(state)

        for idx, step in enumerate(self.steps):
            if idx < from_step:
                continue
            state.log_func(f"--- Step {idx + 1}/{len(self.steps)}: {step.name} ---")
            ok = step.run(state)
            if not ok or state.is_cancelled():
                state.log_func("Pipeline cancelled.")
                return False
        state.log_func("Pipeline complete.")
        return True

    def run_step(self, target, state: PipelineState):
        """Run a single step identified by index (int) or name (str)."""
        self.steps = self._build_steps()
        self._reset_killed_pids(state)

        if isinstance(target, int):
            step = self.steps[target]
        else:
            matches = [s for s in self.steps if s.name == target]
            step = matches[0] if matches else None
            if not step:
                state.log_func(f"Unknown step: {target}")
                return False
        state.log_func(f"--- Single step: {step.name} ---")
        return step.run(state)

    def list_steps(self):
        self.steps = self._build_steps()
        return [(i, s.name, s.weight) for i, s in enumerate(self.steps)]
