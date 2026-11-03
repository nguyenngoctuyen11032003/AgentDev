"""Apply an edited workflow document to its YAML file without reformatting the rest of it.

The editor sends the whole desired document as plain data. Re-dumping that data would lose
comments, anchors/aliases, block scalar styles and the author's layout, so instead:

1. load the current file with ruamel.yaml (round-trip mode) and reconcile it in place against the
   desired data: values that did not change keep their original objects (and so their comments,
   anchors, aliases and styles); only changed values are replaced; null keys that were not in the
   file are not added;
2. dump the reconciled tree and the untouched tree with the same settings and three-way merge the
   difference into the original text line by line, so every line outside the edited region stays
   byte-for-byte as it was.

The merged text is checked to parse to the same data as the full ruamel dump; if it does not (an
edge case the line merge could not place), the full round-trip dump is used instead.
"""

from __future__ import annotations

import io
from difflib import SequenceMatcher
from typing import Any, Iterable

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import (
    DoubleQuotedScalarString,
    FoldedScalarString,
    LiteralScalarString,
    SingleQuotedScalarString,
)

# (mapping, sequence, offset) layouts tried in order; the one that reproduces the file best wins.
_INDENT_LAYOUTS = ((2, 4, 2), (2, 2, 0), (4, 4, 2), (4, 6, 4), (4, 4, 0))

_STRING_STYLES = (
    LiteralScalarString,
    FoldedScalarString,
    DoubleQuotedScalarString,
    SingleQuotedScalarString,
)


def _represent_none(representer, _data):
    return representer.represent_scalar("tag:yaml.org,2002:null", "null")


def _make_yaml(layout: tuple[int, int, int]) -> YAML:
    handler = YAML(typ="rt")
    handler.preserve_quotes = True
    handler.allow_duplicate_keys = True
    handler.width = 4096  # never re-wrap long lines
    mapping, sequence, offset = layout
    handler.indent(mapping=mapping, sequence=sequence, offset=offset)
    handler.representer.add_representer(type(None), _represent_none)
    return handler


def _dump(handler: YAML, data: Any) -> str:
    stream = io.StringIO()
    handler.dump(data, stream)
    return stream.getvalue()


def _pick_layout(text: str) -> tuple[int, int, int]:
    """The indentation layout whose plain round-trip differs from ``text`` in the fewest lines."""
    original = text.splitlines(keepends=True)
    best, best_score = _INDENT_LAYOUTS[0], None
    for layout in _INDENT_LAYOUTS:
        handler = _make_yaml(layout)
        dumped = _dump(handler, handler.load(text)).splitlines(keepends=True)
        matcher = SequenceMatcher(None, original, dumped, autojunk=False)
        score = len(original) + len(dumped) - 2 * sum(block.size for block in matcher.get_matching_blocks())
        if best_score is None or score < best_score:
            best, best_score = layout, score
        if score == 0:
            break
    return best


# --------------------------------------------------------------------------- reconcile


def _same(old: Any, new: Any) -> bool:
    """Plain-data equality that does not treat True as 1."""
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool) and old == new
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(_same(old[key], new[key]) for key in old)
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(_same(a, b) for a, b in zip(old, new))
    if isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
        return False
    return old == new


