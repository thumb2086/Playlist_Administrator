from core.pipeline import PipelineStep, PipelineState
from core.library import prune_missing_from_playlists


class StepPrune(PipelineStep):
    """Remove missing tracks from playlists."""

    @property
    def name(self):
        return "Prune missing tracks"

    @property
    def weight(self):
        return 15.0

    def run(self, state: PipelineState):
        config = state.config
        log_func = state.log_func

        if not state.wait_if_paused() or state.is_cancelled():
            return False

        state.progress_cb(self.name, 0, 1, "Pruning…")
        try:
            removed = prune_missing_from_playlists(
                config, log_func,
                pause_event=state.pause_event,
                stop_event=state.stop_event,
            )
        except Exception as e:
            log_func(f"Prune 失敗: {e}")
            return False

        state.progress_cb(self.name, 1, 1, "Done")
        return True
