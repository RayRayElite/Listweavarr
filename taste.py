# SPDX-License-Identifier: AGPL-3.0-only
"""Personal preference signals for discovery.

Uses local feedback and connected Plex metadata; rankings are suggestions, not a prediction of individual enjoyment.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import time

VALUES = ("like", "favorite", "dislike")


def validate(feedback):
    if not isinstance(feedback, dict) or len(feedback) > 2000:
        raise ValueError("Taste feedback supports up to 2,000 titles.")
    for key, row in feedback.items():
        if (
            not isinstance(row, dict)
            or key != identity(row.get("type"), row.get("tmdb"))
            or row.get("value") not in VALUES
            or not isinstance(row.get("title"), str)
            or len(row["title"]) > 500
        ):
            raise ValueError("Invalid saved taste feedback.")
        for field in ("genres", "genre_ids", "people"):
            values = row.get(field, [])
            if (
                not isinstance(values, list)
                or len(values) > 100
                or any(not isinstance(value, (str, int)) for value in values)
            ):
                raise ValueError("Invalid taste metadata.")
    return feedback


def identity(kind, identifier):
    if (
        kind not in ("movie", "show")
        or not str(identifier).isdigit()
        or int(identifier) < 1
    ):
        raise ValueError("Choose an exact movie or TV show.")
    return kind + ":" + str(int(identifier))


def record(kind, identifier, value, metadata):
    identity(kind, identifier)
    if value not in VALUES:
        raise ValueError(
            "Choose more like this, favorite, less like this, or clear feedback."
        )
    credits = metadata.get("credits") or {}
    return {
        "type": kind,
        "tmdb": str(int(identifier)),
        "value": value,
        "title": metadata.get("title") or metadata.get("name") or "Untitled",
        "genres": [
            row["name"] for row in metadata.get("genres", []) if row.get("name")
        ],
        "genre_ids": [
            int(row["id"])
            for row in metadata.get("genres", [])
            if str(row.get("id", "")).isdigit()
        ],
        "people": [
            str(row["id"])
            for row in credits.get("cast", [])[:5]
            if str(row.get("id", "")).isdigit()
        ]
        + [
            str(row["id"])
            for row in credits.get("crew", [])
            if row.get("job") == "Director" and str(row.get("id", "")).isdigit()
        ],
        "updated_at": time.time(),
    }


def catalog_with_feedback(catalog, feedback):
    rows = copy.deepcopy(catalog)
    seen = set()
    for row in rows:
        identifier = (row.get("ids") or {}).get("tmdb")
        key = row["type"] + ":" + str(identifier) if identifier else ""
        if key in feedback:
            row["_feedback"] = feedback[key]["value"]
            seen.add(key)
            if not row.get("genres"):
                row["genres"] = feedback[key].get("genres", [])
    for key, value in feedback.items():
        if key not in seen and value.get("value") in ("like", "favorite"):
            rows.append(
                {
                    "key": "taste-" + key,
                    "type": value["type"],
                    "title": value["title"],
                    "ids": {"tmdb": value["tmdb"]},
                    "genres": value.get("genres", []),
                    "_feedback": value["value"],
                    "watched": False,
                }
            )
    return rows


def affinity(candidate, feedback):
    kind = candidate["type"]
    identifier = str(candidate["tmdb"])
    reasons = []
    score = 0
    for row in feedback.values():
        same = row["type"] == kind and row["tmdb"] == identifier
        if same:
            if row["value"] == "dislike":
                return -100, ["You asked for less like this title"]
            continue
        # TMDB's movie/TV genre ID spaces differ; never compare them across media.
        shared_genres = (
            set(candidate.get("genre_ids", [])) & set(row.get("genre_ids", []))
            if row["type"] == kind
            else set()
        )
        shared_people = set(candidate.get("people_ids", [])) & set(
            row.get("people", [])
        )
        if not shared_genres and not shared_people:
            continue
        strength = min(len(shared_genres), 2) * 0.35 + min(len(shared_people), 2) * 0.8
        if row["value"] == "dislike":
            score -= strength * 0.5
        else:
            score += strength * (1.5 if row["value"] == "favorite" else 1)
            if shared_people:
                reasons.append(
                    "Shares a credited person with "
                    + row["title"]
                    + ", which you "
                    + ("favorited" if row["value"] == "favorite" else "liked")
                )
            elif shared_genres:
                reasons.append(
                    "Shares genres with "
                    + row["title"]
                    + ", which you "
                    + ("favorited" if row["value"] == "favorite" else "liked")
                )
    return max(-2, min(4, score)), list(dict.fromkeys(reasons))[:2]


def rank(candidates, feedback):
    result = []
    for original in candidates:
        row = copy.deepcopy(original)
        adjustment, reasons = affinity(row, feedback)
        if adjustment <= -100:
            continue
        row["score"] = row.get("score", 0) + adjustment
        row["reasons"] = list(dict.fromkeys(reasons + row.get("reasons", [])))[:6]
        result.append(row)
    return sorted(result, key=lambda row: (-row.get("score", 0), row["title"]))