def _strip_nulls(value: Any) -> Any:
    """Plain copy of a new value without null-valued mapping keys."""
    if isinstance(value, dict):
        return {key: _strip_nulls(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_strip_nulls(item) for item in value]
    return value


def _fresh(value: Any, like: Any = None) -> Any:
    """Round-trip node for a new value, keeping the string style of the value it replaces."""
    if isinstance(value, dict):
        result = CommentedMap()
        for key, item in value.items():
            if item is not None:
                result[key] = _fresh(item)
        return result
    if isinstance(value, list):
        result = CommentedSeq()
        result.extend(_fresh(item) for item in value)
        return result
    if isinstance(value, str):
        if "\n" in value:
            return FoldedScalarString(value) if isinstance(like, FoldedScalarString) else LiteralScalarString(value)
        for style in _STRING_STYLES[2:]:
            if isinstance(like, style):
                return style(value)
    return value


def _count_references(node: Any, counts: dict[int, int]) -> None:
    if isinstance(node, (dict, list)):
        counts[id(node)] = counts.get(id(node), 0) + 1
        if counts[id(node)] > 1:
            return  # an alias: its children were already counted at the anchor
        children: Iterable[Any] = node.values() if isinstance(node, dict) else node
        for child in children:
            _count_references(child, counts)


class _Reconciler:
    def __init__(self, root: Any):
        self.references: dict[int, int] = {}
        _count_references(root, self.references)

    def _shared(self, node: Any) -> bool:
        return self.references.get(id(node), 0) > 1

    def value(self, old: Any, new: Any) -> Any:
        """The node to keep at a position that held ``old`` and should now hold ``new``."""
        if _same(old, new):
            return old
        if isinstance(old, CommentedMap) and isinstance(new, dict):
            # An anchored value used elsewhere through an alias: edit a copy so the alias users
            # keep the original.
            target = self._copy(old) if self._shared(old) else old
            self.mapping(target, new)
            return target
        if isinstance(old, CommentedSeq) and isinstance(new, list):
            target = self._copy(old) if self._shared(old) else old
            self.sequence(target, new)
            return target
        return _fresh(new, like=old)

    @staticmethod
    def _copy(node: Any) -> Any:
        """Deep copy of an aliased value; its children are shared too, so none may be edited in place."""
        if isinstance(node, dict):
            copied = CommentedMap()
            for key, item in node.items():
                copied[key] = _Reconciler._copy(item)
            return copied
        if isinstance(node, list):
            copied = CommentedSeq()
            copied.extend(_Reconciler._copy(item) for item in node)
            return copied
        return node

    def mapping(self, old: CommentedMap, new: dict) -> None:
        for key in [key for key in old if key not in new]:
            del old[key]
        for key, item in new.items():
            if key not in old:
                if item is not None:  # never add a null key the file did not have
                    old[key] = _fresh(_strip_nulls(item))
                continue
            if item is None and old[key] is not None:
                del old[key]  # the field was cleared
                continue
            replacement = self.value(old[key], item)
            if replacement is not old[key]:
                old[key] = replacement

    def sequence(self, old: CommentedSeq, new: list) -> None:
        used: set[int] = set()
        chosen: list[int | None] = [None] * len(new)

        # 1. unchanged items, wherever they are
        for index, item in enumerate(new):
            for position, candidate in enumerate(old):
                if position not in used and _same(candidate, item):
                    chosen[index] = position
                    used.add(position)
                    break
        # 2. edited mappings that kept their id
        for index, item in enumerate(new):
            if chosen[index] is not None or not isinstance(item, dict) or "id" not in item:
                continue
            for position, candidate in enumerate(old):
                if position not in used and isinstance(candidate, dict) and candidate.get("id") == item["id"]:
                    chosen[index] = position
                    used.add(position)
                    break
        # 3. remaining items paired in order (e.g. an edited edge, a renamed node)
        leftovers = iter(position for position in range(len(old)) if position not in used)
        for index, item in enumerate(new):
            if chosen[index] is None:
                position = next(leftovers, None)
                if position is not None and not (
                    (isinstance(item, dict) and isinstance(old[position], dict))
                    or (isinstance(item, list) and isinstance(old[position], list))
                ):
                    position = None
                if position is not None:
                    chosen[index] = position
                    used.add(position)

        items = [
            self.value(old[position], item) if position is not None else _fresh(_strip_nulls(item))
            for position, item in zip(chosen, new)
        ]
        if len(items) == len(old) and all(a is b for a, b in zip(items, old)):
            return
        # Rebuild in place (an anchored list must stay the same object), carrying the comments
        # attached to each kept item along with it.
        comments = old.ca.items
        moved = {
            index: comments[position]
            for index, position in enumerate(chosen)
            if position is not None and position in comments
        }
        list.__delitem__(old, slice(None))
        list.extend(old, items)
        comments.clear()
        comments.update(moved)


# --------------------------------------------------------------------------- three-way line merge


def _merge_lines(original: list[str], base: list[str], changed: list[str]) -> list[str]:
    """diff3: apply the base→changed edit to ``original`` (base is original as ruamel re-dumps it)."""
    base_to_original = {}
    for block in SequenceMatcher(None, base, original, autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            base_to_original[block.a + offset] = block.b + offset
    base_to_changed = {}
    for block in SequenceMatcher(None, base, changed, autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            base_to_changed[block.a + offset] = block.b + offset

    syncs = [(b, base_to_original[b], base_to_changed[b]) for b in range(len(base)) if b in base_to_original and b in base_to_changed]
    syncs.append((len(base), len(original), len(changed)))

    result: list[str] = []
    prev_b = prev_o = prev_c = -1
    for b, o, c in syncs:
        base_gap = base[prev_b + 1 : b]
        original_gap = original[prev_o + 1 : o]
        changed_gap = changed[prev_c + 1 : c]
        if changed_gap == base_gap:
            result.extend(original_gap)  # untouched: keep the author's text
        else:
            result.extend(changed_gap)  # edited (or edited where the layout differed)
        if b < len(base):
            result.append(original[o])
        prev_b, prev_o, prev_c = b, o, c
    return result


def merge_workflow_document(original_text: str, desired: Any) -> str:
    """Return ``original_text`` changed to hold ``desired``, touching as few lines as possible.

    ``original_text`` uses ``\\n`` line endings; callers restore the file's own line endings.
    """
    if not isinstance(desired, dict):
        raise ValueError("Workflow document must be a mapping")

    layout = _pick_layout(original_text)
    handler = _make_yaml(layout)
    untouched = _dump(handler, handler.load(original_text))

    document = handler.load(original_text)
    if not isinstance(document, CommentedMap):
        return _dump(handler, _fresh(desired))
    _Reconciler(document).mapping(document, desired)
    changed = _dump(handler, document)

    merged = "".join(
        _merge_lines(
            original_text.splitlines(keepends=True),
            untouched.splitlines(keepends=True),
            changed.splitlines(keepends=True),
        )
    )
    try:
        if yaml.safe_load(merged) == yaml.safe_load(changed):
            return merged
    except yaml.YAMLError:
        pass
    return changed
