// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
const artwork = require('../integrations/plex-playlist-companion/artwork.js');
(async () => {
  AbortSignal.timeout = undefined;
  const scope = { serverId: 's', userId: 'u', playlistId: '7' };
  const api = { playlists: async () => [scope] };
  let shared;
  const fetcher = async (url, options) => {
    if (!url.endsWith('/posters'))
      return { ok: true, json: async () => ({ schema: 1, items: [] }) };
    const body = JSON.parse(options.body);
    if (body.upload) shared = { ...body.upload, revision: 'hash' };
    return {
      ok: true,
      json: async () => ({
        schema: 1,
        poster: shared && body.revision !== shared.revision ? shared : null,
      }),
    };
  };
  function client() {
    const values = new Map([['playlist-companion:sync-enabled', 'true']]);
    const records = new Map();
    const service = artwork.create(
      core,
      { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) },
      fetcher,
      {
        access: async (k, v) => {
          if (v) records.set(k, v);
          return records.get(k);
        },
      }
    );
    service.connect({
      url: 'http://localhost:8765',
      token: 'a'.repeat(43),
      progressToken: 'p'.repeat(43),
      serverId: 's',
    });
    return { service, records };
  }
  const desktop = client(),
    web = client();
  const original = new Blob(['desktop'], { type: 'image/png' });
  // Old desktop builds saved a raw Blob, without migration metadata.
  desktop.records.set(core.storageKey(scope), original);
  await desktop.service.sync(api, true);
  assert.equal(shared.data, btoa('desktop'));
  await web.service.sync(api, true);
  assert.equal(await (await web.service.get(scope)).text(), 'desktop');
  assert.equal(await web.service.get({ ...scope, userId: 'other' }), null);
  const own = new Blob(['web choice'], { type: 'image/jpeg' });
  await web.service.set(scope, own);
  await web.service.sync(api, true);
  await desktop.service.sync(api, true);
  assert.equal(await desktop.service.get(scope), original, 'Explicit desktop choice stays local');
  assert.equal(await web.service.get(scope), own, 'Explicit web choice stays local');
  console.log('Shared poster migration, download, profile scope and local overrides passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
