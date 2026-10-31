// SPDX-License-Identifier: AGPL-3.0-only
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
const home = require('../integrations/plex-playlist-companion/home.js');
const first = { serverId: 'server', userId: 'user', playlistId: '7', title: 'Long playlist' };
assert.equal(home.playlistHref(first), '#!/server/server/playlist?key=%2Fplaylists%2F7');
assert.equal(
  home.itemHref(first, { ratingKey: '8' }),
  '#!/server/server/details?key=%2Flibrary%2Fmetadata%2F8'
);
assert.equal(home.itemHref(first, { completed: true, ratingKey: '8' }), home.playlistHref(first));
const properties = new Map();
const image = {
  tagName: 'IMG',
  children: [],
  getBoundingClientRect: () => ({ left: 16, top: 43, bottom: 343, width: 200, height: 300 }),
};
const caption = {
  tagName: 'SPAN',
  children: [],
  textContent: 'Episode',
  getBoundingClientRect: () => ({ top: 400, bottom: 420, width: 200, height: 20 }),
};
const heading = { textContent: 'Continue Watching' };
const sectionStyle = { setProperty: (k, v) => properties.set(k, v) };
home.nativeRowMetrics(
  {
    querySelectorAll: (selector) =>
      selector === 'img' ? [image] : selector.startsWith('h1') ? [heading] : [image, caption],
    getBoundingClientRect: () => ({ top: 0, bottom: 480 }),
  },
  {
    style: sectionStyle,
    getBoundingClientRect: () => ({ top: 500, left: 0 }),
  },
  { getComputedStyle: () => ({ fontFamily: 'Plex', fontSize: '22px', fontWeight: '600' }) }
);
assert.equal(properties.get('--lw-poster-width'), '200px');
assert.equal(properties.get('--lw-row-inset'), '16px');
assert.equal(
  sectionStyle.marginTop,
  '-48px',
  'Remove excess native reserved space, leaving a 32px row gap'
);

