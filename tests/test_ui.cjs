// Execute the real client event handlers against a small DOM harness. No browser,
// network connections, or third-party packages are required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id))
    elements.set(id, {
      id,
      textContent: '',
      innerHTML: '',
      value: '',
      hidden: false,
      disabled: false,
      dataset: {},
      classList: { toggle() {} },
      showModal() {
        this.open = true;
      },
      close() {
        this.open = false;
      },
      click() {
        if (!this.disabled) return this.onclick?.({ target: this });
      },
      querySelector() {
        return element('submit');
      },
      addEventListener() {},
      insertAdjacentHTML(position, html) {
        this.innerHTML += html;
      },
    });
  return elements.get(id);
}
const context = vm.createContext({
  document: {
    getElementById: element,
    querySelectorAll: () => [],
    querySelector: (selector) => element('query:' + selector),
  },
  window: { location: { hash: '', pathname: '/' } },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  fetch: () => new Promise(() => {}),
  setTimeout: () => 1,
  clearTimeout() {},
  IntersectionObserver: class {
    observe() {}
    disconnect() {}
    unobserve() {}
  },
  FormData: class {},
  console,
  URL,
});
vm.runInContext(fs.readFileSync('web/app.js', 'utf8'), context);
vm.runInContext(
  `
  state={settings:{radarr:{configured:true},sonarr:{configured:true},tmdb:{configured:true}},lists:[{id:'list',name:'List',items:[
    {id:'movie',type:'movie',title:'Missing movie',tmdb:'1',status:'missing'},
    {id:'episode',type:'episode',title:'Missing episode',show_tmdb:'2',season:'1',episode:'2',status:'missing'}]}]};
  active='list';
  globalThis.calls=[];
  api=async(path,body)=>{calls.push({path,body});if(path==='options')return {radarr:{profiles:[{id:1,name:'HD'}],roots:[{path:'/movies'}]},sonarr:{profiles:[{id:2,name:'HD'}],roots:[{path:'/tv'}]}};return {title:'Details',overview:'Full synopsis',rating:7.5,vote_count:10,genres:['Drama'],cast:[],tmdb_url:'https://www.themoviedb.org/movie/1',trailer:{url:'https://www.youtube.com/watch?v=abcdefghijk',scope:'title'}};};
`,
  context
);

