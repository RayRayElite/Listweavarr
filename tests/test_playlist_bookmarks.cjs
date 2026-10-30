/* SPDX-License-Identifier: AGPL-3.0-only */
const assert = require('node:assert/strict');
const core = require('../integrations/plex-playlist-companion/bookmarks.js');
const context = { serverId: 's', userId: 'u', playlistId: 'p' };
const items = [
  { entryId: 'a', ratingKey: '1' },
  { entryId: 'b', ratingKey: '1' },
  { entryId: 'c', ratingKey: '2' },
];
const book = core.checkpoint(context, items, 'b', 123000, 'session', 2);
assert.equal(core.reconcile(book, items).entryId, 'b');
assert.equal(core.reconcile(book, items).offsetMs, 123000);
assert.equal(core.reconcile(book, [items[2], items[1], items[0]]).index, 1);
assert.equal(
  core.reconcile(book, [
    { entryId: 'new1', ratingKey: '1' },
    { entryId: 'new2', ratingKey: '1' },
  ]).status,
  'needs-review'
);
assert.equal(core.reconcile(book, [items[2]]).reason, 'entry-removed');
assert.equal(
  core.reconcile(book, [{ entryId: 'b', ratingKey: '99' }]).reason,
  'entry-identity-changed'
);
assert.equal(
  core.reconcile(book, [{ entryId: 'replacement', ratingKey: '1' }]).status,
  'needs-review'
);
const unique = core.checkpoint(context, items, 'c', 0, 'session');
assert.equal(core.reconcile(unique, [{ entryId: 'replacement', ratingKey: '2' }]).recovered, true);
assert.equal(core.update(book, { sessionId: 'other', revision: 3 }), book);
assert.equal(core.update(book, { sessionId: 'session', revision: 1 }), book);
const completed = core.update(book, {
  sessionId: 'session',
  revision: 3,
  entryId: 'b',
  offsetMs: 125000,
  completed: true,
});
assert.deepEqual(core.reconcile(completed, items), {
  status: 'ready',
  recovered: false,
  index: 2,
  entryId: 'c',
  ratingKey: '2',
  offsetMs: 0,
});
assert.equal(
  core.reconcile({ ...completed, entryId: 'c', ratingKey: '2' }, items).status,
  'finished'
);
assert.throws(() => core.checkpoint(context, items, 'missing', 0, 's'));
assert.throws(() => core.checkpoint(context, items, 'b', -1, 's'));
const memory = new Map();
const storage = { setItem: (k, v) => memory.set(k, v), getItem: (k) => memory.get(k) ?? null };
core.save(storage, book);
assert.deepEqual(core.load(storage, context), book);
assert.equal(core.load(storage, { ...context, userId: 'other' }), null);
memory.set(core.storageKey(context), '{broken');
assert.equal(core.load(storage, context), null);
console.log(
  'Playlist bookmark checks passed: duplicates, rewatches, edits, sessions, persistence and completion.'
);
