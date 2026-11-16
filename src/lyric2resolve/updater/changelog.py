"""CHANGELOG.md parsing: entries are '## ' headings with free text below.

Newest entries are at the top. The updater shows the entries present in the new
version that are not in the installed one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    heading: str
    body: str

    def render(self) -> str:
        # Plain-text window: drop Markdown emphasis/code marks.
        text = f"{self.heading}\n{'-' * min(len(self.heading), 60)}\n{self.body}".strip()
        return text.replace("**", "").replace("`", "")


def parse(text: str | None) -> list[Entry]:
    entries: list[Entry] = []
    heading: str | None = None
    body: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("## "):
            if heading is not None:
                entries.append(Entry(heading, "\n".join(body).strip()))
            heading, body = line[3:].strip(), []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        entries.append(Entry(heading, "\n".join(body).strip()))
    return entries


def new_entries(old_text: str | None, new_text: str | None) -> list[Entry]:
    """Entries in new_text whose heading is not in old_text (order kept, newest first).

    An entry whose heading exists but whose body changed counts as new too, so
    edits to the current phase entry are shown.
    """
    old = {e.heading: e.body for e in parse(old_text)}
    return [e for e in parse(new_text) if old.get(e.heading) != e.body]


def render_entries(entries: list[Entry]) -> str:
    if not entries:
        return "(No new changelog entries.)"
    return "\n\n".join(e.render() for e in entries)
