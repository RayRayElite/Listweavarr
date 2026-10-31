// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
(async () => {
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
  storage.setItem('playlist-companion:sync-enabled', 'false');
  await sync.sync();
  assert.equal(calls, 1);
  console.log('Playlist sync migration, offline, account and opt-in checks passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
