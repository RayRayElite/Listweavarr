/* Public Trakt browsing; saving and requesting remain explicit actions. */
let traktPage=1,traktPreview=null,traktSearchSequence=0;
const traktProgressPending=new Map(),traktTitleCache=new Map(),broadSuggestionCache=new Map();
const isTraktList=l=>Boolean(l?.source&&/^https:\/\/(www\.)?trakt\.tv\//.test(l.source));
function traktOpen(){openWorkspacePanel('trakt-explore');$('breadcrumb').textContent='Explore Trakt';$('library-nav').classList.toggle('active',false);$('settings-nav').classList.toggle('active',false);}
function traktRows(items){return items.map((r,index)=>`<div class="trakt-result-row"><span class="muted">${index+1}</span><div><button class="person-link" data-trakt-item="${index}">${esc(r.title)}</button><p class="muted">${esc(r.type)} ${r.season!=null?' / Season '+esc(r.season):''}${r.episode!=null?' / Episode '+esc(r.episode):''} ${esc(r.year||'')}</p>${r.release_date?`<p>${esc(new Date(r.release_date).toLocaleString())}</p>`:''}</div><span>${esc(r.status||'Not compared')}${r.manager_status?' / '+esc(r.manager_status):''}${ignoreButton(r)}</span></div>`).join('');}
function traktItemOpen(r){if(!r)return;const id=r.type==='movie'||r.type==='show'?r.tmdb:r.show_tmdb;if(!id){toast('Resolve this title’s metadata in a saved list to open its details.');return;}openExternalTitle(r.type==='season'?'show':r.type,id,r.season,r.episode);}
function traktDescription(value){return String(value||'').replace(/!\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/https?:\/\/\S+/g,'').replace(/<[^>]*>/g,'').replace(/[*_`#~]+/g,'').replace(/\s+/g,' ').trim();}
function traktCards(lists){return lists.map((l,index)=>{const description=traktDescription(l.description),short=description.length>175?description.slice(0,172).replace(/\s+\S*$/,'')+'…':description;return `<article class="trakt-list-row"><span class="trakt-list-rank" aria-hidden="true">${String(index+1).padStart(2,'0')}</span><div class="trakt-list-copy"><h3>${esc(l.name)}</h3><div class="trakt-list-meta"><span>by ${esc(l.owner)}</span><span>${esc(l.count??'—')} titles</span><span>${Number(l.likes||0).toLocaleString()} likes</span></div>${description?`<p class="trakt-list-description">${esc(short)}</p><details class="trakt-list-about"><summary>About this list</summary><p>${esc(description)}</p><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">View original on Trakt &#8599;</a></details>`:''}</div><button class="secondary trakt-preview-button" data-trakt-preview="${esc(l.url)}">Preview list <span aria-hidden="true">&#8594;</span></button></article>`;}).join('')||'<p class="muted">No lists found. Try another search.</p>';}
async function traktSearch(){const sequence=++traktSearchSequence;$('trakt-explore-status').textContent='Finding lists…';const data=await api('trakt/search',{query:$('trakt-query').value,mode:$('trakt-list-mode').value,page:traktPage});if(sequence!==traktSearchSequence)return;$('trakt-list-results').innerHTML=traktCards(data.lists);$('trakt-page-prev').hidden=traktPage<=1;$('trakt-page-next').hidden=!data.has_more;$('trakt-explore-status').textContent='Page '+traktPage+'. Preview preserves each list’s original order.';}
async function traktPreviewList(url){traktOpen();$('trakt-preview').hidden=false;$('trakt-preview-title').textContent='Loading list…';$('trakt-preview-summary').textContent='Reading the complete list and checking Plex. Large episode lists can take a moment.';$('trakt-preview-rows').innerHTML='';$('trakt-preview-save').disabled=true;traktPreview=null;const result=await api('trakt/preview',{url,compare:Boolean(state.settings.plex?.configured)});traktPreview=result;$('trakt-preview-title').textContent=result.name;$('trakt-preview-filter').value='all';traktRenderPreview();$('trakt-preview-save').disabled=false;}
function traktRenderPreview(){if(!traktPreview)return;const mode=$('trakt-preview-filter').value;const rows=traktPreview.items.map((r,index)=>({...r,_index:index})).filter(r=>!isIgnored(r)&&(mode==='all'||(mode==='available'?r.status==='available':['missing','partial'].includes(r.status))));$('trakt-preview-summary').textContent=`${traktPreview.items.length} entries / ${rows.length} shown. ${traktPreview.compared?'Compared with Plex.':'Connect Plex to check availability.'} Saving adds this list to your workspace.`;$('trakt-preview-rows').innerHTML=traktRows(rows).replace(/data-trakt-item="(\d+)"/g,(_,n)=>`data-trakt-item="${rows[Number(n)]._index}"`);}
async function traktCheckUpdates(force=false){const data=await api('trakt/updates',{force});for(const update of data.updates){const l=state.lists.find(l=>l.id===update.id);if(l)l.source_check=update;}window.renderTraktSavedInfo();if(force)toast(data.updates.some(u=>u.error)?'Some sources could not be checked. See the list notice.':'Followed lists checked.');}
window.renderTraktSavedInfo=()=>{const l=current(),follow=$('follow-list');follow.hidden=!isTraktList(l);follow.textContent=l?.followed===false?'Follow source updates':'Following source';$('progress-refresh').disabled=!l||!state.settings.plex?.configured;const check=l?.source_check,p=l?.watch_progress;let html='';if(check)html+=`<p class="source-notice">${esc(check.error|| (check.changed?'This source has changed. Use Refresh source to review its updates.':'Source checked; your saved list is up to date.'))}</p>`;if(p)html+=`<div class="watch-progress"><strong>${p.completed} / ${p.entries} list entries watched</strong><progress max="${p.entries||1}" value="${p.completed}"></progress><span class="muted">Plex watch history checked ${esc(new Date(p.checked_at*1000).toLocaleString())}. Overlapping show and episode entries count separately.</span>${p.next?`<button class="secondary" data-watch-next="${esc(p.next.id)}">Next in order: ${esc(p.next.title)}</button>`:''}${p.next_available&&p.next_available.id!==p.next?.id?`<button class="secondary" data-watch-next="${esc(p.next_available.id)}">Next available: ${esc(p.next_available.title)}</button>`:''}</div>`;$('trakt-saved-info').innerHTML=html;};
window.watchBadgeFor=item=>{const row=current()?.watch_progress?.items.find(r=>r.id===item.id);return row?`<span class="watch-badge">${esc({watched:'Watched',in_progress:'In progress',unwatched:'Unwatched',unknown:'Watch history unknown'}[row.state]||row.state)}</span>`:'';};
async function traktProgress(){const l=current();if(!l||traktProgressPending.has(l.id))return;const id=l.id;const pending=api('progress',{list_id:id});traktProgressPending.set(id,pending);try{const result=await pending;const saved=state.lists.find(l=>l.id===id);if(saved)saved.watch_progress=result;if(active===id)render();}finally{traktProgressPending.delete(id);}}
async function traktCalendar(){traktOpen();$('trakt-calendar').hidden=false;$('trakt-calendar').scrollIntoView?.({block:'start',behavior:'smooth'});$('trakt-calendar-note').textContent='Checking the next seven days…';const data=await api('trakt/calendar',{});$('trakt-calendar-note').textContent=data.note+(data.warnings?.length?' '+data.warnings.join(' '):'');$('trakt-calendar-rows').innerHTML=followedReleaseCards(data.items)||'<p>No upcoming releases found for titles in your followed lists.</p>';$('trakt-calendar-rows').onclick=e=>{const b=e.target.closest('[data-trakt-item]');if(b)traktItemOpen(data.items[Number(b.dataset.traktItem)]);};}
let traktTitleListsContext=null;
function traktTitleListsMarkup(data){return `<details class="trakt-curated-lists"><summary><span><span class="eyebrow">FROM THE COMMUNITY</span><strong>Lists featuring this title</strong></span><span class="trakt-section-count"><span id="trakt-title-list-count">${data.lists.length} lists</span> <span aria-hidden="true">+</span></span></summary><p class="muted">Popular public lists containing this ${esc(data.scope)}.</p><div id="trakt-title-list-rows">${traktCards(data.lists)}</div><div class="trakt-more-lists"><button class="secondary" data-trakt-more-lists ${data.lists_has_more?'':'hidden'}>Show more lists</button><span id="trakt-title-list-status" class="muted" role="status"></span></div></details>`;}
async function loadMoreTraktTitleLists(button){
  const context=traktTitleListsContext;
  if(!context||context.sequence!==titleSequence||!context.data.lists_has_more)return;
  const data=await api('trakt/title-lists',{...context.body,page:(context.data.list_page||1)+1});
  if(context!==traktTitleListsContext||context.sequence!==titleSequence)return;
  const seen=new Set(context.data.lists.map(l=>l.url));
  context.data.lists.push(...data.lists.filter(l=>!seen.has(l.url)&&seen.add(l.url)));
  context.data.list_page=data.page;context.data.lists_has_more=data.has_more;
  $('trakt-title-list-rows').innerHTML=traktCards(context.data.lists);
  $('trakt-title-list-count').textContent=context.data.lists.length+' lists';
  $('trakt-title-list-status').textContent=data.has_more?'':'All available lists shown.';
  button.hidden=!data.has_more;
}
const keepExploringTitles=new Map();
const tmdbExplorationRecommendations=new Map();
window.setExplorationRecommendations=(sequence,rows)=>{
  if(sequence!==titleSequence)return;
  tmdbExplorationRecommendations.set(sequence,rows.map(row=>({...row,provider:'TMDB',reasons:['Recommended on TMDB']})));
  if(tmdbExplorationRecommendations.size>20)tmdbExplorationRecommendations.delete(tmdbExplorationRecommendations.keys().next().value);
  renderMoreToExplore();
};
function exploringTitleKey(row){return (row.type==='show'||row.type==='tv'?'tv':'movie')+':'+String(row.tmdb);}
window.setKeepExploringTitles=(sequence,rows)=>{
  if(sequence!==titleSequence)return;
  keepExploringTitles.set(sequence,new Set(rows.filter(r=>r.tmdb).map(exploringTitleKey)));
  if(keepExploringTitles.size>20)keepExploringTitles.delete(keepExploringTitles.keys().next().value);
  renderMoreToExplore();
};
function renderMoreToExplore(){
  const context=traktTitleListsContext;
  if(!context||context.sequence!==titleSequence)return;
  const excluded=keepExploringTitles.get(context.sequence)||new Set();
  const seen=new Set([exploringTitleKey({type:context.body.type==='movie'?'movie':'show',tmdb:context.body.tmdb})]);
  const recommendations=[...(context.data.broadRecommendations||[]),...(tmdbExplorationRecommendations.get(context.sequence)||[]),...context.data.recommendations].filter(row=>{const key=exploringTitleKey(row);if(isIgnored(row)||excluded.has(key)||seen.has(key))return false;seen.add(key);return true;}).slice(0,36);
  $('trakt-more-explore').innerHTML=`${recommendations.length?`<div class="trakt-recommendation-heading"><h3>More to explore</h3><span class="muted">Picked for this title</span></div><p class="muted trakt-recommendation-note">Shared cast, filmmakers, genres and story themes. Suggestions exclude titles shown in the other rows.</p><div class="related-preview trakt-recommendations" tabindex="0" role="region" aria-label="More to explore titles">${recommendations.map(r=>`<button class="related-card" data-trakt-title="${esc(r.tmdb)}" data-type="${esc(r.type)}">${r.poster?posterArt(r.poster,r):`<span class="trakt-poster-placeholder">${esc(r.title.charAt(0))}</span>`}<strong>${esc(r.title)}</strong>${ratingWidget(r)}<small>${esc(r.year||'')} &middot; ${r.type==='show'?'TV show':'Movie'}</small><small class="suggestion-reason">${esc(r.reasons?.slice(0,2).join(' · ')||'Recommended on Trakt')}</small></button>`).join('')}</div>`:''}`;
}
window.loadTraktTitleExtras=async(item,m,sequence)=>{
  const body={type:item.type,tmdb:m.related_id,season:item.season,episode:item.episode},key=JSON.stringify(body);
  try{
    const parentType=item.type==='movie'?'movie':'show';
    const broadKey=parentType+':'+m.related_id;
    if(!broadSuggestionCache.has(broadKey))broadSuggestionCache.set(broadKey,api('suggestions',{type:parentType,tmdb:m.related_id}).catch(e=>{broadSuggestionCache.delete(broadKey);throw e;}));
    let traktJob=Promise.resolve(null);
    if(state.settings.trakt?.configured){if(!traktTitleCache.has(key))traktTitleCache.set(key,api('trakt/title',body).catch(e=>{traktTitleCache.delete(key);throw e;}));traktJob=traktTitleCache.get(key);}
    const [traktResult,broadResult]=await Promise.allSettled([traktJob,broadSuggestionCache.get(broadKey)]);
    const data={...(traktResult.status==='fulfilled'&&traktResult.value?traktResult.value:{recommendations:[],lists:[]}),broadRecommendations:broadResult.status==='fulfilled'?(broadResult.value.items||[]):[]};
    if(sequence!==titleSequence)return;
    traktTitleListsContext={body,data,sequence};
    $('trakt-title-rating').textContent='';
    if(Number.isFinite(data.rating)){const identity=ratingIdentity({...item,...m});directRatingsCache.set(identity.key,[{source:'trakt',label:'Trakt',value:data.rating,maximum:10,score:data.rating,votes:data.votes,via:'Trakt'}]);repaintRatings();}

    $('trakt-title-extras').innerHTML=`<div id="trakt-more-explore"></div>${state.settings.trakt?.configured?traktTitleListsMarkup(data):''}`;
    renderMoreToExplore();
  }catch(e){if(sequence===titleSequence)$('trakt-title-rating').textContent='';}
};
$('trakt-nav').onclick=()=>{traktOpen();};
$('trakt-search-form').onsubmit=e=>{e.preventDefault();traktPage=1;task($('trakt-search-submit'),traktSearch);};
$('trakt-page-prev').onclick=e=>task(e.target,async()=>{traktPage=Math.max(1,traktPage-1);await traktSearch();});
$('trakt-page-next').onclick=e=>task(e.target,async()=>{traktPage++;await traktSearch();});
$('trakt-list-results').onclick=e=>{const preview=e.target.closest('[data-trakt-preview]');if(preview)task(preview,()=>traktPreviewList(preview.dataset.traktPreview));};
// Title sections are replaced on navigation, so delegate their controls from the persistent parent.
$('title-content').addEventListener('click',e=>{const more=e.target.closest('[data-trakt-more-lists]');if(more){task(more,()=>loadMoreTraktTitleLists(more));return;}const preview=e.target.closest('[data-trakt-preview]'),title=e.target.closest('[data-trakt-title]');if(preview)task(preview,()=>traktPreviewList(preview.dataset.traktPreview));if(title)openExternalTitle(title.dataset.type,title.dataset.traktTitle);});
$('trakt-preview-filter').onchange=traktRenderPreview;
$('trakt-preview-rows').onclick=e=>{const b=e.target.closest('[data-trakt-item]');if(b)traktItemOpen(traktPreview?.items[Number(b.dataset.traktItem)]);};
$('trakt-preview-save').onclick=e=>task(e.target,async()=>{if(!traktPreview)return;const existing=state.lists.find(l=>l.source===traktPreview.source);$('import-dialog').showModal();const job=await api('import/start',existing?{list_id:existing.id}:{url:traktPreview.source});await pollImport(job.job_id);if(state.settings.plex?.configured)replaceList(await api('compare',{list_id:active}));settingsView(false);});
$('follow-list').onclick=e=>task(e.target,async()=>{const l=current();const result=await api('follow',{list_id:l.id,followed:l.followed===false});l.followed=result.followed;window.renderTraktSavedInfo();});
$('check-followed').onclick=e=>task(e.target,()=>traktCheckUpdates(true));
$('progress-refresh').onclick=e=>task(e.target,traktProgress);
$('trakt-saved-info').onclick=e=>{const b=e.target.closest('[data-watch-next]');if(b)openTitle(b.dataset.watchNext);};
for(const id of ['trakt-upcoming','trakt-calendar-refresh'])$(id).onclick=e=>task(e.target,traktCalendar);
let traktReady=false;
window.onReelCheckReady=()=>{if(traktReady)return;traktReady=true;if(state.settings.trakt?.configured)traktCheckUpdates().catch(e=>toast(e.message));};
if(state.csrf)window.onReelCheckReady();
