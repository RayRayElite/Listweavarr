# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded private image cache: browse JSON carries URLs, exports retain originals.

Hashes identify immutable image bytes; the HTTP route still enforces owner auth.
No files or user artwork are uploaded, rewritten or redistributed.
"""
import base64
import hashlib
import re
import threading
from collections import OrderedDict

LIMIT = 64 * 1024 * 1024
_lock = threading.RLock()
_images = OrderedDict()
_size = 0
_PATTERN = re.compile(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)")


def register(value):
    global _size
    if not isinstance(value, str) or len(value) > 1_500_000:
        return value
    match = _PATTERN.fullmatch(value)
    if not match:
        return value
    key = hashlib.sha256(value.encode()).hexdigest()
    with _lock:
        if key in _images:
            _images.move_to_end(key)
            return "/api/artwork/" + key
    try:
        raw = base64.b64decode(match[2], validate=True)
    except ValueError:
        return value
    mime = "image/" + match[1]
    valid = (
        raw.startswith(b"\x89PNG\r\n\x1a\n")
        if match[1] == "png"
        else (
            raw.startswith(b"\xff\xd8\xff")
            if match[1] == "jpeg"
            else raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
        )
    )
    if not valid or len(raw) > 1_000_000:
        return value
    with _lock:
        if key not in _images:
            _images[key] = (mime, raw)
            _size += len(raw)
        while _size > LIMIT and _images:
            _, (_, removed) = _images.popitem(last=False)
            _size -= len(removed)
    return "/api/artwork/" + key


def project(rows):
    return [
        dict(
            row,
            **{
                key: register(row[key])
                for key in ("poster", "playlist_poster")
                if key in row
            },
        )
        for row in rows
    ]


def get(key):
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        return None
    with _lock:
        result = _images.get(key)
        if result:
            _images.move_to_end(key)
        return result


def clear():
    global _size
    with _lock:
        _images.clear()
        _size = 0
