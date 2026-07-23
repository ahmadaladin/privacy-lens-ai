"""Shared domain models for detections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Pixel coordinates using an exclusive bottom-right corner."""

    x1: int
    y1: int
    x2: int
    y2: int

    def clipped(self, width: int, height: int) -> BoundingBox:
        """Return the box clipped to image boundaries."""

        return BoundingBox(
            x1=max(0, min(self.x1, width)),
            y1=max(0, min(self.y1, height)),
            x2=max(0, min(self.x2, width)),
            y2=max(0, min(self.y2, height)),
        )

    @property
    def is_empty(self) -> bool:
        return self.x2 <= self.x1 or self.y2 <= self.y1

    def as_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]


@dataclass(frozen=True, slots=True)
class Detection:
    """A sensitive region produced by a detector."""

    kind: str
    box: BoundingBox
    score: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "score": None if self.score is None else round(float(self.score), 4),
            "box": self.box.as_list(),
        }