(async () => {
  const markup = vm.runInContext('row(current().items[0])', context);
  assert.match(markup, /data-add="movie"/);
  assert.match(markup, /Add to Radarr/);
  assert.match(markup, /data-details="movie"/);
  assert.match(vm.runInContext('row(current().items[1])', context), /Add to Sonarr/);
  vm.runInContext("selected.add('episode'); addOne('movie')", context);
  await new Promise(setImmediate);
  assert.equal(element('review-dialog').open, true);
  assert.equal(vm.runInContext('selected.size', context), 1);
  assert.equal(vm.runInContext("selected.has('movie')", context), true);
  assert.equal(context.calls[0].path, 'options');
  assert.equal(
    context.calls.some((c) => c.path === 'request'),
    false,
    'Opening Add must not submit downloads'
  );
  assert.match(element('review-items').innerHTML, /Missing movie/);
  await vm.runInContext("openTitle('movie')", context);
  assert.equal(element('title-dialog').hidden, false);
  assert.equal(element('workspace').hidden, true);
  assert.match(element('title-content').innerHTML, /Full synopsis/);
  assert.match(element('title-content').innerHTML, /Watch trailer/);
  assert.equal(element('title-add').hidden, false);
  assert.equal(
    context.calls.some((c) => c.path === 'request'),
    false
  );
  // Metadata sorts use a copy, keep unknown values last in either direction,
  // and never alter the source order used for playlists.
  vm.runInContext(
    `
    const extra={id:'unknown',type:'movie',title:'Unknown',tmdb:'3'};
    current().items.push(extra);
    metadataCache.set(metadataKey(current().items[0]),{rating:8,release_date:'2020-01-01',runtime:120});
    metadataCache.set(metadataKey(current().items[1]),{rating:6,release_date:'2010-01-01',runtime:40});
  `,
    context
  );
  assert.equal(
    vm.runInContext("sortEntries(current().items,'rating-desc').map(i=>i.id).join(',')", context),
    'movie,episode,unknown'
  );
  assert.equal(
    vm.runInContext("sortEntries(current().items,'rating-asc').map(i=>i.id).join(',')", context),
    'episode,movie,unknown'
  );
  assert.equal(
    vm.runInContext("current().items.map(i=>i.id).join(',')", context),
    'movie,episode,unknown'
  );
  assert.equal(
    vm.runInContext(
      "metadataKey({type:'episode',show_tvdb:'1',season:'1',episode:'1'})!==metadataKey({type:'episode',show_tvdb:'2',season:'1',episode:'1'})",
      context
    ),
    true
  );
  assert.match(vm.runInContext('row(current().items[1])', context), /data-show="episode"/);
  vm.runInContext(
    `
    const previousApi=api;
    api=async(path,body)=>{if(path==='show'){calls.push({path,body});return {
      show:{type:'show',title:'Parent show',tmdb:'2'},details:{title:'Parent show',overview:'Full show synopsis',genres:[],cast:[],tmdb_url:'https://www.themoviedb.org/tv/2'},
      coverage_known:true,libraries:['TV'],available:1,missing:1,seasons:[{number:1,name:'Season 1',available:1,aired:2,missing:1,episodes:[{season:1,episode:1,title:'First',status:'available'},{season:1,episode:2,title:'Second',status:'missing'}]}]
    };}return previousApi(path,body);};
  `,
    context
  );
  await vm.runInContext("openParent('episode')", context);
  assert.match(element('title-coverage-slot').innerHTML, /YOUR PLEX LIBRARY/);
  assert.match(element('title-coverage-slot').innerHTML, /Season 1/);
  assert.match(element('title-coverage-slot').innerHTML, /In Plex/);
  assert.equal(element('parent-request').hidden, false);
  await vm.runInContext("reviewShowScope({dataset:{showScope:'season',season:'1'}})", context);
  assert.equal(element('show-request-dialog').open, true);
  assert.match(element('show-request-title').textContent, /Season 1/);
  assert.equal(
    context.calls.some((c) => c.path === 'show/request'),
    false,
    'Viewing a parent show or request review must not submit downloads'
  );
  assert.match(vm.runInContext("personLink({id:12,name:'Actor'})", context), /data-person="12"/);
  assert.doesNotMatch(vm.runInContext("personLink({name:'Unknown'})", context), /data-person/);
  vm.runInContext(
    `
    api=async(path,body)=>{calls.push({path,body});if(path==='discover')return {name:'Actor',note:'Credits',items:[{key:'movie:7',type:'movie',tmdb:'7',title:'Film',roles:['Director'],group:'Filmography',year:'2020'},{key:'tv:8',type:'show',tmdb:'8',title:'Series',roles:['Self'],group:'Filmography'}]};throw Error('Unexpected write');};
  `,
    context
  );
  const discoveryOrigin = vm.runInContext('workspacePanel', context);
  await vm.runInContext("openDiscovery('person',12)", context);
  assert.equal(element('discovery-dialog').hidden, false);
  assert.equal(element('title-dialog').hidden, true);
  assert.match(element('discovery-content').innerHTML, /Film/);
  assert.match(element('discovery-content').innerHTML, /Series/);
  element('discovery-type').value = 'movie';
  element('discovery-type').onchange();
  assert.doesNotMatch(element('discovery-content').innerHTML, /Series/);
  element('discovery-all').click();
  assert.equal(vm.runInContext('discoverySelected.size', context), 1);
  assert.equal(element('discovery-save').disabled, false);
  assert.equal(
    context.calls.some((c) => c.path === 'discover/save' || c.path === 'request'),
    false,
    'Browsing and selecting projects must not save lists or request downloads'
  );
  vm.runInContext("closeWorkspacePanel('discovery-dialog')", context);
  assert.equal(
    element(discoveryOrigin).hidden,
    false,
    'Closing projects returns to the page that opened them'
  );
  assert.equal(element('discovery-dialog').hidden, true);
  vm.runInContext(
    `
    renderTitle({type:'movie'}, {title:'Portrait example',overview:'One synopsis only.',cast:[{id:12,name:'Actor',character:'Hero',photo:'https://image.tmdb.org/t/p/w342/actor.jpg'}],related_id:'1',related_type:'movie'});
    api=async(path,body)=>{calls.push({path,body});if(path==='title')return {item:{type:'movie',tmdb:'7',title:'Individual project'},details:{title:'Individual project',overview:'Project synopsis',cast:[]}};if(path==='discover')return {name:'Actor',note:'Credits',profile:{photo:'https://image.tmdb.org/t/p/w342/actor.jpg',biography:'An actor biography.',department:'Acting'},items:[{key:'movie:7',type:'movie',tmdb:'7',title:'Film',roles:['Hero'],group:'Filmography'}]};throw Error('Unexpected write');};
  `,
    context
  );
  assert.equal(element('title-content').innerHTML.split('One synopsis only.').length - 1, 1);
  assert.match(element('title-content').innerHTML, /cast-strip/);
  assert.match(element('title-content').innerHTML, /actor.jpg/);
  assert.ok(
    element('title-content').innerHTML.indexOf('title-coverage-slot') <
      element('title-content').innerHTML.indexOf('related-section')
  );
  vm.runInContext(
    'window.setExplorationRecommendations=(sequence,rows)=>{globalThis.forwardedRecommendations=rows;}',
    context
  );
  await vm.runInContext(
    "loadRelatedPreview({related_id:'1',related_type:'movie'},titleSequence)",
    context
  );
  assert.equal(context.forwardedRecommendations[0].tmdb, '7');
  assert.doesNotMatch(element('related-preview').innerHTML, />Related content</);
  assert.doesNotMatch(element('related-preview').innerHTML, /data-related=/);
  await vm.runInContext("openDiscovery('person',12)", context);
  assert.match(element('person-profile').innerHTML, /An actor biography/);
  assert.match(element('person-profile').innerHTML, /person-portrait/);
  element('discovery-all').click();
  await vm.runInContext("openExternalTitle('movie','7')", context);
  assert.equal(element('title-dialog').hidden, false);
  assert.match(element('title-content').innerHTML, /Individual project/);
  assert.equal(element('title-save').hidden, false);
  assert.equal(
    context.calls.some((c) => c.path === 'title/save'),
    false
  );
  vm.runInContext("closeWorkspacePanel('title-dialog')", context);
  assert.equal(element('discovery-dialog').hidden, false);
  assert.equal(vm.runInContext('discoverySelected.size', context), 1);
  vm.runInContext("closeWorkspacePanel('title-dialog')", context);
  assert.equal(element('workspace').hidden, false);
  assert.equal(element('title-dialog').hidden, true);
  const html = fs.readFileSync('web/index.html', 'utf8');
  assert.match(html, /<section\s+hidden[^>]+id="title-dialog"/);
  assert.match(html, /<option value="">Both<\/option>/);
  assert.match(html, /<option value="show">TV<\/option>/);
  assert.doesNotMatch(html, /<dialog id="(?:title|discovery)-dialog"/);
  assert.doesNotMatch(html, /<\/option\s+value=/);
  vm.runInContext(
    `renderTitle({type:'movie'},{title:'Title facts',overview:'Synopsis',release_date:'2020-01-01',studios:[{id:8,name:'Example studio'}],director_people:[{id:9,name:'Filmmaker',photo:'https://image.tmdb.org/t/p/w342/crew.jpg'}],producer_people:[{id:9,name:'Filmmaker',job:'Producer'}],cast:[]})`,
    context
  );
  assert.doesNotMatch(
    element('title-content').innerHTML,
    /title-expand|Production & title information/
  );
  assert.match(element('title-content').innerHTML, /persistent-facts/);
  assert.match(element('title-content').innerHTML, /2020-01-01/);
  assert.match(element('title-content').innerHTML, /Directors & producers/);
  assert.match(element('title-content').innerHTML, /crew.jpg/);
  assert.match(element('title-content').innerHTML, /Director, Producer/);
  assert.match(element('title-content').innerHTML, /Studio \/ production company/);
  assert.doesNotMatch(element('title-content').innerHTML, /Publisher/);
  assert.match(element('title-content').innerHTML, /Producer/);
  assert.match(element('discovery-content').innerHTML, /project-row/);
  assert.match(element('discovery-content').innerHTML, /data-title-tmdb=/);
  assert.match(element('discovery-content').innerHTML, /&middot;/);
  assert.doesNotMatch(element('discovery-content').innerHTML, / \? /);
  vm.runInContext('settingsView(true)', context);
  assert.equal(element('settings').hidden, false);
  assert.equal(element('workspace').hidden, true);
  assert.equal(element('title-dialog').hidden, true);
  assert.equal(element('discovery-dialog').hidden, true);
  vm.runInContext(
    `
    const projects=[{key:'a',title:'Alpha',rating:6,release_date:'2010-01-01',roles:['Writer'],type:'movie'},{key:'b',title:'Beta',rating:9,release_date:'2020-01-01',roles:['Actor'],type:'show'},{key:'c',title:'Unknown',rating:null,roles:[],type:'movie'}];
    globalThis.projects=projects;
  `,
    context
  );
  assert.equal(
    vm.runInContext("sortProjects(projects,'rating-desc').map(r=>r.key).join(',')", context),
    'b,a,c'
  );
  assert.equal(
    vm.runInContext("sortProjects(projects,'rating-asc').map(r=>r.key).join(',')", context),
    'a,b,c'
  );
  assert.equal(
    vm.runInContext("sortProjects(projects,'date-desc').map(r=>r.key).join(',')", context),
    'b,a,c'
  );
  assert.equal(
    vm.runInContext("sortProjects(projects,'role-asc').map(r=>r.key).join(',')", context),
    'b,a,c'
  );
  assert.equal(vm.runInContext("projects.map(r=>r.key).join(',')", context), 'a,b,c');
  vm.runInContext(
    "discoveryContext.data.items=projects;discoverySelected=new Set(['a']);$('discovery-type').value='';$('discovery-search').value='';$('discovery-sort').value='title-desc';$('discovery-sort').onchange()",
    context
  );
  assert.equal(vm.runInContext("discoverySelected.has('a')", context), true);
  assert.ok(
    element('discovery-content').innerHTML.indexOf('Unknown') <
      element('discovery-content').innerHTML.indexOf('Alpha')
  );
  vm.runInContext(
    `globalThis.people=[{name:'No photo regular',episode_count:136,popularity:100},{name:'Popular guest',photo:'/guest.jpg',episode_count:1,popularity:200},{name:'Regular',photo:'/regular.jpg',episode_count:136,popularity:2},{name:'Popular regular',photo:'/popular.jpg',episode_count:136,popularity:20}]`,
    context
  );
  assert.equal(
    vm.runInContext("sortPeople(people).map(p=>p.name).join('|')", context),
    'Popular regular|Regular|Popular guest|No photo regular'
  );
  assert.equal(vm.runInContext('people[0].name', context), 'No photo regular');
  const crew = vm.runInContext(
    "crewStrip({director_people:[{id:1,name:'Filmmaker',episode_count:10,popularity:2}],producer_people:[{id:1,name:'Filmmaker',episode_count:20,popularity:2,job:'Producer'}]})",
    context
  );
  assert.match(crew, /20 episodes in largest role/);
  assert.doesNotMatch(crew, /30 episodes/);
  vm.runInContext(
    `api=async(path,body)=>{calls.push({path,body});return {item:{type:'episode',title:'Pilot',show_tmdb:'10',season:'1',episode:'1'},details:{title:'Pilot',show_title:'Parent show',overview:'Episode synopsis',cast:[]}}}`,
    context
  );
  await vm.runInContext("openExternalTitle('episode','10',1,1)", context);
  assert.match(element('title-content').innerHTML, /Pilot/);
  assert.match(element('title-content').innerHTML, /Episode synopsis/);
  assert.match(element('title-content').innerHTML, /Season 1, Episode 1/);
  assert.match(element('title-content').innerHTML, /data-title-tmdb="10"/);
  assert.equal(vm.runInContext('externalTitle.episode', context), 1);
  assert.match(
    vm.runInContext(
      "coverageMarkup({show:{tmdb:'10'},libraries:[],available:0,missing:1,coverage_known:true,seasons:[{name:'Season 1',number:1,episodes:[{title:'Pilot',season:1,episode:1,status:'missing'}]}]})",
      context
    ),
    /data-episode-show="10"/
  );
  vm.runInContext(
    `
    showPageCache.clear();metadataCache.clear();globalThis.showReads=0;
    globalThis.fullShow={show:{type:'show',tmdb:'2',title:'Cached show'},details:{title:'Cached show',cast:[]},coverage_known:true,libraries:[],available:0,missing:0,seasons:[]};
    api=async(path,body)=>{if(path==='details')return {title:'Fast show preview',cast:[]};if(path==='show'){showReads++;return new Promise(resolve=>{globalThis.finishShow=resolve});}throw Error('Unexpected request');};
    globalThis.openingShow=openParent('episode');
  `,
    context
  );
  await new Promise(setImmediate);
  assert.match(element('title-content').innerHTML, /Fast show preview/);
  vm.runInContext('finishShow(fullShow)', context);
  await vm.runInContext('openingShow', context);
  await vm.runInContext("openParent('episode')", context);
  assert.equal(context.showReads, 1, 'Reopening a recent show must reuse coverage');
  vm.runInContext("globalThis.refreshingShow=openParent('episode',true)", context);
  assert.equal(context.showReads, 2, 'Explicit refresh must bypass coverage cache');
  vm.runInContext('finishShow(fullShow)', context);
  await vm.runInContext('refreshingShow', context);
  vm.runInContext("showPageCache.set('expired',{time:Date.now()-180001,data:fullShow})", context);
  assert.equal(vm.runInContext("recentShowPage('expired')", context), null);
  vm.runInContext(
    `
    current().items=Array.from({length:21},(_,n)=>({id:'sort'+n,type:'movie',tmdb:String(100+n),title:'Film '+n,status:'missing'}));
    metadataCache.clear();$('sort').value='rating-desc';
    api=async(path,body)=>{if(path!=='metadata')throw Error('Unexpected request');const result={items:body.ids.map(id=>({id,details:{rating:Number(id.slice(4)),overview:'Details'}}))};if(body.ids.includes('sort20'))return new Promise(resolve=>{globalThis.finishSort=()=>resolve({items:[{id:'sort20',details:{rating:100}}]})});return result;};
    globalThis.sortingList=applySort();
  `,
    context
  );
  await new Promise(setImmediate);
  assert.match(element('sort-progress').textContent, /20\/21/);
  assert.ok(
    element('entries').innerHTML.indexOf('data-entry="sort19"') <
      element('entries').innerHTML.indexOf('data-entry="sort0"'),
    'Known ratings must reorder before the final metadata batch finishes'
  );
  vm.runInContext('finishSort()', context);
  await vm.runInContext('sortingList', context);
  assert.match(element('sort-progress').textContent, /Sort complete/);
  assert.ok(
    element('entries').innerHTML.indexOf('data-entry="sort20"') <
      element('entries').innerHTML.indexOf('data-entry="sort19"'),
    'Final batch must redraw without navigating away'
  );
  assert.equal(element('sort').disabled, false);
  assert.equal(vm.runInContext('sortLoading', context), false);
  vm.runInContext(
    `current().refresh_report={added:['New film'],removed:['Old film'],changed:[],order_changed:true};current().availability_report=[{title:'New film',from:'missing',to:'available'}];current().playlist_needs_update=true;current().warnings=['Confirm TV season'];renderListUpdates()`,
    context
  );
  assert.match(element('list-updates').innerHTML, /1 added, 1 removed/);
  assert.match(element('list-updates').innerHTML, /order changed/);
  assert.match(element('list-updates').innerHTML, /missing.*available/);
  assert.match(element('list-updates').innerHTML, /linked Plex playlist has updates to review/);
  vm.runInContext(
    `api=async(path,body)=>{calls.push({path,body});if(path==='playlist/preview')return {name:'Mixed',count:1,omitted:1,entries:[{title:'Playable film',type:'movie',status:'available',count:1},{title:'Unresolved episode',type:'episode',status:'unmatched',count:0}]};if(path==='identify')return {results:[{id:42,title:'Exact film',year:'2020'}]};throw Error('Unexpected write');}`,
    context
  );
  await vm.runInContext("$('playlist-open').onclick({target:$('playlist-open')})", context);
  assert.match(element('playlist-preview-items').innerHTML, /Playable film/);
  assert.match(element('playlist-preview-items').innerHTML, /Omitted: unmatched/);
  vm.runInContext(
    "editingId=current().items[0].id;$('identify-query').value='Exact film'",
    context
  );
  await vm.runInContext("$('identify-search').onclick({target:$('identify-search')})", context);
  vm.runInContext("$('identify-choice').onchange({target:{value:'42'}})", context);
  assert.equal(element('query:#edit-fields input[name="tmdb"]').value, 42);
  assert.equal(
    context.calls.some((c) => c.path === 'playlist/create'),
    false,
    'Playlist review must not publish a playlist'
  );
  vm.runInContext(fs.readFileSync('web/trakt.js', 'utf8'), context);
  vm.runInContext(
    `calls=[];api=async(path,body)=>{calls.push({path,body});if(path==='trakt/search')return {lists:[{name:'Chronology',owner:'Owner',count:2,likes:1,description:'Mixed titles',url:'https://trakt.tv/lists/1'}],has_more:true};if(path==='trakt/preview')return {name:'Chronology',source:'https://trakt.tv/lists/1',compared:true,items:[{id:'1',title:'Owned',type:'movie',tmdb:'1',status:'available'},{id:'2',title:'Missing',type:'movie',tmdb:'2',status:'missing'}]};throw Error('Unexpected write');};$('trakt-query').value='Marvel';$('trakt-list-mode').value='search';`,
    context
  );
  await vm.runInContext('traktSearch()', context);
  assert.match(element('trakt-list-results').innerHTML, /Chronology/);
  assert.equal(element('trakt-page-next').hidden, false);
  await vm.runInContext("traktPreviewList('https://trakt.tv/lists/1')", context);
  vm.runInContext("$('trakt-preview-filter').value='missing';traktRenderPreview()", context);
  assert.match(element('trakt-preview-rows').innerHTML, /Missing/);
  assert.doesNotMatch(element('trakt-preview-rows').innerHTML, />Owned</);
  assert.equal(
    context.calls.some((c) => c.path === 'import/start' || c.path === 'requests'),
    false,
    'Preview must never save or download'
  );
  assert.equal(
    vm.runInContext(
      "traktDescription('**Updated** _today_ [Read more](https://example.com) https://example.com/list')",
      context
    ),
    'Updated today Read more'
  );
  vm.runInContext(
    `state.settings.trakt={configured:true};api=async()=>({rating:8,votes:50,scope:'show',lists:[{name:'Community list',owner:'Owner',count:3,likes:4,description:'**Watch order**',url:'https://trakt.tv/lists/1'}],recommendations:[{title:'Next title',tmdb:'42',type:'show',year:2020,poster:'https://image.tmdb.org/t/p/w342/test.jpg'}]});`,
    context
  );
  await vm.runInContext(
    "window.loadTraktTitleExtras({type:'show'},{related_id:'2'},titleSequence)",
    context
  );
  assert.match(element('trakt-title-extras').innerHTML, /<details class="trakt-curated-lists">/);
  assert.match(element('trakt-more-explore').innerHTML, /<img[^>]* src="https:\/\/image.tmdb.org/);
  assert.equal(
    vm.runInContext(
      "availableRatings({type:'show',tmdb:'2'}).find(r=>r.source==='trakt').value",
      context
    ),
    8
  );
  assert.ok(
    element('trakt-title-extras').innerHTML.indexOf('trakt-more-explore') <
      element('trakt-title-extras').innerHTML.indexOf('Lists featuring this title')
  );
  vm.runInContext(
    `window.setKeepExploringTitles(titleSequence,[{type:'show',tmdb:'42'}])`,
    context
  );
  assert.equal(
    element('trakt-more-explore').innerHTML,
    '',
    'Late-loading relationship rows must remove duplicate recommendations'
  );
  assert.match(
    element('trakt-title-extras').innerHTML,
    /Community list/,
    'Filtering recommendations must preserve community list controls'
  );
  vm.runInContext(
    `traktTitleListsContext.data.recommendations=[{type:'movie',tmdb:'42',title:'Different movie'},{type:'show',tmdb:'42',title:'Duplicate show'},{type:'movie',tmdb:'42',title:'Repeated movie'}];renderMoreToExplore()`,
    context
  );
  assert.match(element('trakt-more-explore').innerHTML, /Different movie/);
  assert.doesNotMatch(element('trakt-more-explore').innerHTML, /Duplicate show|Repeated movie/);
  vm.runInContext(
    `window.setKeepExploringTitles(titleSequence-1,[{type:'movie',tmdb:'42'}])`,
    context
  );
  assert.match(
    element('trakt-more-explore').innerHTML,
    /Different movie/,
    'Stale requests must not filter the current title'
  );
  vm.runInContext(
    `traktTitleListsContext.data.lists_has_more=true;api=async(path,body)=>{calls.push({path,body});return {page:2,has_more:false,lists:[{name:'Second page list',owner:'Owner',count:2,likes:1,description:'',url:'https://trakt.tv/lists/2'}]};};`,
    context
  );
  await vm.runInContext("loadMoreTraktTitleLists($('more-lists-test'))", context);
  assert.match(element('trakt-title-list-rows').innerHTML, /Second page list/);
  assert.match(element('trakt-title-list-rows').innerHTML, /Community list/);
  assert.equal(element('more-lists-test').hidden, true);
  assert.equal(context.calls.at(-1).body.page, 2);
  vm.runInContext(fs.readFileSync('web/enrichment.js', 'utf8'), context);
  vm.runInContext(
    `api=async()=>({scope:'parent show',sources:[{provider:'Wikidata',status:'matched',facts:[{label:'Alternate titles',value:'<script>bad</script>'}],franchise:[{key:'tv:42',type:'show',tmdb:'42',title:'Confirmed show',relationship:'Franchise member',provider:'Wikidata'}],connections:[],notes:[]},{provider:'TheTVDB',status:'not connected',notes:['Add your key.']}]});`,
    context
  );
  await vm.runInContext(
    `window.loadSupplementalMetadata({related_type:'show',related_id:'2',title:'Current'},titleSequence,{sections:{sequence:{items:[]},franchise:{items:[]},related:{items:[{key:'tv:42',type:'show',tmdb:'42',title:'Confirmed show',group:'Recommendations'}]}}})`,
    context
  );
  assert.match(element('supplemental-metadata').innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(element('supplemental-metadata').innerHTML, /<script>/);
  assert.match(element('related-preview').innerHTML, /Confirmed universe/);
  assert.equal(
    (element('related-preview').innerHTML.match(/Confirmed show/g) || []).length,
    1,
    'Confirmed membership must be removed from recommendations'
  );
  assert.match(element('supplemental-metadata').innerHTML, /parent show/);
  assert.equal(vm.runInContext("supplementalSafeURL('javascript:alert(1)')", context), null);
  assert.doesNotMatch(
    element('related-preview').innerHTML,
    />Related content</,
    'Recommendations should use one consolidated row'
  );
  vm.runInContext(
    `window.setExplorationRecommendations(titleSequence,[{type:'movie',tmdb:'99',title:'TMDB suggestion'},{type:'show',tmdb:'42',title:'Confirmed duplicate'}])`,
    context
  );
  assert.match(element('trakt-more-explore').innerHTML, /TMDB suggestion/);
  assert.match(element('trakt-more-explore').innerHTML, /Recommended on TMDB/);
  assert.doesNotMatch(element('trakt-more-explore').innerHTML, /Confirmed duplicate/);
  vm.runInContext(
    `
    metadataCache.clear();metadataAttempts.clear();metadataQueue.clear();visibleMetadata.clear();
    globalThis.retryItem={id:'retry-test',type:'movie',title:'Retry test',tmdb:'991'};
    metadataAttempts.set(metadataKey(retryItem),1);storeListMetadata(retryItem,null,'Temporary failure');
  `,
    context
  );
  assert.equal(
    vm.runInContext('metadataNeedsLoad(retryItem)', context),
    false,
    'Retries must respect backoff'
  );
  vm.runInContext(`metadataCache.get(metadataKey(retryItem)).retry_at=0;`, context);
  assert.equal(
    vm.runInContext('metadataNeedsLoad(retryItem)', context),
    true,
    'Transient failures must become retryable'
  );
  vm.runInContext(`metadataAttempts.set(metadataKey(retryItem),3);`, context);
  assert.equal(
    vm.runInContext('metadataNeedsLoad(retryItem)', context),
    false,
    'Automatic retries must be bounded'
  );
  vm.runInContext(
    `storeListMetadata(retryItem,{summary_only:true,overview:'Recovered'});storeListMetadata(retryItem,null,'Late error');`,
    context
  );
  assert.equal(
    vm.runInContext('metadataCache.get(metadataKey(retryItem)).overview', context),
    'Recovered',
    'A late failure must not replace successful metadata'
  );
  vm.runInContext(
    `metadataCache.set(metadataKey(retryItem),{overview:'Full details',cast:[{name:'Actor'}]});storeListMetadata(retryItem,{summary_only:true,overview:'Summary'});`,
    context
  );
  assert.equal(
    vm.runInContext('metadataCache.get(metadataKey(retryItem)).overview', context),
    'Full details',
    'Summary requests must preserve full details'
  );
  vm.runInContext(
    `
    state.lists=[{id:'summary-list',name:'Summary list',items:[retryItem]}];active='summary-list';
    metadataCache.set(metadataKey(retryItem),{summary_only:true,overview:'List summary'});
    globalThis.savedRenderTitle=renderTitle;renderTitle=()=>{};
    globalThis.fullDetailReads=0;api=async(path)=>{if(path==='details'){fullDetailReads++;return {title:'Full title',overview:'Full details',cast:[{name:'Actor'}]};}throw Error('Unexpected request');};
  `,
    context
  );
  await vm.runInContext("openTitle('retry-test')", context);
  assert.equal(
    context.fullDetailReads,
    1,
    'Opening a summary-only entry must still fetch full credits and trailers'
  );
  vm.runInContext('renderTitle=savedRenderTitle', context);
  vm.runInContext(fs.readFileSync('web/explore.js', 'utf8'), context);
  vm.runInContext(
    `
    $('explore-media').value='both';$('explore-quality').value='6.0';$('explore-cult').checked=false;
    globalThis.exploreCalls=[];
    api=async(path,body)=>{exploreCalls.push({path,body});if(path==='explore/home')return {library_connected:true,profile:{count:100,watched:50,genres:['Drama']},quality_note:'6.0 minimum',warnings:[],rows:[{id:'for-you',name:'Picked for your library',note:'Matched metadata',items:[{key:'movie:42',type:'movie',tmdb:'42',title:'Discovery',year:'2020',rating:8,vote_count:500,reasons:['Similar genres: Drama']}]}]};if(path==='explore/route')return {items:[],tracked:0,compared:1,entry:{id:'discoveries',name:'Explore picks',items:[{id:'picked',type:'movie',tmdb:'42',title:'Discovery',status:'missing'}]}};throw Error('Unexpected request');};
  `,
    context
  );
  await vm.runInContext('loadExploreHome()', context);
  assert.match(element('explore-home-rows').innerHTML, /Picked for your library/);
  assert.match(element('explore-home-rows').innerHTML, /Similar genres: Drama/);
  assert.match(element('explore-personalization').textContent, /100 library titles/);
  vm.runInContext("explorePicks.set('movie:42',exploreRows[0]);exploreSelection()", context);
  await vm.runInContext(
    "$('explore-save-picks').onclick({target:$('explore-save-picks')})",
    context
  );
  assert.equal(context.exploreCalls.at(-1).path, 'explore/route');
  assert.equal(
    context.exploreCalls.some((c) => /request|playlist\/create/.test(c.path)),
    false,
    'Saving discovery picks must not download or publish'
  );
  assert.equal(vm.runInContext('active', context), 'discoveries');
  assert.match(
    vm.runInContext("posterArt('poster.jpg',{type:'show',tmdb:'42'})", context),
    /data-poster-show="42"/
  );
  assert.doesNotMatch(
    vm.runInContext("posterArt('poster.jpg',{type:'movie',tmdb:'42'})", context),
    /data-poster-show/
  );
  assert.match(
    vm.runInContext("posterArt('poster.jpg',{type:'episode',tmdb:'99',show_tmdb:'42'})", context),
    /data-poster-show="42"/
  );
  assert.equal(
    vm.runInContext(
      `(()=>{const previous=state.ignored_titles;state.ignored_titles=[{tokens:ignoredTokens({type:'show',tmdb:'20',title:'Series'})}];const hidden=isIgnored({type:'episode',show_tmdb:'20',season:1,episode:2});const movie=isIgnored({type:'movie',tmdb:'20',title:'Other'});state.ignored_titles=[];const restored=!isIgnored({type:'show',tmdb:'20'});state.ignored_titles=previous;return hidden&&!movie&&restored;})()`,
      context
    ),
    true,
    'Ignored shows cover their episodes, not movies sharing the numeric ID, and can be restored'
  );
  vm.runInContext(
    `state.release_watchlist=[{id:'CA:42',tmdb:'42',type:'movie',title:'Tracked movie',region:'CA',status:'home',home_date:'2026-10-23',home_format:'Digital',acknowledged:false}];renderReleaseWatchlist();`,
    context
  );
  assert.equal(element('release-notice').hidden, false);
  assert.match(element('release-notice').innerHTML, /1 tracked title/);
  assert.match(element('release-watch-items').innerHTML, /Save & compare/);
  vm.runInContext(
    `state.release_watchlist[0].acknowledged=true;renderReleaseWatchlist();`,
    context
  );
  assert.equal(
    element('release-notice').hidden,
    true,
    'Acknowledged release notices stay dismissed'
  );
  vm.runInContext(`state.explore_languages=['en','fr'];renderExploreLanguages();`, context);
  assert.equal(element('explore-language-all').checked, false);
  assert.equal(element('explore-language-summary').textContent, 'English, French');
  vm.runInContext(`state.explore_languages=[];renderExploreLanguages();`, context);
  assert.equal(element('explore-language-all').checked, true);
  assert.equal(element('explore-language-summary').textContent, 'All languages');
  vm.runInContext(
    `api=async(path,body)=>{if(path!=='explore/languages'||!body)throw Error('Language requests need a JSON body');return {languages:[{code:'en',name:'English'},{code:'fr',name:'French'}]};};$('explore-language-panel').open=true;`,
    context
  );
  await vm.runInContext(`$('explore-language-panel').ontoggle()`, context);
  assert.equal(vm.runInContext('exploreLanguageOptionsLoaded', context), true);
  const upcomingCard = vm.runInContext(
    `exploreTitleCard({key:'tv:88',type:'show',tmdb:'88',title:'Future series',upcoming:true,rating:null,vote_count:0,reasons:[]})`,
    context
  );
  assert.match(upcomingCard, /Track premiere/);
  assert.match(upcomingCard, /Not yet rated/);
  assert.match(upcomingCard, /data-release-type="show"/);
  vm.runInContext(
    `state.release_watchlist=[{id:'CA:show:88',tmdb:'88',type:'show',title:'Future series',region:'CA',status:'premiered',premiere_date:'2026-10-23',acknowledged:false}];renderReleaseWatchlist();`,
    context
  );
  assert.equal(element('release-notice').hidden, false);
  assert.match(element('release-watch-items').innerHTML, /Premiered/);
  vm.runInContext(
    `state.rating_preferences={main:'imdb',display:'all'};extraRatingsCache.set('movie:tmdb:555',{ratings:[{source:'imdb',label:'IMDb',value:8.1,maximum:10,score:8.1,via:'MDBList'},{source:'tomatoes',label:'Rotten Tomatoes critics',value:92,maximum:100,score:9.2,via:'MDBList'},{source:'metacritic',label:'Metacritic critics',value:76,maximum:100,score:7.6,via:'MDBList'}]});`,
    context
  );
  const compactRating = vm.runInContext(
    `ratingContents({type:'movie',tmdb:'555',rating:7.2},false)`,
    context
  );
  assert.match(compactRating, /IMDb 8.1/);
  assert.doesNotMatch(
    compactRating,
    /Rotten Tomatoes|TMDB/,
    'Compact cards must show exactly one score'
  );
  const fullRatings = vm.runInContext(
    `ratingContents({type:'movie',tmdb:'555',rating:7.2},true)`,
    context
  );
  assert.match(fullRatings, /Rotten Tomatoes critics/);
  assert.match(fullRatings, /TMDB/);
  assert.match(fullRatings, /92%/);
  assert.match(
    fullRatings,
    /76 \/ 100/,
    'Metacritic averages must not be mislabeled as approval percentages'
  );
  vm.runInContext(`state.rating_preferences.display=['imdb'];`, context);
  const singleFullRating = vm.runInContext(
    `ratingContents({type:'movie',tmdb:'555',rating:7.2},true)`,
    context
  );
  assert.doesNotMatch(singleFullRating, /rating-chip[^>]*>[\s\S]*Rotten Tomatoes/);
  assert.equal(
    vm.runInContext(
      `ratingIdentity({type:'episode',show_tmdb:'5',season:1,episode:2}).key!==ratingIdentity({type:'episode',show_tmdb:'5',season:1,episode:3}).key`,
      context
    ),
    true
  );
  assert.match(
    vm.runInContext(`ratingContents({type:'movie',tmdb:'556',rating:7.2})`, context),
    /preferred source unavailable/
  );
  vm.runInContext(`state.rating_preferences={main:'tmdb',display:'all'};`, context);
  const paintedRating = vm.runInContext(
    `(()=>{const oldQuery=document.querySelectorAll;const rating={innerHTML:'',textContent:''};const item={id:'rating-test',type:'movie',tmdb:'55',title:'Test'};metadataCache.set(metadataKey(item),{type:'movie',tmdb:'55',rating:7.2,overview:'Summary'});document.querySelectorAll=()=>[{dataset:{entry:item.id},querySelector:selector=>selector==='.entry-rating'?rating:{}}];paintMetadata(item);document.querySelectorAll=oldQuery;return rating.innerHTML;})()`,
    context
  );
  assert.match(
    paintedRating,
    /data-rating-row/,
    'Arriving metadata must retain the preferred-rating widget rather than overwrite it with TMDB text'
  );
  vm.runInContext(
    `state.rating_preferences={main:'imdb',display:'all',order:['tomatoes','tmdb','imdb','metacritic']};`,
    context
  );
  const orderedRatings = vm.runInContext(
    `ratingContents({type:'movie',tmdb:'555',rating:7.2},true)`,
    context
  );
  assert.ok(orderedRatings.indexOf('Rotten Tomatoes critics') < orderedRatings.indexOf('IMDb'));
  assert.match(
    vm.runInContext(`ratingContents({type:'movie',tmdb:'555',rating:7.2},false)`, context),
    /IMDb 8.1/
  );
  element('year-from').value = '2000';
  element('year-to').value = '2020';
  assert.equal(vm.runInContext(`matchesMovieYear({type:'movie',year:'1999'})`, context), false);
  assert.equal(vm.runInContext(`matchesMovieYear({type:'movie',year:'2000'})`, context), true);
  assert.equal(vm.runInContext(`matchesMovieYear({type:'movie',year:'2020'})`, context), true);
  assert.equal(vm.runInContext(`matchesMovieYear({type:'movie'})`, context), false);
  assert.equal(vm.runInContext(`matchesMovieYear({type:'episode',year:'1990'})`, context), true);
  element('year-from').value = '';
  element('year-to').value = '';
  assert.equal(vm.runInContext(`matchesMovieYear({type:'movie'})`, context), true);
  vm.runInContext(fs.readFileSync('web/lists.js', 'utf8'), context);
  vm.runInContext(
    `state.lists=[{id:'select-a',name:'Alpha',items:[]},{id:'select-b',name:'Beta',items:[]},{id:'author',name:'Author',official_authoring:true,items:[]}];$('my-list-search').value='';batchListMode.my=true;`,
    context
  );
  element('my-batch-all').onclick();
  assert.equal(vm.runInContext(`batchListSelection.my.size`, context), 2);
  element('my-batch-clear').onclick();
  element('my-list-search').value = 'Alpha';
  element('my-batch-all').onclick();
  assert.equal(vm.runInContext(`[...batchListSelection.my].join(',')`, context), 'select-a');
  element('my-list-search').value = '';
  vm.runInContext(
    `officialCatalogue=[{id:'one',name:'One'},{id:'two',name:'Two'}];$('official-list-search').value='';batchListMode.official=true;`,
    context
  );
  element('official-batch-all').onclick();
  assert.equal(vm.runInContext(`batchListSelection.official.size`, context), 2);
  element('official-batch-clear').onclick();
  vm.runInContext(
    `
    state.lists=[{id:'batch-a',name:'Batch A',items:[]},{id:'batch-b',name:'Batch B',items:[]},{id:'batch-empty',name:'Empty',items:[]}];
    calls=[]; batchListSelection.my=new Set(['batch-a','batch-b','batch-empty']);
    api=async(path,body)=>{calls.push({path,body});if(path==='playlist/preview')return {count:body.list_id==='batch-empty'?0:3,omitted:1};if(path==='playlist/create'){if(body.list_id==='batch-a')throw Error('one failed');return {key:'123',count:3,title:body.title};}throw Error('unexpected route');};
  `,
    context
  );
  await vm.runInContext(`previewBatchPlaylists('my')`, context);
  assert.equal(context.calls.length, 3);
  assert.equal(
    context.calls.some((call) => call.path === 'playlist/create'),
    false,
    'Preview must not publish playlists'
  );
  assert.equal(vm.runInContext('batchPlaylistRows.filter(row=>row.ready).length', context), 2);
  await element('batch-playlist-confirm').onclick({ target: element('batch-playlist-confirm') });
  assert.equal(
    context.calls.filter((call) => call.path === 'playlist/create').length,
    2,
    'One failure does not stop the remaining playlist'
  );
  assert.equal(
    context.calls
      .filter((call) => call.path === 'playlist/create')
      .every((call) => call.body.replace === false && call.body.watch_order === null),
    true
  );
  assert.equal(
    element('batch-playlist-confirm').disabled,
    true,
    'Completed batches cannot be submitted again'
  );
  assert.match(element('batch-playlist-status').textContent, /1 of 2 playlists created/);
  vm.runInContext(
    `
    officialCatalogue=[{id:'official-batch',name:'Official batch'}];batchListSelection.official=new Set(['official-batch']);calls=[];
    api=async(path,body)=>{calls.push({path,body});if(path==='explore/official/open')return {entry:{id:'official-copy',official_id:'official-batch',name:'Official batch',items:[]}};return {count:2,omitted:0};};
  `,
    context
  );
  await vm.runInContext(`previewBatchPlaylists('official')`, context);
  assert.equal(context.calls[0].path, 'explore/official/open');
  assert.equal(context.calls[1].body.list_id, 'official-copy');
  assert.equal(
    context.calls.some((call) => call.path === 'playlist/create'),
    false
  );
  element('batch-playlist-dialog').close();
  vm.runInContext(
    `
    listEditor={original:null,items:[{id:'a',title:'A'},{id:'d',title:'D'}]};
    $('list-insert-position').value='2';
    insertEditorEntries([{id:'b',title:'B'},{id:'c',title:'C'}]);
  `,
    context
  );
  assert.equal(vm.runInContext(`listEditor.items.map(row=>row.id).join(',')`, context), 'a,b,c,d');
  assert.equal(
    element('list-insert-position').value,
    '4',
    'Insertion advances so consecutive additions stay in source order'
  );
  assert.equal(
    vm.runInContext(`moveEditorEntry(3,1);listEditor.items.map(row=>row.id).join(',')`, context),
    'd,a,b,c'
  );
  vm.runInContext(`$('list-insert-position').value='99'`, context);
  assert.equal(vm.runInContext(`insertEditorEntries([{id:'bad'}])`, context), false);
  assert.equal(vm.runInContext('listEditor.items.length', context), 4);
  const linkedMarkup = vm.runInContext(
    `playlistLinkMarkup({id:'linked',name:'Example',playlist:{key:'7',title:'Example'},playlist_needs_update:true})`,
    context
  );
  assert.match(linkedMarkup, /data-review-publication="linked"/);
  vm.runInContext(
    `api=async()=>({token:'review',title:'Saved Plex title',before_count:2,after_count:3,added:1,removed:0,omitted:0,entries:[{title:'A',count:1}]});`,
    context
  );
  await vm.runInContext(`reviewLinkedPlaylist('linked')`, context);
  assert.equal(element('playlist-replace').checked, true);
  assert.equal(vm.runInContext('publicationListId', context), 'linked');
  assert.equal(element('playlist-title').value, 'Saved Plex title');
  element('playlist-dialog').close();
  assert.equal(
    vm.runInContext(
      "catalogueSort([{name:'Z',count:3},{name:'A',count:1}],'title_asc').map(r=>r.name).join(',')",
      context
    ),
    'A,Z'
  );
  assert.equal(
    vm.runInContext(
      "catalogueSort([{name:'Z',count:3},{name:'A',count:1}],'title_desc').map(r=>r.name).join(',')",
      context
    ),
    'Z,A'
  );
  assert.equal(
    vm.runInContext(
      "catalogueSort([{name:'Z',count:3},{name:'A',count:1}],'count_desc').map(r=>r.name).join(',')",
      context
    ),
    'Z,A'
  );
  assert.equal(
    vm.runInContext(
      "catalogueSort([{name:'Z',updated_at:1},{name:'A',updated_at:2}],'updated_desc').map(r=>r.name).join(',')",
      context
    ),
    'A,Z'
  );
  vm.runInContext(
    `state.lists=[{id:'collection',name:'My collection',source:'https://example.com/watch-order',items:[{id:'one',type:'movie',title:'One'}]}];active='collection';drawListCatalogue();showListCatalogue();`,
    context
  );
  assert.match(element('saved-list-grid').innerHTML, /My collection/);
  assert.match(element('saved-list-grid').innerHTML, /LINKED SOURCE/);
  assert.equal(element('list-detail').hidden, true);
  vm.runInContext(`openSavedList('collection')`, context);
  assert.equal(element('list-detail').hidden, false);
  assert.equal(element('list-catalogue').hidden, true);
  vm.runInContext(
    `listEditor={original:state.lists[0],items:[...state.lists[0].items]};$('list-edit-mode').value='linked';drawEditorItems();`,
    context
  );
  assert.equal(element('list-detach-warning').hidden, true);
  vm.runInContext(`listEditor.items=[];drawEditorItems();`, context);
  assert.equal(
    element('list-detach-warning').hidden,
    false,
    'Membership edits must expose the explicit source-detachment warning'
  );
  vm.runInContext(fs.readFileSync('web/requests.js', 'utf8'), context);
  vm.runInContext(
    `requestRows=[{id:'r1',item:{type:'movie',title:'Requested movie',tmdb:'44'},service:'radarr',mode:'search',status:'attention',message:'Import needs attention',events:[],created_at:1}];requestNotices=[{id:'n1',title:'Ready',read:false}];$('requests-filter').value='';$('requests-search').value='';drawRequests();`,
    context
  );
  assert.match(element('requests-items').innerHTML, /Import needs attention/);
  assert.match(element('requests-items').innerHTML, /Review \/ retry/);
  assert.equal(element('requests-notice').hidden, false);
  vm.runInContext(`$('requests-filter').value='available';drawRequests()`, context);
  assert.match(element('requests-items').innerHTML, /No matching requests/);
  vm.runInContext(
    `state.settings.prowlarr={configured:false};$('explore-indexers').checked=true;$('explore-indexers').onchange({target:$('explore-indexers')})`,
    context
  );
  assert.equal(
    element('explore-indexers').checked,
    false,
    'Optional indexer discovery must require a configured connection'
  );
  const compactPreferences = vm.runInContext('ratingPreferencesMarkup()', context);
  assert.doesNotMatch(compactPreferences, /id="rating-main"|rating-source-options/);
  assert.equal((compactPreferences.match(/data-rating-display=/g) || []).length, 11);
  assert.equal(
    vm.runInContext(
      `ratingPreferencesFromRows([{dataset:{ratingOrder:'tmdb'},querySelector:()=>({checked:false})},{dataset:{ratingOrder:'imdb'},querySelector:()=>({checked:true})}]).main`,
      context
    ),
    'imdb'
  );
  assert.throws(
    () =>
      vm.runInContext(
        `ratingPreferencesFromRows([{dataset:{ratingOrder:'tmdb'},querySelector:()=>({checked:false})}])`,
        context
      ),
    /at least one/
  );
  vm.runInContext(
    `document.addEventListener=(event,handler)=>{if(event==='change')globalThis.workflowChange=handler;}`,
    context
  );
  vm.runInContext(fs.readFileSync('web/workflow.js', 'utf8'), context);
  const routesMarkup = vm.runInContext(
    `requestRouteMarkup({route:'uhd',routes:[{id:'primary',name:'HD',tier:'standard',enabled:true,configured:true},{id:'uhd',name:'UHD server',tier:'4k',enabled:true,configured:true}]},'radarr','radarr')`,
    context
  );
  assert.match(routesMarkup, /value="uhd" selected/);
  assert.match(routesMarkup, /UHD server - 4K/);
  vm.runInContext(
    `requestRows=[{id:'approval',item:{title:'Queued film',type:'movie'},status:'awaiting_approval',tier:'4k',service:'radarr',events:[],created_at:1}];$('requests-filter').value='';$('requests-search').value='';drawRequests()`,
    context
  );
  assert.match(element('requests-items').innerHTML, /Review & approve/);
  assert.match(element('requests-items').innerHTML, /Decline/);
  assert.match(element('requests-items').innerHTML, /4K/);
  vm.runInContext(
    `globalThis.routeSelect={value:'uhd',dataset:{managerRoute:'radarr',routePrefix:'radarr',loadedRoute:'primary'}};$('radarr-root').value='/primary';api=async()=>{throw Error('UHD server offline');};workflowChange({target:{closest:()=>routeSelect}})`,
    context
  );
  await new Promise(setImmediate);
  assert.equal(
    context.routeSelect.value,
    'primary',
    'Failed route changes must restore the loaded instance instead of submitting another server with stale profiles'
  );
  assert.equal(element('radarr-root').value, '/primary');
  vm.runInContext(`drawListCatalogue();openListShare('collection')`, context);
  assert.match(element('saved-list-grid').innerHTML, /data-share-list="collection"/);
  assert.equal(element('list-share-dialog').open, true);
  vm.runInContext(`$('shared-list-open').onclick()`, context);
  assert.equal(
    element('shared-list-accept').hidden,
    true,
    'Shared-list imports require a preview before confirmation'
  );
  vm.runInContext(fs.readFileSync('web/builder.js', 'utf8'), context);
  vm.runInContext(
    `openListBuilder('https://example.com/guide','Guide');builderRows=[{index:0,raw:'Film',source_line:1,query:'Film',type:'movie',matches:[{type:'movie',tmdb:'1',title:'Film',year:'2000'}],chosen:0,confirmed:false,removed:false}];builderCounts()`,
    context
  );
  assert.equal(
    element('builder-save').disabled,
    true,
    'A suggested match cannot be saved without explicit confirmation'
  );
  vm.runInContext(`builderRows[0].confirmed=true;builderCounts()`, context);
  assert.equal(element('builder-save').disabled, false);
  vm.runInContext(`builderRows[0].type='episode';builderCounts()`, context);
  assert.equal(
    element('builder-save').disabled,
    true,
    'TV scope and movie/show identity must match before saving'
  );
  vm.runInContext(
    `builderRows=[{index:0,raw:'Film',source_line:1,query:'Film',type:'movie',matches:[{type:'movie',tmdb:'1',title:'Film'}],chosen:0,confirmed:false},{index:1,type:'movie',matches:[],chosen:-1,confirmed:false},{index:2,type:'episode',matches:[{type:'show',tmdb:'2'}],chosen:0,confirmed:false},{index:3,type:'movie',matches:[{type:'movie',tmdb:'3'}],chosen:0,confirmed:false,removed:true}];$('builder-filter').value='pending';$('builder-confirm-all').onclick()`,
    context
  );
  assert.equal(vm.runInContext('builderRows[0].confirmed', context), true);
  assert.equal(
    vm.runInContext('builderRows.slice(1).some(row=>row.confirmed)', context),
    false,
    'Bulk confirmation skips unmatched, incomplete and removed entries'
  );
  assert.equal(element('builder-save').disabled, true);
  vm.runInContext(
    `builderRows[1].removed=true;builderRows[2].removed=true;builderCounts()`,
    context
  );
  assert.equal(element('builder-save').disabled, false);
  vm.runInContext(
    `builderRows=[{index:0,raw:'Season 2 (Ep 46-89)',source_line:1,query:'Anime',type:'episode',season:'2',episode:'46',episode_end:'89',numbering:'absolute',confirmed:false,matches:[{type:'show',tmdb:'9',title:'Anime',scope:{season:'1',episode:'46',episode_end:'89'},scope_note:'Continuous numbering'}],chosen:0}];applyBuilderScope(builderRows[0]);$('builder-confirm-all').onclick()`,
    context
  );
  assert.equal(vm.runInContext('builderRows[0].season', context), '1');
  assert.equal(vm.runInContext('builderRows[0].confirmed', context), true);
  assert.match(vm.runInContext('builderRowMarkup(builderRows[0])', context), /Last episode/);
  vm.runInContext(
    `builderRows[0].scope_error='Range exceeds metadata';builderRows[0].confirmed=false;builderCounts()`,
    context
  );
  assert.equal(
    element('builder-confirm-all').disabled,
    true,
    'Invalid anime numbering must not be bulk confirmed'
  );
  vm.runInContext(
    `builderRows=[{index:0,raw:'Named special',source_line:1,query:'Example',type:'episode',episode_title:'Named special',source_note:'Source instructions retained',matches:[{type:'show',tmdb:'9',title:'Example',scope:{type:'episode',season:'0',episode:'6',episode_end:'6'},scope_label:'S0 E6 / Named special'}],chosen:0}];applyBuilderScope(builderRows[0]);`,
    context
  );
  assert.match(
    vm.runInContext('builderRowMarkup(builderRows[0])', context),
    /Named episode \/ story/
  );
  assert.match(
    vm.runInContext('builderRowMarkup(builderRows[0])', context),
    /S0 E6 \/ Named special/
  );
  assert.match(
    vm.runInContext('builderRowMarkup(builderRows[0])', context),
    /Source instructions retained/
  );
  assert.equal(vm.runInContext('builderValid(builderRows[0])', context), true);
  assert.match(
    vm.runInContext('builderRowMarkup(builderRows[0])', context),
    /data-builder-field="tmdb_input"/
  );
  await vm.runInContext(
    `api=async(path,body)=>{globalThis.directLookupCall={path,body};return {items:[{type:'show',tmdb:'9',title:'Exact show',year:'2005',direct_scope:{type:'episode',season:'0',episode:'6'}}]};};$('list-add-query').value='9';$('list-add-type').value='show';findListEditorTitle($('list-add-tmdb'),true)`,
    context
  );
  assert.equal(context.directLookupCall.path, 'lists/search');
  assert.equal(context.directLookupCall.body.tmdb_input, '9');
  assert.match(element('list-add-results').innerHTML, /Exact show.*S0 E6/);
  context.crypto = require('node:crypto').webcrypto;
  vm.runInContext(
    `listEditor={original:null,items:[],poster:''};$('list-insert-position').value='1';$('list-edit-mode').value='local';$('list-add-results').onclick({target:{closest:()=>({dataset:{listAdd:'0'}})}})`,
    context
  );
  assert.equal(vm.runInContext('listEditor.items[0].show_tmdb', context), '9');
  assert.equal(vm.runInContext('listEditor.items[0].type', context), 'episode');
  assert.equal(vm.runInContext('listEditor.items[0].episode', context), '6');
  vm.runInContext(
    `builderRows=[{index:0,raw:'Show (seasons 1-4)',source_line:1,query:'Show',type:'season',season:'1',season_end:'4',matches:[{type:'show',tmdb:'9',title:'Show'}],chosen:0,confirmed:false}];$('builder-confirm-all').onclick()`,
    context
  );
  assert.match(vm.runInContext('builderRowMarkup(builderRows[0])', context), /First season/);
  assert.match(vm.runInContext('builderRowMarkup(builderRows[0])', context), /Last season/);
  assert.equal(vm.runInContext('builderRows[0].confirmed', context), true);
  vm.runInContext(`builderRows[0].season_end='0';builderCounts()`, context);
  assert.equal(element('builder-save').disabled, true);
  vm.runInContext(
    `listEditor={original:null,items:[],poster:''};$('list-insert-position').value='1';listEditorSearch=[{type:'show',tmdb:'9',title:'Show'}];$('list-add-scope').value='season';$('list-add-season').value='1';$('list-add-season-end').value='4';$('list-add-results').onclick({target:{closest:()=>({dataset:{listAdd:'0'}})}})`,
    context
  );
  assert.equal(vm.runInContext('listEditor.items.length', context), 4);
  assert.equal(vm.runInContext('listEditor.items[3].season', context), '4');
  vm.runInContext('drawListCatalogue()', context);
  assert.match(element('saved-list-grid').innerHTML, /data-delete-list=/);
  assert.match(element('saved-list-grid').innerHTML, /data-add-entries=/);
  await vm.runInContext(
    `api=async()=>({entry:{id:'collection',name:'Existing list',source:'https://example.com/list',items:[]},revision:'current'});openListBuilder('','','collection')`,
    context
  );
  vm.runInContext(
    `builderRows=[{index:0,type:'movie',matches:[{type:'movie',tmdb:'4',title:'New'}],chosen:0,confirmed:true}];builderCounts()`,
    context
  );
  assert.equal(
    element('builder-save').disabled,
    true,
    'A manual linked-list update requires conversion confirmation'
  );
  vm.runInContext(
    `$('builder-confirm-detach').checked=true;$('builder-confirm-detach').onchange();$('builder-mode').value='replace';$('builder-mode').onchange()`,
    context
  );
  assert.equal(element('builder-save').disabled, false);
  assert.equal(element('builder-replace-note').hidden, false);
  assert.equal(
    element('builder-name').readOnly,
    true,
    'Updating entries preserves the existing list identity'
  );
  await vm.runInContext(
    `state.lists=[{id:'delete-me',name:'Delete me',items:[]}];active='delete-me';api=async(path,body)=>path==='lists/revision'?{entry:state.lists[0],revision:'delete-current'}:(globalThis.deleteCall={path,body},{deleted_id:'delete-me'});openListDelete('delete-me')`,
    context
  );
  assert.equal(element('list-delete-dialog').open, true);
  assert.equal(
    vm.runInContext('state.lists.length', context),
    1,
    'Opening deletion review must not remove a list'
  );
  await vm.runInContext(
    `$('list-delete-confirm').onclick({target:$('list-delete-confirm')})`,
    context
  );
  assert.equal(context.deleteCall.path, 'lists/delete');
  assert.equal(context.deleteCall.body.confirmed, true);
  assert.equal(vm.runInContext('state.lists.length', context), 0);
  assert.equal(element('list-catalogue').hidden, false);
  vm.runInContext(fs.readFileSync('web/collection-tools.js', 'utf8'), context);
  await vm.runInContext(
    `api=async()=>({lists:[{list_id:'copy',name:'My copy',installed_version:1,version:2,available:true,added:['A <new> title'],removed:['Old'],changed:0,order_changed:true,has_baseline:true,revision:'revision'}],recent:[]});loadCollectionUpdates()`,
    context
  );
  assert.equal(element('official-updates-panel').hidden, false);
  assert.equal(element('official-items').hidden, true);
  assert.match(element('official-update-items').innerHTML, /Preserve my personal changes/);
  assert.match(element('official-update-items').innerHTML, /A &lt;new&gt; title/);
  assert.match(element('official-update-items').innerHTML, /Apply reviewed update/);
  vm.runInContext(`$('official-updates-close').onclick()`, context);
  assert.equal(element('official-items').hidden, false);
  await vm.runInContext(
    `active='health-copy';api=async()=>({total:1,note:'No changes made',issues:[{code:'duplicate',title:'Repeated title',positions:[1,2],message:'Review the repeat.'}]});$('list-health-check').onclick({target:$('list-health-check')})`,
    context
  );
  assert.equal(element('list-health-panel').hidden, false);
  assert.match(element('list-health-results').innerHTML, /Repeated title/);
  assert.match(element('list-health-heading').textContent, /1 review notes/);
  vm.runInContext(fs.readFileSync('web/taste.js', 'utf8'), context);
  vm.runInContext(
    `state.taste_feedback={'movie:1':{type:'movie',tmdb:'1',title:'A <favorite>',value:'favorite',updated_at:1}};drawTasteFeedback()`,
    context
  );
  assert.match(element('taste-feedback-items').innerHTML, /A &lt;favorite&gt;/);
  assert.match(element('taste-feedback-items').innerHTML, /data-taste-clear="1"/);
  assert.match(vm.runInContext("tasteControls('movie','1')", context), /aria-pressed="true"/);
  assert.match(
    vm.runInContext("tasteControls('show','9',true)", context),
    /Applies to the whole show/
  );
  vm.runInContext(
    `exploreRows=[{type:'movie',tmdb:'1',reasons:['Because you liked A','Similar genres: Drama']}]`,
    context
  );
  assert.match(vm.runInContext("whyThisMarkup('movie','1')", context), /Because you liked A/);
  assert.equal(vm.runInContext("whyThisMarkup('show','1')", context), '');
  await vm.runInContext(
    `api=async(path,body)=>{globalThis.tasteCall={path,body};return {items:{}};};saveTaste('movie','1','clear')`,
    context
  );
  assert.equal(context.tasteCall.path, 'taste/set');
  assert.equal(context.tasteCall.body.value, 'clear');
  assert.equal(vm.runInContext('exploreHomeLoaded', context), false);
  context.document.body = { classList: { toggle() {} } };
  vm.runInContext(fs.readFileSync('web/workbench.js', 'utf8'), context);
  vm.runInContext(
    `$('workbench-tool').value='planning';workbenchState={manager_routes:{radarr:[{id:'primary',name:'Main Radarr'}]}};drawWorkbench()`,
    context
  );
  assert.match(element('workbench-controls').innerHTML, /Main Radarr/);
  assert.match(element('workbench-controls').innerHTML, /Storage estimate/);
  vm.runInContext(`$('workbench-tool').value='tonight';drawWorkbench()`, context);
  assert.match(element('workbench-controls').innerHTML, /connected multi-watch session/);
  vm.runInContext(
    `workbenchItems=[{key:'plex1',type:'movie',tmdb:'1',title:'Movie',runtime:90}];shortlist.set('plex1',workbenchItems[0])`,
    context
  );
  await vm.runInContext("workAction('choose')", context);
  assert.match(element('workbench-results').innerHTML, /Tonight’s finalist/);
  assert.match(element('workbench-results').innerHTML, /90 min/);
  vm.runInContext(
    `$('workbench-tool').value='radar';workbenchState.creator_follows=[{id:'9',name:'Director',role:'crew'}];drawWorkbench()`,
    context
  );
  assert.match(element('workbench-controls').innerHTML, /data-work-unfollow="9"/);
  vm.runInContext(`$('workbench-tool').value='insights';drawWorkbench()`, context);
  assert.match(element('workbench-controls').innerHTML, /reset the selected local history/);
  vm.runInContext(
    `pathRows=[{id:'one',title:'First',included:true},{id:'two',title:'Second',included:false}];drawPathRows()`,
    context
  );
  assert.match(element('list-path-entries').innerHTML, /data-path-include="0" checked/);
  assert.match(element('list-path-entries').innerHTML, /data-path-move/);
  await vm.runInContext(
    `$('catalogue-source-url').value='https://example.com/official-lists.json';api=async()=>({token:'reviewed',version:3,summary:{added:[{name:'New <list>',version:1,entries:10}],updated:[],older:[],unchanged:2,kept_local:1}});previewCatalogue(false)`,
    context
  );
  assert.match(element('catalogue-feed-review').innerHTML, /New &lt;list&gt;/);
  assert.equal(element('catalogue-feed-install').hidden, false);
  vm.runInContext(`$('catalogue-source-url').oninput()`, context);
  assert.equal(element('catalogue-feed-install').hidden, true);
  assert.equal(vm.runInContext('cataloguePreviewToken', context), null);
  vm.runInContext(fs.readFileSync('web/workspace.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('web/audit-workflows.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('web/discovery-updates.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('web/navigation.js', 'utf8'), context);
  const candidate = vm.runInContext(
    `requestCandidateMarkup({title:'Arrival <2016>',year:'2016',type:'movie',tmdb:'329865',poster:'https://image.tmdb.org/t/p/w342/a.jpg',overview:'A linguist makes first contact.'},0)`,
    context
  );
  assert.match(candidate, /A linguist makes first contact/);
  assert.match(candidate, /Arrival &lt;2016&gt;/);
  assert.match(candidate, /TMDB 329865/);
  assert.match(candidate, /<img/);
  vm.runInContext(
    `titleWorkspaceContext={sequence:titleSequence,item:{type:'movie',title:'Owned'},state:{ownership:'available'}};$('title-save').hidden=true`,
    context
  );
  assert.match(vm.runInContext('titleActionMarkup()', context), /In your Plex library/);
  assert.doesNotMatch(vm.runInContext('titleActionMarkup()', context), /data-title-request/);
  vm.runInContext(`titleWorkspaceContext.state={ownership:'missing',can_request:true}`, context);
  assert.match(vm.runInContext('titleActionMarkup()', context), /Add to library/);
  vm.runInContext(
    `titleWorkspaceContext.state={ownership:'missing',tracked:true,upcoming:true}`,
    context
  );
  assert.match(vm.runInContext('titleActionMarkup()', context), /Manage release tracking/);
  assert.doesNotMatch(vm.runInContext('titleActionMarkup()', context), /data-track-release/);
  vm.runInContext(
    `titleWorkspaceContext=null;workspacePanel='workspace';listReturnTab='official';$('list-detail').hidden=false`,
    context
  );
  assert.match(
    vm.runInContext('currentWorkspaceRoute()', context),
    /#\/lists\/view\/.*origin=official/
  );
  vm.runInContext(`$('list-detail').hidden=true;listsTab='official'`, context);
  assert.equal(vm.runInContext('currentWorkspaceRoute()', context), '#/lists/official');
  vm.runInContext(
    `workspacePanel='title-dialog';activeShowContext={data:{show:{tmdb:'1403'}}}`,
    context
  );
  assert.equal(
    vm.runInContext('currentWorkspaceRoute()', context),
    '#/title/show/1403',
    'A parent show route must not inherit the originating episode scope'
  );
  vm.runInContext(
    `activeShowContext=null;externalTitle={type:'episode',tmdb:'1403',season:1,episode:2}`,
    context
  );
  assert.equal(
    vm.runInContext('currentWorkspaceRoute()', context),
    '#/title/episode/1403/1/2',
    'Direct episode pages must keep their parent-show ID in the route'
  );
  vm.runInContext(
    `externalTitle=null;const busyLabel=$('busy-label-check');busyLabel.textContent='Track release';globalThis.busyLabel=busyLabel`,
    context
  );
  await vm.runInContext(
    `task(busyLabel,async()=>{busyLabel.textContent='Tracking release';})`,
    context
  );
  assert.equal(
    element('busy-label-check').textContent,
    'Tracking release',
    'Busy presentation must preserve the successful action label'
  );
  vm.runInContext(
    `$('title-add').hidden=false;$('title-add').disabled=true;$('title-add').textContent='Add to Radarr';$('parent-request').hidden=true;$('title-save').hidden=false;$('title-save').disabled=false;$('title-save').textContent='Save & compare'`,
    context
  );
  const titleCommands = vm.runInContext('titleActionMarkup()', context);
  assert.match(titleCommands, /data-title-command="title-add" disabled/);
  assert.match(titleCommands, /Save &amp; compare/);
  assert.doesNotMatch(titleCommands, /data-title-command="parent-request"/);
  vm.runInContext(
    `explorePicks.clear();explorePicks.set('a',{upcoming:true});explorePicks.set('b',{availability:{status:'home'}});exploreSelection()`,
    context
  );
  assert.match(element('explore-pick-count').textContent, /1 to compare.*1 to track/);
  assert.equal(element('explore-save-picks').textContent, 'Save & track selected');
  vm.runInContext(
    `requestRows=[{id:'done',item:{title:'Done',type:'movie'},status:'available',events:[],created_at:10},{id:'fix',item:{title:'Fix first',type:'movie'},status:'attention',events:[],created_at:1}];$('requests-filter').value='';$('requests-search').value='';drawRequests()`,
    context
  );
  assert.ok(
    element('requests-items').innerHTML.indexOf('Fix first') <
      element('requests-items').innerHTML.indexOf('>Done<')
  );
  const discoveryCard = (extra) =>
    vm.runInContext(
      `exploreTitleCard(${JSON.stringify({ key: 'movie:42', type: 'movie', tmdb: '42', title: 'Example', ...extra })})`,
      context
    );
  assert.doesNotMatch(discoveryCard({ in_library: true, upcoming: true }), /data-track-release=/);
  assert.doesNotMatch(discoveryCard({ availability: { status: 'home' } }), /data-track-release=/);
  assert.match(discoveryCard({ upcoming: true }), /data-track-release="42"/);
  assert.match(
    discoveryCard({ availability: { status: 'theatrical' } }),
    /data-track-release="42"/
  );
  assert.doesNotMatch(vm.runInContext("releaseDateLine('Theaters','2020-01-01')", context), / \? /);
  const candidates = vm.runInContext(
    `personSearchMarkup([{id:206,name:'Jim <Carrey>',known_for_department:'Acting',following:'all',known_for:[{title:'The Mask'}]},{id:206,name:'Duplicate'}])`,
    context
  );
  assert.equal((candidates.match(/creator-identity/g) || []).length, 1);
  assert.match(candidates, /Jim &lt;Carrey&gt;/);
  assert.match(candidates, /The Mask/);
  assert.match(candidates, /Following/);
  const releaseCards = vm.runInContext(
    `followedReleaseCards([{type:'episode',title:'Pilot',show_title:'Series',show_tmdb:'42',season:'1',episode:'1',release_date:'2099-01-01T10:00:00Z',poster:'https://example.com/poster.jpg'}])`,
    context
  );
  assert.match(releaseCards, /Series/);
  assert.match(releaseCards, /Season 1/);
  assert.match(releaseCards, /poster.jpg/);
  assert.equal(
    vm.runInContext(
      `mediaRoute({type:'episode',tmdb:'99',show_tmdb:'42',season:2,episode:3})`,
      context
    ),
    '#/title/episode/42/2/3'
  );
  vm.runInContext(`workbenchItems=[{key:'m',type:'movie',tmdb:'1',title:'A',runtime:50}]`, context);
  const sessionMarkup = vm.runInContext(
    `tonightResults({minutes:120,items:workbenchItems,plans:[{key:'p',kind:'movies',title:'Double feature',runtime:100,remaining:20,reason:'Shared genres',items:workbenchItems}]})`,
    context
  );
  assert.match(sessionMarkup, /100 min/);
  assert.match(sessionMarkup, /20 min spare/);
  assert.doesNotMatch(sessionMarkup, /<small>\?/);
  const unreadMarkup = vm.runInContext(
    `notificationInboxMarkup([{id:'one',category:'requests',title:'New film',detail:'Available in Plex',read:false},{id:'two',category:'creators',title:'Read film',detail:'Upcoming',read:true}])`,
    context
  );
  assert.match(unreadMarkup, /Mark read/);
  assert.match(unreadMarkup, /New film/);
  assert.doesNotMatch(unreadMarkup, /Read film/);
  vm.runInContext(
    `state.lists=[{id:'curated-test',name:'Order',items:[{id:'a',type:'movie',title:'A'},{id:'b',type:'movie',title:'B'}],watch_paths:{recommended:['b','a']}}];active='curated-test';curatedChoices.set(active,'recommended');$('sort').value='original';$('search').value='';filter='all'`,
    context
  );
  assert.equal(vm.runInContext(`curatedListItems().map(row=>row.id).join(',')`, context), 'b,a');
  assert.equal(
    vm.runInContext(`current().items.map(row=>row.id).join(',')`, context),
    'a,b',
    'Viewing a curated order must not mutate source membership'
  );
  vm.runInContext(`curatedChoices.set(active,'');window.refreshCuratedOrders()`, context);
  assert.equal(vm.runInContext('selectedCuratedOrder()', context), '');
  assert.equal(vm.runInContext('curatedOrderRoute()', context), '&order=original');
  assert.equal(
    vm.runInContext(
      `recentDownloadRequests([{id:'new',status:'requested',created_at:9999999},{id:'draft',status:'pending',created_at:9999999},{id:'old',status:'available',created_at:1}],10000000).map(r=>r.id).join(',')`,
      context
    ),
    'new'
  );
  const followsMarkup = vm.runInContext(
    `followedCreatorsMarkup([{id:'206',name:'Jim Carrey',role:'cast',profile_path:'/photo.jpg'}])`,
    context
  );
  assert.match(followsMarkup, /Actor \/ cast/);
  assert.match(followsMarkup, /data-work-follow-role="206"/);
  assert.match(followsMarkup, /projects\/person\/206/);
  vm.runInContext(fs.readFileSync('web/list-updates.js', 'utf8'), context);
  vm.runInContext(
    `renderLinkedUpdates({paused:true,running:null,lists:[{id:'linked',name:'Safe <name>',schedule:{interval:'daily',last_error:'Provider <error>'},review:{changed:true,added:2,removed:1,reordered:true,added_items:[{title:'New <title>',show_title:'Series',season:1,episode:2}],removed_items:[]}}]})`,
    context
  );
  assert.match(element('list-updates-rows').innerHTML, /Safe &lt;name&gt;/);
  assert.match(element('list-updates-rows').innerHTML, /2 added \/ 1 removed/);
  assert.match(element('list-updates-rows').innerHTML, /order changed/);
  assert.match(element('list-updates-rows').innerHTML, /S1 E2/);
  assert.equal(element('list-updates-pause').textContent, 'Resume scheduled checks');
  const pinnedOrder = vm.runInContext(
    `linkedOrderPreviews.set('test', {token:'checked-token',visible:100,items:[{title:'New <title>',previous_position:null},{title:'Existing',previous_position:4}]});linkedOrderMarkup('test')`,
    context
  );
  assert.match(pinnedOrder, /New &lt;title&gt;/);
  assert.match(pinnedOrder, /previously #4/);
  assert.match(pinnedOrder, /data-token="checked-token"/);
  assert.match(pinnedOrder, /Apply this checked version/);
  const providerMerge = vm.runInContext(
    `mergeProviderDraft([{type:'movie',tmdb:'1'}],[{id:'remote1',type:'movie',tmdb:'1'},{id:'remote2',type:'movie',tmdb:'2'},{type:'movie',tmdb:'2'},{id:'remote3',type:'episode',show_tvdb:'42',season:'1',episode:'2'},{type:'episode',show_tvdb:'42',season:'1',episode:'3'}])`,
    context
  );
  assert.equal(providerMerge.length, 3);
  assert.equal(providerMerge[0].tmdb, '2');
  assert.equal(providerMerge[0].id, undefined);
  assert.equal(providerMerge[1].show_tvdb, '42');
  assert.equal(providerMerge[2].episode, '3');
  const parallelPayload = vm.runInContext(
    `builderOrderPayload([{type:'season',season:'1',parallel_group:'parallel-1',parallel_lane:0,matches:[{type:'show',tmdb:'42'}],chosen:0}])`,
    context
  );
  assert.equal(parallelPayload[0].parallel_lane, 0);
  assert.equal(parallelPayload[0].parallel_group, 'parallel-1');
  const parallelMarkup = vm.runInContext(
    `builderRowMarkup({index:0,raw:'Alpha (Season 1)',query:'Alpha',type:'season',season:'1',season_end:'1',parallel_group:'parallel-1',parallel_lane:0,matches:[{type:'show',tmdb:'42',title:'Alpha'}],chosen:0})`,
    context
  );
  assert.match(parallelMarkup, /Parallel lane 1 \(starts first\)/);
  assert.match(parallelMarkup, /Make block sequential/);
  console.log(
    'UI checks passed, including catalogue delivery, Workbench, paths, taste and maintenance.'
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
