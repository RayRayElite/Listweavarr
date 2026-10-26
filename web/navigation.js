/* Hash routes are shareable within this installation; navigation never submits data. */
let routeApplying=false,routePending=false,routeReady=false,incomingRouteTimer=null,parentRouteIntent=null,projectRouteIntent=null;
const initialWorkspaceRoute=window.location.hash;
function currentWorkspaceRoute(){
  if(workspacePanel==='settings')return '#/settings/'+settingsTab;
  if(workspacePanel==='requests-page')return requestSection==='downloads'?'#/requests/downloads':'#/requests';
  if(workspacePanel==='title-dialog'){
    if(parentRouteIntent)return '#/title/show/'+parentRouteIntent;
    if(activeShowContext?.data?.show?.tmdb)return '#/title/show/'+activeShowContext.data.show.tmdb;
    const item=externalTitle||current()?.items.find(row=>row.id===openedItem);
    if(item?.type==='season')return '#/lists/view/'+encodeURIComponent(active)+'?origin='+listReturnTab+'&item='+encodeURIComponent(item.id);
    if(item){const kind=item.type==='movie'?'movie':item.type==='episode'?'episode':'show',id=kind==='episode'?(item.show_tmdb||item.tmdb):item.tmdb||item.show_tmdb;if(id)return '#/title/'+kind+'/'+id+(kind==='episode'?'/'+item.season+'/'+item.episode:'');}
  }
  if(workspacePanel==='discovery-dialog'&&(projectRouteIntent||discoveryContext)){const context=projectRouteIntent||discoveryContext;return '#/projects/'+encodeURIComponent(context.kind)+'/'+encodeURIComponent(context.identifier);}
  if(workspacePanel==='trakt-explore'){
    if(exploreTab==='discover'&&shelfContext)return '#/explore/shelf/'+encodeURIComponent(shelfContext.id)+'?name='+encodeURIComponent($('explore-shelf-title').textContent);
    return '#/explore/'+exploreTab+(exploreTab==='workbench'?'/'+($('workbench-tool').value||'tonight'):'');
  }
  if(workspacePanel==='workspace')return !$('list-detail').hidden?'#/lists/view/'+encodeURIComponent(active)+'?origin='+listReturnTab+(typeof curatedOrderRoute==='function'?curatedOrderRoute():''):'#/lists/'+listsTab;
  return '#/explore/discover';
}
function queueWorkspaceRoute(){
  if(!routeReady||routeApplying||typeof history==='undefined')return;
  if(routePending)return;routePending=true;
  const enqueue=typeof queueMicrotask==='function'?queueMicrotask:fn=>setTimeout(fn,0);
  enqueue(()=>{routePending=false;if(routeApplying)return;const hash=currentWorkspaceRoute();if(window.location.hash!==hash)history.pushState({reelcheck:true,depth:(history.state?.depth||0)+1,scroll:0},'',hash);});
}
async function applyWorkspaceRoute(hash){
  if(!routeReady)return;
  routeApplying=true;
  const targetScroll=typeof history!=='undefined'?history.state?.scroll||0:0;
  try{
    document.querySelectorAll('dialog[open]').forEach(dialog=>dialog.close());
    const [path,query='']=String(hash||'#/explore/discover').replace(/^#\/?/,'').split('?');
    const parts=path.split('/').map(decodeURIComponent),params=new URLSearchParams(query);
    if(parts[0]==='settings'){settingsView(true);selectSettingsTab(parts[1]||'preferences');}
    else if(parts[0]==='requests'){if(parts[1]==='downloads')openRequestDownloads();else openRequests();}
    else if(parts[0]==='lists'){
      settingsView(false);
      if(parts[1]==='view'&&state.lists.some(row=>row.id===parts[2])){selectListsTab(params.get('origin')==='official'?'official':'mine');openSavedList(parts[2]);if(params.has('order')&&typeof selectCuratedOrder==='function')selectCuratedOrder(params.get('order'));if(params.get('item')&&current()?.items.some(row=>row.id===params.get('item')))await openTitle(params.get('item'));}
      else selectListsTab(['mine','official','ignored','downloads'].includes(parts[1])?parts[1]:'mine');
    }
    else if(parts[0]==='title'&&['movie','show','episode'].includes(parts[1])&&/^\d+$/.test(parts[2]||'')){titleBackStack=[];await openExternalTitle(parts[1],parts[2],parts[3],parts[4]);}
    else if(parts[0]==='projects'&&['person','company','movie','show'].includes(parts[1])&&/^\d+$/.test(parts[2]||'')){await openDiscovery(parts[1],parts[2]);}
    else{
      traktOpen();selectExploreTab(['discover','watchlist','lists','workbench'].includes(parts[1])?parts[1]:'discover');
      if(parts[1]==='workbench'&&WORK_TOOLS.some(row=>row[0]===parts[2])){await loadWorkbench();if($('workbench-tool').value!==parts[2])showTool(parts[2]);}
      if(parts[1]==='shelf'&&/^[\w-]+$/.test(parts[2]||''))await openExploreShelf(parts[2],params.get('name')||'Discover more');else if(parts[1]==='discover')closeExploreShelf();
    }
  }catch(error){toast('This page could not be opened: '+error.message);}
  finally{scrollWorkspace(targetScroll);routeApplying=false;}
}
// Batch nested handlers into one browser-history entry rather than recording transient panels.
const parentBeforeRouteIntent=openParent;
openParent=function(id,...args){const item=current()?.items.find(row=>row.id===id);parentRouteIntent=item?.show_tmdb||item?.tmdb||null;return Promise.resolve(parentBeforeRouteIntent(id,...args)).finally(()=>{parentRouteIntent=null;});};
const projectsBeforeRouteIntent=openDiscovery;
openDiscovery=function(kind,identifier){projectRouteIntent={kind,identifier};return Promise.resolve(projectsBeforeRouteIntent(kind,identifier)).finally(()=>{projectRouteIntent=null;});};
const externalBeforeRouteIntent=openExternalTitle;
openExternalTitle=function(...args){parentRouteIntent=null;return externalBeforeRouteIntent(...args);};
function routed(fn){return function(...args){const result=fn.apply(this,args);if(result?.then)return result.finally(queueWorkspaceRoute);queueWorkspaceRoute();return result;};}
openWorkspacePanel=routed(openWorkspacePanel);selectListsTab=routed(selectListsTab);selectSettingsTab=routed(selectSettingsTab);selectExploreTab=routed(selectExploreTab);
openSavedList=routed(openSavedList);openExternalTitle=routed(openExternalTitle);openTitle=routed(openTitle);openParent=routed(openParent);openDiscovery=routed(openDiscovery);
openExploreShelf=routed(openExploreShelf);closeExploreShelf=routed(closeExploreShelf);showTool=routed(showTool);closeWorkspacePanel=routed(closeWorkspacePanel);restoreBrowsePage=routed(restoreBrowsePage);
selectRequestSection=routed(selectRequestSection);
if(typeof window.addEventListener==='function'){
  bindTabKeys('data-lists-tab',selectListsTab);bindTabKeys('data-explore-tab',selectExploreTab);
  const incoming=()=>{clearTimeout(incomingRouteTimer);incomingRouteTimer=setTimeout(()=>applyWorkspaceRoute(window.location.hash),0);};
  window.addEventListener('popstate',incoming);window.addEventListener('hashchange',incoming);
  const rememberScroll=()=>{if(routeReady&&!routeApplying&&history.state?.reelcheck&&window.location.hash===currentWorkspaceRoute())history.replaceState({...history.state,scroll:window.scrollY||0},'',window.location.hash);};
  window.addEventListener('scroll',rememberScroll,{passive:true});document.addEventListener('click',rememberScroll,true);
  for(const button of document.querySelectorAll('[data-close="title-dialog"],[data-close="discovery-dialog"]'))button.onclick=()=>{if(history.state?.reelcheck&&history.state.depth>0)history.back();else closeWorkspacePanel(button.dataset.close);};
  document.addEventListener('click',()=>{queueWorkspaceRoute();});
  const readyBeforeRoutes=window.onReelCheckReady;
  window.onReelCheckReady=()=>{routeApplying=true;readyBeforeRoutes?.();routeApplying=false;routeReady=true;if(initialWorkspaceRoute.startsWith('#/'))applyWorkspaceRoute(initialWorkspaceRoute);else history.replaceState({reelcheck:true,depth:0,scroll:0},'',currentWorkspaceRoute());};
}

// State can arrive before the final script on a warm local connection.
if(state.csrf&&!routeReady&&typeof window.onReelCheckReady==='function')window.onReelCheckReady();