const parent = {};
const hubs = Array.from({ length: 3 }, (_, index) => ({
  name: 'row' + index,
  parentElement: parent,
  nextSibling: 'after' + index,
  closest: () => null,
}));
const rowDocument = { querySelectorAll: () => hubs };
assert.equal(home.findHomePlacement(rowDocument, { mode: 'top' }).before, hubs[0]);
assert.equal(home.findHomePlacement(rowDocument, { mode: 'after-row', index: 2 }).hub, hubs[1]);
assert.equal(home.findHomePlacement(rowDocument, { mode: 'after-row', index: 99 }).hub, hubs[2]);
assert.equal(home.findHomePlacement(rowDocument, { mode: 'bottom' }).hub, hubs[2]);
assert.equal(home.rowPreference({ getItem: () => '{broken' }).mode, 'after-continue');

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attributes = {};
    this.style = { setProperty() {} };
    this._text = '';
  }
  set textContent(value) {
    this._text = value;
    this.children = [];
  }
  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join('');
  }
  append(...children) {
    for (let child of children) {
      if (typeof child === 'string') {
        const span = new Element('span');
        span.textContent = child;
        child = span;
      }
      child.parentElement = this;
      this.children.push(child);
    }
  }
  replaceChildren(...children) {
    this.children.forEach((child) => (child.parentElement = null));
    this.children = [];
    this._text = '';
    this.append(...children);
  }
  insertBefore(child, before) {
    child.remove();
    child.parentElement = this;
    const index = this.children.indexOf(before);
    this.children.splice(index < 0 ? this.children.length : index, 0, child);
  }
  remove() {
    if (this.parentElement)
      this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
    this.parentElement = null;
  }
  setAttribute(name, value) {
    this.attributes[name] = value;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [
      ...(selector.split(',').includes(child.tagName.toLowerCase()) ? [child] : []),
      ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  get isConnected() {
    return this.connected || !!this.parentElement?.isConnected;
  }
  get firstChild() {
    return this.children[0] || null;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
  }
  click() {
    this.clicks = (this.clicks || 0) + 1;
  }
}
(async () => {
  const body = new Element('body'),
    head = new Element('head'),
    container = new Element('main');
  body.connected = head.connected = true;
  body.append(container);
  const elements = [];
  const document = {
    body,
    head,
    createElement: (tag) => {
      const value = new Element(tag);
      elements.push(value);
      return value;
    },
    createElementNS: (_ns, tag) => new Element(tag),
    querySelectorAll: () => [],
    querySelector: (selector) =>
      selector.includes('PageContent-pageContentScroller') ? container : null,
    getElementById: () => null,
  };
  const values = new Map();
  const storage = { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v) };
  const second = { ...first, playlistId: '9', title: 'Short playlist' };
  const bookmark = (scope, title) => ({
    ...core.checkpoint(scope, [{ entryId: 'e', ratingKey: '8' }], 'e', 1000, 'session'),
    itemTitle: title,
    entryNumber: 1,
    totalEntries: 3,
    updatedAt: 1,
  });
  core.save(storage, bookmark(first, 'A long episode name that takes two lines'));
  core.save(storage, bookmark(second, 'Short'));
  let starts = 0;
  const api = {
    playlists: async () =>
      [first, second].map((scope) => ({ ...scope, bookmark: core.load(storage, scope) })),
    start: async () => {
      starts++;
      return { title: 'Playing' };
    },
    poster: async () => null,
  };
  const context = vm.createContext({
    document,
    location: { hash: '#!/' },
    localStorage: storage,
    console,
    URL,
    MutationObserver: class {
      observe() {}
      disconnect() {}
    },
    setTimeout: () => 1,
    clearTimeout() {},
    addEventListener() {},
    removeEventListener() {},
    ListweavarrPlaylistArtwork: { get: async () => null, set: async () => {}, paired: () => false },
    Event,
    dispatchEvent() {},
    ListweavarrPlaylistCore: core,
  });
  vm.runInContext(fs.readFileSync('integrations/plex-playlist-companion/home.js', 'utf8'), context);
  const dispose = context.ListweavarrPlaylistHome.mount(api, core, storage);
  await new Promise(setImmediate);
  const cards = elements.filter((element) => element.className === 'lw-playlist-card');
  assert.equal(cards.length, 2);
  for (const card of cards) {
    const poster = card.children[0],
      cover = poster.children[0];
    assert.equal(cover.tagName, 'A');
    assert.match(cover.href, /playlist\?key=/);
    assert.equal(cover.onclick, undefined, 'Poster navigation must not start playback');
    const play = poster.children.find((child) => child.className === 'lw-playlist-play');
    await play.onclick({ preventDefault() {}, stopPropagation() {} });
    const edit = poster.children.find((child) => child.className === 'lw-playlist-edit');
    edit.onclick({ preventDefault() {}, stopPropagation() {} });
    assert.equal(elements.find((element) => element.tagName === 'DIALOG').open, true);
    assert.equal(card.children[2].className, 'lw-playlist-caption');
    assert.equal(card.children[3].className, 'lw-playlist-position');
  }
  assert.equal(starts, 2, 'Only explicit Play actions start playback');
  assert.equal(
    elements.find((element) => element.tagName === 'INPUT').clicks,
    undefined,
    'Pencil opens options instead of a bare file picker'
  );
  const css = elements.find((element) => element.tagName === 'STYLE').textContent;
  assert.match(css, /grid-template-rows:var\(--lw-poster-height,252px\) 22px 36px 18px 4px/);
  assert.match(css, /left:7px;bottom:7px/);
  context.location.hash = '#!/settings/web/general';
  vm.runInContext(
    fs.readFileSync('integrations/plex-playlist-companion/settings.js', 'utf8'),
    context
  );
  const dashboard = { verifiedBuild: true, progressSync: { sync: async () => {} } };
  const disposeSettings = context.ListweavarrPlaylistSettings.mount(api, dashboard);
  dashboard.openSettings();
  const position = elements.find((element) => element.tagName === 'SELECT');
  position.value = 'after-row';
  const number = elements.find((element) => element.type === 'number');
  number.value = '2';
  position.onchange();
  assert.equal(JSON.parse(storage.getItem('playlist-companion:home-position')).index, 2);
  const connectionTab = elements.find((element) => element.textContent === 'Connection & sync');
  connectionTab.onclick();
  assert.equal(connectionTab.attributes['aria-selected'], 'true');
  assert.ok(
    elements.some((element) => element.textContent === 'Open companion settings'),
    'Dashboard entry is available within Plex Settings'
  );
  disposeSettings();
  dispose();
  console.log(
    'Playlist home card navigation, play/edit controls, uniform slots and native sizing passed'
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
