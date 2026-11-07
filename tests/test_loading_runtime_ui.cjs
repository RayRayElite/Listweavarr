// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id))
    elements.set(id, {
      value: '',
      textContent: '',
      innerHTML: '',
      hidden: false,
      disabled: false,
      checked: false,
      onclick() {},
      showModal() {
        this.open = true;
      },
      close() {
        this.open = false;
      },
    });
  return elements.get(id);
}
const context = vm.createContext({
  $: element,
  state: { settings: { tmdb: { configured: true } }, lists: [] },
  document: { querySelectorAll: () => [] },
  Date,
  Map,
  Set,
  setTimeout: () => 1,
  clearTimeout() {},
  render() {},
  current: () => context.fixtureEntry,
  selectedCuratedOrder: () => '',
  curatedListItems: (entry) => entry.items,
  api: async () => {},
  task: async (button, fn) => fn(),
  replaceList() {},
  toast() {},
  esc: (value) =>
    String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
});
context.fixtureEntry = { id: 'a', items: [{ id: 'one' }] };
vm.runInContext(fs.readFileSync('web/list-runtime.js', 'utf8'), context);
(async () => {
  const data = {
    minutes: 1530,
    entries: 1,
    known_units: 1,
    estimated_units: 0,
    complete: true,
    estimated: false,
    unknown_entries: 0,
    missing_paths: 0,
    note: 'Metadata',
  };
  let calls = 0;
  context.api = async () => {
    calls++;
    return data;
  };
  await context.loadWatchLength();
  assert.match(element('list-runtime-summary').textContent, /1d 1h 30m/);
  await context.loadWatchLength();
  assert.equal(calls, 1, 'Repeated renders reuse totals');
  vm.runInContext('runtimeCache.clear()', context);
  let finish;
  context.api = () => new Promise((resolve) => (finish = resolve));
  const pending = context.loadWatchLength(true);
  await context.loadWatchLength();
  assert.equal(
    element('list-runtime-fill').disabled,
    true,
    'Render must not supersede an explicit fill'
  );
  finish(data);
  await pending;
  assert.equal(element('list-runtime-fill').disabled, false);
  vm.runInContext('runtimeCache.clear()', context);
  let finishOld;
  context.api = () => new Promise((resolve) => (finishOld = resolve));
  const old = context.loadWatchLength();
  context.fixtureEntry = { id: 'b', items: [] };
  context.api = async () => ({ ...data, minutes: 90 });
  await context.loadWatchLength();
  finishOld(data);
  await old;
  assert.match(element('list-runtime-summary').textContent, /1h 30m/);
  assert.doesNotMatch(element('list-runtime-summary').textContent, /1d/);
  element('favorites-open').onclick = () => {
    context.favoritesOpened = true;
  };
  vm.runInContext(fs.readFileSync('web/smart-lists.js', 'utf8'), context);
  context.state.lists = [{ id: 'one', name: '<Source>', items: [] }];
  element('favorites-open').onclick();
  assert.match(element('smart-ready-sources').innerHTML, /&lt;Source>/);
  let resolvePreview;
  context.api = () => new Promise((resolve) => (resolvePreview = resolve));
  const preview = element('smart-ready-preview').onclick({
    target: element('smart-ready-preview'),
  });
  context.invalidateSmartReady();
  resolvePreview({ token: 'old', items: [], skipped: {}, note: '' });
  await preview;
  assert.equal(vm.runInContext('smartReadyProposal', context), null);
  assert.equal(element('smart-ready-create').hidden, true);
  element('smart-favorites').onclick();
  assert.equal(context.favoritesOpened, true);
  console.log(
    'Watch-length caching, fill/stale response protection and smart-list preview invalidation passed.'
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
