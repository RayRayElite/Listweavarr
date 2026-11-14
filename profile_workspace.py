# SPDX-License-Identifier: AGPL-3.0-only
"""Request-scoped household workspaces; never substitute an owner's Plex token.

Provider metadata settings are shared read-only. Personal lists, comparisons,
watch snapshots, preferences and taste stay in a profile-specific private file.
"""
import contextlib
import contextvars
import copy
import hashlib

ACTIVE = contextvars.ContextVar("listweavarr_profile", default=None)
SHARED_PROVIDERS = ("tmdb", "trakt", "mdblist", "omdb", "tvdb")


def identity():
    return ACTIVE.get()


def member():
    return bool(identity() and identity().get("role") == "member")


def scope():
    user = identity()
    if not member():
        return "owner"
    return hashlib.sha256(
        (str(user["account_id"]) + ":" + str(user["user_id"])).encode()
    ).hexdigest()


def directory(root):
    return root / "profiles" / scope() if member() else root


@contextlib.contextmanager
def use(user):
    token = ACTIVE.set(user)
    try:
        yield
    finally:
        ACTIVE.reset(token)


def merge_settings(state, shared):
    result = copy.deepcopy(state)
    settings = result.setdefault("settings", {})
    for key in SHARED_PROVIDERS:
        if key in shared.get("settings", {}):
            settings[key] = copy.deepcopy(shared["settings"][key])
    user = identity()
    result["plex_auth"] = {
        "token": user["plex_token"],
        "client_id": user["client_id"],
        "account_id": user["user_id"],
        "account": user["name"],
    }
    return result


def private_state(state):
    result = copy.deepcopy(state)
    if member():
        for key in SHARED_PROVIDERS:
            result.get("settings", {}).pop(key, None)
        # Session credentials are owned by owner_access, not workspace backups.
        result.pop("plex_auth", None)
    return result


def allowed(path):
    """Member mutations are explicit; unknown/admin routes fail closed."""
    if not member():
        return True
    if path.startswith("/api/lists/acquisition/"):
        return False
    if path.startswith(
        (
            "/api/lists/",
            "/api/search/",
            "/api/issues/",
            "/api/smart-lists/",
            "/api/taste/",
            "/api/ignore/",
            "/api/releases/",
            "/api/discover",
            "/api/trakt/",
        )
    ):
        return True
    if path.startswith("/api/explore/"):
        action = path.rsplit("/", 1)[-1]
        return action in (
            "home",
            "extra",
            "shelf",
            "lists",
            "preview",
            "save",
            "route",
            "row-order",
            "preferences",
            "languages",
            "official",
            "open",
        )
    if path.startswith("/api/companion/"):
        return path.rsplit("/", 1)[-1] in (
            "state",
            "recipe-save",
            "recipe-delete",
            "preferences",
            "inbox-read",
            "follow",
            "unfollow",
            "impressions",
            "reset-insights",
            "path-save",
            "person-search",
            "genres",
            "priorities",
            "path",
            "path-editor",
            "path-copy",
            "episode-groups",
            "episode-group",
            "episode-map",
            "episode-map-save",
            "inbox",
            "favorites",
            "recipes",
            "blindspots",
            "tonight",
            "franchises",
            "insights",
            "watched",
        )
    return path in (
        "/api/auth/logout",
        "/api/plex/servers",
        "/api/plex/status",
        "/api/plex/connect",
        "/api/plex/disconnect",
        "/api/compare",
        "/api/import",
        "/api/import/start",
        "/api/metadata",
        "/api/details",
        "/api/show",
        "/api/title",
        "/api/title/save",
        "/api/title/status",
        "/api/title/scopes",
        "/api/find",
        "/api/identify",
        "/api/correct",
        "/api/resolve",
        "/api/suggestions",
        "/api/enrichment",
        "/api/calendar",
        "/api/poster-info",
        "/api/ratings",
        "/api/ratings/preferences",
        "/api/playlist/preview",
        "/api/playlist/create",
        "/api/publications/preview",
        "/api/publications/apply",
    )
