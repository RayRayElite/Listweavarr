// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('integrations/plex-playlist-companion/layout.js', 'utf8');
const saved = new Map([
  ['bookmark', 'keep'],
  ['poster', 'keep'],
]);
let reloads = 0;
function boot() {
  let keyboard;
  const context = vm.createContext({
    localStorage: {
      getItem: (key) => saved.get(key),
      setItem: (key, value) => saved.set(key, value),
    },
    location: { reload: () => reloads++ },
    document: { scripts: [{ src: 'https://app.plex.tv/desktop/js/brand-new-plex.js' }] },
    addEventListener: (name, callback, capture) => {
      assert.equal(name, 'keydown');
      assert.equal(capture, true);
      keyboard = callback;
    },
  });
  vm.runInContext(source, context);
  return { context, key: keyboard };
}
const active = boot();
assert.equal(active.context.__listweavarrCompanionSafety.disabled(), false);
const chunks = active.context.webpackChunkplex_web_client;
const factory = (module, exports, require) =>
  require.d(exports, { Ay: () => (type) => (type === 'movie' ? 2 / 3 : 1) });
const entry = [['fixture'], { 77981: factory }];
chunks.push(entry);
const moduleValue = { exports: {} };
entry[1][77981](moduleValue, moduleValue.exports, {
  d: (exports, values) => {
    for (const [key, get] of Object.entries(values)) Object.defineProperty(exports, key, { get });
  },
});
assert.equal(
  moduleValue.exports.Ay('playlist'),
  2 / 3,
  'A new version string alone does not disable a compatible metric'
);
let prevented = 0;
active.key({
  code: 'KeyL',
  ctrlKey: true,
  altKey: true,
  shiftKey: true,
  preventDefault() {
    prevented++;
  },
  stopImmediatePropagation() {},
});
assert.equal(reloads, 1);
assert.equal(prevented, 1);
const paused = boot();
assert.equal(paused.context.__listweavarrCompanionSafety.disabled(), true);
assert.equal(
  paused.context.webpackChunkplex_web_client,
  undefined,
  'Paused boot installs no Webpack hooks'
);
vm.runInContext(
  fs.readFileSync('integrations/plex-playlist-companion/runtime.js', 'utf8'),
  paused.context
);
assert.equal(
  paused.context.__listweavarrPlaylistCompanion,
  undefined,
  'Paused boot installs no player or UI hooks'
);
paused.key({
  key: 'L',
  ctrlKey: true,
  altKey: true,
  shiftKey: true,
  preventDefault() {},
  stopImmediatePropagation() {},
});
assert.equal(saved.get('playlist-companion:disabled'), 'false');
assert.equal(reloads, 2);
assert.equal(saved.get('bookmark'), 'keep');
assert.equal(saved.get('poster'), 'keep');
console.log(
  'Early panic shortcut, clean paused boot, re-enable and new-version compatibility passed'
);
