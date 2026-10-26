// SPDX-License-Identifier: AGPL-3.0-only
function priorityCards(rows) {
  return (
    '<div class="priority-cards">' +
    rows
      .map(
        (row) =>
          `<article class="priority-card"><button class="priority-art" data-work-list="${esc(row.list_id)}" aria-label="Review ${esc(row.title)}">${row.poster ? `<img src="${esc(row.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<span>${esc(row.title.charAt(0))}</span>`}</button><div><p class="eyebrow">${esc(row.list_name)}</p><h3>${esc(row.title)}</h3><p class="muted">${esc(row.overview || 'Review this gap in its saved watch order.')}</p><p class="priority-reason">${esc(row.reasons.join(' / '))}</p><button class="secondary" data-work-list="${esc(row.list_id)}">Review list</button></div></article>`
      )
      .join('') +
    '</div>'
  );
}
function followedCreatorsMarkup(people) {
  return (
    '<h3>Following</h3>' +
    (people
      .map(
        (person) =>
          `<article class="creator-identity"><div class="creator-portrait">${person.profile_path ? `<img src="https://image.tmdb.org/t/p/w185${esc(person.profile_path)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span>No photo</span>'}</div><div><a class="title-link" href="#/projects/person/${esc(person.id)}" data-person-link="${esc(person.id)}">${esc(person.name)}</a><p>${esc({ all: 'All credits', cast: 'Actor / cast', crew: 'Director / crew' }[person.role] || person.role)} - TMDB ${esc(person.id)}</p><label>Follow credits<select data-work-follow-role="${esc(person.id)}">${[
            ['cast', 'Actor / cast'],
            ['crew', 'Director / crew'],
            ['all', 'All credits'],
          ]
            .map(
              ([value, label]) =>
                `<option value="${value}" ${person.role === value ? 'selected' : ''}>${label}</option>`
            )
            .join(
              ''
            )}</select></label></div><button class="secondary" data-work-unfollow="${esc(person.id)}">Unfollow</button></article>`
      )
      .join('') || '<p class="muted">No followed people yet.</p>')
  );
}
/* Larger workflows live here instead of growing the Discover toolbar. */
let workbenchState = {},
  workbenchLoaded = false,
  workbenchSequence = 0,
  workbenchItems = [],
  shortlist = new Map(),
  pathEditor = null,
  editionGroups = [];
const selectExploreBeforeWorkbench = selectExploreTab;
selectExploreTab = function (name) {
  if (name !== 'workbench') return selectExploreBeforeWorkbench(name);
  exploreTab = name;
  setTabGroup('data-explore-tab', name, (key) => 'explore-' + key);
  $('trakt-preview').hidden = true;
  $('trakt-calendar').hidden = true;
  $('breadcrumb').textContent = 'EXPLORE / WORKBENCH';
  loadWorkbench();
};
bindTabKeys('data-explore-tab', selectExploreTab);
function workInput(label, id, value = '', type = 'text') {
  return `<label>${label}<input id="${id}" type="${type}" value="${esc(value)}"></label>`;
}
function workButton(action, label, primary = false) {
  return `<button class="${primary ? 'primary' : 'secondary'}" data-work-action="${action}">${label}</button>`;
}
function workTitle(item) {
  return `<button class="title-link" data-work-title="${esc(item.tmdb || '')}" data-work-type="${esc(item.type)}" data-work-season="${esc(item.season || '')}" data-work-episode="${esc(item.episode || '')}">${state.companion_preferences?.spoiler_safe && item.type === 'episode' ? 'Episode details' : esc(item.title)}</button>`;
}
async function loadWorkbench() {
  if (workbenchLoaded) {
    drawWorkChooser();
    return;
  }
  const seq = ++workbenchSequence;
  $('workbench-status').textContent = '';
  $('workbench-results').innerHTML = '';
  try {
    workbenchState = await api('companion/state', {});
    if (seq !== workbenchSequence) return;
    workbenchLoaded = true;
    drawWorkbench();
  } catch (e) {
    $('workbench-status').textContent = e.message;
  }
}
function drawWorkbench() {
  const tool = $('workbench-tool').value || 'recipes';
  let html = '';
  if (tool === 'recipes')
    html = `<p class="muted">Combine genres, exact theme tags, runtime and years. The discovery dial adjusts familiarity within the returned pool.</p><div class="workbench-form"><label>Saved recipe<select id="work-recipe"><option value="">New recipe</option>${(workbenchState.discovery_recipes || []).map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('')}</select></label>${workInput('Recipe name', 'work-name', 'My discovery recipe')}<label>Content<select id="work-type"><option value="movie">Movies</option><option value="show">TV</option></select></label><label>Genres (any selected)<select id="work-genres" multiple size="4"></select></label>${workInput('Theme tags, separated by commas', 'work-tags')}${workInput('Maximum minutes (per TV episode)', 'work-minutes', 120, 'number')}${workInput('From year', 'work-year-from', 1980, 'number')}${workInput('Through year', 'work-year-to', new Date().getFullYear(), 'number')}<label>Rating<select id="work-rating">${[5, 6, 7, 8, 9].map((n) => `<option ${n === 6 ? 'selected' : ''}>${n}</option>`).join('')}</select></label><label>Discovery dial<select id="work-dial"><option value="familiar">Familiar</option><option value="adventurous">Adventurous</option><option value="surprise">Surprise me</option></select></label><label>Movie release<select id="work-release"><option value="home">Digital / disc released</option><option value="any">Include theatrical releases</option></select></label><label>Availability<select id="work-availability"><option value="missing">Missing from Plex</option><option value="all">All titles</option></select></label></div><div class="workbench-actions">${workButton('discover', 'Find titles', true)}${workButton('blindspots', 'Explore my blind spots')}${workButton('recipe-save', 'Save recipe')}${workButton('recipe-delete', 'Delete recipe')}</div>`;
  if (tool === 'tonight')
    html = `<p class="muted">Pick something already available in Plex. Choose a single movie, one episode or a connected multi-watch session that fits your time. Movies and TV are listed separately; nothing plays automatically.</p><div class="workbench-form">${workInput('Time available (minutes)', 'work-minutes', 120, 'number')}<label>Content<select id="work-type"><option value="both">Movies &amp; TV</option><option value="movie">Movies</option><option value="show">TV</option></select></label>${workInput('Genre (optional exact name)', 'work-genre')}<label class="preference-check"><input id="work-rewatch" type="checkbox">Include watched movies</label></div><div class="workbench-actions">${workButton('tonight', 'Find tonight’s watch', true)}${workButton('shortlist', 'View shortlist')}${workButton('choose', 'Choose a finalist')}${workButton('shortlist-clear', 'Clear shortlist')}</div>`;
  if (tool === 'franchises')
    html = `<p class="muted">Find missing movies in collections represented in your Plex library. Watched collections and single-entry gaps come first. Full TV/cross-media paths live with your curated lists.</p>${workButton('franchises', 'Check franchise gaps', true)}`;
  if (tool === 'planning')
    html = `<details open><summary>What to collect next</summary><p class="muted">Prioritises the next missing entry, partially collected scopes and final list gaps. Uses your latest saved Plex comparison.</p>${workButton('priorities', 'Rank missing content')}</details><details><summary>Storage estimate</summary><p class="muted">Uses free space reported by Radarr/Sonarr and a size range you enter. A quality profile does not guarantee file size.</p><div class="workbench-form"><label>Manager<select id="work-service"><option value="radarr">Radarr</option><option value="sonarr">Sonarr</option></select></label><label>Instance<select id="work-route">${(workbenchState.manager_routes?.radarr || []).map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('')}</select></label><label>Destination<select id="work-root"></select></label><label>Quality profile<select id="work-profile"></select></label>${workInput('Number of movies or episodes', 'work-count', 1, 'number')}${workInput('Low GiB per item', 'work-low', 2, 'number')}${workInput('High GiB per item', 'work-high', 12, 'number')}</div><div class="workbench-actions">${workButton('storage-options', 'Load destinations')}${workButton('storage', 'Estimate storage', true)}</div></details>`;
  if (tool === 'radar')
    html = `<p class="muted">Follow creators without requesting everything they make. Checks upcoming credited projects in the next year when you click Check radar.</p><div class="workbench-form">${workInput('Person name', 'work-person-query')}<label>Credits<select id="work-person-role"><option value="cast">Actor / cast</option><option value="crew">Director / crew</option><option value="all">All credits</option></select></label></div><div class="workbench-actions">${workButton('person-search', 'Find person')}${workButton('radar', 'Check radar', true)}</div><div id="work-person-matches"></div><div class="work-following">${followedCreatorsMarkup(workbenchState.creator_follows || [])}</div>`;
  if (tool === 'inbox')
    html = `<p class="muted">Release availability, request completion, official-list versions and results from your last creator-radar check. Checks occur while you use the app.</p><div class="workbench-actions">${workButton('inbox', 'Refresh inbox', true)}${workButton('inbox-read', 'Mark visible items read')}</div><details><summary>Notification categories</summary>${['releases', 'requests', 'lists', 'creators'].map((c) => `<label class="preference-check"><input type="checkbox" data-inbox-category="${c}" ${!(workbenchState.companion_preferences?.muted_inbox || []).includes(c) ? 'checked' : ''}>${c}</label>`).join('')}${workButton('inbox-settings', 'Save categories')}</details>`;
  if (tool === 'insights')
    html = `<p class="muted">Compare locally logged recommendations with requests, Plex watch status and explicit feedback. These are correlations, not success guarantees.</p><label class="preference-check"><input id="work-log" type="checkbox" ${workbenchState.companion_preferences?.log_recommendations ? 'checked' : ''}>Record displayed recommendations locally (up to 2,000 titles)</label><div class="workbench-actions">${workButton('insight-settings', 'Save logging preference')}${workButton('insights', 'View feedback report', true)}</div><details><summary>Reset influences</summary><p class="muted">Clear recommendation history. Optionally clear explicit taste feedback too; Plex watch history and ratings remain unchanged.</p><label class="preference-check"><input id="work-reset-taste" type="checkbox">Also clear local taste feedback</label><label class="preference-check"><input id="work-reset-confirm" type="checkbox">I want to reset the selected local history</label>${workButton('reset-insights', 'Reset selected history')}</details>`;
  $('workbench-controls').innerHTML = html;
  $('workbench-save-picks').hidden = !['recipes', 'franchises', 'radar'].includes(tool);
  exploreSelection();
  if (tool === 'recipes') loadWorkGenres();
}
async function loadWorkGenres(selected = []) {
  const kind = $('work-type').value || 'movie';
  try {
    const data = await api('companion/genres', { type: kind });
    if (($('workbench-tool').value || 'recipes') !== 'recipes' || $('work-type').value !== kind)
      return;
    $('work-genres').innerHTML = data.items
      .map(
        (g) =>
          `<option value="${g.id}" ${selected.includes(String(g.id)) ? 'selected' : ''}>${esc(g.name)}</option>`
      )
      .join('');
    window.paintGenreChoices?.();
  } catch (e) {
    $('workbench-status').textContent = e.message;
  }
}
function recipeBody() {
  return {
    id: $('work-recipe').value || undefined,
    name: $('work-name').value,
    type: $('work-type').value,
    genres: [...$('work-genres').selectedOptions].map((o) => o.value),
    tags: $('work-tags').value,
    minutes: $('work-minutes').value,
    year_from: $('work-year-from').value,
    year_to: $('work-year-to').value,
    rating: $('work-rating').value,
    dial: $('work-dial').value,
    availability: $('work-availability').value,
    release: $('work-release').value,
  };
}
function workCards(items) {
  exploreRows.push(...items);
  return `<div class="explore-browse-grid">${items.map(exploreTitleCard).join('')}</div>`;
}
function tonightRows(items) {
  return items
    .map(
      (r, i) =>
        `<article class="work-result-row"><div class="tonight-title">${r.poster ? `<img src="${esc(r.poster)}" alt="" loading="lazy">` : ''}<div>${r.tmdb ? workTitle(r) : `<b>${esc(r.title)}</b>`}<p>${Math.round(r.runtime)} min / ${esc(r.reason || 'Shortlisted')}</p></div></div><div><button class="secondary" data-shortlist-add="${i}">Shortlist</button><button class="text-action" data-shortlist-remove="${esc(r.key)}">Eliminate</button></div></article>`
    )
    .join('');
}
$('workbench-tool').onchange = () => {
  ++workbenchSequence;
  $('workbench-status').textContent = '';
  $('workbench-results').innerHTML = '';
  drawWorkbench();
};
$('workbench-controls').onchange = (e) => {
  if (e.target.id === 'work-service') {
    $('work-route').innerHTML = (workbenchState.manager_routes?.[e.target.value] || [])
      .map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`)
      .join('');
    $('work-root').innerHTML = '';
    $('work-profile').innerHTML = '';
  }
  if (e.target.id === 'work-type' && $('workbench-tool').value === 'recipes') loadWorkGenres();
  if (e.target.id === 'work-recipe') {
    const recipe = (workbenchState.discovery_recipes || []).find((r) => r.id === e.target.value);
    if (!recipe) return;
    for (const [field, id] of Object.entries({
      name: 'work-name',
      type: 'work-type',
      tags: 'work-tags',
      minutes: 'work-minutes',
      year_from: 'work-year-from',
      year_to: 'work-year-to',
      rating: 'work-rating',
      dial: 'work-dial',
      availability: 'work-availability',
      release: 'work-release',
    }))
      $(id).value = recipe[field];
    loadWorkGenres(recipe.genres);
  }
};
async function workAction(action) {
  const seq = workbenchSequence;
  let data,
    html = '';
  $('workbench-status').textContent = 'Working...';
  if (action === 'recipe-save') {
    await api('companion/recipe-save', recipeBody());
    await loadWorkbench();
    $('workbench-status').textContent = 'Recipe saved.';
    return;
  }
  if (action === 'recipe-delete') {
    if (!$('work-recipe').value) throw Error('Choose a saved recipe.');
    await api('companion/recipe-delete', { id: $('work-recipe').value });
    return loadWorkbench();
  }
  if (action === 'discover' || action === 'blindspots') {
    data = await api(
      'companion/' + (action === 'discover' ? 'recipes' : 'blindspots'),
      recipeBody()
    );
    html = workCards(data.items);
  }
  if (action === 'tonight') {
    data = await api('companion/tonight', {
      minutes: $('work-minutes').value,
      type: $('work-type').value,
      genre: $('work-genre').value,
      rewatch: $('work-rewatch').checked,
    });
    workbenchItems = data.items;
    html = typeof tonightResults === 'function' ? tonightResults(data) : tonightRows(data.items);
  }
  if (action === 'shortlist') {
    workbenchItems = [...shortlist.values()];
    html = tonightRows(workbenchItems);
  }
  if (action === 'shortlist-clear') {
    shortlist.clear();
    workbenchItems = [];
    html = '<p class="muted">Shortlist cleared.</p>';
  }
  if (action === 'choose') {
    if (!shortlist.size) throw Error('Shortlist some titles first.');
    const items = [...shortlist.values()];
    workbenchItems = [items[Math.floor(Math.random() * items.length)]];
    html = '<h3>Tonight’s finalist</h3>' + tonightRows(workbenchItems);
  }
  if (action === 'franchises') {
    data = await api('companion/franchises', {});
    html =
      data.groups
        .filter((group) => group.missing > 0)
        .map(
          (group) =>
            `<section class="relationship-block"><h3>${esc(group.name)} / ${group.missing} released titles missing</h3><p class="muted">${group.items.filter((item) => item.in_library).length} already in Plex. Missing released titles are shown first.</p>${workCards(group.items.filter((item) => !item.in_library).sort((a, b) => Number(a.upcoming) - Number(b.upcoming)))}</section>`
        )
        .join('') ||
      '<div class="empty"><h3>No released gaps found in the sampled collections.</h3><p>Check your curated lists for broader TV and shared-universe coverage.</p></div>';
  }
  if (action === 'priorities') {
    data = await api('companion/priorities', {});
    html = priorityCards(data.items);
  }
  if (action === 'storage-options' || action === 'storage') {
    const body = {
      service: $('work-service').value,
      route: $('work-route').value,
      root: action === 'storage' ? $('work-root').value : '',
      profile: $('work-profile').value,
      count: $('work-count').value,
      low_gb: $('work-low').value,
      high_gb: $('work-high').value,
    };
    data = await api('companion/storage', body);
    if (data.roots) {
      $('work-root').innerHTML = data.roots.map((r) => `<option>${esc(r.path)}</option>`).join('');
      $('work-profile').innerHTML = data.profiles
        .map((r) => `<option value="${r.id}">${esc(r.name)}</option>`)
        .join('');
      html = '<p>Choose a destination/profile and enter the size range, then estimate.</p>';
    } else
      html = `<h3>${data.low_gb.toFixed(1)}–${data.high_gb.toFixed(1)} GiB estimated</h3><p>${data.free_gb == null ? 'Free space unknown' : data.free_gb.toFixed(1) + ' GiB reported free'} / ${data.fits == null ? 'Cannot determine fit' : data.fits ? 'Upper estimate fits' : 'Upper estimate exceeds free space'}</p>`;
  }
  if (action === 'person-search') {
    data = await api('companion/person-search', { query: $('work-person-query').value });
    $('work-person-matches').innerHTML = personSearchMarkup(data.items);
    $('workbench-status').textContent = 'Choose the correct person. Only public metadata is used.';
    return;
  }
  if (action === 'radar') {
    data = await api('companion/radar', {});
    html = workCards(data.items.map((r) => r.item));
  }
  if (action === 'inbox') {
    data = await api('companion/inbox', {});
    workbenchItems = data.items;
    html = notificationInboxMarkup(data.items);
  }
  if (action === 'inbox-read') {
    await api('companion/inbox-read', { ids: workbenchItems.map((r) => r.id) });
    return workAction('inbox');
  }
  if (action === 'inbox-settings') {
    await api('companion/preferences', {
      muted_inbox: [...document.querySelectorAll('[data-inbox-category]')]
        .filter((i) => !i.checked)
        .map((i) => i.dataset.inboxCategory),
    });
    return loadWorkbench();
  }
  if (action === 'insight-settings') {
    await api('companion/preferences', { log_recommendations: $('work-log').checked });
    state.companion_preferences = {
      ...state.companion_preferences,
      log_recommendations: $('work-log').checked,
    };
    $('workbench-status').textContent = 'Logging preference saved.';
    return;
  }
  if (action === 'insights') {
    data = await api('companion/insights', {});
    html =
      `<div class="workbench-metrics"><div><b>${data.recommended}</b>Recommended</div><div><b>${data.requested}</b>Requested</div><div><b>${data.watched}</b>Watched in Plex</div></div><p>Local feedback: ${
        Object.entries(data.feedback)
          .map(([k, v]) => esc(k) + ': ' + v)
          .join(' / ') || 'None yet'
      }</p>` +
      data.items
        .map(
          (r) =>
            `<article class="work-result-row"><div>${workTitle(r)}<p>${r.requested ? 'Requested / ' : ''}${r.watched ? 'Watched / ' : ''}${esc(r.feedback || 'No explicit feedback')}</p></div></article>`
        )
        .join('');
  }
  if (action === 'reset-insights') {
    if (!$('work-reset-confirm').checked) throw Error('Confirm which local history to reset.');
    await api('companion/reset-insights', {
      confirmed: true,
      reset_taste: $('work-reset-taste').checked,
    });
    if ($('work-reset-taste').checked) {
      state.taste_feedback = {};
      exploreHomeLoaded = false;
    }
    return workAction('insights');
  }
  if (seq !== workbenchSequence) return;
  $('workbench-results').innerHTML = html || '<p class="muted">No matching results.</p>';
  $('workbench-status').textContent = [data?.note, ...(data?.warnings || [])]
    .filter(Boolean)
    .join(' ');
}
$('explore-workbench').onclick = (e) => {
  const action = e.target.closest('[data-work-action]'),
    title = e.target.closest('[data-work-title]'),
    list = e.target.closest('[data-work-list]'),
    follow = e.target.closest('[data-work-follow]'),
    unfollow = e.target.closest('[data-work-unfollow]'),
    add = e.target.closest('[data-shortlist-add]'),
    remove = e.target.closest('[data-shortlist-remove]'),
    exploreTitle = e.target.closest('[data-explore-title]');
  if (action)
    task(action, () =>
      workAction(action.dataset.workAction).catch(
        (error) => ($('workbench-status').textContent = error.message)
      )
    );
  if (title && title.dataset.workTitle)
    openExternalTitle(
      title.dataset.workType,
      title.dataset.workTitle,
      title.dataset.workSeason,
      title.dataset.workEpisode
    );
  if (exploreTitle) openExternalTitle(exploreTitle.dataset.type, exploreTitle.dataset.exploreTitle);
  if (list) {
    openSavedList(list.dataset.workList);
  }
  if (follow)
    task(follow, async () => {
      await api('companion/follow', {
        person: follow.dataset.workFollow,
        role: $('work-person-role').value,
      });
      loadWorkbench();
    });
  if (unfollow)
    task(unfollow, async () => {
      await api('companion/unfollow', { person: unfollow.dataset.workUnfollow });
      loadWorkbench();
    });
  if (add) {
    const row = workbenchItems[Number(add.dataset.shortlistAdd)];
    if (row) shortlist.set(row.key, row);
    toast(shortlist.size + ' titles shortlisted.');
  }
  if (remove) {
    shortlist.delete(remove.dataset.shortlistRemove);
    workbenchItems = workbenchItems.filter((r) => r.key !== remove.dataset.shortlistRemove);
    $('workbench-results').innerHTML = tonightRows(workbenchItems);
  }
};
$('explore-workbench').onchange = (e) => {
  const pick = e.target.closest('[data-explore-pick]');
  if (!pick) return;
  const row = exploreRows.find((r) => r.key === pick.dataset.explorePick);
  if (!row) return;
  if (pick.checked && explorePicks.size < 100) explorePicks.set(row.key, row);
  else {
    pick.checked = false;
    explorePicks.delete(row.key);
  }
  exploreSelection();
};

