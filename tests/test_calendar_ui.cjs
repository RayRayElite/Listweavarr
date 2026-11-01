// SPDX-License-Identifier: AGPL-3.0-only
// Exercise the real calendar renderer and asynchronous navigation without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id))
    elements.set(id, { value: '', innerHTML: '', textContent: '', hidden: false, disabled: false });
  return elements.get(id);
}
const context = vm.createContext({
  console,
  Date,
  Map,
  encodeURIComponent,
  $: element,
  state: { companion_preferences: {} },
  esc: (value) =>
    String(value ?? '').replace(
      /[&<>"]/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]
    ),
  mediaRoute: (item) => '#/title/' + item.type + '/' + (item.tmdb || item.show_tmdb),
  selectExploreTab() {},
  bindTabKeys() {},
  setTabGroup() {},
  traktCalendar() {},
  traktOpen() {},
});
vm.runInContext(fs.readFileSync('web/calendar.js', 'utf8'), context);
for (const id of ['calendar-source', 'calendar-media']) element(id).value = 'all';
element('calendar-view').value = 'agenda';
vm.runInContext(
  `calendarData={month:'2026-11',note:'Provider dates',items:[{id:'movie',date:'2026-11-01',release_kind:'digital',region:'CA',sources:[{type:'watchlist',name:'Watchlist'},{type:'followed',name:'<script>List</script>',list_id:'one'}],item:{type:'movie',tmdb:'1',title:'Movie',poster:'https://image.test/movie.jpg'}},{id:'episode',date:'2026-11-30',release_kind:'episode',sources:[{type:'creators',name:'Actor',person_id:'10'}],item:{type:'episode',show_tmdb:'2',show_title:'Show',title:'Spoiler name',season:1,episode:2}}]};drawReleaseCalendar();`,
  context
);
assert.match(element('calendar-items').innerHTML, /Digital release/);
assert.match(element('calendar-items').innerHTML, /Show/);
assert.match(element('calendar-items').innerHTML, /#\/lists\/view\/one/);
assert.doesNotMatch(element('calendar-items').innerHTML, /<script>/);
assert.match(element('calendar-items').innerHTML, /&lt;script&gt;/);
element('calendar-source').value = 'creators';
vm.runInContext('drawReleaseCalendar()', context);
assert.doesNotMatch(element('calendar-items').innerHTML, /Digital release/);
assert.match(element('calendar-items').innerHTML, /Show/);
vm.runInContext('state.companion_preferences.spoiler_safe=true;drawReleaseCalendar()', context);
assert.doesNotMatch(element('calendar-items').innerHTML, /Spoiler name/);
element('calendar-view').value = 'month';
vm.runInContext("calendarSelectedDay='2026-11-30';drawReleaseCalendar()", context);
assert.equal((element('calendar-grid').innerHTML.match(/data-calendar-day=/g) || []).length, 30);
assert.match(element('calendar-grid').innerHTML, /aria-pressed="true"/);
assert.match(element('calendar-items').innerHTML, /Show/);
(async () => {
  vm.runInContext(
    `globalThis.pending=[];api=(path,body)=>new Promise((resolve,reject)=>pending.push({path,body,resolve,reject}));`,
    context
  );
  element('calendar-month').value = '2026-11';
  const first = vm.runInContext('loadReleaseCalendar(true)', context);
  element('calendar-month').value = '2026-12';
  const second = vm.runInContext('loadReleaseCalendar(true)', context);
  vm.runInContext(
    "pending[1].resolve({month:'2026-12',items:[],note:'December',warnings:[]})",
    context
  );
  await second;
  vm.runInContext("pending[0].resolve({month:'2026-11',items:[],note:'Old',warnings:[]})", context);
  await first;
  assert.equal(element('calendar-note').textContent, 'December');
  assert.equal(element('calendar-refresh').disabled, false);
  const offline = vm.runInContext('loadReleaseCalendar(true)', context);
  vm.runInContext("pending[2].reject(Error('offline'))", context);
  await offline;
  assert.match(element('calendar-status').textContent, /Showing saved dates.*offline/);
  assert.equal(element('calendar-note').textContent, 'December');
  assert.equal(
    vm.runInContext('pending.every(p=>p.path === "calendar")', context),
    true,
    'Calendar never submits acquisition requests'
  );
  console.log(
    'Calendar UI filters, dates, escaping, spoiler protection, stale responses and offline retention passed.'
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
