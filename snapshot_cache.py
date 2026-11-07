# SPDX-License-Identifier: AGPL-3.0-only
"""Cache parsed local JSON by filesystem identity; every caller owns its copy.

Atomic replacements and external edits invalidate the snapshot. Failed reads
never return stale credentials or hide corrupt files. Bounded for test workspaces.
"""
import copy
import json
import threading
from collections import OrderedDict

_lock = threading.RLock()
_cache = OrderedDict()


def read(path, default):
    try:
        stat = path.stat()
    except FileNotFoundError:
        with _lock:
            _cache.pop(str(path.resolve()), None)
        return copy.deepcopy(default)
    key = str(path.resolve())
    stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            _cache.move_to_end(key)
            value = cached[1]
        else:
            value = None
    if value is None:
        value = json.loads(path.read_text("utf-8"))
        with _lock:
            _cache[key] = (stamp, value)
            _cache.move_to_end(key)
            while len(_cache) > 2:
                _cache.popitem(last=False)
    return copy.deepcopy(value)
