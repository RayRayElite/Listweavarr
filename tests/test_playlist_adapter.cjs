/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
const { create } = require('../integrations/plex-playlist-companion/plex-adapter.js');
const {
  isHome,
  findHomeContainer,
  findHomePlacement,
} = require('../integrations/plex-playlist-companion/home.js');
// Placement must follow the complete native hub, never its heading alone.
const parent = {},
  followingHub = {};
const nativeHub = { parentElement: parent, nextSibling: followingHub };
const heading = { textContent: 'Continue Watching', closest: () => nativeHub };
assert.deepEqual(findHomePlacement({ querySelectorAll: () => [heading] }), {
  container: parent,
  before: followingHub,
  hub: nativeHub,
});
assert.equal(
  findHomePlacement({
    querySelectorAll: () => [
      {
        textContent: 'Continue Watching',
        closest: () => null,
        parentElement: null,
      },
    ],
  }),
  null
);
const combinedPageAndScroller = { querySelector: () => null };
assert.equal(
  findHomeContainer({ querySelector: () => combinedPageAndScroller }),
  combinedPageAndScroller
);
const nestedScroller = {};
assert.equal(
  findHomeContainer({ querySelector: () => ({ querySelector: () => nestedScroller }) }),
  nestedScroller
);
assert.equal(isHome('#!/'), true);
assert.equal(isHome('#!/home'), true);
assert.equal(isHome('#!/server/abc/playlist/3'), false);
class Model {
  constructor(values, id) {
    this.values = values;
    this.id = id;
  }
  get(key) {
    return this.values[key];
  }
  on(name, callback) {
    (this.listeners ||= new Map()).set(callback, name);
  }
  off(name, callback) {
    this.listeners?.delete(callback);
  }
  previousAttributes() {
    return this.previous;
  }
  set(values) {
    this.previous = { ...this.values };
    Object.assign(this.values, values);
    for (const [callback, name] of this.listeners || []) if (name === 'change') callback(this);
  }
  entityID() {
    return this.id;
  }
}
async function main() {
  const memory = new Map();
  const storage = {
    getItem: (key) => memory.get(key) ?? null,
    setItem: (key, value) => memory.set(key, value),
  };
  const dispatched = [];
  const requests = [];
  let wrongOccurrence = false;
  let omitTotal = false;
  const rows = [
    {
      playlistItemID: 10,
      ratingKey: 100,
      key: '/library/metadata/100',
      title: 'Episode',
      type: 'episode',
    },
    {
      playlistItemID: 11,
      ratingKey: 101,
      key: '/library/metadata/101',
      title: 'Movie',
      type: 'movie',
    },
  ];
  const provider = new Model({}, 'provider');
  provider.getXHROptions = (url, options) => ({ url: 'http://plex.test' + url, ...options });
  const providers = { populate: () => Promise.resolve(), get: () => provider };
  const server = new Model(
    { isConnected: true, machineIdentifier: 'server', providers },
    'server-entity'
  );
  const user = new Model({}, 'user');
  const player = new Model({ isOpen: false, isPaused: true, positionSeconds: 0 });
  const app = new Model({
    servers: { models: [server] },
    user,
    ui: new Model({ audioVideoPlayer: player }),
  });
  const registry = {
    hd: (key) => (key === 'appModel' ? app : { dispatch: (action) => dispatched.push(action) }),
  };
  const ajax = async (options) => {
    requests.push(options);
    const path = new URL(options.url).pathname;
    if (path === '/playlists' || path === '/playlists/3')
      return {
        MediaContainer: {
          Metadata: [{ ratingKey: 3, title: 'Test', playlistType: 'video', leafCount: 2 }],
        },
      };
    if (path === '/playlists/3/items') {
      const offset = options.data['X-Plex-Container-Start'];
      const page = rows.slice(offset, offset + 500);
      return {
        MediaContainer: {
          size: page.length,
          ...(omitTotal ? {} : { totalSize: rows.length }),
          offset,
          Metadata: page,
        },
      };
    }
    if (path === '/playQueues') {
      const params = new URLSearchParams(options.url.split('?')[1]);
      assert.equal(params.get('playlistID'), '3');
      assert.equal(params.get('type'), 'video');
      assert.equal(params.get('shuffle'), '0');
      assert.equal(options.data, undefined);
      const index = rows.findIndex((row) => row.key === params.get('key'));
      return {
        MediaContainer: {
          playQueueID: 9,
          playQueueSelectedItemOffset: wrongOccurrence ? 1 - index : index,
          playQueueSelectedMetadataItemID: rows[index].ratingKey,
          playQueueShuffled: false,
        },
      };
    }
    throw new Error('Unexpected request');
  };
  let native;
  let sample;
  const interval = global.setInterval;
  const dispatchEvent = global.dispatchEvent;
  let notices = 0;
  global.dispatchEvent = () => {
    notices += 1;
  };
  global.setInterval = (callback, delay) => {
    sample = callback;
    return interval(callback, delay);
  };
  const api = create(
    (id) =>
      id === 3467
        ? registry
        : {
            ajax,
            ajaxPrefilter: (callback) => {
              native = callback;
            },
          },
    storage,
    core
  );
  try {
    const [playlist] = await api.playlists();
    const start = await api.start(playlist, false);
    assert.equal(start.nextTitle, 'Movie');
    assert.equal(dispatched[0].payload.startOffsetMilliseconds, 0);
    const metadata = new Model({ ratingKey: 100 });
    const entry = new Model({ metadataItem: metadata });
    player.values.playQueue = new Model({
      playQueueID: 9,
      playQueueSelectedItemOffset: 0,
      playQueueSelectedItemID: 44,
      playQueueItems: { get: () => entry },
    });
    Object.assign(player.values, {
      isOpen: true,
      isMediaLoading: false,
      playbackSessionID: 'session',
      positionSeconds: 37,
    });
    assert.equal(api.tick().offsetMs, 37000);
    player.set({ positionSeconds: 43, isPaused: false });
    assert.equal(core.load(storage, playlist).offsetMs, 43000);
    player.set({ positionSeconds: 99, durationSeconds: 100, hasError: true });
    assert.equal(core.load(storage, playlist).offsetMs, 43000);
    assert.equal(core.load(storage, playlist).completed, false);
    player.set({ positionSeconds: 43, durationSeconds: 0, hasError: false });
    // Stop atomically clears the player. Retain its last live state, not zero.
    player.set({ isOpen: false, positionSeconds: 0, playQueue: null });
    assert.equal(core.load(storage, playlist).offsetMs, 43000);
    assert.equal(core.load(storage, playlist).completed, false);
    player.set({ ...player.previousAttributes(), isPaused: true, positionSeconds: 37 });
    // Native desktop Stop may emit no model event. Polling must notify Home
    // exactly once and must not overwrite a newer sample with stale attributes.
    player.values.positionSeconds = 160;
    sample();
    const beforeStop = notices;
    const openState = { ...player.values };
    player.values.isOpen = false;
    player.values.positionSeconds = 0;
    sample();
    assert.equal(notices, beforeStop + 1);
    assert.equal(core.load(storage, playlist).offsetMs, 160000);
    sample();
    assert.equal(notices, beforeStop + 1);
    player.set({ ...openState, positionSeconds: 37 });
    player.values.isPaused = true;
    const resumed = await api.start(playlist, true);
    assert.equal(resumed.offsetMs, 37000);
    assert.equal(resumed.nextTitle, 'Movie');
    assert.equal(dispatched.at(-1).payload.startOffsetMilliseconds, 37000);
    player.values.playQueue.values.playQueueID = 99;
    player.values.positionSeconds = 2;
    assert.equal(api.tick(), null);
    assert.equal(core.load(storage, playlist).offsetMs, 37000);
    wrongOccurrence = true;
    const count = dispatched.length;
    await assert.rejects(api.start(playlist, true), /exact playlist occurrence/);
    assert.equal(dispatched.length, count);
    assert.equal(
      requests.some((r) => /scrobble|timeline|prefs/.test(r.url)),
      false
    );
    user.id = 'different-user';
    await assert.rejects(api.start(playlist, true), /user changed/);
    user.id = 'user';
    wrongOccurrence = false;
    player.values.playQueue.values.playQueueID = 9;
    player.set({ durationSeconds: 100, positionSeconds: 99, isPaused: true });
    assert.equal(core.load(storage, playlist).completed, true);
    assert.equal(core.load(storage, playlist).nextTitle, 'Movie');
    player.set({ isOpen: false, positionSeconds: 0, playQueue: null });
    const next = await api.start(playlist, true);
    assert.equal(next.index, 1);
    assert.equal(next.offsetMs, 0);
    // Checkpoint the final movie, including completion before player teardown.
    metadata.values.ratingKey = 101;
    player.set({
      isOpen: true,
      isPaused: false,
      positionSeconds: 20,
      durationSeconds: 120,
      playQueue: new Model({
        playQueueID: 9,
        playQueueSelectedItemOffset: 1,
        playQueueSelectedItemID: 45,
        playQueueItems: { get: () => entry },
      }),
    });
    assert.equal(core.load(storage, playlist).completed, false);
    player.set({ positionSeconds: 120, isPaused: true });
    player.set({ isOpen: false, positionSeconds: 0, playQueue: null });
    assert.equal(
      core.reconcile(core.load(storage, playlist), [
        { entryId: '10', ratingKey: '100' },
        { entryId: '11', ratingKey: '101' },
      ]).status,
      'finished'
    );
    // A changed profile must never flush the old profile's position on Stop.
    const finished = core.load(storage, playlist);
    user.id = 'other';
    player.set({ isOpen: true, positionSeconds: 5 });
    player.set({ isOpen: false, positionSeconds: 0 });
    assert.deepEqual(core.load(storage, playlist), finished);
    user.id = 'user';
    player.values.playQueue = new Model({
      playQueueID: 9,
      playQueueSelectedItemOffset: 0,
      playQueueSelectedItemID: 44,
      playQueueItems: { get: () => entry },
    });
    rows.splice(
      0,
      rows.length,
      ...Array.from({ length: 641 }, (_, index) => ({
        playlistItemID: index + 1,
        ratingKey: index + 1000,
        key: '/library/metadata/' + (index + 1000),
        title: 'Item ' + index,
        type: index % 2 ? 'movie' : 'episode',
      }))
    );
    const priorPages = requests.filter(
      (r) => new URL(r.url).pathname === '/playlists/3/items'
    ).length;
    await api.start(playlist, false);
    assert.equal(
      requests.filter((r) => new URL(r.url).pathname === '/playlists/3/items').length - priorPages,
      2
    );
    omitTotal = true;
    await assert.rejects(api.start(playlist, false), /verifiable total/);
    omitTotal = false;
    let work;
    native(
      { url: 'http://plex.test/playQueues?playlistID=3', type: 'POST' },
      {},
      {
        done: (callback) => {
          work = callback(
            JSON.stringify({
              MediaContainer: {
                playQueueID: 77,
                playQueueTotalCount: 641,
                playQueueShuffled: false,
              },
            })
          );
        },
      }
    );
    await work;
    player.values.isOpen = true;
    player.values.isMediaLoading = false;
    player.values.playQueue.values.playQueueID = 77;
    player.values.playQueue.values.playQueueSelectedItemOffset = 4;
    metadata.values.ratingKey = 1004;
    player.values.positionSeconds = 18;
    assert.equal(api.tick().entryId, '5');
    assert.equal(core.load(storage, playlist).offsetMs, 18000);
    let observed = false;
    native(
      { url: 'http://plex.test/playQueues?uri=unrelated', type: 'POST' },
      {},
      {
        done: () => {
          observed = true;
        },
      }
    );
    assert.equal(observed, false);
  } finally {
    api.dispose();
    global.setInterval = interval;
    if (dispatchEvent) global.dispatchEvent = dispatchEvent;
    else delete global.dispatchEvent;
    assert.equal(player.listeners.size, 0, 'Detach model observers on disposal');
  }
  console.log(
    'Playlist adapter checks passed: source order, offsets, profile/queue isolation and no watched writes.'
  );
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
