/* SPDX-License-Identifier: AGPL-3.0-only */
/* Plex Web 4.160.0 adapter. Uses the client's existing authenticated transport;
 * credentials and internal models never enter bookmarks or diagnostic logs. */
(function (root) {
  'use strict';
  function create(require, storage, core) {
    const registry = require(3467);
    const app = registry.hd('appModel');
    const store = registry.hd('appStore');
    const ajax = require(74692).ajax;
    if (!app || !store || !ajax) throw new Error('Plex services are not ready');
    let binding = null;
    let revision = 0;
    let error = '';
    let report = () => {};
    function progress(message) {
      report(message);
      console.info('[Listweavarr Playlist Companion] ' + message);
    }
    const get = (model, key) => model && model.get(key);
    const player = () => get(get(app, 'ui'), 'audioVideoPlayer');
    const userId = () => String(get(app, 'user').id || '');
    const context = (server, playlistId) => ({
      serverId: String(get(server, 'machineIdentifier')),
      userId: userId(),
      playlistId: String(playlistId),
    });
    async function request(provider, path, method = 'GET', data = {}) {
      // Plex's queue-creation parameters belong in the URL, not a POST body.
      const target = method === 'GET' ? path : path + '?' + new URLSearchParams(data).toString();
      const options = provider.getXHROptions(target, {
        type: method,
        data: method === 'GET' ? data : undefined,
        dataType: 'json',
        timeout: 20000,
      });
      options.headers = { ...options.headers, Accept: 'application/json' };
      let result;
      try {
        result = await Promise.resolve(ajax(options));
      } catch (failure) {
        const status = Number.isInteger(failure?.status) ? ` (HTTP ${failure.status})` : '';
        throw new Error(
          'Plex request failed' + status + '. Check the server connection and retry.'
        );
      }
      if (!result || !result.MediaContainer)
        throw new Error('Plex returned an unsupported response');
      return result.MediaContainer;
    }
    async function sources() {
      const results = [];
      for (const server of get(app, 'servers').models) {
        if (!get(server, 'isConnected') || get(server, 'isCloud')) continue;
        const providers = get(server, 'providers');
        await Promise.resolve(providers.populate());
        const provider = providers.get('com.plexapp.plugins.library');
        if (provider) results.push({ server, provider });
      }
      return results;
    }
    async function playlists() {
      const result = [];
      for (const source of await sources()) {
        const data = await request(source.provider, '/playlists', 'GET', { playlistType: 'video' });
        for (const item of data.Metadata || []) {
          if (item.smart || item.playlistType !== 'video') continue;
          const scope = context(source.server, item.ratingKey);
          result.push({
            ...scope,
            title: item.title,
            count: item.leafCount || 0,
            bookmark: core.load(storage, scope),
          });
        }
      }
      return result;
    }
    async function contents(provider, playlistId) {
      const result = [];
      let total = null;
      while (total === null || result.length < total) {
        const page = await request(provider, `/playlists/${playlistId}/items`, 'GET', {
          'X-Plex-Container-Start': result.length,
          'X-Plex-Container-Size': 500,
        });
        const rows = page.Metadata || [];
        if (page.totalSize == null && rows.length >= 500)
          throw new Error('Plex did not provide a verifiable total for this large playlist');
        if (page.offset != null && Number(page.offset) !== result.length)
          throw new Error('Plex returned an unexpected playlist page');
        const declared = Number(page.totalSize ?? page.size);
        if (!Number.isSafeInteger(declared) || declared < 0 || declared > 10000)
          throw new Error('Playlist size cannot be verified');
        if (total === null) total = declared;
        if (page.totalSize != null && Number(page.totalSize) !== total)
          throw new Error('Playlist changed while reading; retry');
        if (!rows.length && result.length < total)
          throw new Error('Plex returned an incomplete playlist');
        for (const item of rows) {
          if (!item.playlistItemID || !item.ratingKey)
            throw new Error('Playlist entry identity is missing');
          result.push({
            entryId: String(item.playlistItemID),
            ratingKey: String(item.ratingKey),
            key: item.key,
            title: item.title,
            showTitle: item.grandparentTitle || '',
            type: item.type,
          });
        }
        if (
          result.length > total ||
          new Set(result.map((item) => item.entryId)).size !== result.length
        )
          throw new Error('Plex returned repeated or unexpected entries');
      }
      return result;
    }
    function tick() {
      if (!binding) return null;
      const p = player();
      const queue = get(p, 'playQueue');
      if (
        userId() !== binding.userId ||
        String(get(queue, 'playQueueID')) !== binding.queueId ||
        !get(p, 'isOpen') ||
        get(p, 'isMediaLoading') ||
        get(p, 'hasError')
      )
        return null;
      const index = get(queue, 'playQueueSelectedItemOffset');
      const selected = get(queue, 'playQueueItems').get(get(queue, 'playQueueSelectedItemID'));
      const metadata = get(selected, 'metadataItem');
      const entry = binding.items[index];
      const position = get(p, 'positionSeconds');
      if (
        !entry ||
        String(get(metadata, 'ratingKey')) !== entry.ratingKey ||
        !Number.isFinite(position) ||
        position < 0
      )
        return null;
      const session = String(get(p, 'playbackSessionID') || binding.queueId);
      const bookmark = {
        ...core.checkpoint(
          binding,
          binding.items,
          entry.entryId,
          Math.floor(position * 1000),
          session,
          ++revision
        ),
        title: binding.title,
        itemTitle: entry.title,
        showTitle: entry.showTitle,
        updatedAt: Date.now(),
      };
      core.save(storage, bookmark);
      binding.bookmark = bookmark;
      error = '';
      return bookmark;
    }
    async function start(selection, resume) {
      progress('Checking playlist playback context…');
      if (selection.userId !== userId())
        throw new Error('Plex user changed; refresh the playlist list');
      const current = player();
      if (get(current, 'isOpen') && !get(current, 'isPaused'))
        throw new Error('Pause or stop current playback before starting another playlist');
      const source = (await sources()).find(
        (value) => String(get(value.server, 'machineIdentifier')) === selection.serverId
      );
      if (!source) throw new Error('Playlist server is unavailable');
      progress('Reading the complete playlist…');
      const items = await contents(source.provider, selection.playlistId);
      if (!items.length) throw new Error('Playlist has no available entries');
      const saved = core.load(storage, selection);
      if (resume && !saved) throw new Error('No saved playlist bookmark');
      const target = resume
        ? core.reconcile(saved, items)
        : { status: 'ready', index: 0, ...items[0], offsetMs: 0 };
      if (target.status !== 'ready')
        throw new Error(
          target.status === 'finished'
            ? 'Playlist is finished'
            : 'Playlist changed; bookmark needs review'
        );
      progress('Creating the ordered playlist queue…');
      const data = await request(source.provider, '/playQueues', 'POST', {
        playlistID: selection.playlistId,
        type: 'video',
        key: items[target.index].key,
        shuffle: 0,
        repeat: 0,
      });
      if (
        Number(data.playQueueSelectedItemOffset) !== target.index ||
        String(data.playQueueSelectedMetadataItemID) !== target.ratingKey ||
        data.playQueueShuffled
      )
        throw new Error(
          'Plex did not select the exact playlist occurrence. Playback was not started.'
        );
      binding = { ...selection, items, queueId: String(data.playQueueID) };
      revision = saved ? saved.revision : 0;
      progress('Sending the playlist queue to the desktop player…');
      store.dispatch({
        type: 'ui/player/playerLifecycle/startExistingPlayQueuePlayback',
        payload: {
          serverEntityID: source.server.entityID(),
          providerEntityID: source.provider.entityID(),
          playQueueType: 'video',
          playQueueID: binding.queueId,
          startOffsetMilliseconds: target.offsetMs,
        },
      });
      return {
        index: target.index,
        title: items[target.index].title,
        offsetMs: target.offsetMs,
        nextTitle: items[target.index + 1]?.title || null,
      };
    }
    function pause() {
      const p = player();
      if (!binding || String(get(get(p, 'playQueue'), 'playQueueID')) !== binding.queueId)
        throw new Error('No companion-bound playback to pause');
      if (!get(p, 'isPaused'))
        store.dispatch({
          type: 'ui/player/playerMedia/togglePlayPause',
          payload: { playerType: 'audioVideo' },
        });
      return tick();
    }
    function status() {
      const p = player();
      const queue = get(p, 'playQueue');
      return {
        connected: true,
        tracking: !!binding,
        paused: !!get(p, 'isPaused'),
        open: !!get(p, 'isOpen'),
        loading: !!get(p, 'isMediaLoading'),
        index: get(queue, 'playQueueSelectedItemOffset') ?? null,
        offsetMs: Math.floor((get(p, 'positionSeconds') || 0) * 1000),
        bookmark: binding?.bookmark || null,
        error,
      };
    }
    function observe() {
      try {
        tick();
      } catch {
        error = 'Could not save playlist progress';
      }
    }
    const timer = setInterval(observe, 2000);
    return {
      playlists,
      start,
      pause,
      status,
      tick,
      onProgress(callback) {
        report = callback;
      },
      dispose() {
        observe();
        clearInterval(timer);
        binding = null;
      },
    };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { create };
  else root.ListweavarrPlexAdapter = { create };
})(globalThis);
