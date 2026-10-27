# SPDX-License-Identifier: AGPL-3.0-only
"""Merge ordered sources around shared anchors without inventing chronology.

The primary sequence is authoritative. Secondary-only runs are inserted before
their next shared anchor, or at the end when only a preceding anchor exists.
Conflicting or disconnected runs are returned for review rather than guessed.
"""
from collections import defaultdict
import copy


def align(primary, secondary, identity):
    def unique(rows):
        seen, result, duplicates = set(), [], []
        for row in rows:
            key = identity(row)
            if key in seen:
                duplicates.append(copy.deepcopy(row))
            else:
                result.append(copy.deepcopy(row))
                seen.add(key)
        return result, duplicates

    base, primary_duplicates = unique(primary)
    other, secondary_duplicates = unique(secondary)
    positions = {identity(row): index for index, row in enumerate(base)}
    inserts = defaultdict(list)
    conflicts, run, previous = [], [], None

    def place(following):
        nonlocal run
        if not run:
            return
        if (previous is None and following is None) or (
            previous is not None and following is not None and previous >= following
        ):
            conflicts.append(
                {
                    "reason": (
                        "No shared anchors"
                        if previous is None and following is None
                        else "Shared anchors contradict the primary order"
                    ),
                    "items": run,
                }
            )
        else:
            inserts[following if following is not None else len(base)].extend(run)
        run = []

    for row in other:
        position = positions.get(identity(row))
        if position is None:
            run.append(row)
        else:
            place(position)
            previous = position
    place(None)
    result = []
    for position, row in enumerate(base):
        result.extend(inserts[position])
        result.append(row)
    result.extend(inserts[len(base)])
    return {
        "items": result,
        "conflicts": conflicts,
        "primary_duplicates": primary_duplicates,
        "secondary_duplicates": secondary_duplicates,
        "added": len(result) - len(base),
    }
