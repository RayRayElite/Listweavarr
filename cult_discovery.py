# SPDX-License-Identifier: AGPL-3.0-only
"""Curated so-bad-its-good discovery with personal ranking.

Explore uses curated_candidates. The earlier experimental scorer is retained
for comparison tests, but is not an automatic fallback or membership source.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
import copy
import datetime
import hashlib
import math
import re
import threading
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import providers
import ratings
import taste
import ignored_titles

_cache = {}
_lock = threading.Lock()
ANCHORS = ("tt0368226", "tt0105643", "tt0052077", "tt1316037")


def curated_candidates(state, catalog, page=1, skip=lambda row: False):
    """Curated eligibility, personalized ordering; no heuristic filler.

    Rank a bounded pool per page to keep cold metadata requests manageable.
    Daily stable rotation avoids permanently favoring the beginning of a list.
    Ownership alone never counts as a positive preference.
    """
    selected = state.get("cult_list_id")
    source = next(
        (row for row in state.get("lists", []) if row["id"] == selected), None
    )
    if source is None and not selected:
        source = next(
            (
                row
                for row in state.get("lists", [])
                if canonical(row.get("name", "")).replace("'", "") == "so bad its good"
            ),
            None,
        )
    if source is None:
        return (
            [],
            [
                "Create a saved list named So Bad Its Good to supply curated candidates. No experimental substitutes are used."
            ],
            False,
        )
    settings = state["settings"]
    pool, seen = [], set()
    for original in source["items"]:
        row = dict(original)
        if row.get("type") not in ("movie", "show") or row.get("metadata_unresolved"):
            continue
        if skip(row) or ignored_titles.matches(row, state.get("ignored_titles", [])):
            continue
        identity = (
            row["type"],
            str(row.get("tmdb") or row.get("imdb") or row.get("tvdb") or row["title"]),
        )
        if identity not in seen:
            seen.add(identity)
            pool.append(row)
    day = datetime.date.today().isoformat()
    pool.sort(
        key=lambda row: hashlib.sha256(
            (day + row["type"] + str(row.get("tmdb") or row["title"])).encode()
        ).hexdigest()
    )
    start, limit = (page - 1) * 60, 60
    seeds = [
        row
        for row in taste.catalog_with_feedback(catalog, state.get("taste_feedback", {}))
        if row.get("_feedback") != "dislike"
        and (
            row.get("_feedback") in ("favorite", "like")
            or row.get("watched")
            and (not row.get("user_rating") or row["user_rating"] >= 5)
        )
        and not ignored_titles.matches(
            {**row, **row.get("ids", {})}, state.get("ignored_titles", [])
        )
    ]
    seeds.sort(
        key=lambda row: (
            row.get("_feedback") == "favorite",
            row.get("user_rating") or 0,
            row.get("last_viewed_at") or 0,
        ),
        reverse=True,
    )

    def details(row):
        value = dict(row)
        if not value.get("tmdb"):
            value = providers.enrich(value, settings)
        if not value.get("tmdb"):
            raise ValueError("No exact metadata match")
        media = "movie" if value["type"] == "movie" else "tv"
        return providers.cached_tmdb(
            media + "/" + str(value["tmdb"]) + "?append_to_response=credits,keywords",
            settings,
        )

    seed_features = []
    for seed in seeds[:8]:
        try:
            data = details({**seed, **seed.get("ids", {})})
            seed_features.append((seed, data))
        except ValueError:
            continue

    def features(data):
        genres = {row.get("name") for row in data.get("genres", [])}
        credits = data.get("credits") or {}
        people = {
            str(row["id"]) for row in credits.get("cast", [])[:8] if row.get("id")
        }
        people.update(
            str(row["id"])
            for row in credits.get("crew", [])
            if row.get("id") and row.get("job") == "Director"
        )
        keywords = data.get("keywords") or {}
        tags = {
            str(row["id"])
            for row in keywords.get("keywords", keywords.get("results", []))
            if row.get("id")
        }
        return genres, people, tags

    def evaluate(row):
        try:
            data = details(row)
            genres, people, tags = features(data)
            reasons, points = ["Selected from your curated list: " + source["name"]], 0
            for seed, metadata in seed_features:
                other_genres, other_people, other_tags = features(metadata)
                overlap = (
                    min(len(genres & other_genres), 2) * 0.3
                    + min(len(people & other_people), 2) * 1.2
                    + min(len(tags & other_tags), 3) * 0.4
                )
                points += overlap * (
                    1.5
                    if seed.get("_feedback") == "favorite"
                    or (seed.get("user_rating") or 0) >= 8
                    else 1
                )
                if overlap and len(reasons) < 4:
                    signal = (
                        "credited people"
                        if people & other_people
                        else "story themes" if tags & other_tags else "genres"
                    )
                    reasons.append(
                        "Shares "
                        + signal
                        + " with "
                        + seed["title"]
                        + (
                            ", which you favorited"
                            if seed.get("_feedback") == "favorite"
                            else (
                                ", which you liked"
                                if seed.get("_feedback") == "like"
                                else (
                                    ", which you highly rated"
                                    if (seed.get("user_rating") or 0) >= 8
                                    else ", which you watched"
                                )
                            )
                        )
                    )
            candidate = {
                "type": row["type"],
                "tmdb": str(data["id"]),
                "genre_ids": [g["id"] for g in data.get("genres", [])],
                "people_ids": list(people),
            }
            adjustment, feedback_reasons = taste.affinity(
                candidate, state.get("taste_feedback", {})
            )
            if adjustment <= -100:
                return None
            return {
                "details": {**data, "genre_ids": candidate["genre_ids"]},
                "kind": row["type"],
                "score": points + adjustment,
                "reasons": list(dict.fromkeys(reasons + feedback_reasons)),
                "confidence": (
                    "Personally curated eligibility; ranked using available taste and watch-history signals"
                    if seed_features or state.get("taste_feedback")
                    else "Personally curated pick; watch history and feedback can personalize its ranking"
                ),
            }
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        found = [
            value
            for value in executor.map(evaluate, pool[start : start + limit])
            if value
        ]
    found.sort(key=lambda value: -value["score"])
    notices = [
        "Personalized within a rotating pool of up to 60 curated titles per page; no outside titles are added."
    ]
    return found, notices, start + limit < len(pool)


STRONG = {"so bad it's good", "so bad its good", "bad movie night"}
CULT = {"cult", "cult film", "cult classic", "cult movie", "midnight movie"}
CAMP = {
    "camp",
    "campy",
    "campiness",
    "cheesy",
    "cheesiness",
    "b movie",
    "b-movie",
    "z movie",
    "z-movie",
    "low-budget",
    "low budget",
    "exploitation",
    "trash film",
}


def score(data, support=0, extra=None, today=None):
    today = today or datetime.date.today()
    votes = int(data.get("vote_count") or 0)
    rating = float(data.get("vote_average") or 0)
    try:
        age = (
            today - datetime.date.fromisoformat(data.get("release_date", "")[:10])
        ).days / 365.25
    except (ValueError, TypeError):
        return None
    if data.get("adult") or votes < 100 or not 2 <= rating <= 6.3 or age < 3:
        return None
    words = {
        canonical(r.get("name", ""))
        for r in data.get("keywords", {}).get("keywords", [])
    }
    strong = bool(words & STRONG)
    cult = bool(words & CULT)
    camp = len(words & CAMP)
    review_fans = int(data.get("enjoyable_bad_reviews") or 0)
    reasons = []
    points = 0
    if review_fans:
        points += min(6, review_fans * 3)
        reasons.append(
            str(review_fans)
            + " sampled reviewers explicitly describe enjoyable-bad or unintentionally funny qualities"
        )
    if strong:
        points += 6
        reasons.append("Tagged as enjoyable-bad cinema")
    if cult:
        points += 2
        reasons.append("Cult or midnight-film metadata")
    if camp:
        points += min(3, camp)
        reasons.append("Camp/B-movie themes")
    if support:
        points += min(4, support * 2)
        reasons.append(
            "Related to " + str(support) + " established enjoyable-bad favorites"
        )
    values = {
        r["source"]: r.get("value")
        for r in (extra or {}).get("ratings", [])
        if r.get("value") is not None
    }
    gap = values.get("popcorn", 0) - values.get("tomatoes", 100)
    disagreement = values.get("popcorn", 0) >= 55 and gap >= 25
    if disagreement:
        points += 3
        reasons.append(
            "Audience approval exceeds critics by " + str(round(gap)) + " points"
        )
    # Popularity and age support confidence only; they never provide the core fun evidence.
    if age >= 10:
        points += 1
        reasons.append("Has an established release history")
    if votes >= 500:
        points += 1
    evidence = (
        strong
        or review_fans >= 2
        or (review_fans and (camp or cult or support))
        or (camp and support >= 2 and disagreement)
    )
    if not evidence or points < 7:
        return None
    return {
        "score": points,
        "reasons": reasons,
        "confidence": "Experimental match - enjoyment is subjective",
    }


def candidates(settings, refresh=False):
    key = hashlib.sha256(
        (
            settings.get("tmdb", {}).get("key", "")
            + "\0"
            + settings.get("mdblist", {}).get("key", "")
        ).encode()
    ).hexdigest()
    with _lock:
        saved = _cache.get(key)
    if saved and not refresh and time.time() - saved[0] < 21600:
        return copy.deepcopy(saved[1]), list(saved[2])
    candidates = {}
    support = defaultdict(set)
    warnings = []
    anchors = set()
    # Anchors generate candidates; they are not a fixed output list and never auto-qualify.
    for imdb in ANCHORS:
        try:
            found = providers.cached_tmdb(
                "find/" + imdb + "?external_source=imdb_id", settings
            ).get("movie_results", [])
            if len(found) != 1:
                continue
            seed = found[0]
            anchors.add(str(seed["id"]))
            candidates[str(seed["id"])] = seed
            for row in providers.cached_tmdb(
                "movie/" + str(seed["id"]) + "/recommendations", settings
            ).get("results", []):
                candidates[str(row["id"])] = row
                support[str(row["id"])].add(imdb)
        except ValueError:
            warnings.append("Some cult-film candidate sources were unavailable.")
    for term in ("so bad it's good", "cult film", "campy", "b-movie"):
        try:
            matches = providers.cached_tmdb(
                "search/keyword?" + urllib.parse.urlencode({"query": term}), settings
            ).get("results", [])
            ids = [
                str(r["id"])
                for r in matches
                if canonical(r.get("name", "")) in STRONG | CULT | CAMP
            ][:3]
            if not ids:
                continue
            query = {
                "with_keywords": "|".join(ids),
                "vote_average.gte": 2,
                "vote_average.lte": 6.3,
                "vote_count.gte": 100,
                "sort_by": "vote_count.desc",
                "include_adult": "false",
            }
            for row in providers.cached_tmdb(
                "discover/movie?" + urllib.parse.urlencode(query), settings
            ).get("results", []):
                candidates[str(row["id"])] = row
        except ValueError:
            warnings.append("Some cult-film keyword discovery was unavailable.")
    shortlist = sorted(
        [
            r
            for r in candidates.values()
            if 2 <= float(r.get("vote_average") or 0) <= 6.3
            and int(r.get("vote_count") or 0) >= 100
        ],
        key=lambda r: -(
            50 * (str(r["id"]) in anchors)
            + len(support[str(r["id"])]) * 10
            + math.log1p(int(r.get("vote_count") or 0))
        ),
    )[:50]
    review_ids = {str(r["id"]) for r in shortlist[:24]}

    def evaluate(row):
        try:
            data = providers.cached_tmdb(
                "movie/" + str(row["id"]) + "?append_to_response=keywords", settings
            )
            if str(row["id"]) in review_ids:
                try:
                    reviews = providers.cached_tmdb(
                        "movie/" + str(row["id"]) + "/reviews", settings
                    ).get("results", [])
                    data["enjoyable_bad_reviews"] = review_evidence(reviews)
                except ValueError:
                    pass
            result = score(data, len(support[str(row["id"])]))
            return (data, result)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        evaluated = [r for r in pool.map(evaluate, shortlist) if r]
    # Optional extra evidence for a bounded set of near misses; no mandatory ratings subscription.
    if settings.get("mdblist", {}).get("key"):
        near = [r for r in evaluated if not r[1]][:8]
        for data, _ in near:
            try:
                extra = ratings.lookup(
                    {"type": "movie", "tmdb": str(data["id"])}, settings
                )
                result = score(data, len(support[str(data["id"])]), extra)
                if result:
                    evaluated.append((data, result))
            except ValueError:
                pass
    result = sorted(
        [{"details": data, **scored} for data, scored in evaluated if scored],
        key=lambda r: (-r["score"], -int(r["details"].get("vote_count") or 0)),
    )
    seen = set()
    result = [
        r
        for r in result
        if not (r["details"]["id"] in seen or seen.add(r["details"]["id"]))
    ]
    with _lock:
        _cache[key] = (time.time(), result, list(dict.fromkeys(warnings)))
    return copy.deepcopy(result), list(dict.fromkeys(warnings))


def review_evidence(reviews):
    """Count distinct reviewers explicitly describing enjoyable failure, not generic praise."""
    authors = set()
    for review in reviews[:20]:
        text = canonical(review.get("content", ""))
        # Require explicit phrases. Negated statements and generic 'bad movie' do not count.
        positive = re.search(
            r"so bad.{0,35}?(?:good|fun|hilarious)|hilariously bad|unintentionally (?:funny|hilarious)|delightfully (?:bad|terrible)|enjoyably (?:bad|terrible)",
            text,
        )
        if not positive:
            continue
        if re.search(
            r"(?:not|never|isn't)\s+(?:good|fun|hilarious)", positive.group(0)
        ):
            continue
        prefix = text[max(0, positive.start() - 15) : positive.start()]
        if re.search(r"(?:not|isn't|is not|never)\s*$", prefix):
            continue
        author = (
            review.get("author_details", {}).get("username")
            or review.get("author")
            or review.get("id")
        )
        if author:
            authors.add(author)
    return len(authors)


def canonical(value):
    return (
        str(value)
        .casefold()
        .replace(chr(0x2019), "'")
        .replace(chr(0x2018), "'")
        .strip()
    )
