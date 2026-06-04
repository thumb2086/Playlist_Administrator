from core.pipeline import PipelineStep, PipelineState
from core.metadata_enricher import create_metadata_enricher


class StepMetadata(PipelineStep):
    """Optional metadata enrichment (config: enable_metadata_enrichment)."""

    @property
    def name(self):
        return "Enrich metadata"

    @property
    def weight(self):
        return 10.0

    def run(self, state: PipelineState):
        config = state.config
        log_func = state.log_func

        if not config.get("enable_metadata_enrichment", False):
            log_func("Metadata enrichment 未啟用，跳過。")
            state.progress_cb(self.name, 1, 1, "Skipped")
            return True

        if not state.wait_if_paused() or state.is_cancelled():
            return False

        library_path = config.get("library_path", "")
        log_func("強化元資料…")

        try:
            enricher = create_metadata_enricher(config)

            def meta_progress(current, total):
                state.progress_cb(self.name, current, total or 1,
                                  f"{current}/{total}")
                state.wait_if_paused()

            enricher.enrich_library_metadata(library_path, log_func, meta_progress)
            enricher.cleanup()
        except Exception as e:
            log_func(f"Metadata enrichment 失敗: {e}")

        state.progress_cb(self.name, 1, 1, "Done")
        return True
