// SPDX-License-Identifier: AGPL-3.0-only
// Run the actual search/notebook renderers and async handlers without a browser.
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id))
    elements.set(id, {
      id,
      value: '',
      checked: false,
      hidden: false,
      disabled: false,
      open: false,
      innerHTML: '',
      textContent: '',
      dataset: {},
      handlers: {},
      focus() {},
      showModal() {
        this.open = true;
      },
      close() {
        this.open = false;
        this.handlers.close?.({});
      },
      addEventListener(event, fn) {
        this.handlers[event] = fn;
      },
      setAttribute() {},
    });
  return elements.get(id);
}
const context = vm.createContext({
  $: element,
  console,
  AbortController,
  setTimeout: () => 1,
  clearTimeout() {},
  document: {
    getElementById: element,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
  },
  window: { confirm: () => false },
  state: { lists: [] },
  active: '',
  openedItem: '',
  externalTitle: null,
  current: () => null,
  renderTitle() {},
  openRequests() {},
  selectRequestSection() {},
  requestSection: 'requests',
  api: async () => ({}),
  task: async (button, fn) => fn(),
  toast() {},
  mediaRoute: (item) => '#/title/' + item.type + '/' + (item.tmdb || item.show_tmdb),
  esc: (value) =>
    String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
    ),
  REQUEST_LABELS: { requested: 'Requested', downloading: 'Downloading' },
});
vm.runInContext(fs.readFileSync('web/search.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('web/issues.js', 'utf8'), context);
const media = {
  item: {
    type: 'movie',
    title: '<img src=x>',
    tmdb: '10',
    poster: 'https://image.test/poster.jpg',
  },
  library_known: false,
};
context.fixture = media;
let markup = vm.runInContext('searchTitleCard(fixture)', context);
assert.match(markup, /Library not checked/);
assert.match(markup, /&lt;img/);
assert.doesNotMatch(markup, /<img src=x>/);
const issue = {
  id: 'fixture',
  item: {
    type: 'episode',
    title: 'Pilot',
    show_title: 'Show',
    show_tmdb: '20',
    season: '1',
    episode: '2',
  },
  category: 'subtitles',
  status: 'open',
  severity: 'high',
  note: '<script>unsafe</script>\nMissing text',
  updated_at: 100,
  revision: 'revision',
  requests: [],
};
context.fixtureIssue = issue;
markup = vm.runInContext('issueCards([fixtureIssue])', context);
assert.match(markup, /Show.*Pilot/);
assert.match(markup, /&lt;script&gt;/);
assert.doesNotMatch(markup, /<script>/);
vm.runInContext('openIssueEditor(fixtureIssue)', context);
element('issue-note').value = 'Changed note';
assert.equal(vm.runInContext('canLeaveIssueEditor()', context), false);
vm.runInContext('closeIssueEditor()', context);
assert.equal(element('issue-editor').open, true);
vm.runInContext('window.confirm=()=>true;closeIssueEditor()', context);
assert.equal(element('issue-editor').open, false);
(async () => {
  vm.runInContext(
    'globalThis.pending=[];api=(path,body,renew,signal)=>new Promise((resolve,reject)=>pending.push({path,body,signal,resolve,reject}));',
    context
  );
  element('global-search-provider').checked = true;
  element('global-search-query').value = 'old';
  const first = vm.runInContext('runGlobalSearch()', context);
  element('global-search-query').value = 'new';
  const second = vm.runInContext('runGlobalSearch()', context);
  assert.equal(vm.runInContext('pending[0].signal.aborted', context), true);
  context.localResult = {
    query: 'new',
    titles: [{ ...media, item: { ...media.item, title: 'New match' } }],
    lists: [],
    titles_total: 1,
    lists_total: 0,
    library_note: 'Cached only',
    has_more: false,
  };
  vm.runInContext(
    'pending[2].resolve(localResult);pending[3].resolve({items:[],people:[],has_more:false,note:"Provider checked"});',
    context
  );
  await second;
  assert.match(element('global-search-local').innerHTML, /New match/);
  vm.runInContext(
    'pending[0].resolve({...localResult,titles:[{...localResult.titles[0],item:{...localResult.titles[0].item,title:"Old result"}}]});pending[1].resolve({items:[],people:[],has_more:false});',
    context
  );
  await first;
  assert.doesNotMatch(element('global-search-local').innerHTML, /Old result/);
  vm.runInContext(
    'api=async(path)=>{if(path==="search/provider")throw Error("offline");return localResult;}',
    context
  );
  await vm.runInContext('runGlobalSearch()', context);
  assert.match(element('global-search-local').innerHTML, /New match/);
  assert.match(element('global-search-remote').innerHTML, /offline/);
  vm.runInContext(
    'globalThis.shortQueries=[];api=async(path,body)=>{shortQueries.push(body.query);return path==="search/local"?localResult:{items:[],people:[],has_more:false};}',
    context
  );
  element('global-search-query').value = '9';
  await vm.runInContext('runGlobalSearch()', context);
  assert.equal(vm.runInContext('shortQueries.length', context), 0);
  await vm.runInContext('runGlobalSearch(true)', context);
  assert.equal(vm.runInContext('shortQueries.length', context), 2);
  vm.runInContext(
    'openIssueEditor(fixtureIssue);api=async()=>{throw Error("This issue changed. Reopen it before saving.");}',
    context
  );
  element('issue-note').value = 'Keep my pending edit';
  element('issue-form').onsubmit({ preventDefault() {} });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(element('issue-editor').open, true);
  assert.equal(element('issue-note').value, 'Keep my pending edit');
  assert.match(element('issue-editor-status').textContent, /Reopen/);
  console.log(
    'Search escaping, cancellation, stale results, offline local results, short titles and notebook edit protection passed.'
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
