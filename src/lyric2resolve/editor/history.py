"""Undo/redo with project snapshots (simple and robust; projects are small JSON)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from lyric2resolve.project import Project


@dataclass
class History:
    limit: int = 200
    undo_stack: list[tuple[str, dict]] = field(default_factory=list)
    redo_stack: list[tuple[str, dict]] = field(default_factory=list)

    def record(self, label: str, before: Project) -> None:
        """Call BEFORE applying an edit, with the current project."""
        self.undo_stack.append((label, copy.deepcopy(before.to_dict())))
        if len(self.undo_stack) > self.limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def discard_last(self) -> None:
        """The edit failed: drop the snapshot recorded for it."""
        if self.undo_stack:
            self.undo_stack.pop()

    def undo(self, current: Project) -> tuple[str, Project] | None:
        if not self.undo_stack:
            return None
        label, snap = self.undo_stack.pop()
        self.redo_stack.append((label, copy.deepcopy(current.to_dict())))
        return label, Project.from_dict(snap)

    def redo(self, current: Project) -> tuple[str, Project] | None:
        if not self.redo_stack:
            return None
        label, snap = self.redo_stack.pop()
        self.undo_stack.append((label, copy.deepcopy(current.to_dict())))
        return label, Project.from_dict(snap)

    def state(self) -> dict:
        return {"can_undo": bool(self.undo_stack), "can_redo": bool(self.redo_stack),
                "undo_label": self.undo_stack[-1][0] if self.undo_stack else None,
                "redo_label": self.redo_stack[-1][0] if self.redo_stack else None}