let pathRows = [],
  pathLimit = 200,
  episodeMapBody = null;
$('list-watch-paths').onclick = (e) =>
  task(e.target, async () => {
    const data = await api('companion/path-editor', { list_id: active });
    pathEditor = data;
    pathRows = data.entry.items.map((r) => ({ ...r, included: true }));
    pathLimit = 200;
    $('list-path-workbench').hidden = false;
    $('list-path-controls').innerHTML =
      `<p class="muted">Curate an essential or chronological route without changing the underlying list. Recommended, chronological and essential orders are curated by the list creator. They are included when you share or publish the list. Completionist defaults to all entries. Release defaults to known years, not exact episode air dates. Saved paths use the selection and ordering below.</p><label>Order to edit<select id="watch-path-mode"><option value="recommended">Recommended</option><option value="completionist">Completionist</option><option value="release">Release</option><option value="chronological">Chronological</option><option value="essential">Essential story</option></select></label><div class="workbench-actions">${workButton('path-load', 'Load saved order')}${workButton('path-save', 'Save this order', true)}${workButton('path-preview', 'Preview selected route')}${workButton('path-copy', 'Create list from saved path')}${workButton('path-select', 'Select all')}${workButton('path-clear', 'Clear selection')}</div>`;
    $('list-path-status').textContent = '';
    drawPathRows();
  });
