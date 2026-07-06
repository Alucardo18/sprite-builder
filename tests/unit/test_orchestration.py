from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sprite_builder.domain.errors import StageTransitionError
from sprite_builder.orchestration.artifacts import (
    ArtifactManifest,
    ArtifactRecord,
    ArtifactStore,
    build_cache_key,
)
from sprite_builder.orchestration.state import JobState, Stage, StageStatus


class ArtifactTests(unittest.TestCase):
    def test_manifest_round_trip_and_cache_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "jobs/demo/raw/frame.png"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"png-like-data")
            record = ArtifactRecord.from_path(output, root=root)
            cache_key = build_cache_key(stage="generation", config={"version": 1}, inputs=())
            manifest = ArtifactManifest(
                schema_version="1.0",
                job_id="demo",
                stage="generation",
                status="passed",
                cache_key=cache_key,
                outputs=(record,),
            )
            store = ArtifactStore(root)
            store.write_manifest(manifest)
            self.assertTrue(store.cache_hit("demo", "generation", cache_key))
            output.write_bytes(b"changed")
            self.assertFalse(store.cache_hit("demo", "generation", cache_key))


class StateTests(unittest.TestCase):
    def test_enforces_order(self) -> None:
        state = JobState("demo")
        with self.assertRaises(StageTransitionError):
            state.start(Stage.GENERATION)
        state.start(Stage.CHARACTER)
        state.finish(Stage.CHARACTER, StageStatus.PASSED)
        state.start(Stage.GENERATION)
        self.assertEqual(state.statuses[Stage.GENERATION], StageStatus.RUNNING)

    def test_manual_review_blocks_next_stage(self) -> None:
        state = JobState("demo")
        state.start(Stage.CHARACTER)
        state.finish(Stage.CHARACTER, StageStatus.MANUAL_REVIEW)
        with self.assertRaises(StageTransitionError):
            state.start(Stage.GENERATION)


if __name__ == "__main__":
    unittest.main()
