/* SPDX-License-Identifier: AGPL-3.0-only */
/* Plex Web 4.160.0 adapter. Uses the client's existing authenticated transport;
 * credentials and internal models never enter bookmarks or diagnostic logs. */
(function (root) {
  'use strict';
  function playlistIdFromSource(value) {
    if (typeof value !== 'string') return null;
    try {
      // Plex source URIs can contain an encoded /playlists/ID/items path.
      for (let i = 0; i < 2; i++) value = decodeURIComponent(value);
    } catch {
      return null;
    }
    return value.match(/(?:^|\/)playlists\/(\d+)(?:\/items)?(?:$|[?#])/i)?.[1] || null;
  }
  const enabled = (value) => value === true || value === 1 || value === '1';
  function create(require, storage, core) {
    const registry = require(3467);
    const app = registry.hd('appModel');
    const store = registry.hd('appStore');
    const transport = require(74692);
    const ajax = transport.ajax;
    if (!app || !store || !ajax) throw new Error('Plex services are not ready');
    let binding = null;
    let revision = 0;
    let error = '';
    let report = () => {};
    let disposed = false;
    let intentSequence = 0;
    let nativeTracking = false;
    let inspectedQueue = '';
    let reportedQueue = '';
    let pendingNative = null;
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
      options.listweavarrOwnQueue = true;
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
          if (enabled(item.smart) || item.playlistType !== 'video') continue;
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
    async function poster(selection) {
      const source = (await sources()).find(
        (value) => String(get(value.server, 'machineIdentifier')) === selection.serverId
      );
      if (!source || selection.userId !== userId()) return null;
      const data = await request(source.provider, '/playlists/' + selection.playlistId);
      const path = data.Metadata?.[0]?.thumb || data.Metadata?.[0]?.composite;
      if (typeof path !== 'string' || !/^\/(?:playlists|library)\//.test(path)) return null;
      const options = source.provider.getXHROptions(path, { type: 'GET', timeout: 15000 });
      options.xhrFields = { ...options.xhrFields, responseType: 'blob' };
      delete options.dataType;
      const blob = await Promise.resolve(ajax(options));
      return blob instanceof Blob && /^image\/(?:jpeg|png|webp|gif)$/i.test(blob.type)
        ? blob
        : null;
    }
    function notify() {
      if (typeof root.dispatchEvent === 'function')
        root.dispatchEvent(new Event('listweavarr-playlist-progress'));
    }
    // Observe the existing client's queue request, rather than guessing playlist
    // membership from the currently playing episode. Never replace its callback.
    if (typeof transport.ajaxPrefilter === 'function') {
      nativeTracking = true;
      transport.ajaxPrefilter((options, original, xhr) => {
        if (disposed || original.listweavarrOwnQueue) return;
        let url;
        try {
          url = new URL(options.url);
        } catch {
          return;
        }
        if (!/\/playQueues\/?$/.test(url.pathname) || String(options.type).toUpperCase() !== 'POST')
          return;
        const sequence = ++intentSequence;
        const parameters = new URLSearchParams(
          typeof options.data === 'string' ? options.data : options.data || {}
        );
        for (const [key, value] of url.searchParams) parameters.set(key, value);
        const id = parameters.get('playlistID') || playlistIdFromSource(parameters.get('uri'));
        if (!id || !/^\d+$/.test(id) || parameters.get('shuffle') === '1') return;
        console.info('[Listweavarr Playlist Companion] native playlist queue request observed');
        const profile = userId();
        const requestServerEntity = get(player(), 'serverEntityID');
        xhr.done(async (response) => {
          try {
            console.info(
              '[Listweavarr Playlist Companion] native playlist response received ' +
                JSON.stringify({
                  latestRequest: sequence === intentSequence,
                  sameUser: profile === userId(),
                })
            );
            if (disposed || profile !== userId()) return;
            let queue = response?.MediaContainer;
            // Plex's model transport intentionally receives JSON as text and
            // parses it after the jqXHR callback. Observe that same format.
            if (!queue && typeof response === 'string' && response.trim().startsWith('{')) {
              const parsed = JSON.parse(response);
              queue = parsed.MediaContainer || parsed;
            }
            if (!queue && typeof DOMParser !== 'undefined') {
              const document =
                typeof response === 'string'
                  ? new DOMParser().parseFromString(response, 'application/xml')
                  : response;
              const element = document?.documentElement;
              if (element?.nodeName === 'MediaContainer')
                queue = Object.fromEntries(
                  Array.from(element.attributes, (attr) => [attr.name, attr.value])
                );
            }
            if (
              !queue?.playQueueID ||
              String(queue.playQueueShuffled) === '1' ||
              queue.playQueueShuffled === true
            ) {
              console.info(
                '[Listweavarr Playlist Companion] native response has no usable ordered queue'
              );
              return;
            }
            // The request may use a different connection URL from the server's
            // current preferred URL. Retain its explicit identity, then verify
            // against the actual player queue/server rather than guessing by host.
            pendingNative = {
              id,
              queueId: String(queue.playQueueID),
              profile,
              sequence,
              serverEntity: requestServerEntity,
            };
            const source = (await sources()).find((value) => {
              const candidate = value.provider.getXHROptions('/playQueues', { type: 'POST' });
              return new URL(candidate.url).origin === url.origin;
            });
            if (!source) {
              console.info(
                '[Listweavarr Playlist Companion] native request connection differs; awaiting active queue'
              );
              void discoverActivePlaylist();
              return;
            }
            const metadata = await request(source.provider, '/playlists/' + id);
            const playlist = metadata.Metadata?.[0];
            if (!playlist || enabled(playlist.smart) || playlist.playlistType !== 'video') return;
            const items = await contents(source.provider, id);
            if (
              Number(queue.playQueueTotalCount) !== items.length ||
              disposed ||
              sequence !== intentSequence ||
              profile !== userId()
            ) {
              console.info(
                '[Listweavarr Playlist Companion] native queue size or playback intent changed'
              );
              return;
            }
            binding = {
              ...context(source.server, id),
              title: playlist.title,
              items,
              queueId: String(queue.playQueueID),
            };
            revision = core.load(storage, binding)?.revision || 0;
            error = '';
            console.info('[Listweavarr Playlist Companion] normal Plex playlist queue bound');
            observe();
          } catch {
            error = 'Could not bind this playlist; ordinary Plex playback was left unchanged';
            console.info('[Listweavarr Playlist Companion] native queue verification failed');
          }
        });
      });
    }
    async function discoverActivePlaylist() {
      const p = player();
      const queue = get(p, 'playQueue');
      const queueId = String(get(queue, 'playQueueID') || '');
      if (
        !queueId ||
        !get(p, 'isOpen') ||
        enabled(get(queue, 'playQueueShuffled')) ||
        (binding?.queueId === queueId && binding.userId === userId())
      )
        return;
      const pending =
        pendingNative?.queueId === queueId &&
        pendingNative.profile === userId() &&
        pendingNative.serverEntity === get(p, 'serverEntityID')
          ? pendingNative
          : null;
      const id = playlistIdFromSource(get(queue, 'playQueueSourceURI')) || pending?.id;
      const reportKey = JSON.stringify([userId(), get(p, 'serverEntityID'), queueId, !!id]);
      if (reportedQueue !== reportKey) {
        reportedQueue = reportKey;
        console.info(
          '[Listweavarr Playlist Companion] native queue source inspected ' +
            JSON.stringify({
              playlistSource: !!id,
              count: Number(get(queue, 'playQueueTotalCount')) || 0,
            })
        );
      }
      if (!id) return; // Never guess playlist membership from a movie/episode alone.
      const profile = userId();
      const serverEntity = get(p, 'serverEntityID');
      const identity = JSON.stringify([
        profile,
        serverEntity,
        queueId,
        id,
        get(queue, 'playQueueTotalCount'),
      ]);
      if (inspectedQueue === identity) return;
      inspectedQueue = identity;
      const sequence = intentSequence;
      try {
        const source = (await sources()).find(
          (value) => value.server === queue.server || value.server.entityID() === serverEntity
        );
        if (!source) throw new Error('source');
        const data = await request(source.provider, '/playlists/' + id);
        const playlist = data.Metadata?.[0];
        if (!playlist || enabled(playlist.smart) || playlist.playlistType !== 'video') return;
        const items = await contents(source.provider, id);
        if (
          disposed ||
          profile !== userId() ||
          sequence !== intentSequence ||
          queue !== get(player(), 'playQueue') ||
          Number(get(queue, 'playQueueTotalCount')) !== items.length
        )
          return;
        binding = { ...context(source.server, id), title: playlist.title, items, queueId };
        revision = core.load(storage, binding)?.revision || 0;
        error = '';
        console.info('[Listweavarr Playlist Companion] active native playlist queue bound');
        observe();
      } catch {
        error = 'Could not verify the active playlist; ordinary playback was left unchanged';
      }
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
    function tick(p = player(), forceNotify = false) {
      if (!binding) return null;
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
      const selected = get(queue, 'playQueueItems')?.get(get(queue, 'playQueueSelectedItemID'));
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
      const durationMs = Math.max(0, Math.floor((get(p, 'durationSeconds') || 0) * 1000));
      const offsetMs = Math.floor(position * 1000);
      // The desktop player reports whole seconds. Only its final second counts
      // as complete; ordinary Stop, errors and Plex's watched threshold do not.
      const completed = durationMs > 0 && offsetMs > 0 && offsetMs >= durationMs - 1000;
      const previous = binding.bookmark;
      const bookmark = {
        ...core.checkpoint(binding, binding.items, entry.entryId, offsetMs, session, ++revision),
        title: binding.title,
        itemTitle: entry.title,
        showTitle: entry.showTitle,
        entryNumber: index + 1,
        totalEntries: binding.items.length,
        durationMs,
        completed,
        nextTitle: binding.items[index + 1]?.title || '',
        nextShowTitle: binding.items[index + 1]?.showTitle || '',
        paused: !!get(p, 'isPaused'),
        updatedAt: Date.now(),
      };
      core.save(storage, bookmark);
      binding.bookmark = bookmark;
      binding.wasOpen = true;
      if (
        forceNotify ||
        !previous ||
        previous.entryId !== bookmark.entryId ||
        previous.paused !== bookmark.paused ||
        previous.completed !== bookmark.completed
      )
        notify();
      error = '';
      return bookmark;
    }
    async function start(selection, resume) {
      ++intentSequence; // A pending normal Play response must not replace this intent.
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
        // Queue source metadata survives transport differences and also covers
        // starting directly at an entry in the middle of a native playlist.
        void discoverActivePlaylist();
        // Some desktop state changes are silent. Poll the lifecycle as well as
        // position so Stop still refreshes Home when no model event arrives.
        playerChanged();
      } catch {
        error = 'Could not save playlist progress';
      }
    }
    const observedPlayer = player();
    function playerChanged() {
      if (disposed || !binding) return;
      try {
        // Stop may silently clear the queue. The latest valid position is
        // already persisted; previousAttributes can instead contain an older
        // seek/pause snapshot, so never write it over that newer checkpoint.
        const stopped = binding.wasOpen && !get(observedPlayer, 'isOpen');
        if (stopped) {
          binding.wasOpen = false;
          if (binding.userId === userId()) notify();
        } else tick();
      } catch {
        error = 'Could not save playlist progress';
      }
    }
    observedPlayer.on?.('change', playerChanged);
    // Flush synchronously on an orderly window close. Regular model changes
    // already persist progress, so this is a fallback rather than a requirement.
    root.addEventListener?.('pagehide', observe);
    root.addEventListener?.('beforeunload', observe);
    const timer = setInterval(observe, 2000);
    return {
      playlists,
      poster,
      nativeTracking,
      start,
      pause,
      status,
      tick,
      onProgress(callback) {
        report = callback;
      },
      dispose() {
        observe();
        disposed = true;
        observedPlayer.off?.('change', playerChanged);
        root.removeEventListener?.('pagehide', observe);
        root.removeEventListener?.('beforeunload', observe);
        clearInterval(timer);
        binding = null;
      },
    };
  }
  if (typeof module !== 'undefined' && module.exports)
    module.exports = { create, playlistIdFromSource };
  else root.ListweavarrPlexAdapter = { create };
})(globalThis);
