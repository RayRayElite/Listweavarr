# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only, grouped workspace and provider search.

Local search never loads Plex or TMDB remotely. Ownership uses exact IDs from a
cached library snapshot; an unindexed library is unknown, not missing. Provider
search is a separate paged request so local results remain usable offline.
"""
import copy
import re
import unicodedata
import urllib.parse
import ignored_titles
import providers
import saved_lists


def text(value):
    return " ".join(
        re.findall(
            r"\w+",
            "".join(
                c
                for c in unicodedata.normalize("NFKD", str(value or "")).casefold()
                if not unicodedata.combining(c)
            ),
        )
    )


def query(body):
    value = body.get("query", "")
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= 120
        or not text(value)
    ):
        raise ValueError("Search with 1 to 120 characters.")
    return value.strip()


def page(body):
    try:
        number = int(body.get("page", 1))
    except (ValueError, TypeError):
        raise ValueError("Choose a valid search page.") from None
    if not 1 <= number <= 100:
        raise ValueError("Choose a search page from 1 to 100.")
    return number


def score(title, terms, extra=""):
    name = text(title)
    other = text(extra)
    acronym = (
        "".join(word[0] for word in name.split()) if len(name.split()) >= 3 else ""
    )
    haystack = " ".join(
        [name, other, name.replace(" ", ""), other.replace(" ", ""), acronym]
    )
    if not all(term in haystack for term in terms):
        return None
    wanted = " ".join(terms)
    return (
        (
            0
            if name == wanted
            else (
                1
                if name.startswith(wanted)
                else 2 if all(term in name for term in terms) else 3
            )
        ),
        len(name),
        name,
    )


def same(first, second):
    if not saved_lists.identity_keys(first).intersection(
        saved_lists.identity_keys(second)
    ):
        return False
    prefix = "show_" if first.get("type") in ("season", "episode") else ""
    return not any(
        first.get(prefix + p)
        and second.get(prefix + p)
        and str(first[prefix + p]) != str(second[prefix + p])
        for p in ("tmdb", "tvdb", "imdb")
    )


def media_fields(row):
    return {
        k: row[k]
        for k in (
            "type",
            "title",
            "show_title",
            "year",
            "tmdb",
            "tvdb",
            "imdb",
            "show_tmdb",
            "show_tvdb",
            "show_imdb",
            "season",
            "episode",
        )
        if row.get(k) is not None
    }


def artwork(item):
    identifier = (
        item.get("show_tmdb")
        if item["type"] in ("season", "episode")
        else item.get("tmdb")
    )
    if identifier:
        path = ("movie/" if item["type"] == "movie" else "tv/") + str(identifier)
        data = providers.peek_tmdb(path)
        return providers.image_url(data.get("poster_path"))
    return None


def library_item(row):
    return {
        "type": row["type"],
        "title": row["title"],
        "year": row.get("year"),
        **{
            k: str(v)
            for k, v in row.get("ids", {}).items()
            if k in ("tmdb", "tvdb", "imdb") and v
        },
    }


def decorate(item, state, catalog, known):
    parent = item["type"] in ("season", "episode")
    candidate = (
        {
            "type": "show",
            **{
                k: item["show_" + k]
                for k in ("tmdb", "tvdb", "imdb")
                if item.get("show_" + k)
            },
        }
        if parent
        else item
    )
    owned = any(same(candidate, library_item(row)) for row in catalog)
    requests = [
        row
        for row in state.get("requests", [])
        if same(item, row.get("item", {}))
        and row.get("status") not in ("cancelled", "declined")
    ]
    request = max(
        requests,
        key=lambda r: r.get("updated_at") or r.get("created_at", 0),
        default=None,
    )
    return {
        "library_known": known,
        "in_plex": owned if not parent else False,
        "parent_in_plex": owned if parent else False,
        "request_status": request.get("status") if request else None,
        "request_id": request.get("id") if request else None,
        "tracked": any(
            same(candidate, row) for row in state.get("release_watchlist", [])
        ),
        "ignored": ignored_titles.matches(item, state.get("ignored_titles", [])),
    }


def local(state, body, catalog=None, library_known=False, official=None):
    wanted, number = query(body), page(body)
    terms = text(wanted).split()
    catalog = catalog or []
    groups = {}
    key_index = {}

    def add(item, source=None, plex=None):
        rank = score(
            item.get("title"),
            terms,
            str(item.get("show_title", "")) + " " + str(item.get("year") or ""),
        )
        if (
            rank is None
            or not body.get("include_ignored")
            and ignored_titles.matches(item, state.get("ignored_titles", []))
        ):
            return
        keys = saved_lists.identity_keys(item)
        choices = {index for key in keys for index in key_index.get(key, [])}
        index = next(
            (index for index in sorted(choices) if same(item, groups[index]["item"])),
            None,
        )
        if index is None:
            index = len(groups)
            groups[index] = {
                "item": media_fields(item),
                "lists": [],
                "libraries": [],
                "rank": rank,
            }
        row = groups[index]
        # Adding exact IDs improves the details link, without guessing by title.
        for key, value in media_fields(item).items():
            if not row["item"].get(key):
                row["item"][key] = value
        if source and source not in row["lists"]:
            row["lists"].append(source)
        if plex:
            if plex.get("library") not in row["libraries"]:
                row["libraries"].append(plex.get("library"))
            if plex.get("server_id") and plex.get("key"):
                row["plex_href"] = (
                    "https://app.plex.tv/desktop/#!/server/"
                    + urllib.parse.quote(str(plex["server_id"]), safe="")
                    + "/details?key="
                    + urllib.parse.quote(
                        "/library/metadata/" + str(plex["key"]), safe=""
                    )
                )
        for key in keys:
            key_index.setdefault(key, []).append(index)

    for row in catalog:
        add(library_item(row), plex=row)
    lists = []
    for entry in state.get("lists", []):
        rank = score(entry["name"], terms, entry.get("description", ""))
        if rank is not None:
            lists.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "count": len(entry["items"]),
                    "poster": entry.get("poster"),
                    "kind": "saved",
                    "official_authoring": bool(entry.get("official_authoring")),
                    "rank": rank,
                }
            )
        for item in entry["items"]:
            add(
                item,
                {"list_id": entry["id"], "item_id": item["id"], "name": entry["name"]},
            )
    for entry in official or []:
        rank = score(entry["name"], terms, entry.get("description", ""))
        if rank is not None and not any(
            row.get("official_id") == entry["id"] for row in state.get("lists", [])
        ):
            lists.append(
                {
                    "id": entry["id"],
                    "name": entry["name"],
                    "count": entry.get("count", 0),
                    "poster": entry.get("poster"),
                    "kind": "official",
                    "rank": rank,
                }
            )
    titles = sorted(groups.values(), key=lambda row: row["rank"])
    lists.sort(key=lambda row: (row["rank"], row["kind"] != "saved"))
    start = (number - 1) * 20
    result = []
    for row in titles[start : start + 20]:
        row.pop("rank", None)
        row["item"]["poster"] = artwork(row["item"])
        row.update(decorate(row["item"], state, catalog, library_known))
        if row["libraries"] and row["item"]["type"] in ("movie", "show"):
            row["in_plex"] = True
        result.append(row)
    visible_lists = [
        {k: v for k, v in row.items() if k != "rank"}
        for row in lists[start : start + 20]
    ]
    return {
        "query": wanted,
        "page": number,
        "titles": result,
        "lists": visible_lists,
        "titles_total": len(titles),
        "lists_total": len(lists),
        "has_more": start + 20 < max(len(titles), len(lists)),
        "library_known": library_known,
        "library_note": (
            "Library matches use the cached Plex snapshot; show presence does not confirm every episode."
            if library_known
            else "Library not checked yet. Use Refresh library to load Plex titles; unverified results are not labeled missing."
        ),
    }


def remote(state, body, catalog=None, library_known=False):
    wanted, number = query(body), page(body)
    if not state.get("settings", {}).get("tmdb", {}).get("key"):
        return {
            "items": [],
            "people": [],
            "page": number,
            "has_more": False,
            "note": "Connect TMDB to search provider titles and people.",
        }
    response = providers.cached_tmdb(
        "search/multi?"
        + urllib.parse.urlencode(
            {"query": wanted, "page": number, "include_adult": "false"}
        ),
        state["settings"],
    )
    items, people = [], []
    for row in response.get("results", []):
        if row.get("adult") or not str(row.get("id", "")).isdigit():
            continue
        media = row.get("media_type")
        if media == "person":
            people.append(
                {
                    "id": str(row["id"]),
                    "name": row.get("name") or "Person",
                    "department": row.get("known_for_department"),
                    "poster": providers.image_url(row.get("profile_path")),
                }
            )
        elif media in ("movie", "tv"):
            item = {
                "type": "movie" if media == "movie" else "show",
                "tmdb": str(row["id"]),
                "title": row.get("title") or row.get("name") or "Untitled",
                "year": (row.get("release_date") or row.get("first_air_date") or "")[
                    :4
                ],
                "poster": providers.image_url(row.get("poster_path")),
            }
            decoration = decorate(item, state, catalog or [], library_known)
            if decoration["ignored"] and not body.get("include_ignored"):
                continue
            items.append({"item": item, **decoration})
    return {
        "items": items,
        "people": people,
        "page": number,
        "has_more": number < min(int(response.get("total_pages", 1)), 100),
        "note": "TMDB results. A request or tracked release is not proof of a playable file.",
    }
