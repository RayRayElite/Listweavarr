/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
const { create } = require('../integrations/plex-playlist-companion/plex-adapter.js');
class Model {
  constructor(values, id) {
    this.values = values;
    this.id = id;
  }
  get(key) {
    return this.values[key];
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
  provider.getXHROptions = (url, options) => ({ url, ...options });
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
    if (options.url === '/playlists')
      return {
        MediaContainer: {
          Metadata: [{ ratingKey: 3, title: 'Test', playlistType: 'video', leafCount: 2 }],
        },
      };
    if (options.url === '/playlists/3/items') {
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
    if (options.url.startsWith('/playQueues?')) {
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
  const api = create((id) => (id === 3467 ? registry : { ajax }), storage, core);
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
    const priorPages = requests.filter((r) => r.url === '/playlists/3/items').length;
    await api.start(playlist, false);
    assert.equal(requests.filter((r) => r.url === '/playlists/3/items').length - priorPages, 2);
    omitTotal = true;
    await assert.rejects(api.start(playlist, false), /verifiable total/);
  } finally {
    api.dispose();
  }
  console.log(
    'Playlist adapter checks passed: source order, offsets, profile/queue isolation and no watched writes.'
  );
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
