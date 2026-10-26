// SPDX-License-Identifier: AGPL-3.0-only
/* Workflow composition and addressable navigation for the audited workspace. */
const WORK_TOOLS = [
  ['tonight', 'Tonight', 'Choose from the library you already have.', '◷'],
  ['recipes', 'Discover by mood', 'Combine genres, themes and time.', '✦'],
  ['franchises', 'Complete a franchise', 'Find the missing pieces in a collection.', '◫'],
  ['radar', 'Creator radar', 'Follow people and their next projects.', '◎'],
  ['planning', 'Plan your library', 'Prioritize gaps and estimate storage.', '▥'],
  ['inbox', 'Discovery inbox', 'Releases, requests and list updates.', '↗'],
  ['insights', 'Recommendation insights', 'Review feedback and local influences.', '⌁'],
];
let requestSection = 'requests';
let exploreProfileText = '';
window.refreshExploreHeading = () => {
  if (typeof document.querySelector !== 'function') return;
  const heading = document.querySelector('#trakt-explore>.workspace-heading h1');
  if (!heading) return;
  const description = $('explore-personalization');
  if (/^(Inspired by|Connect Plex)/.test(description.textContent))
    exploreProfileText = description.textContent;
  heading.textContent =
    exploreTab === 'watchlist'
      ? 'Release watchlist'
      : exploreTab === 'lists'
        ? 'Lists & watch orders'
        : 'Explore your next watch.';
  description.textContent =
    exploreTab === 'watchlist'
      ? 'Follow releases and choose what your library should collect automatically.'
      : exploreTab === 'lists'
        ? 'Find curated collections and watch orders, then compare them with Plex.'
        : exploreProfileText || description.textContent;
  const shortcut = $('tonight-shortcut');
  if (shortcut) shortcut.hidden = exploreTab !== 'discover';
};
const selectExploreBeforeHeadings = selectExploreTab;
selectExploreTab = function (name) {
  selectExploreBeforeHeadings(name);
  window.refreshExploreHeading();
  refreshTonightControls();
};
function selectRequestSection(name) {
  requestSection = name === 'downloads' ? 'downloads' : 'requests';
  if ($('request-queue-panel')) $('request-queue-panel').hidden = requestSection !== 'requests';
  $('activity-panel').hidden = requestSection !== 'downloads';
  document.querySelectorAll('[data-request-section]').forEach((button) => {
    const selected = button.dataset.requestSection === requestSection;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $('breadcrumb').textContent =
    requestSection === 'downloads' ? 'REQUESTS / DOWNLOAD PROGRESS' : 'REQUESTS';
}
const openRequestsBeforeSections = openRequests;
openRequests = function () {
  openRequestsBeforeSections();
  selectRequestSection('requests');
};
function openRequestDownloads() {
  openRequests();
  selectRequestSection('downloads');
  loadActivity().catch((error) => ($('activity-status').textContent = error.message));
}

let titleWorkspaceContext = null;
const renderTitleBeforeWorkspaceState = renderTitle;
renderTitle = function (item, metadata) {
  const kind = item.type === 'episode' ? 'episode' : item.type === 'movie' ? 'movie' : 'show';
  const tmdb = ['episode', 'season'].includes(item.type)
    ? item.show_tmdb || metadata.related_id
    : item.tmdb || metadata.related_id;
  titleWorkspaceContext = {
    sequence: titleSequence,
    item: {
      ...item,
      ...(kind === 'episode' ? { show_tmdb: tmdb } : { tmdb }),
      title: metadata.title,
      show_title: metadata.show_title || item.show_title,
    },
    metadata,
    loading: Boolean(tmdb),
    state: null,
  };
  renderTitleBeforeWorkspaceState(item, {
    ...metadata,
    upcoming: Boolean(
      metadata.release_date && metadata.release_date > new Date().toISOString().slice(0, 10)
    ),
  });
  if (kind === 'episode' && typeof document.createElement === 'function') {
    const context = titleWorkspaceContext;
    const heading = document.querySelector('#title-content h2');
    const nav = document.createElement('div');
    nav.className = 'episode-navigation';
    nav.innerHTML = `<span>${esc(metadata.show_title || item.show_title || 'TV episode')} · S${esc(item.season)} E${esc(item.episode)}</span>`;
    heading.after(nav);
    api('title/scopes', { tmdb, season: item.season })
      .then((data) => {
        if (context !== titleWorkspaceContext) return;
        const index = data.episodes.findIndex((row) => String(row.number) === String(item.episode)),
          previous = data.episodes[index - 1],
          next = data.episodes[index + 1];
        const live = document.querySelector('#title-content .episode-navigation');
        if (live)
          live.innerHTML += `${previous ? `<button class="secondary" data-episode-neighbor="${esc(tmdb)}" data-season="${esc(item.season)}" data-episode="${previous.number}">← Previous episode</button>` : ''}${next ? `<button class="secondary" data-episode-neighbor="${esc(tmdb)}" data-season="${esc(item.season)}" data-episode="${next.number}">Next episode →</button>` : ''}`;
      })
      .catch(() => {});
  }
  if (!tmdb || item.type === 'season') {
    titleWorkspaceContext.loading = false;
    return;
  }
  const context = titleWorkspaceContext;
  api('title/status', {
    type: kind,
    tmdb,
    title: metadata.title,
    season: item.season,
    episode: item.episode,
  })
    .then((result) => {
      if (context !== titleWorkspaceContext || context.sequence !== titleSequence) return;
      context.state = result;
      context.loading = false;
      syncTitleActions();
    })
    .catch(() => {
      if (context === titleWorkspaceContext) {
        context.loading = false;
        context.error = true;
        syncTitleActions();
      }
    });
};
const originalTitleActionMarkup = titleActionMarkup;
titleActionMarkup = function () {
  const context = titleWorkspaceContext;
  if (!context || context.sequence !== titleSequence) return originalTitleActionMarkup();
  const data = context.state,
    item = context.item;
  const save = !$('title-save').hidden
    ? `<button class="secondary" data-title-command="title-save" ${$('title-save').disabled ? 'disabled' : ''}>Save to a list & compare</button>`
    : '';
  if (!data)
    return `<span class="title-availability" role="status">${context.loading ? 'Checking Plex availability…' : context.error ? 'Library check unavailable. You can retry from this title.' : ''}</span>${originalTitleActionMarkup()}${context.error ? '<button class="secondary" data-title-check>Retry library check</button>' : ''}`;
  let primary = '';
  if (data.ownership === 'available')
    primary =
      '<span class="title-owned">✓ In your Plex library</span>' +
      (data.plex_url
        ? `<a class="primary" href="${esc(data.plex_url)}" target="_blank" rel="noopener noreferrer">Open in Plex &nearr;</a>`
        : '');
  else if (data.request && data.request.status !== 'available')
    primary = `<button class="primary" data-title-progress>${esc(REQUEST_LABELS[data.request.status] || 'View request')} &rarr;</button>`;
  else if (data.tracked)
    primary =
      '<span class="title-owned">✓ Tracking release</span><button class="secondary" data-open-release-watch>Manage release tracking</button>';
  else if (data.upcoming && ['movie', 'show'].includes(item.type))
    primary = `<button class="primary" data-track-release="${esc(item.tmdb || context.metadata.related_id)}" data-release-type="${esc(item.type)}">${item.type === 'show' ? 'Track premiere' : 'Track home release'}</button><button class="secondary" data-title-request="monitor">Set up automatic download</button>`;
  else if (data.can_request)
    primary =
      '<span class="title-availability">Not in your Plex library</span><button class="primary" data-title-request="search">Add to library</button>';
  else if (data.ownership === 'partial')
    primary = '<span class="title-availability">Show in Plex · review coverage below</span>';
  else
    primary = `<span class="title-availability">${esc(data.label)}</span>${data.ownership === 'unchecked' ? '<button class="secondary" data-settings-open="connections">Connect Plex</button>' : '<button class="secondary" data-title-check>Recheck library match</button>'}`;
  return `<div class="title-state-actions">${primary}${save}</div>`;
};
const captureBeforeTitleState = captureBrowsePage;
captureBrowsePage = function () {
  return { ...captureBeforeTitleState(), titleWorkspaceContext };
};
const restoreBeforeTitleState = restoreBrowsePage;
restoreBrowsePage = function (page) {
  restoreBeforeTitleState(page);
  titleWorkspaceContext = page.titleWorkspaceContext
    ? { ...page.titleWorkspaceContext, sequence: titleSequence }
    : null;
  syncTitleActions();
};
const captureDiscoveryState = captureBrowsePage;
captureBrowsePage = function () {
  return {
    ...captureDiscoveryState(),
    projects: discoveryContext,
    projectSelection: [...discoverySelected],
    projectFilters: {
      sort: $('discovery-sort').value,
      search: $('discovery-search').value,
      type: $('discovery-type').value,
    },
  };
};
const restoreDiscoveryState = restoreBrowsePage;
restoreBrowsePage = function (page) {
  restoreDiscoveryState(page);
  if (page.panel === 'discovery-dialog' && page.projects) {
    discoveryContext = page.projects;
    discoverySelected = new Set(page.projectSelection || []);
    $('discovery-sort').value = page.projectFilters.sort;
    $('discovery-search').value = page.projectFilters.search;
    $('discovery-type').value = page.projectFilters.type;
    renderPersonProfile(page.projects.data);
    $('discovery-title').textContent = page.projects.data.profile
      ? 'Filmography'
      : page.projects.data.name;
    drawDiscovery();
  }
};
const releaseActionBeforeTitleState = releaseAction;
releaseAction = async function (action, body = {}) {
  const result = await releaseActionBeforeTitleState(action, body);
  if (titleWorkspaceContext?.state) {
    const item = titleWorkspaceContext.item;
    titleWorkspaceContext.state.tracked = (state.release_watchlist || []).some(
      (row) =>
        (row.type || 'movie') === item.type &&
        String(row.tmdb) === String(item.tmdb) &&
        row.region === exploreFilters().region
    );
    syncTitleActions();
  }
  return result;
};
const placeCoverageBeforeSummary = placeCoverage;
placeCoverage = function (data, allowRequests = true) {
  placeCoverageBeforeSummary(data, allowRequests);
  if (typeof document.createElement !== 'function') return;
  const information = document.querySelector('#title-content .title-information');
  if (!information) return;
  let summary = information.querySelector('.title-coverage-summary');
  if (!summary) {
    summary = document.createElement('div');
    summary.className = 'title-coverage-summary';
    information.querySelector('h2').after(summary);
  }
  summary.innerHTML = `<div><strong>${data.coverage_known ? `${data.available} in Plex · ${data.missing} aired episodes missing` : 'Episode coverage needs checking'}</strong><small>Regular episodes · specials are separate</small></div><button class="secondary" data-view-seasons>View seasons &amp; episodes</button>${data.coverage_known && data.missing ? `<button class="primary" ${allowRequests ? 'data-show-scope' : 'data-external-scope'}="show">Request missing episodes</button>` : ''}`;
};

async function openRequestFor(item, mode = 'search') {
  workflowManagers = await api('managers/list', {});
  const tv = item.type !== 'movie';
  newRequestItem = {
    ...item,
    type: tv ? 'show' : 'movie',
    tmdb: tv ? item.show_tmdb || item.tmdb : item.tmdb,
    title: tv ? item.show_title || item.title : item.title,
  };
  newRequestResults = [];
  $('request-new-results').innerHTML = '';
  $('request-new-query').value = newRequestItem.title;
  $('request-new-type').value = tv ? 'show' : 'movie';
  $('request-new-scope').value = ['season', 'episode'].includes(item.type) ? item.type : 'show';
  $('request-new-season').value = item.season ?? '';
  $('request-new-episode').value = item.episode ?? '';
  $('request-new-mode').value = mode;
  $('request-new-selection').textContent =
    'Selected: ' +
    item.title +
    (['season', 'episode'].includes(item.type)
      ? ' · S' + item.season + (item.episode ? ' E' + item.episode : '')
      : '');
  $('request-new-queue').checked = $('workflow-approval').checked;
  drawNewRequestRoutes();
  $('request-new-dialog').showModal();
  if (tv) loadRequestScopes(item.season, item.episode);
}

let requestScopeSequence = 0;
async function loadRequestScopes(season, episode) {
  const item = newRequestItem;
  if (item?.type !== 'show') return;
  const sequence = ++requestScopeSequence;
  const selectedSeason = season ?? $('request-new-season').value,
    selectedEpisode = episode ?? $('request-new-episode').value;
  requestScopeLoading = true;
  drawNewRequestRoutes();
  $('request-new-status').textContent = 'Loading verified TV scope…';
  try {
    const data = await api('title/scopes', {
      tmdb: item.tmdb,
      ...(selectedSeason !== '' && selectedSeason != null ? { season: selectedSeason } : {}),
    });
    if (sequence !== requestScopeSequence || item !== newRequestItem) return;
    $('request-new-season').innerHTML =
      '<option value="">Choose a season</option>' +
      data.seasons
        .map(
          (row) => `<option value="${row.number}">${esc(row.name)} · ${row.count} episodes</option>`
        )
        .join('');
    if (data.seasons.some((row) => String(row.number) === String(selectedSeason)))
      $('request-new-season').value = String(selectedSeason);
    $('request-new-episode').innerHTML =
      '<option value="">Choose an episode</option>' +
      data.episodes
        .map((row) => `<option value="${row.number}">E${row.number} · ${esc(row.name)}</option>`)
        .join('');
    if (data.episodes.some((row) => String(row.number) === String(selectedEpisode)))
      $('request-new-episode').value = String(selectedEpisode);
    $('request-new-status').textContent = '';
    drawNewRequestRoutes();
  } catch (error) {
    if (sequence === requestScopeSequence) {
      $('request-new-season').innerHTML = '<option value="">Season data unavailable</option>';
      $('request-new-episode').innerHTML = '<option value="">Episode data unavailable</option>';
      $('request-new-status').textContent = 'TV scope could not be loaded: ' + error.message;
    }
  } finally {
    if (sequence === requestScopeSequence) {
      requestScopeLoading = false;
      const message = $('request-new-status').textContent;
      drawNewRequestRoutes();
      if (message.startsWith('TV scope could not')) $('request-new-status').textContent = message;
    }
  }
}

function renderListIdentity() {
  const entry = current();
  if (!entry) return;
  const cover = $('list-detail-cover');
  if (
    cover &&
    (cover.dataset.entry !== entry.id || cover.dataset.poster !== (entry.poster || ''))
  ) {
    cover.dataset.entry = entry.id;
    cover.dataset.poster = entry.poster || '';
    cover.innerHTML = entry.poster
      ? `<img src="${esc(entry.poster)}" alt="">`
      : `<span>${esc(entry.name.charAt(0))}</span>`;
  }
  const items = entry.items,
    available = items.filter((row) => row.status === 'available').length,
    missing = items.filter((row) => ['missing', 'partial'].includes(row.status)).length,
    unchecked = items.filter((row) => !row.status || row.status === 'unchecked').length;
  $('list-availability').innerHTML =
    `<span><strong>${items.length}</strong> entries</span><span><strong>${available}</strong> in Plex</span><span><strong>${missing}</strong> missing / partial</span>${unchecked ? `<span>${unchecked} not checked</span>` : ''}`;
  $('list-context').textContent = entry.description || 'Your collection, in its saved watch order.';
  $('list-review-missing').hidden = !missing && !unchecked;
  $('list-review-missing').textContent = unchecked
    ? 'Check library availability'
    : 'Review ' + missing + ' missing / partial';
}
const renderBeforeAudit = render;
render = function () {
  renderBeforeAudit();
  renderListIdentity();
};
$('list-review-missing').onclick = () => {
  if (current()?.items.some((row) => !row.status || row.status === 'unchecked'))
    $('compare').click();
  else {
    document.querySelector('[data-filter="missing"]')?.click();
    $('entries').scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  }
};

function drawWorkChooser() {
  const host = $('workbench-chooser');
  if (!host) return;
  host.innerHTML = WORK_TOOLS.map(
    ([id, name, note, icon]) =>
      `<button type="button" data-work-tool="${id}" class="work-tool-choice ${$('workbench-tool').value === id ? 'active' : ''}" aria-pressed="${$('workbench-tool').value === id}"><span class="work-tool-icon" aria-hidden="true">${icon}</span><span><strong>${name}</strong><small>${note}</small></span></button>`
  ).join('');
  const tool = WORK_TOOLS.find((row) => row[0] === $('workbench-tool').value);
  if (tool) $('workbench-current-title').textContent = tool[1];
}
const drawWorkbenchBeforeAudit = drawWorkbench;
drawWorkbench = function () {
  drawWorkbenchBeforeAudit();
  drawWorkChooser();
  if ($('workbench-tool').value === 'recipes') {
    const save = document.querySelector('[data-work-action="recipe-save"]'),
      remove = document.querySelector('[data-work-action="recipe-delete"]');
    if (save) save.hidden = !$('workbench-results').textContent?.trim();
    if (remove) remove.hidden = !$('work-recipe').value;
    const name = $('work-name').closest?.('label');
    if (name) name.hidden = !$('work-recipe').value;
  }
  refreshTonightControls();
};

function showTool(name) {
  $('workbench-tool').value = name;
  $('workbench-tool').onchange();
  drawWorkChooser();
  if ($('workbench-picker')) $('workbench-picker').open = false;
}
function refreshTonightControls() {
  const tray = $('tonight-shortlist-tray');
  if (tray) {
    tray.hidden =
      !shortlist.size ||
      workspacePanel !== 'trakt-explore' ||
      exploreTab !== 'workbench' ||
      $('workbench-tool').value !== 'tonight';
    tray.querySelector('span').textContent = shortlist.size + ' shortlisted';
  }
  if ($('workbench-tool').value !== 'tonight') return;
  for (const action of ['choose', 'shortlist', 'shortlist-clear']) {
    const button = document.querySelector(`#workbench-controls [data-work-action="${action}"]`);
    if (button) button.hidden = true;
  }
}
window.paintGenreChoices = () => {
  if (typeof document.createElement !== 'function' || !$('work-genres')) return;
  const select = $('work-genres');
  let host = $('work-genre-choices');
  if (!host) {
    host = document.createElement('fieldset');
    host.id = 'work-genre-choices';
    host.className = 'genre-choices';
    select.closest('label').before(host);
    select.closest('label').hidden = true;
  }
  host.innerHTML =
    '<legend>Genres · choose any</legend>' +
    [...select.options]
      .map(
        (option) =>
          `<label><input type="checkbox" data-work-genre-id="${esc(option.value)}" ${option.selected ? 'checked' : ''}>${esc(option.textContent)}</label>`
      )
      .join('');
  host.onchange = (event) => {
    const input = event.target.closest('[data-work-genre-id]');
    if (input)
      for (const option of select.options)
        if (option.value === input.dataset.workGenreId) option.selected = input.checked;
  };
};
function tonightRows(items) {
  return `<div class="tonight-grid">${items.map((row, index) => `<article class="tonight-card">${row.poster ? `<img src="${esc(row.poster)}" alt="" loading="lazy">` : '<div class="tonight-art-placeholder"></div>'}<div>${row.tmdb ? workTitle(row) : `<strong>${esc(row.title)}</strong>`}<p>${Math.round(row.runtime || 0)} minutes &middot; ${esc(row.reason || 'From your library')}</p><div class="tonight-card-actions"><button class="${shortlist.has(row.key) ? 'secondary' : 'primary'}" data-shortlist-add="${index}" ${shortlist.has(row.key) ? 'disabled' : ''}>${shortlist.has(row.key) ? 'Shortlisted' : 'Add to shortlist'}</button><button class="text-action" data-shortlist-remove="${esc(row.key)}">Eliminate</button></div></div></article>`).join('')}</div>`;
}

function loadingTitleMarkup(type, tmdb, known = {}) {
  const seed = known.title
    ? known
    : exploreRows.find((row) => String(row.tmdb) === String(tmdb) && row.type === type) || {};
  return `<div class="title-loading"><div class="title-loading-art">${seed.poster ? `<img src="${esc(seed.poster)}" alt="">` : ''}</div><div><p class="eyebrow">${type === 'show' ? 'TV SHOW' : type === 'episode' ? 'EPISODE' : 'MOVIE'}</p><h2 id="title-heading">${esc(seed.title || 'Title details')}</h2><p role="status">Loading details and library availability…</p></div></div>`;
}

const preferenceBaselines = new WeakMap();
function preferenceSnapshot(card) {
  return JSON.stringify(
    [...card.querySelectorAll('input,select,textarea,[data-rating-order]')]
      .filter((input) => input.type !== 'checkbox' || input.checked)
      .map((input) => [
        input.id || input.name || JSON.stringify(input.dataset),
        input.type === 'checkbox' ? true : (input.value ?? input.dataset.ratingOrder),
      ])
  );
}
function rememberPreference(card) {
  if (card && !preferenceBaselines.has(card))
    preferenceBaselines.set(card, preferenceSnapshot(card));
}
function markPreference(card) {
  if (card) card.dataset.dirty = String(preferenceBaselines.get(card) !== preferenceSnapshot(card));
}
function clearSavedPreference(card) {
  if (card) {
    card.dataset.dirty = 'false';
    preferenceBaselines.set(card, preferenceSnapshot(card));
  }
}
const apiBeforePreferenceState = api;
api = async function (path, body) {
  const card = document.activeElement?.closest?.('.connection'),
    form = document.activeElement?.closest?.('#settings-form');
  const result = await apiBeforePreferenceState(path, body);
  if (path === 'companion/inbox' && result.items) window.updateWorkspaceInbox?.(result.items);
  if (
    [
      'companion/recipe-save',
      'companion/recipe-delete',
      'companion/follow',
      'companion/unfollow',
      'companion/preferences',
      'companion/reset-insights',
    ].includes(path)
  )
    workbenchLoaded = false;
  if (
    [
      'settings',
      'ratings/preferences',
      'explore/preferences',
      'requests/policy-save',
      'notifications/save',
      'companion/preferences',
    ].includes(path)
  ) {
    clearSavedPreference(card);
    if (path === 'settings' && form) form.dataset.dirty = 'false';
  }
  if (path.startsWith('requests/') && Array.isArray(result.items) && titleWorkspaceContext?.state) {
    const item = titleWorkspaceContext.item;
    const row = result.items.find(
      (row) =>
        row.item.type === item.type &&
        String(row.item.tmdb || row.item.show_tmdb) === String(item.tmdb || item.show_tmdb) &&
        String(row.item.season ?? '') === String(item.season ?? '') &&
        String(row.item.episode ?? '') === String(item.episode ?? '') &&
        !['cancelled', 'declined'].includes(row.status)
    );
    if (row) {
      titleWorkspaceContext.state.request = row;
      if (row.status === 'available') titleWorkspaceContext.state.ownership = 'available';
      syncTitleActions();
    }
  }
  return result;
};
let shelfReturnScroll = 0,
  projectsReturnScroll = 0;
const panelBeforeShelfReturn = openWorkspacePanel;
openWorkspacePanel = function (id) {
  if (workspacePanel === 'trakt-explore' && shelfContext && !$('explore-shelf-page').hidden)
    shelfReturnScroll = window.scrollY || 0;
  if (workspacePanel === 'discovery-dialog') projectsReturnScroll = window.scrollY || 0;
  panelBeforeShelfReturn(id);
  refreshTonightControls();
};
const openShelfBeforePreserve = openExploreShelf;
openExploreShelf = async function (id, name) {
  if (shelfContext?.id === id && $('explore-shelf-items').children?.length) {
    $('explore-extra-rows').hidden = true;
    $('explore-home-rows').hidden = true;
    $('explore-shelf-page').hidden = false;
    scrollWorkspace(shelfReturnScroll);
    return;
  }
  return openShelfBeforePreserve(id, name);
};
const drawPathBeforeSummary = drawPathRows;
drawPathRows = function () {
  drawPathBeforeSummary();
  if ($('path-edit-summary'))
    $('path-edit-summary').textContent =
      `${pathRows.filter((row) => row.included).length} included · ${pathRows.length} total. Changes apply to this path only when you save.`;
};
const projectViews = new Map(),
  openProjectsBeforeCache = openDiscovery;
openDiscovery = async function (kind, identifier) {
  if (discoveryContext) {
    const key = discoveryContext.kind + ':' + discoveryContext.identifier;
    projectViews.set(key, {
      data: discoveryContext.data,
      sort: $('discovery-sort').value,
      search: $('discovery-search').value,
      type: $('discovery-type').value,
      selected: [...discoverySelected],
      scroll: workspacePanel === 'discovery-dialog' ? window.scrollY || 0 : projectsReturnScroll,
      time: Date.now(),
    });
    if (projectViews.size > 12) projectViews.delete(projectViews.keys().next().value);
  }
  const cached = projectViews.get(kind + ':' + identifier);
  if (!cached || Date.now() - cached.time > 600000)
    return openProjectsBeforeCache(kind, identifier);
  discoveryReturnPage = captureBrowsePage();
  ++discoverySequence;
  discoveryContext = { kind, identifier, data: cached.data };
  discoverySelected = new Set(cached.selected);
  $('discovery-sort').value = cached.sort;
  $('discovery-search').value = cached.search;
  $('discovery-type').value = cached.type;
  openWorkspacePanel('discovery-dialog');
  $('discovery-title').textContent = cached.data.profile ? 'Filmography' : cached.data.name;
  $('discovery-note').textContent = cached.data.note;
  renderPersonProfile(cached.data);
  drawDiscovery();
  $('breadcrumb').textContent = cached.data.name;
  scrollWorkspace(cached.scroll);
};

// DOM rearrangement preserves control identities and their existing review handlers.
if (typeof document.createElement === 'function') {
  const details = $('list-detail'),
    identity = details.querySelector('.list-identity'),
    tools = details.querySelector('.list-detail-tools');
  identity.after(tools);
  const menu = details.querySelector('.list-tools-menu>div');
  const maintenance = document.createElement('div');
  maintenance.className = 'list-maintenance';
  maintenance.append(
    details.querySelector('.list-tools'),
    details.querySelector('.library-summary'),
    $('metadata-health')
  );
  menu.append(maintenance);
  const source = document.createElement('details');
  source.className = 'list-source-details';
  source.innerHTML = '<summary>List updates, source & watched progress</summary>';
  source.append($('trakt-saved-info'), $('list-updates'));
  tools.after(source);
  const display = details.querySelector('.list-display-options');
  details.querySelector('.toolbar>div:last-child').append(display);
  const sortStatus = $('sort-progress');
  const hideDefaultSortNote = () => {
    sortStatus.hidden =
      !sortStatus.textContent ||
      sortStatus.textContent.startsWith('Sorting changes this view only.');
  };
  new MutationObserver(hideDefaultSortNote).observe(sortStatus, { childList: true, subtree: true });
  hideDefaultSortNote();
  const switcher = details.querySelector('.workspace-switch');
  const switchDetails = document.createElement('details');
  switchDetails.className = 'list-switcher';
  switchDetails.innerHTML = '<summary>Switch collection</summary>';
  switcher.replaceWith(switchDetails);
  switchDetails.append(switcher);
  $('import-open').className = 'secondary';
  const work = $('explore-workbench'),
    chooser = document.createElement('div');
  chooser.id = 'workbench-chooser';
  chooser.className = 'workbench-chooser';
  chooser.setAttribute('aria-label', 'Choose a task');
  const workHeading = work.querySelector('.workbench-heading');
  workHeading.after(chooser);
  const picker = document.createElement('details');
  picker.id = 'workbench-picker';
  picker.open = true;
  picker.innerHTML = '<summary>Choose or change your task</summary>';
  chooser.before(picker);
  picker.append(chooser);
  const currentHeading = document.createElement('h3');
  currentHeading.id = 'workbench-current-title';
  picker.after(currentHeading);
  const toolLabel = $('workbench-tool').closest('label');
  toolLabel.hidden = true;
  const shortlistTray = document.createElement('div');
  shortlistTray.id = 'tonight-shortlist-tray';
  shortlistTray.className = 'tonight-shortlist-tray';
  shortlistTray.hidden = true;
  shortlistTray.setAttribute('aria-label', 'Tonight shortlist');
  shortlistTray.innerHTML =
    '<span></span><button class="secondary" data-work-action="shortlist">View shortlist</button><button class="primary" data-work-action="choose">Choose a finalist</button><button class="text-action" data-work-action="shortlist-clear">Clear</button>';
  $('workbench-results').after(shortlistTray);
  chooser.onclick = (event) => {
    const button = event.target.closest('[data-work-tool]');
    if (button) showTool(button.dataset.workTool);
  };
  $('builder-rows').addEventListener(
    'toggle',
    (event) => {
      if (event.target.matches('.builder-correction')) {
        const row =
          builderRows[Number(event.target.closest('[data-builder-row]').dataset.builderRow)];
        if (row) row.expanded = event.target.open;
      }
    },
    true
  );
  // Less common source-format controls and prose belong to help, not the default path.
  const advanced = document.createElement('details');
  advanced.className = 'builder-source-options';
  advanced.innerHTML = '<summary>TV numbering & source options</summary>';
  const sourceFields = $('builder-input').querySelector('.builder-fields');
  sourceFields.before(advanced);
  advanced.append(sourceFields, $('builder-dragon-options'));
  const sourceHelp = $('builder-input').querySelector(':scope>p.muted');
  if (sourceHelp) {
    const help = document.createElement('details');
    help.className = 'builder-help';
    help.innerHTML = '<summary>Supported formats & import help</summary>';
    sourceHelp.before(help);
    help.append(sourceHelp);
  }
  const steps = document.createElement('ol');
  steps.className = 'builder-steps';
  steps.setAttribute('aria-label', 'Build steps');
  steps.innerHTML =
    '<li>1. Source & text</li><li>2. Match & review</li><li>3. Save confirmed list</li>';
  $('list-builder').querySelector('.section-heading').after(steps);
  const builderMeta = document.createElement('div');
  builderMeta.className = 'builder-list-meta';
  steps.after(builderMeta);
  builderMeta.append(
    $('builder-name').closest('label'),
    $('builder-destination').closest('label'),
    $('builder-update-options')
  );
  const reviewHelp = $('builder-review').querySelector(':scope>p.muted');
  if (reviewHelp) {
    const help = document.createElement('details');
    help.className = 'builder-help';
    help.innerHTML = '<summary>How confirmations work</summary>';
    reviewHelp.before(help);
    help.append(reviewHelp);
  }
  const updateSheetOptions = () => {
    const label = $('builder-sheet-scope').closest('label');
    if (label) label.hidden = !/docs\.google\.com\/spreadsheets/i.test($('builder-url').value);
  };
  $('builder-url').addEventListener('input', updateSheetOptions);
  $('list-builder').addEventListener('toggle', updateSheetOptions);
  updateSheetOptions();
  $('builder-match-all').className = 'primary';
  const pathDialog = document.createElement('dialog');
  pathDialog.id = 'path-editor-dialog';
  pathDialog.setAttribute('aria-label', 'Watch-order path and episode editor');
  document.body.append(pathDialog);
  pathDialog.append($('list-path-workbench'));
  const pathSummary = document.createElement('p');
  pathSummary.id = 'path-edit-summary';
  pathSummary.className = 'muted';
  pathSummary.setAttribute('role', 'status');
  $('list-path-entries').before(pathSummary);
  const pathObserver = new MutationObserver(() => {
    if (!$('list-path-workbench').hidden && !pathDialog.open) pathDialog.showModal();
    else if ($('list-path-workbench').hidden && pathDialog.open) pathDialog.close();
  });
  pathObserver.observe($('list-path-workbench'), { attributes: true, attributeFilter: ['hidden'] });
  pathDialog.addEventListener('close', () => {
    if (!$('list-path-workbench').hidden) $('list-path-close').click();
  });
  document.addEventListener('click', (event) => {
    if (event.target.closest('.skip-link')) {
      event.preventDefault();
      $('main-content').focus();
      return;
    }
    const request = event.target.closest('[data-title-request]');
    if (request && titleWorkspaceContext)
      task(request, () => openRequestFor(titleWorkspaceContext.item, request.dataset.titleRequest));
    if (event.target.closest('[data-title-progress]')) {
      openRequests();
      $('requests-search').value = titleWorkspaceContext?.item.title || '';
      drawRequests();
    }
    if (event.target.closest('[data-title-check]') && titleWorkspaceContext)
      renderTitle(titleWorkspaceContext.item, titleWorkspaceContext.metadata);
    const retryItem = event.target.closest('[data-title-retry-item]');
    if (retryItem) openTitle(retryItem.dataset.titleRetryItem);
    if (event.target.closest('[data-title-retry-external]') && externalTitle)
      openExternalTitle(
        externalTitle.type,
        externalTitle.tmdb,
        externalTitle.season,
        externalTitle.episode
      );
    if (event.target.closest('[data-view-seasons]'))
      $('title-coverage-slot').scrollIntoView?.({ block: 'start', behavior: 'smooth' });
    const scope = event.target.closest('[data-external-scope]');
    if (scope && titleWorkspaceContext)
      task(scope, () =>
        openRequestFor({
          ...titleWorkspaceContext.item,
          type: scope.dataset.externalScope,
          show_tmdb: titleWorkspaceContext.item.tmdb,
          season: scope.dataset.season,
        })
      );
    const neighbor = event.target.closest('[data-episode-neighbor]');
    if (neighbor)
      openExternalTitle(
        'episode',
        neighbor.dataset.episodeNeighbor,
        neighbor.dataset.season,
        neighbor.dataset.episode
      );
    if (event.target.closest('#list-watch-paths,#list-episode-orders')) {
      const editions = event.target.closest('#list-episode-orders');
      $('list-path-workbench').querySelector('h2').textContent = editions
        ? 'Episode order & editions'
        : 'Watch-order paths';
      pathSummary.hidden = Boolean(editions);
    }
    if (event.target.closest('[data-reset-list-filters]')) {
      $('search').value = '';
      $('year-from').value = '';
      $('year-to').value = '';
      document.querySelector('[data-filter="all"]')?.click();
      render();
    }
    const inboxItem = event.target.closest('[data-inbox-open]');
    if (inboxItem) {
      const row = workbenchItems.find((item) => item.id === inboxItem.dataset.inboxOpen);
      if (row?.item) openExternalTitle(row.item.type, row.item.tmdb);
      else if (row?.category === 'requests') openRequests();
      else if (row?.category === 'releases') {
        traktOpen();
        selectExploreTab('watchlist');
      } else if (row?.category === 'lists') {
        settingsView(false);
        selectListsTab('official');
        loadCollectionUpdates();
      }
    }
    const clearCatalogue = event.target.closest('[data-clear-catalogue]');
    if (clearCatalogue) {
      $(clearCatalogue.dataset.clearCatalogue).value = '';
      clearCatalogue.dataset.clearCatalogue === 'my-list-search'
        ? drawListCatalogue()
        : drawOfficialCatalogue();
    }
  });
  const updater = $('catalogue-source-panel');
  updater.querySelector('summary').textContent = 'Advanced: catalogue source & file import';
  const check = document.createElement('button');
  check.id = 'catalogue-check-now';
  check.type = 'button';
  check.className = 'primary';
  check.textContent = 'Check for catalogue updates';
  updater.before(check);
  check.onclick = (event) =>
    task(event.target, async () => {
      const data = await api('explore/official/feed-source', {});
      if (!data.url) {
        updater.open = true;
        $('catalogue-feed-status').textContent =
          'No update source is configured yet. Add the publisher’s catalogue link below, or import a catalogue file.';
        $('catalogue-source-url').focus();
        return;
      }
      $('catalogue-source-url').value = data.url;
      await previewCatalogue(false);
      updater.open = true;
    });
  const ignoredSearch = document.createElement('input');
  ignoredSearch.type = 'search';
  ignoredSearch.placeholder = 'Search ignored titles';
  ignoredSearch.setAttribute('aria-label', 'Search ignored titles');
  $('ignored-items').before(ignoredSearch);
  ignoredSearch.oninput = () => {
    for (const row of $('ignored-items').children)
      row.hidden = !row.textContent.toLowerCase().includes(ignoredSearch.value.toLowerCase());
  };
  const requestsPage = $('requests-page'),
    queue = document.createElement('section');
  queue.id = 'request-queue-panel';
  queue.setAttribute('role', 'tabpanel');
  queue.setAttribute('aria-labelledby', 'request-requests-tab');
  const requestsHeading = requestsPage.querySelector('.workspace-heading');
  for (const child of [...requestsPage.children])
    if (child !== requestsHeading) queue.append(child);
  requestsPage.append(queue);
  const requestTabs = document.createElement('div');
  requestTabs.className = 'workspace-tabs';
  requestTabs.setAttribute('role', 'tablist');
  requestTabs.setAttribute('aria-label', 'Request activity');
  requestTabs.innerHTML =
    '<button id="request-requests-tab" role="tab" aria-controls="request-queue-panel" aria-selected="true" data-request-section="requests">Requests</button><button id="request-downloads-tab" role="tab" aria-controls="activity-panel" aria-selected="false" tabindex="-1" data-request-section="downloads">Download progress</button>';
  requestsHeading.after(requestTabs);
  requestsPage.append($('activity-panel'));
  $('activity-panel').setAttribute('role', 'tabpanel');
  $('activity-panel').setAttribute('aria-labelledby', 'request-downloads-tab');
  requestTabs.onclick = (event) => {
    const button = event.target.closest('[data-request-section]');
    if (!button) return;
    if (button.dataset.requestSection === 'downloads') openRequestDownloads();
    else selectRequestSection('requests');
  };
  requestTabs.onkeydown = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const target =
      event.key === 'Home'
        ? 'requests'
        : event.key === 'End'
          ? 'downloads'
          : requestSection === 'requests'
            ? 'downloads'
            : 'requests';
    if (target === 'downloads') openRequestDownloads();
    else selectRequestSection('requests');
    requestTabs.querySelector(`[data-request-section="${target}"]`).focus();
  };
  const listsBeforeActivity = selectListsTab;
  selectListsTab = function (name) {
    listsBeforeActivity(name);
    if (name === 'downloads') openRequestDownloads();
  };
  $('requests-nav').onclick = openRequests;
  for (const [id, container, draw] of [
    ['my-list-search', 'list-catalogue', drawListCatalogue],
    ['official-list-search', 'lists-official', drawOfficialCatalogue],
  ]) {
    const input = document.createElement('input');
    input.id = id;
    input.type = 'search';
    input.placeholder = 'Find a collection';
    input.setAttribute(
      'aria-label',
      id === 'my-list-search' ? 'Find my list' : 'Find official list'
    );
    $(container).querySelector('.catalogue-sort').prepend(input);
    input.oninput = draw;
  }
  const mobileExploreActions = document.createElement('div');
  mobileExploreActions.className = 'explore-mobile-actions';
  mobileExploreActions.innerHTML =
    '<button type="button" class="secondary" data-settings-open="preferences">Language &amp; release settings</button><button type="button" class="secondary" data-mobile-explore-refresh>Refresh from Plex</button>';
  document.querySelector('.explore-filter-options>div').append(mobileExploreActions);
  mobileExploreActions.querySelector('[data-mobile-explore-refresh]').onclick = () =>
    $('explore-refresh').click();
  const tonightShortcut = document.createElement('button');
  tonightShortcut.id = 'tonight-shortcut';
  tonightShortcut.type = 'button';
  tonightShortcut.className = 'secondary';
  tonightShortcut.textContent = 'Watching now? Pick from Plex';
  tonightShortcut.onclick = () => {
    traktOpen();
    selectExploreTab('workbench');
    showTool('tonight');
  };
  $('trakt-upcoming').before(tonightShortcut);
  $('release-watch-check').after($('trakt-upcoming'));
  const oldWorkAction = workAction;
  workAction = async function (action) {
    await oldWorkAction(action);
    if (['discover', 'blindspots'].includes(action)) {
      const save = document.querySelector('[data-work-action="recipe-save"]');
      if (save) save.hidden = false;
      const name = $('work-name').closest('label');
      if (name) name.hidden = false;
    }
    refreshTonightControls();
    if (action === 'inbox') {
      const read = document.querySelector('[data-work-action="inbox-read"]');
      if (read) read.hidden = !workbenchItems.some((row) => !row.read);
    }
    if (action === 'tonight' || action === 'shortlist' || action === 'choose')
      $('workbench-results').scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  };
  document.addEventListener('click', (event) => {
    const add = event.target.closest('[data-shortlist-add]');
    if (add) {
      add.textContent = 'Shortlisted';
      add.disabled = true;
    }
    if (add || event.target.closest('[data-shortlist-remove]')) refreshTonightControls();
  });
  $('workbench-controls').addEventListener('change', (event) => {
    if (event.target.id === 'work-recipe') {
      const remove = document.querySelector('[data-work-action="recipe-delete"]');
      if (remove) remove.hidden = !event.target.value;
      const name = $('work-name').closest('label');
      if (name) name.hidden = !event.target.value;
    }
  });
  $('settings').addEventListener('focusin', (event) => {
    rememberPreference(event.target.closest('.connection'));
    rememberPreference(event.target.closest('#settings-form'));
  });
  document.addEventListener('input', (event) => {
    if (
      !$('settings').contains(event.target) ||
      ['release-region', 'spoiler-safe', 'settings-entry-size'].includes(event.target.id)
    )
      return;
    markPreference(event.target.closest('.connection'));
    markPreference(event.target.closest('#settings-form'));
  });
  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-rating-move]'))
      markPreference(event.target.closest('.connection'));
  });
  const connectionsBeforeBaselines = renderArr;
  renderArr = function () {
    connectionsBeforeBaselines();
    document
      .querySelectorAll('#settings .connection')
      .forEach((card) => clearSavedPreference(card));
    clearSavedPreference($('settings-form'));
  };
  const settingsSubmit = $('settings-form').querySelector('[type="submit"]');
  const saveDock = document.createElement('div');
  saveDock.className = 'connection-save-dock';
  settingsSubmit.before(saveDock);
  saveDock.append(settingsSubmit);
  saveDock.insertAdjacentHTML(
    'afterbegin',
    '<span class="connection-dirty-label">Connection changes are not saved yet.</span>'
  );
  const requestOptions = document.createElement('details');
  requestOptions.className = 'request-download-options';
  requestOptions.innerHTML = '<summary>Download options · tier, manager and monitoring</summary>';
  $('request-new-selection').before(requestOptions);
  for (const id of [
    'request-new-tier',
    'request-new-route',
    'request-new-mode',
    'request-new-queue',
  ])
    requestOptions.append($(id).closest('label'));
  const scopeChange = $('request-new-scope').onchange;
  $('request-new-scope').onchange = () => {
    scopeChange();
    if (newRequestItem?.type === 'show') loadRequestScopes();
  };
  $('request-new-season').onchange = () => {
    drawNewRequestRoutes();
    loadRequestScopes($('request-new-season').value, '');
  };
  $('request-new-episode').onchange = drawNewRequestRoutes;
  // Keep an entry point to the complete inbox even when there are no unread notices.
  const inbox = document.querySelector('.workspace-inbox'),
    allUpdates = document.createElement('button');
  allUpdates.type = 'button';
  allUpdates.className = 'secondary';
  allUpdates.textContent = 'Open all updates';
  allUpdates.onclick = () => {
    inbox.open = false;
    traktOpen();
    selectExploreTab('workbench');
    showTool('inbox');
    workAction('inbox');
  };
  inbox.querySelector('.workspace-inbox-messages').append(allUpdates);
  inbox.hidden = false;
  const refreshInboxAvailability = () => {
    inbox.hidden = false;
  };
  new MutationObserver(refreshInboxAvailability).observe(inbox, {
    attributes: true,
    attributeFilter: ['hidden'],
  });
  const titleFocusCapture = captureBrowsePage;
  captureBrowsePage = function () {
    return { ...titleFocusCapture(), returnFocus: document.activeElement };
  };
  const titleFocusRestore = restoreBrowsePage;
  restoreBrowsePage = function (page) {
    titleFocusRestore(page);
    if (page.returnFocus?.isConnected) page.returnFocus.focus({ preventScroll: true });
  };
  const listMenu = document.querySelector('.list-tools-menu>div');
  listMenu.prepend($('list-add-entries'));
  listMenu.prepend($('list-manage'));
  renderListIdentity();
  drawWorkChooser();
  const readyBeforeAuditInbox = window.onListweavarrReady;
  window.onListweavarrReady = () => {
    readyBeforeAuditInbox?.();
    api('companion/inbox', {}).catch(() => {});
    window.refreshExploreHeading();
  };
}
