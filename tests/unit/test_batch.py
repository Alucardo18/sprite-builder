from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from sprite_builder.batch import BatchSpec, batch_status, prepare_batch
from sprite_builder.cli import main
from sprite_builder.domain.errors import ConfigurationError
from tests.unit.test_domain import valid_job_dict


def batch_dict() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "batch": {"id": "multi-character"},
        "characters": [
            {"id": "hero", "jobs": ["configs/hero-walk.json", "configs/hero-idle.json"]},
            {"id": "enemy", "jobs": ["configs/enemy-walk.json", "configs/enemy-attack.json"]},
        ],
    }


def write_batch_workspace(root: Path) -> None:
    (root / "configs").mkdir()
    (root / "prompts").mkdir()
    (root / "characters/hero").mkdir(parents=True)
    (root / "characters/enemy").mkdir(parents=True)
    (root / "prompts/animation_frame.jinja2").write_text(
        "{{ character_description }} {{ animation }} {{ direction }} {{ phase }} "
        "{{ background_color }}",
        encoding="utf-8",
    )
    bible = {
        "identity": {
            "name": "Fixture",
            "immutable_features": ["fixed silhouette"],
            "forbidden_changes": ["drift"],
        },
        "visual_rules": {"outline": "crisp"},
    }
    for character_id in ("hero", "enemy"):
        (root / f"characters/{character_id}/bible.json").write_text(
            json.dumps(bible), encoding="utf-8"
        )
        for animation in ("walk", "idle") if character_id == "hero" else ("walk", "attack"):
            job = valid_job_dict()
            job["job"] = {"id": f"{character_id}-{animation}"}
            job["character"] = {
                "id": character_id,
                "bible": f"characters/{character_id}/bible.json",
                "references": [],
            }
            job["animation"]["name"] = animation  # type: ignore[index]
            job["animation"]["frame_count"] = 1  # type: ignore[index]
            job["animation"]["phases"] = ["key"]  # type: ignore[index]
            job["generation"]["candidates_per_frame"] = 1  # type: ignore[index]
            (root / f"configs/{character_id}-{animation}.json").write_text(
                json.dumps(job), encoding="utf-8"
            )


class BatchSpecTests(unittest.TestCase):
    def test_counts_derive_from_character_and_job_lists(self) -> None:
        spec = BatchSpec.from_dict(batch_dict())
        self.assertEqual(spec.character_count, 2)
        self.assertEqual(spec.animation_count, 4)

    def test_rejects_duplicate_characters_and_jobs(self) -> None:
        duplicate_character = batch_dict()
        duplicate_character["characters"][1]["id"] = "hero"  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "unique"):
            BatchSpec.from_dict(duplicate_character)

        duplicate_job = batch_dict()
        duplicate_job["characters"][1]["jobs"][0] = "configs/hero-walk.json"  # type: ignore[index]
        with self.assertRaisesRegex(ConfigurationError, "only once"):
            BatchSpec.from_dict(duplicate_job)

    def test_validates_job_character_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_batch_workspace(root)
            spec = BatchSpec.from_dict(batch_dict())
            job = json.loads((root / "configs/enemy-walk.json").read_text(encoding="utf-8"))
            job["character"]["id"] = "hero"
            (root / "configs/enemy-walk.json").write_text(json.dumps(job), encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "does not match"):
                spec.load_jobs(root)

    def test_prepare_and_status_cover_all_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_batch_workspace(root)
            spec = BatchSpec.from_dict(batch_dict())
            prepared = prepare_batch(spec, workspace=root)
            self.assertEqual(prepared["character_count"], 2)
            self.assertEqual(prepared["animation_count"], 4)
            self.assertEqual(prepared["request_count"], 4)

            initial = batch_status(spec, workspace=root)
            self.assertEqual(initial["pending"], 4)
            self.assertEqual(initial["ingested"], 0)

            request_dir = root / "jobs/hero-walk/generation/requests"
            index = json.loads((request_dir / "index.json").read_text(encoding="utf-8"))
            request = json.loads(
                (request_dir / f"{index['request_ids'][0]}.json").read_text(encoding="utf-8")
            )
            raw = root / "jobs/hero-walk/raw" / request["output_filename"]
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"ingested fixture")

            resumed = batch_status(spec, workspace=root)
            self.assertEqual(resumed["pending"], 3)
            self.assertEqual(resumed["ingested"], 1)
            self.assertEqual(resumed["total"], 4)

    def test_cli_batch_prepare_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_batch_workspace(root)
            batch_path = root / "batch.json"
            batch_path.write_text(json.dumps(batch_dict()), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = main(
                    [
                        "--workspace",
                        str(root),
                        "batch-prepare",
                        "--batch",
                        str(batch_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["request_count"], 4)

            output = StringIO()
            with redirect_stdout(output):
                code = main(
                    [
                        "--workspace",
                        str(root),
                        "batch-status",
                        "--batch",
                        str(batch_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["pending"], 4)


if __name__ == "__main__":
    unittest.main()
