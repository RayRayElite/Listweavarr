# SPDX-License-Identifier: AGPL-3.0-only
"""Reviewed, additive manager tags. Never create tags or remove existing tags."""


def identifiers(values):
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > 50:
        raise ValueError("Choose up to 50 existing manager tags.")
    if any(
        isinstance(value, bool) or not str(value).isdigit() or int(value) < 1
        for value in values
    ):
        raise ValueError("Choose valid manager tag IDs.")
    return list(dict.fromkeys(int(value) for value in values))


def options(call):
    return [
        {"id": int(row["id"]), "label": str(row.get("label") or row["id"])}
        for row in call("tag")
        if str(row.get("id", "")).isdigit()
    ]


def validate(values, choices):
    selected = identifiers(values)
    if not set(selected).issubset({row["id"] for row in choices}):
        raise ValueError(
            "A selected manager tag was removed. Reload the request options and review tags again."
        )
    return selected


def for_request(settings, call):
    selected = identifiers(settings.get("_request_tags"))
    return validate(selected, options(call)) if selected else []


def apply(record, selected):
    """Merge on a copied manager record; true means a PUT is necessary."""
    if not selected:
        return False
    existing = list(record.get("tags") or [])
    merged = list(dict.fromkeys(existing + selected))
    if merged == existing:
        return False
    record["tags"] = merged
    return True
