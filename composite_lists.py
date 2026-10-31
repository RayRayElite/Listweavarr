# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic, read-only composite previews from explicit saved-list sources.

Set operations use exact provider identity AND media scope. A show never absorbs
its episodes. Conflicting IDs and unidentified titles stay separate. The first
source controls order; generated snapshots never edit their inputs or Plex.
"""
import copy
import hashlib
import json

import list_sharing
import saved_lists


def recipe(body, lists):
    operation = body.get("operation", "union")
    if operation not in ("union", "intersection", "difference"):
        raise ValueError("Choose combine, common entries, or subtract.")
    ids = body.get("sources")
    excluded = body.get("exclude", [])
    if not isinstance(ids, list) or not 2 <= len(ids) <= 20:
        raise ValueError("Choose between two and twenty source lists.")
    if not isinstance(excluded, list) or len(excluded) > 20:
        raise ValueError("Choose up to twenty exclusion lists.")
    known = {row["id"] for row in lists}
    if any(not isinstance(i, str) or i not in known for i in ids + excluded):
        raise ValueError("A source list is no longer available.")
    if len(set(ids)) != len(ids) or len(set(excluded)) != len(excluded):
        raise ValueError("Choose each source only once.")
    if set(ids) & set(excluded):
        raise ValueError("A source cannot also be an exclusion list.")
    return {"operation": operation, "sources": ids, "exclude": excluded}


def exact(a, b):
    left, right = saved_lists.identity_keys(a), saved_lists.identity_keys(b)
    if not left & right:
        return False
    # A shared IMDb ID must not hide conflicting TMDB/TVDB identities.
    first = {key[1]: key[2] for key in left}
    second = {key[1]: key[2] for key in right}
    return not any(first[p] != second[p] for p in first.keys() & second.keys())


class Index:
    def __init__(self, rows=()):
        self.by_key = {}
        for row in rows:
            self.add(row)

    def add(self, row):
        for key in saved_lists.identity_keys(row):
            self.by_key.setdefault(key, []).append(row)

    def matches(self, row):
        return any(
            exact(row, other)
            for key in saved_lists.identity_keys(row)
            for other in self.by_key.get(key, [])
        )


def preview(body, lists):
    rule = recipe(body, lists)
    by_id = {row["id"]: row for row in lists}
    sources = [by_id[i] for i in rule["sources"]]
    if sum(len(by_id[i]["items"]) for i in rule["sources"] + rule["exclude"]) > 100000:
        raise ValueError("Use sources totaling at most 100,000 entries.")
    others = [Index(row["items"]) for row in sources[1:]]
    exclusions = Index(item for i in rule["exclude"] for item in by_id[i]["items"])
    selected, seen, provenance = [], Index(), []
    for source in sources if rule["operation"] == "union" else sources[:1]:
        for item in source["items"]:
            if rule["operation"] == "intersection" and not all(
                idx.matches(item) for idx in others
            ):
                continue
            if rule["operation"] == "difference" and any(
                idx.matches(item) for idx in others
            ):
                continue
            if exclusions.matches(item) or seen.matches(item):
                continue
            seen.add(item)
            selected.append(
                {
                    key: copy.deepcopy(item[key])
                    for key in list_sharing.FIELDS
                    if key in item
                }
            )
            provenance.append({"source": source["id"], "entry": item["id"]})
            if len(selected) > 10000:
                raise ValueError("A generated list supports up to 10,000 entries.")
    fingerprints = {
        i: saved_lists.revision(by_id[i]) for i in rule["sources"] + rule["exclude"]
    }
    result = {
        "recipe": rule,
        "items": selected,
        "provenance": provenance,
        "sources": fingerprints,
    }
    result["fingerprint"] = hashlib.sha256(
        json.dumps(result, sort_keys=True).encode()
    ).hexdigest()
    result["unidentified"] = sum(not saved_lists.identity_keys(row) for row in selected)
    return result
