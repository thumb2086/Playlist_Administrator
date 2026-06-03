from core.pipeline import PipelineStep, PipelineState
from core.library import unblock_files
from core.spotify import scrape_via_spotify_embed
from core.library import UpdateStats


class StepScrape(PipelineStep):
    """Scrape Spotify playlists and rebuild M3U8 files."""

    @property
    def name(self):
        return "Scrape Spotify playlists"

    @property
    def weight(self):
        return 30.0

    def run(self, state: PipelineState):
        config = state.config
        log_func = state.log_func

        if not state.wait_if_paused() or state.is_cancelled():
            return False

        library_path = config.get("library_path", "")
        log_func("清理檔案安全性封鎖…")
        unblock_files(library_path, log_func)

        state.progress_cb(self.name, 0, 100, "Scraping…")

        stats = UpdateStats()
        stats.stop_event = state.stop_event
        stats.pause_event = state.pause_event

        try:
            scrape_via_spotify_embed(config, stats, log_func)
        except Exception as e:
            log_func(f"Scrape 失敗: {e}")
            return False

        state.progress_cb(self.name, 100, 100, "Done")
        return True