function drawPathRows() {
  const view = pathRows.slice(0, pathLimit);
  $('list-path-entries').innerHTML =
    view
      .map(
        (r, i) =>
          `<div class="path-edit-row"><label><input type="checkbox" data-path-include="${i}" ${r.included ? 'checked' : ''}>${esc(r.title)} ${r.season ? ' / S' + esc(r.season) : ''}${r.episode ? ' E' + esc(r.episode) : ''}</label><button class="secondary" data-path-move="${i}" data-step="-1" aria-label="Move ${esc(r.title)} up">&#8593;</button><button class="secondary" data-path-move="${i}" data-step="1" aria-label="Move ${esc(r.title)} down">&#8595;</button></div>`
      )
      .join('') +
    (pathRows.length > pathLimit
      ? '<button class="secondary" data-path-more>Show more entries</button>'
      : '');
}
$('list-path-close').onclick = () => {
  $('list-path-workbench').hidden = true;
  pathEditor = null;
  episodeMapBody = null;
};
$('list-path-workbench').onchange = (e) => {
  if (e.target.dataset.pathInclude !== undefined)
    pathRows[Number(e.target.dataset.pathInclude)].included = e.target.checked;
};
$('list-path-workbench').onclick = (e) => {
  const move = e.target.closest('[data-path-move]'),
    more = e.target.closest('[data-path-more]'),
    action = e.target.closest('[data-work-action]');
  if (more) {
    pathLimit += 200;
    drawPathRows();
  }
  if (move) {
    const i = Number(move.dataset.pathMove),
      j = i + Number(move.dataset.step);
    if (j >= 0 && j < pathRows.length) {
      [pathRows[i], pathRows[j]] = [pathRows[j], pathRows[i]];
      drawPathRows();
    }
  }
  if (action)
    task(action, async () => {
      try {
        const name = action.dataset.workAction;
        if (name === 'path-select' || name === 'path-clear') {
          pathRows.forEach((r) => (r.included = name === 'path-select'));
          drawPathRows();
          return;
        }
        if (name === 'path-preview') {
          const selected = pathRows.filter((r) => r.included);
          $('list-path-status').textContent =
            selected.length +
            ' entries selected. Save the path, then create a separate viewing list when ready. Runtime depends on editions and available metadata.';
          $('list-path-entries').innerHTML =
            selected
              .map(
                (r, i) =>
                  `<div class="collection-health-note">${i + 1}. ${esc(r.title)} ${r.season ? 'S' + esc(r.season) : ''}${r.episode ? ' E' + esc(r.episode) : ''}</div>`
              )
              .join('') + `<button class="secondary" data-path-more>Return to editor</button>`;
          return;
        }
        if (name === 'path-load') {
          const data = await api('companion/path', {
            list_id: pathEditor.entry.id,
            mode: $('watch-path-mode').value,
          });
          const ids = new Set(data.items.map((r) => r.id));
          pathRows = [
            ...data.items.map((r) => ({ ...r, included: true })),
            ...pathEditor.entry.items
              .filter((r) => !ids.has(r.id))
              .map((r) => ({ ...r, included: false })),
          ];
          drawPathRows();
          $('list-path-status').textContent = data.note;
          return;
        }
        if (name === 'path-copy') {
          const data = await api('companion/path-copy', {
            list_id: pathEditor.entry.id,
            revision: pathEditor.revision,
            mode: $('watch-path-mode').value,
          });
          replaceList(data.entry);
          $('list-path-workbench').hidden = true;
          pathEditor = null;
          toast(
            'Path copied to a new local list. Compare it with Plex before requesting or making a playlist.'
          );
          return;
        }
        if (name === 'path-save') {
          await api('companion/path-save', {
            list_id: pathEditor.entry.id,
            revision: pathEditor.revision,
            mode: $('watch-path-mode').value,
            ids: pathRows.filter((r) => r.included).map((r) => r.id),
          });
          pathEditor = await api('companion/path-editor', { list_id: pathEditor.entry.id });
          const index = state.lists.findIndex((r) => r.id === pathEditor.entry.id);
          if (index >= 0) state.lists[index] = pathEditor.entry;
          render();
          window.refreshCuratedOrders?.();
          $('list-path-status').textContent =
            'Order saved. Viewers can select it from Watch order; share or publish an official update to include it for others.';
          return;
        }
        await episodeAction(name);
      } catch (error) {
        $('list-path-status').textContent = error.message;
      }
    });
};
$('list-episode-orders').onclick = () => {
  $('list-path-workbench').hidden = false;
  pathEditor = null;
  episodeMapBody = null;
  $('list-path-entries').innerHTML = '';
  $('list-path-status').textContent = '';
  $('list-path-controls').innerHTML =
    `<p class="muted">Choose a TMDB show, then an official provider episode-group order. Review the translated aired-season scopes before adding them. An edited dub that merges or cuts episodes is not automatically interchangeable with the uncut version.</p><div class="workbench-form">${workInput('TV show TMDB ID', 'edition-tmdb')}<label>Episode group<select id="edition-group"></select></label><label>Source block<select id="edition-block"><option value="all">Across all blocks</option></select></label>${workInput('First source position', 'edition-first', 1, 'number')}${workInput('Last source position', 'edition-last', 1, 'number')}</div><div class="workbench-actions">${workButton('edition-groups', 'Find orders')}${workButton('edition-blocks', 'Load blocks')}${workButton('edition-map', 'Preview mapping', true)}</div><label class="preference-check"><input id="edition-detach" type="checkbox">If linked, convert this list to local before adding episodes</label><label class="preference-check"><input id="edition-confirm" type="checkbox">I reviewed the mapping and want to append these episodes</label>${workButton('edition-save', 'Append reviewed mapping')}`;
};
async function episodeAction(action) {
  if (action === 'edition-groups') {
    const data = await api('companion/episode-groups', { tmdb: $('edition-tmdb').value });
    editionGroups = data.results || [];
    $('edition-group').innerHTML = editionGroups
      .map(
        (g) => `<option value="${esc(g.id)}">${esc(g.name)} / ${g.episode_count} episodes</option>`
      )
      .join('');
    $('list-path-status').textContent = editionGroups.length
      ? 'Choose an order, then load its blocks.'
      : 'No provider episode groups available. Use continuous numbering in the text builder for ordinary saga splits.';
    episodeMapBody = null;
    return;
  }
  if (action === 'edition-blocks') {
    const data = await api('companion/episode-group', { group: $('edition-group').value });
    $('edition-block').innerHTML =
      '<option value="all">Across all blocks</option>' +
      data.groups
        .sort((a, b) => a.order - b.order)
        .map(
          (g) =>
            `<option value="${esc(g.id)}">${esc(g.name)} / ${g.episodes.length} episodes</option>`
        )
        .join('');
    episodeMapBody = null;
    return;
  }
  const body = {
    tmdb: $('edition-tmdb').value,
    group: $('edition-group').value,
    block: $('edition-block').value,
    first: $('edition-first').value,
    last: $('edition-last').value,
  };
  if (action === 'edition-map') {
    const data = await api('companion/episode-map', body);
    episodeMapBody = JSON.stringify(body);
    $('list-path-entries').innerHTML = data.items
      .map(
        (r) =>
          `<div class="collection-health-note">${esc(r.show_title)} / S${r.season} E${r.episode} / ${esc(r.title)}</div>`
      )
      .join('');
    $('list-path-status').textContent = data.note;
    return;
  }
  if (action === 'edition-save') {
    if (episodeMapBody !== JSON.stringify(body) || !$('edition-confirm').checked)
      throw Error('Preview this exact range and confirm the mapping first.');
    const latest = await api('lists/revision', { list_id: active });
    const data = await api('companion/episode-map-save', {
      ...body,
      list_id: active,
      revision: latest.revision,
      confirmed: true,
      confirm_detach: $('edition-detach').checked,
    });
    replaceList(data.entry);
    $('list-path-workbench').hidden = true;
    episodeMapBody = null;
    toast(data.report.added + ' mapped episodes added.');
  }
}

