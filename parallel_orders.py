# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit parallel watch blocks: parse evidence, then round-robin exact scopes.

Parallel means requested alternation, not inferred airing chronology. Notes may
link only to the next explicitly scoped title; no missing 'rest of season'
range is invented. The first listed lane starts, and longer lanes finish after
shorter ones end. Ordinary list entries retain their position outside blocks.
"""
import re
from itertools import zip_longest


def readable(line):
    line = re.sub(r"\[([^\]]+)\]\([^\n]*?\)", r"\1", line)
    return line.replace("**", "").strip()


def scoped(line):
    return bool(
        re.search(r"(?i)\b(?:seasons?|series)\s+\d+|\bS\d+E\d+|\b\d+x\d+", line)
    )


def named_scope(line):
    prefix = re.split(r"(?i)\(|\b(?:seasons?|series)\s+\d|\bS\d+E\d+|\b\d+x\d+", line)[
        0
    ]
    prefix = re.sub(r"(?i)^\s*parallel\s*:\s*", "", prefix)
    return scoped(line) and bool(re.search(r"\w", prefix))


def split_lanes(line):
    parts, start, depth = [], 0, 0
    for index, char in enumerate(line):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif (
            char == "/"
            and not depth
            and index
            and line[index - 1].isspace()
            and index + 1 < len(line)
            and line[index + 1].isspace()
        ):
            parts.append(line[start:index].strip())
            start = index + 1
    parts.append(line[start:].strip())
    return (
        parts if len(parts) > 1 and all(named_scope(part) for part in parts) else [line]
    )


def prepare(text):
    lines = text.splitlines()
    output, annotations = [], {}
    group, index = 0, 0

    def add(line, original, lane=None):
        output.append(line)
        annotations[len(output)] = {"original_line": original + 1}
        if lane is not None:
            annotations[len(output)].update(
                parallel_group="parallel-" + str(group), parallel_lane=lane
            )

    while index < len(lines):
        line = readable(lines[index])
        parts = split_lanes(line)
        if len(parts) > 1:
            if len(parts) > 8:
                raise ValueError(
                    "A parallel block supports up to eight explicitly scoped titles."
                )
            group += 1
            for lane, part in enumerate(parts):
                add(re.sub(r"(?i)^\s*parallel\s*:\s*", "", part), index, lane)
            index += 1
            continue
        note = re.search(
            r"(?i)\(([^)]*\b(?:runs?\s+(?:in\s+)?parallel|parallel\s+(?:to|with))\b[^)]*)\)",
            line,
        )
        if note:
            following = next(
                (n for n in range(index + 1, len(lines)) if lines[n].strip()), None
            )
            other = readable(lines[following]) if following is not None else ""
            title = re.split(r"(?i)\(|\b(?:seasons?|series)\s+\d|\bS\d+E\d+", other)[0]
            title = re.sub(r"^[\W\d_]+", "", title).strip(" '*\"")
            if (
                not scoped(line[: note.start()])
                or not scoped(other)
                or not title
                or title.casefold() not in note[1].casefold()
                or len(split_lanes(other)) != 1
            ):
                raise ValueError(
                    "Parallel note at line "
                    + str(index + 1)
                    + " needs the next title's explicit season/episode scope. List both scopes on one line separated by / if the reference is ambiguous."
                )
            group += 1
            add(line[: note.start()].rstrip(" *"), index, 0)
            add(other, following, 1)
            index = following + 1
            continue
        add(line, index)
        index += 1
    return "\n".join(output), annotations


def annotate(rows, annotations):
    for row in rows:
        note = annotations.get(row["source_line"], {})
        row["source_line"] = note.get("original_line", row["source_line"])
        if "parallel_group" in note:
            if row["type"] not in ("season", "episode"):
                raise ValueError(
                    "Parallel blocks require explicit TV season or episode scopes."
                )
            row.update({key: note[key] for key in ("parallel_group", "parallel_lane")})
            row["source_note"] = (
                "Parallel block "
                + note["parallel_group"].split("-")[-1]
                + ", lane "
                + str(note["parallel_lane"] + 1)
                + ": alternate one episode per lane, first listed title first. Remaining episodes continue when a shorter lane ends."
            )
    return rows


def expand(rows, settings, normalize, sequential, metadata):
    """Expand confirmed scopes using the existing validator, then interleave."""
    result, seen, index = [], set(), 0
    while index < len(rows):
        row = rows[index]
        if not isinstance(row, dict):
            raise ValueError("Invalid list entry.")
        group = row.get("parallel_group")
        if not group:
            result.extend(sequential([row], settings, normalize))
            index += 1
        else:
            if (
                not isinstance(group, str)
                or not re.fullmatch(r"parallel-\d{1,4}", group)
                or group in seen
            ):
                raise ValueError(
                    "Parallel blocks must be contiguous. Review their order before saving."
                )
            seen.add(group)
            lanes = {}
            while (
                index < len(rows)
                and isinstance(rows[index], dict)
                and rows[index].get("parallel_group") == group
            ):
                value = rows[index]
                lane = value.get("parallel_lane")
                if (
                    isinstance(lane, bool)
                    or not isinstance(lane, int)
                    or not 0 <= lane < 8
                    or value.get("type") not in ("season", "episode")
                ):
                    raise ValueError(
                        "Parallel lanes must have confirmed TV season or episode scopes."
                    )
                expanded = sequential([value], settings, normalize)
                episodes = lanes.setdefault(lane, [])
                for item in expanded:
                    if len(result) + sum(map(len, lanes.values())) >= 10000:
                        raise ValueError("Expanded lists support up to 10,000 entries.")
                    if item["type"] == "episode":
                        episodes.append(item)
                    elif item["type"] == "season":
                        season = metadata(
                            "tv/" + item["show_tmdb"] + "/season/" + item["season"],
                            settings,
                        )
                        values = season.get("episodes", [])
                        numbers = [episode.get("episode_number") for episode in values]
                        if (
                            not values
                            or len(values) > 10000
                            or any(not episode.get("id") for episode in values)
                            or any(
                                not isinstance(number, int) or not 1 <= number <= 9999
                                for number in numbers
                            )
                            or sorted(numbers) != list(range(1, len(values) + 1))
                        ):
                            raise ValueError(
                                "A parallel season has incomplete episode metadata. Correct its scope before saving."
                            )
                        for episode in sorted(
                            values, key=lambda e: e["episode_number"]
                        ):
                            if len(result) + sum(map(len, lanes.values())) >= 10000:
                                raise ValueError(
                                    "Expanded lists support up to 10,000 entries."
                                )
                            episodes.append(
                                dict(
                                    normalize(
                                        {
                                            **item,
                                            "type": "episode",
                                            "id": "",
                                            "episode": str(episode["episode_number"]),
                                            "title": episode.get("name")
                                            or item["show_title"],
                                        }
                                    ),
                                    status="unchecked",
                                )
                            )
                    else:
                        raise ValueError(
                            "Parallel blocks can contain only TV episodes."
                        )
                if sum(map(len, lanes.values())) > 10000:
                    raise ValueError("Expanded lists support up to 10,000 entries.")
                index += 1
            if len(lanes) < 2 or list(lanes) != list(range(len(lanes))):
                raise ValueError(
                    "A parallel block needs at least two lanes in listed order. Restore the missing lane or make the block sequential."
                )
            for turn in zip_longest(*lanes.values()):
                result.extend(item for item in turn if item is not None)
        if len(result) > 10000:
            raise ValueError("Expanded lists support up to 10,000 entries.")
    return result
