# SPDX-License-Identifier: AGPL-3.0-only
"""Confirmed movie/TV relationship classification and ordering.

Separates chronology, collection membership and recommendations; overlapping universes are not automatically a single canon.

See docs/CODE_MAP.md for related modules, routes and contribution guidance.
"""
from concurrent.futures import ThreadPoolExecutor

# Exact TMDB IDs in story order. Sources are retained with every sequence.
SEQUENCES = [
    {
        "name": "Skywalker saga",
        "ids": [
            "1893",
            "1894",
            "1895",
            "11",
            "1891",
            "1892",
            "140607",
            "181808",
            "181812",
        ],
        "source": "https://www.disneyplus.com/en-nz/explore/articles/star-wars-movies-in-order",
    },
    {
        "name": "Iron Man",
        "ids": ["1726", "10138", "68721"],
        "source": "https://www.marvel.com/movies",
    },
    {
        "name": "Captain America",
        "ids": ["1771", "100402", "271110", "822119"],
        "source": "https://www.marvel.com/movies",
    },
    {
        "name": "Thor",
        "ids": ["10195", "76338", "284053", "616037"],
        "source": "https://www.marvel.com/movies",
    },
    {
        "name": "Avengers",
        "ids": ["24428", "99861", "299536", "299534"],
        "source": "https://www.marvel.com/movies",
    },
    {
        "name": "Guardians of the Galaxy",
        "ids": ["118340", "283995", "447365"],
        "source": "https://www.marvel.com/movies",
    },
]


def sections(kind, identifier, title, collection, rows, settings, lookup, image_url):
    current_key = ("movie:" if kind == "movie" else "tv:") + identifier

    def row(data, relationship=None):
        date = data.get("release_date") or data.get("first_air_date") or ""
        key = ("movie:" if kind == "movie" else "tv:") + str(data["id"])
        return {
            "key": key,
            "type": kind,
            "tmdb": str(data["id"]),
            "title": data.get("title") or data.get("name") or "Untitled",
            "poster": image_url(data.get("poster_path")),
            "year": date[:4],
            "release_date": date,
            "current": key == current_key,
            "relationship": relationship,
        }

    sequence = next(
        (s for s in SEQUENCES if kind == "movie" and identifier in s["ids"]), None
    )
    sequence_rows = []
    if sequence:
        available = {str(r["id"]): r for r in (collection or {}).get("parts", [])}
        available[identifier] = dict(title, id=int(identifier))

        def fetch(identifier):
            try:
                return available.get(identifier) or lookup(
                    "movie/" + identifier, settings
                )
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            details = list(pool.map(fetch, sequence["ids"]))
        current_position = sequence["ids"].index(identifier)
        current_date = title.get("release_date") or ""
        for index, data in enumerate(details):
            if data:
                date = data.get("release_date") or ""
                label = (
                    "Current title"
                    if index == current_position
                    else (
                        "Prequel"
                        if index < current_position
                        and current_date
                        and date > current_date
                        else (
                            "Earlier installment"
                            if index < current_position
                            else (
                                "Later in the story"
                                if current_date and date and date < current_date
                                else "Sequel"
                            )
                        )
                    )
                )
                entry = row(data, label)
                entry["position"] = index + 1
                sequence_rows.append(entry)
    sequence_keys = {r["key"] for r in sequence_rows}
    franchise = [
        row(r, "Franchise member")
        for r in (collection or {}).get("parts", [])
        if str(r.get("id", "")).isdigit()
    ]
    franchise = sorted(
        (r for r in franchise if r["key"] not in sequence_keys and not r["current"]),
        key=lambda r: (r["release_date"] or "9999", r["title"]),
    )
    confirmed = sequence_keys | {r["key"] for r in franchise} | {current_key}
    related = [
        r
        for r in rows
        if r["group"].startswith("Recommendations") and r["key"] not in confirmed
    ]
    return {
        "sequence": {
            "name": sequence["name"] if sequence else "",
            "source": sequence["source"] if sequence else "",
            "note": "Story order within this film series; crossovers and spin-offs are listed separately.",
            "items": sequence_rows,
        },
        "franchise": {
            "name": (collection or {}).get("name", ""),
            "note": "Confirmed TMDB collection membership. Release order; a collection can span different continuities.",
            "items": franchise,
        },
        "related": {"items": related},
    }