let spoilerRevealed = new Set();
const titleBeforeSpoiler = renderTitle;
renderTitle = function (item, metadata) {
  const identity =
    (metadata.related_type || item.type) +
    ':' +
    metadata.related_id +
    ':' +
    (item.season || '') +
    ':' +
    (item.episode || '');
  if (!state.companion_preferences?.spoiler_safe || spoilerRevealed.has(identity))
    return titleBeforeSpoiler(item, metadata);
  const safe = {
    ...metadata,
    overview: 'Description hidden by spoiler protection.',
    backdrop: null,
    cast: [],
    tagline: '',
    title: ['episode', 'season'].includes(item.type) ? 'Episode details (hidden)' : metadata.title,
  };
  titleBeforeSpoiler(item, safe);
  const slot = $('title-content').querySelector('.title-information');
  slot?.insertAdjacentHTML(
    'afterbegin',
    '<button class="secondary" id="spoiler-reveal-title">Reveal this title’s details</button>'
  );
  $('spoiler-reveal-title').onclick = () => {
    spoilerRevealed.add(identity);
    titleBeforeSpoiler(item, metadata);
  };
};
const entryBeforeSpoiler = row;
row = function (item) {
  const html = entryBeforeSpoiler(item);
  return state.companion_preferences?.spoiler_safe
    ? html.replace(
        /<p class="entry-overview">[\s\S]*?<\/p>/,
        '<p class="entry-overview">Description hidden by spoiler protection.</p>'
      )
    : html;
};
const coverageBeforeSpoiler = coverageMarkup;
coverageMarkup = function (data) {
  if (!state.companion_preferences?.spoiler_safe) return coverageBeforeSpoiler(data);
  const safe = {
    ...data,
    seasons: data.seasons.map((s) => ({
      ...s,
      episodes: s.episodes.map((e) => ({ ...e, title: 'Episode ' + e.episode })),
    })),
  };
  return coverageBeforeSpoiler(safe);
};
const cardBeforeSpoiler = exploreTitleCard;
exploreTitleCard = function (row) {
  const html = cardBeforeSpoiler(row);
  if (state.companion_preferences?.log_recommendations) {
    queueImpression(row);
  }
  return html;
};
let pendingImpressions = new Map(),
  impressionTimer = null;
