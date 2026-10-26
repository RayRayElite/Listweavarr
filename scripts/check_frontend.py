# SPDX-License-Identifier: AGPL-3.0-only
"""Validate the static shell and shipped script references after UI composition changes."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Shell(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.ids = []
        self.controls = []
        self.assets = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        self.controls.extend(attrs.get("aria-controls", "").split())
        if tag == "script" and attrs.get("src"):
            self.assets.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.assets.append(attrs["href"])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"Unexpected </{tag}> after {self.stack[-1:]}")
        else:
            self.stack.pop()


shell = Shell()
shell.feed((ROOT / "web/index.html").read_text("utf-8"))
assert not shell.errors, shell.errors[:10]
assert not shell.stack, shell.stack
assert not [
    key for key, value in Counter(shell.ids).items() if value > 1
], "Duplicate shell IDs"
assert all(
    control in shell.ids for control in shell.controls
), "Missing aria-controls targets"
assert all(
    (ROOT / "web" / asset.lstrip("/")).is_file() for asset in shell.assets
), "Missing web assets"
print(
    f"Valid shell: {len(shell.ids)} unique IDs, {len(shell.controls)} tab targets, {len(shell.assets)} assets."
)
