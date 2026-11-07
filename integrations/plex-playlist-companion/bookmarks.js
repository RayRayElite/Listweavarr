/* SPDX-License-Identifier: AGPL-3.0-only */
/* Shared, offline bookmark rules. No Plex tokens, network calls or watched flags. */
(function (root) {
  'use strict';
  function required(value, label) {
    if (typeof value !== 'string' || !value.trim() || value.length > 300)
      throw new Error(`Missing or invalid ${label}`);
    return value;
  }
  function entries(items) {
    if (!Array.isArray(items) || items.length > 10000) throw new Error('Invalid playlist entries');
    const seen = new Set();
    return items.map((item) => {
      const entryId = required(item.entryId, 'playlist entry ID');
      if (seen.has(entryId)) throw new Error('Duplicate playlist entry ID');
      seen.add(entryId);
      return { entryId, ratingKey: required(item.ratingKey, 'rating key') };
    });
  }
  function checkpoint(context, items, entryId, offsetMs, sessionId, revision = 0) {
    const list = entries(items);
    const index = list.findIndex((item) => item.entryId === entryId);
    if (index < 0) throw new Error('Entry is not in the playlist');
    if (
      !Number.isSafeInteger(offsetMs) ||
      offsetMs < 0 ||
      !Number.isSafeInteger(revision) ||
      revision < 0
    )
      throw new Error('Invalid playback offset or revision');
    return {
      schema: 1,
      serverId: required(context.serverId, 'server'),
      userId: required(context.userId, 'user'),
      playlistId: required(context.playlistId, 'playlist'),
      ...list[index],
      offsetMs,
      sessionId: required(sessionId, 'session'),
      ratingKeyOccurrences: list.filter((item) => item.ratingKey === list[index].ratingKey).length,
      revision,
      completed: false,
    };
  }
  function storageKey(context) {
    return (
      'playlist-companion:v1:' +
      JSON.stringify([
        required(context.serverId, 'server'),
        required(context.userId, 'user'),
        required(context.playlistId, 'playlist'),
      ])
    );
  }
  function reconcile(bookmark, items) {
    const list = entries(items);
    let index = list.findIndex((item) => item.entryId === bookmark.entryId);
    if (index >= 0 && list[index].ratingKey !== bookmark.ratingKey)
      return { status: 'needs-review', reason: 'entry-identity-changed' };
    let recovered = false;
    if (index < 0) {
      const candidates = list
        .map((item, position) => ({ ...item, position }))
        .filter((item) => item.ratingKey === bookmark.ratingKey);
      if (candidates.length !== 1 || bookmark.ratingKeyOccurrences !== 1)
        return {
          status: 'needs-review',
          reason: candidates.length ? 'duplicate-occurrence' : 'entry-removed',
        };
      index = candidates[0].position;
      recovered = true;
    }
    if (bookmark.completed) index += 1;
    if (index === list.length) return { status: 'finished' };
    return {
      status: 'ready',
      recovered,
      index,
      ...list[index],
      offsetMs: bookmark.completed ? 0 : bookmark.offsetMs,
    };
  }
  function update(bookmark, event) {
    if (
      event.sessionId !== bookmark.sessionId ||
      !Number.isSafeInteger(event.revision) ||
      event.revision <= bookmark.revision
    )
      return bookmark; // Old callbacks and other sessions cannot move this bookmark.
    if (
      event.entryId !== bookmark.entryId ||
      !Number.isSafeInteger(event.offsetMs) ||
      event.offsetMs < 0
    )
      throw new Error('Progress does not belong to the selected playlist entry');
    return {
      ...bookmark,
      offsetMs: event.offsetMs,
      revision: event.revision,
      completed: event.completed === true,
    };
  }
  function save(storage, bookmark) {
    storage.setItem(storageKey(bookmark), JSON.stringify(bookmark));
  }
  // Keep the bookmark as a synced tombstone: deletion would let an offline client restore it.
  // A new playback checkpoint has no dismissed flag and brings the card back naturally.
  function dismiss(storage, context) {
    const bookmark = load(storage, context);
    if (!bookmark) return;
    save(storage, {
      ...bookmark,
      dismissed: true,
      updatedAt: Math.max(Date.now(), (bookmark.updatedAt || 0) + 1),
    });
    root.dispatchEvent?.(new Event('listweavarr-playlist-progress'));
  }
  function pinKey(context) {
    return 'playlist-companion:pins:v1:' + required(context.userId, 'user');
  }
  function pins(storage, context) {
    try {
      const values = JSON.parse(storage.getItem(pinKey(context)) || '[]');
      if (!Array.isArray(values)) return [];
      return [
        ...new Set(
          values.filter((value) => {
            if (typeof value !== 'string' || !value.startsWith('playlist-companion:v1:'))
              return false;
            try {
              const [serverId, userId, playlistId] = JSON.parse(
                value.slice('playlist-companion:v1:'.length)
              );
              return (
                userId === context.userId && storageKey({ serverId, userId, playlistId }) === value
              );
            } catch {
              return false;
            }
          })
        ),
      ].slice(0, 100);
    } catch {
      return [];
    }
  }
  function isPinned(storage, context) {
    return pins(storage, context).includes(storageKey(context));
  }
  function savePins(storage, context, values) {
    storage.setItem(pinKey(context), JSON.stringify(values));
    root.dispatchEvent?.(new Event('listweavarr-playlist-settings'));
  }
  function pin(storage, context) {
    const key = storageKey(context),
      list = pins(storage, context).filter((value) => value !== key);
    if (list.length >= 100) throw new Error('Up to 100 playlists can be pinned.');
    savePins(storage, context, [key, ...list]);
    const bookmark = load(storage, context);
    if (bookmark?.dismissed)
      save(storage, {
        ...bookmark,
        dismissed: false,
        updatedAt: Math.max(Date.now(), (bookmark.updatedAt || 0) + 1),
      });
  }
  function unpin(storage, context) {
    savePins(
      storage,
      context,
      pins(storage, context).filter((value) => value !== storageKey(context))
    );
  }
  function movePin(storage, context, direction) {
    const list = pins(storage, context),
      index = list.indexOf(storageKey(context)),
      next = index + direction;
    if (index < 0 || next < 0 || next >= list.length || ![-1, 1].includes(direction)) return;
    [list[index], list[next]] = [list[next], list[index]];
    savePins(storage, context, list);
  }
  function orderPlaylists(rows, storage) {
    return [...rows].sort((a, b) => {
      const left = pins(storage, a).indexOf(storageKey(a)),
        right = pins(storage, b).indexOf(storageKey(b));
      if (left >= 0 || right >= 0)
        return (left < 0 ? Infinity : left) - (right < 0 ? Infinity : right);
      return (b.bookmark?.updatedAt || 0) - (a.bookmark?.updatedAt || 0);
    });
  }
  function load(storage, context) {
    const text = storage.getItem(storageKey(context));
    if (!text) return null;
    try {
      const value = JSON.parse(text);
      if (
        value.schema !== 1 ||
        storageKey(value) !== storageKey(context) ||
        !Number.isSafeInteger(value.offsetMs) ||
        value.offsetMs < 0 ||
        !Number.isSafeInteger(value.revision) ||
        value.revision < 0 ||
        !Number.isSafeInteger(value.ratingKeyOccurrences) ||
        value.ratingKeyOccurrences < 1 ||
        (value.dismissed !== undefined && typeof value.dismissed !== 'boolean') ||
        typeof value.completed !== 'boolean'
      )
        return null;
      required(value.entryId, 'entry');
      required(value.ratingKey, 'rating key');
      required(value.sessionId, 'session');
      return value;
    } catch {
      return null;
    }
  }
  // Older Plex desktop Chromium supports AbortController but not the newer
  // AbortSignal.timeout API. Always clear our timer after success or failure.
  async function fetchWithTimeout(fetcher, url, options, milliseconds) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), milliseconds);
    try {
      return await fetcher(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }
  // Both clients keep their original local bookmarks. A separate, revocable
  // capability permits syncing only bookmarks, never artwork-only credentials.
  function createSync(storage, player, fetcher = globalThis.fetch.bind(globalThis)) {
    let busy = false;
    async function sync() {
      if (busy || storage.getItem('playlist-companion:sync-enabled') !== 'true') return;
      const cfg = JSON.parse(storage.getItem('playlist-companion:artwork-pairing') || 'null');
      if (!cfg?.progressToken)
        throw new Error('Create a new pairing in Listweavarr to enable progress sync.');
      const url = new URL(cfg.url);
      if (
        !['http:', 'https:'].includes(url.protocol) ||
        url.username ||
        url.password ||
        url.pathname !== '/' ||
        url.search ||
        url.hash
      )
        throw new Error('Invalid sync server.');
      busy = true;
      try {
        const scopes = (await player.playlists())
          .filter((scope) => !cfg.serverId || scope.serverId === cfg.serverId)
          .map(({ serverId, userId, playlistId }) => ({ serverId, userId, playlistId }));
        const items = scopes
          .map((scope) => load(storage, scope))
          .filter((row) => row && Number.isSafeInteger(row.updatedAt));
        const response = await fetchWithTimeout(
          fetcher,
          url.origin + '/api/playlist-companion/progress',
          {
            method: 'POST',
            credentials: 'omit',
            cache: 'no-store',
            headers: {
              Authorization: 'Bearer ' + cfg.progressToken,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ scopes, items }),
          },
          10000
        );
        if (!response.ok)
          throw new Error('Sync server unavailable or pairing revoked. Local progress is safe.');
        const data = await response.json();
        if (data.schema !== 1 || !Array.isArray(data.items) || data.items.length > 1000)
          throw new Error('Invalid sync response.');
        // Re-read current account and local progress after the network wait.
        const current = await player.playlists();
        let changed = false;
        for (const row of data.items) {
          if (!current.some((scope) => storageKey(scope) === storageKey(row))) continue;
          const local = load(storage, row);
          if (!Number.isSafeInteger(row.updatedAt) || (local?.updatedAt || 0) >= row.updatedAt)
            continue;
          const scratch = { getItem: () => JSON.stringify(row) };
          if (!load(scratch, row)) continue;
          save(storage, row);
          changed = true;
        }
        if (changed) globalThis.dispatchEvent?.(new Event('listweavarr-playlist-progress'));
        return { updated: changed };
      } finally {
        busy = false;
      }
    }
    return { sync };
  }
  const api = Object.freeze({
    checkpoint,
    dismiss,
    pins,
    isPinned,
    pin,
    unpin,
    movePin,
    orderPlaylists,
    reconcile,
    update,
    storageKey,
    save,
    load,
    createSync,
    fetchWithTimeout,
  });
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ListweavarrPlaylistCore = api;
})(globalThis);