function queueImpression(row) {
  pendingImpressions.set(row.type + ':' + row.tmdb, {
    type: row.type,
    tmdb: row.tmdb,
    title: row.title,
  });
  if (impressionTimer) return;
  impressionTimer = setTimeout(async () => {
    const rows = [...pendingImpressions.values()].slice(0, 100);
    pendingImpressions.clear();
    impressionTimer = null;
    try {
      await api('companion/impressions', { items: rows });
    } catch {}
  }, 800);
}
$('spoiler-safe').onchange = (e) =>
  task(e.target, async () => {
    await api('companion/preferences', { spoiler_safe: e.target.checked });
    state.companion_preferences = {
      ...state.companion_preferences,
      spoiler_safe: e.target.checked,
    };
    document.body.classList.toggle('spoiler-safe', e.target.checked);
    render();
    toast('Spoiler preference saved. Reopen an active title to apply it.');
  });
const readyBeforeWorkbench = window.onListweavarrReady;
window.onListweavarrReady = () => {
  readyBeforeWorkbench?.();
  $('spoiler-safe').checked = Boolean(state.companion_preferences?.spoiler_safe);
  document.body.classList.toggle(
    'spoiler-safe',
    Boolean(state.companion_preferences?.spoiler_safe)
  );
};

const selectionBeforeWorkbench = exploreSelection;
exploreSelection = function () {
  selectionBeforeWorkbench();
  $('workbench-save-picks').hidden =
    !explorePicks.size ||
    !['recipes', 'franchises', 'radar'].includes($('workbench-tool').value || 'recipes');
  $('workbench-save-picks').disabled = !explorePicks.size;
  $('workbench-save-picks').textContent = explorePicks.size
    ? 'Save selected discoveries (' + explorePicks.size + ')'
    : 'Save selected discoveries';
};
$('workbench-save-picks').onclick = () => $('explore-save-picks').click();

$('workbench-controls').addEventListener('change', (e) => {
  const field = e.target.closest('[data-work-follow-role]');
  if (field)
    task(field, async () => {
      await api('companion/follow', { person: field.dataset.workFollowRole, role: field.value });
      await loadWorkbench();
      toast('Follow scope updated.');
    });
});
