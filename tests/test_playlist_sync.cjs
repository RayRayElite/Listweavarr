// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
(async () => {
  // Match the desktop client's older browser API rather than modern Node.
  AbortSignal.timeout = undefined;
  await assert.rejects(
    core.fetchWithTimeout(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener('abort', () => reject(new Error('deadline reached')));
        }),
      'http://localhost',
      {},
      5
    ),
    /deadline reached/
  );
  let successfulSignal;
  await core.fetchWithTimeout(
    async (_url, options) => {
      successfulSignal = options.signal;
      return { ok: true };
    },
    'http://localhost',
    {},
    5
  );
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(successfulSignal.aborted, false, 'Successful request clears its timeout');
  const scope = { serverId: 's', userId: 'u', playlistId: 'p' };
  const base = {
    ...core.checkpoint(scope, [{ entryId: 'e', ratingKey: 'r' }], 'e', 100, 'session'),
    updatedAt: 1000,
  };
  const values = new Map([
    ['playlist-companion:sync-enabled', 'true'],
    [
      'playlist-companion:artwork-pairing',
      JSON.stringify({ url: 'http://localhost:8765', progressToken: 'x'.repeat(43) }),
    ],
  ]);
  const storage = { getItem: (k) => values.get(k) || null, setItem: (k, v) => values.set(k, v) };
  core.save(storage, base);
  let calls = 0;
  const player = { playlists: async () => [scope] };
  const sync = core.createSync(storage, player, async (url, options) => {
    calls++;
    assert.equal(JSON.parse(options.body).items[0].offsetMs, 100);
    return {
      ok: true,
      json: async () => ({ schema: 1, items: [{ ...base, offsetMs: 200, updatedAt: 2000 }] }),
    };
  });
  await sync.sync();
  assert.equal(core.load(storage, scope).offsetMs, 200);
  // An offline failure must leave the last local position intact.
  await assert.rejects(
    core
      .createSync(storage, player, async () => {
        throw Error('offline');
      })
      .sync()
  );
  assert.equal(core.load(storage, scope).offsetMs, 200);
  // Account changes during the request cannot import another profile's data.
  let profile = [scope];
  await core
    .createSync(storage, { playlists: async () => profile }, async () => {
      profile = [{ ...scope, userId: 'other' }];
      return {
        ok: true,
        json: async () => ({ schema: 1, items: [{ ...base, offsetMs: 300, updatedAt: 3000 }] }),
      };
    })
    .sync();
  assert.equal(core.load(storage, scope).offsetMs, 200);
  // A new device reads pins; local unpin creates a durable empty order.
  let responsePins = [{ serverId: 's', userId: 'u', updatedAt: 1000, playlistIds: ['p'] }];
  let sentPins;
  const pinSync = core.createSync(storage, player, async (_url, options) => {
    sentPins = JSON.parse(options.body).pins;
    return { ok: true, json: async () => ({ schema: 1, items: [], pins: responsePins }) };
  });
  await pinSync.sync();
  assert.equal(sentPins.length, 0);
  assert.equal(core.isPinned(storage, scope), true);
  core.unpin(storage, scope);
  await pinSync.sync();
  assert.deepEqual(sentPins[0].playlistIds, []);
  assert.equal(
    core.isPinned(storage, scope),
    false,
    'Old server pins cannot resurrect local unpin'
  );
  const stamp = sentPins[0].updatedAt;
  responsePins = [{ serverId: 's', userId: 'u', updatedAt: stamp + 1, playlistIds: ['p'] }];
  await pinSync.sync();
  assert.equal(core.isPinned(storage, scope), true);
  // In-flight pin edits must beat the response that started before the edit.
  await core
    .createSync(storage, player, async () => {
      core.unpin(storage, scope);
      return { ok: true, json: async () => ({ schema: 1, items: [], pins: responsePins }) };
    })
    .sync();
  assert.equal(core.isPinned(storage, scope), false);
  storage.setItem('playlist-companion:sync-enabled', 'false');
  await sync.sync();
  assert.equal(calls, 1);
  console.log('Playlist sync migration, offline, account and opt-in checks passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
