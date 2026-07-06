"""Explicit job-stage state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sprite_builder.domain.errors import StageTransitionError


class Stage(StrEnum):
    CHARACTER = "character"
    GENERATION = "generation"
    CONSISTENCY = "consistency"
    POSTPROCESS = "postprocess"
    ALIGNMENT = "alignment"
    EXPORT = "export"


ORDERED_STAGES = tuple(Stage)


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"


@dataclass(slots=True)
class JobState:
    job_id: str
    statuses: dict[Stage, StageStatus] = field(
        default_factory=lambda: {stage: StageStatus.PENDING for stage in ORDERED_STAGES}
    )

    def start(self, stage: Stage) -> None:
        current = self.statuses[stage]
        if current not in {StageStatus.PENDING, StageStatus.FAILED}:
            raise StageTransitionError(f"Cannot start {stage}: current status is {current}")
        position = ORDERED_STAGES.index(stage)
        blockers = [
            previous
            for previous in ORDERED_STAGES[:position]
            if self.statuses[previous] != StageStatus.PASSED
        ]
        if blockers:
            raise StageTransitionError(f"Cannot start {stage}; blocked by {blockers}")
        self.statuses[stage] = StageStatus.RUNNING

    def finish(self, stage: Stage, status: StageStatus) -> None:
        if self.statuses[stage] != StageStatus.RUNNING:
            raise StageTransitionError(f"Cannot finish {stage}: stage is not running")
        if status not in {
            StageStatus.PASSED,
            StageStatus.MANUAL_REVIEW,
            StageStatus.FAILED,
        }:
            raise StageTransitionError(f"Invalid terminal status: {status}")
        self.statuses[stage] = status

    @property
    def complete(self) -> bool:
        return all(status == StageStatus.PASSED for status in self.statuses.values())
