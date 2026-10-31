/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
const layout = require('../integrations/plex-playlist-companion/layout.js');
const artwork = require('../integrations/plex-playlist-companion/artwork.js');
function metricFactory(module, exports, require) {
  require.d(exports, { Ay: () => (type) => (type === 'movie' ? 2 / 3 : 1), Yc: () => 2 / 3 });
}
const requireFixture = {
  d: (exports, getters) => {
    for (const [key, get] of Object.entries(getters))
      Object.defineProperty(exports, key, { enumerable: true, get });
  },
};
const chunks = [];
layout.install(chunks, () => true);
const parent = chunks.push.bind(chunks),
  registered = {};
// Webpack replaces the array's push function and delegates to its previous one.
chunks.push = function (entry) {
  Object.assign(registered, entry[1]);
  return parent(entry);
};
chunks.push([['fixture'], { 77981: metricFactory }]);
const moduleFixture = { exports: {} };
registered[77981](moduleFixture, moduleFixture.exports, requireFixture);
const metrics = moduleFixture.exports;
assert.equal(metrics.Ay('playlist'), 2 / 3);
assert.equal(metrics.Ay('playlist', 'audio'), 1);
assert.equal(metrics.Ay('movie'), 2 / 3);
assert.equal(
  Math.floor(200 / metrics.Ay('playlist') + 40),
  340,
  'Row and poster use the same height metric'
);
assert.equal(
  layout.supported({ scripts: [{ src: 'https://app.plex.tv/desktop/js/' + layout.builds[2] }] }),
  true
);
assert.equal(
  layout.supported({ scripts: [{ src: 'https://app.plex.tv/desktop/js/unknown.js' }] }),
  false
);
assert.equal(
  artwork.targetFromHref('#!/server/machine/playlist?key=%2Fplaylists%2F7'),
  'machine/7'
);
assert.equal(
  artwork.targetFromHref('#!/server/machine/details?key=%2Flibrary%2Fmetadata%2F7'),
  null
);
assert.throws(() =>
  artwork.pairing({ url: 'https://user:pass@example.test', token: 'a'.repeat(43) })
);
assert.throws(() => artwork.pairing({ url: 'file:///tmp/', token: 'a'.repeat(43) }));

async function main() {
  const memory = new Map(),
    images = new Map(),
    requests = [];
  const storage = {
    getItem: (key) => memory.get(key),
    setItem: (key, value) => memory.set(key, value),
    removeItem: (key) => memory.delete(key),
  };
  const cache = {
    access: async (key, value) => (value ? (images.set(key, value), value) : images.get(key)),
  };
  const scope = { serverId: 'machine', playlistId: '7', userId: 'user' };
  const api = { playlists: async () => [scope] };
  const blob = new Blob(['fixture'], { type: 'image/png' });
  let offline = false,
    revision = 'one';
  const fetcher = async (url, options) => {
    requests.push({ url, options });
    if (offline) throw Error('Offline');
    return url.includes('?')
      ? { ok: true, blob: async () => blob }
      : {
          ok: true,
          json: async () => ({
            schema: 1,
            items: [
              { serverId: 'machine', playlistId: '7', revision },
              { serverId: 'unrelated', playlistId: '8', revision },
            ],
          }),
        };
  };
  const service = artwork.create(core, storage, fetcher, cache);
  service.connect({ url: 'http://127.0.0.1:8765', token: 'a'.repeat(43) });
  assert.equal((await service.sync(api, true)).updated, 1);
  assert.equal(requests.length, 2, 'Fetch only artwork for this profile’s verified playlists');
  assert.equal(requests[0].options.credentials, 'omit');
  assert.equal(await service.get(scope), blob);
  assert.equal((await service.sync(api, true)).updated, 0, 'Skip unchanged revisions');
  offline = true;
  await assert.rejects(service.sync(api, true), /Offline/);
  assert.equal(await service.get(scope), blob, 'Offline sync must retain the cached poster');
  offline = false;
  const local = new Blob(['local'], { type: 'image/jpeg' });
  await service.set(scope, local);
  revision = 'two';
  assert.equal(
    (await service.sync(api, true)).updated,
    0,
    'Never replace an explicit local poster'
  );
  service.disconnect();
  assert.equal(service.paired(), false);
  assert.equal(await service.get(scope), local);
  assert.equal(await service.get({ ...scope, userId: 'other' }), null);
  console.log(
    'Playlist feature checks passed: native metrics, Webpack lifecycle, scoped artwork, offline cache and local overrides.'
  );
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
