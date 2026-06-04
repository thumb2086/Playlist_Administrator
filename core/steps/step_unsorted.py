from core.pipeline import PipelineStep, PipelineState
from core.library import move_unsorted_songs


class StepUnsorted(PipelineStep):
    """Scan and organize unsorted songs."""

    @property
    def name(self):
        return "Organize unsorted songs"

    @property
    def weight(self):
        return 10.0

    def run(self, state: PipelineState):
        config = state.config
        log_func = state.log_func

        if not state.wait_if_paused() or state.is_cancelled():
            return False

        state.progress_cb(self.name, 0, 1, "Scanning…")
        try:
            move_unsorted_songs(config, log_func)
        except Exception as e:
            log_func(f"整理未分類歌曲失敗: {e}")

        state.progress_cb(self.name, 1, 1, "Done")
        return True
