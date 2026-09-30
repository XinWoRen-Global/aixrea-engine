"""Drama Developer adapter.

Wraps the existing PipelineExecutor (app/gateway/pipeline_executor.py)
to satisfy the HohDeveloper protocol. The real executor is album-based
and expects an existing album_id + user_id; this adapter is the bridge.

Phase 1: interface only. Real wiring requires:
  - an album row in studio_albums
  - a user_id with credits
  - PipelineExecutor instance injected via DI
  - polling execute_phase() until completion

Until then, the adapter raises NotImplementedError so callers know
exactly what's missing.
"""

from __future__ import annotations

from typing import Any

from .types import Artifact, DevDoc


class DramaDeveloper:
    """Adapts PipelineExecutor to HohDeveloper."""

    def __init__(self, executor: Any = None) -> None:
        self._executor = executor  # PipelineExecutor, injected at runtime

    async def develop(self, current: Artifact, spec: str, dev_doc: DevDoc) -> Artifact:
        if self._executor is None:
            # Dry-run / skeleton: echo the dev_doc as a new artifact.
            # This lets us test the loop contract without a real pipeline.
            return Artifact(
                module=dev_doc.module,
                version=current.version + 1,
                payload={
                    "increment": dev_doc.scope,
                    "acceptance": dev_doc.acceptance,
                    "preserve": dev_doc.preserve,
                    "note": "dry-run: no PipelineExecutor wired",
                },
                notes=f"hoh-loop-{dev_doc.iteration}",
            )

        # Real path (TODO Phase 2):
        # 1. create or reuse an album row with dev_doc.scope
        # 2. call self._executor.execute_album(album_id)
        # 3. poll until status in {completed, failed}
        # 4. collect metrics (duration, subtitle_sync, copyright_score)
        # 5. return Artifact with those metrics
        raise NotImplementedError("Real PipelineExecutor wiring pending. Inject an album_id and user_id.")
