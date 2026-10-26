// SPDX-License-Identifier: AGPL-3.0-only
/* Curated orders, native links and focused discovery decisions. */
const apiBeforeSelectedOrder = api;
api = async function (path, body = {}) {
  if (['playlist/preview', 'playlist/create'].includes(path))
    body = { ...body, watch_order: selectedCuratedOrder() || null };
  return apiBeforeSelectedOrder(path, body);
};
const CURATED_ORDER_NAMES = {
  recommended: 'Recommended',
  chronological: 'Chronological',
  release: 'Release',
  essential: 'Essential story',
  completionist: 'Completionist',
};
const curatedChoices = new Map();
function selectedCuratedOrder() {
  return curatedChoices.get(active) || '';
}
function curatedOrderRoute() {
  return Object.keys(current()?.watch_paths || {}).length
    ? '&order=' + encodeURIComponent(selectedCuratedOrder() || 'original')
    : '';
}
function curatedListItems(entry = current()) {
  if (!entry) return [];
  const mode = entry.id === active ? selectedCuratedOrder() : '';
  if (!mode || !entry.watch_paths?.[mode]) return entry.items;
  const byId = new Map(entry.items.map((row) => [row.id, row]));
  return entry.watch_paths[mode].map((id) => byId.get(id)).filter(Boolean);
}
window.refreshCuratedOrders = () => {
  const host = $('curated-order-controls'),
    entry = current();
  if (!host || !entry) return;
  const modes = Object.keys(CURATED_ORDER_NAMES).filter((key) => entry.watch_paths?.[key]);
  host.hidden = !modes.length;
  if (!modes.length) {
    curatedChoices.delete(active);
    return;
  }
  $('curated-order').innerHTML =
    '<option value="">Original list order</option>' +
    modes
      .map((key) => `<option value="${key}">${CURATED_ORDER_NAMES[key]} - creator curated</option>`)
      .join('');
  if (
    !curatedChoices.has(active) ||
    (selectedCuratedOrder() && !modes.includes(selectedCuratedOrder()))
  )
    curatedChoices.set(active, modes.includes('recommended') ? 'recommended' : '');
  $('curated-order').value = selectedCuratedOrder();
  $('curated-order-note').textContent = selectedCuratedOrder()
    ? `${curatedListItems().length} entries in this creator-curated order. Other sorts change only this view. Plex playlists use this selected watch order.`
    : 'Original list membership and order.';
};
function selectCuratedOrder(mode) {
  if (mode && current()?.watch_paths?.[mode]) curatedChoices.set(active, mode);
  else curatedChoices.set(active, '');
  $('sort').value = 'original';
  selected.clear();
  render();
  if (typeof queueWorkspaceRoute === 'function') queueWorkspaceRoute();
}
const visibleBeforeCuratedOrders = visible;
visible = function () {
  const rows = visibleBeforeCuratedOrders(),
    mode = selectedCuratedOrder();
  if (!mode || !current()?.watch_paths?.[mode]) return rows;
  const positions = new Map(curatedListItems().map((r, i) => [r.id, i]));
  const included = rows.filter((row) => positions.has(row.id));
  return $('sort').value === 'original'
    ? included.sort((a, b) => positions.get(a.id) - positions.get(b.id))
    : included;
};
const rowBeforeCuratedOrders = row;
row = function (item) {
  const html = rowBeforeCuratedOrders(item);
  return selectedCuratedOrder()
    ? html.replace(
        /(<span class="rank">)[^<]*(<\/span>)/,
        (_, a, b) =>
          a + String(curatedListItems().findIndex((r) => r.id === item.id) + 1).padStart(2, '0') + b
      )
    : html;
};
const renderBeforeCuratedOrders = render;
render = function () {
  window.refreshCuratedOrders();
  renderBeforeCuratedOrders();
};
function trackedDiscoveryItem(row) {
  return (state.release_watchlist || []).some(
    (saved) => String(saved.tmdb) === String(row.tmdb) && (saved.type || 'movie') === row.type
  );
}
function hideTrackedDiscoveries() {
  for (const card of document.querySelectorAll('#explore-discover .explore-card')) {
    const link = card.querySelector('[data-explore-title]');
    if (link && trackedDiscoveryItem({ type: link.dataset.type, tmdb: link.dataset.exploreTitle }))
      card.remove();
  }
  for (const [key, item] of explorePicks) if (trackedDiscoveryItem(item)) explorePicks.delete(key);
  exploreSelection();
}
const discoveryCardBeforeTracking = exploreTitleCard;
exploreTitleCard = function (item) {
  return trackedDiscoveryItem(item) ? '' : discoveryCardBeforeTracking(item);
};
const releaseBeforeDiscoveryTracking = releaseAction;
releaseAction = async function (...args) {
  const result = await releaseBeforeDiscoveryTracking(...args);
  exploreHomeLoaded = false;
  hideTrackedDiscoveries();
  return result;
};

function personSearchMarkup(people) {
  const seen = new Set();
  const unique = people.filter((person) => {
    if (seen.has(String(person.id))) return false;
    seen.add(String(person.id));
    return true;
  });
  const primary = unique.find((person) => person.profile_path && (person.known_for || []).length),
    sparse = primary
      ? unique.filter(
          (person) =>
            person !== primary &&
            person.name.toLowerCase() === primary.name.toLowerCase() &&
            !person.profile_path &&
            !(person.known_for || []).length
        )
      : [];
  const cards = new Map();
  unique.forEach((person) => {
    const follow =
      person.following ||
      (workbenchState.creator_follows || []).find((row) => String(row.id) === String(person.id))
        ?.role;
    const known = (person.known_for || [])
      .map((row) => row.title || row.name)
      .filter(Boolean)
      .slice(0, 3);
    cards.set(
      person,
      `<article class="creator-identity"><div class="creator-portrait">${person.profile_path ? `<img src="https://image.tmdb.org/t/p/w185${esc(person.profile_path)}" alt="" loading="lazy">` : '<span>No photo</span>'}</div><div><a class="title-link" href="#/projects/person/${esc(person.id)}" data-person-link="${esc(person.id)}">${esc(person.name)}</a><p>${esc(person.known_for_department || 'Department not reported')} - TMDB ${esc(person.id)}</p><p class="muted">${known.length ? 'Known for ' + esc(known.join(', ')) : 'No known-for credits reported.'}</p><a class="creator-source" href="https://www.themoviedb.org/person/${esc(person.id)}" target="_blank" rel="noopener noreferrer">Verify on TMDB &nearr;</a></div><button class="${follow ? 'secondary' : 'primary'}" data-work-follow="${esc(person.id)}" ${follow ? 'disabled' : ''}>${follow ? 'Following - ' + (follow === 'all' ? 'all credits' : follow) : 'Follow'}</button></article>`
    );
  });
  return (
    unique
      .filter((person) => !sparse.includes(person))
      .map((person) => cards.get(person))
      .join('') +
      (sparse.length
        ? `<details class="creator-alternates"><summary>Other same-name records (${sparse.length})</summary><p class="muted">These TMDB records have limited identity information. Verify them before following; separate IDs are not automatically merged.</p>${sparse.map((person) => cards.get(person)).join('')}</details>`
        : '') ||
    '<div class="empty"><h3>No people found.</h3><p>Try a full name or check the spelling.</p></div>'
  );
}
let followedReleaseItems = [];
function followedReleaseCards(items) {
  followedReleaseItems = items;
  return items
    .map((item, index) => {
      const show = item.type === 'episode';
      const date = new Date(item.release_date);
      const label = Number.isNaN(date.getTime())
        ? 'Date unavailable'
        : show
          ? date.toLocaleString(undefined, {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
            })
          : exploreCardDate(String(item.release_date).slice(0, 10));
      return `<article class="followed-release-card"><button class="followed-release-art" data-trakt-item="${index}" aria-label="Details for ${esc(item.show_title || item.title)}">${item.poster ? `<img src="${esc(item.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-release-art>` : `<span>${esc((item.show_title || item.title || '?').charAt(0))}</span>`}</button><div><p class="eyebrow">${show ? 'TV EPISODE' : 'MOVIE RELEASE'}</p>${show ? `<strong class="followed-show-name">${esc(item.show_title || 'TV show')}</strong>` : ''}<button class="title-link" data-trakt-item="${index}">${esc(item.title)}</button><p class="muted">${show ? `Season ${esc(item.season)} - Episode ${esc(item.episode)}` : esc(item.year || '')}</p><time datetime="${esc(item.release_date)}">${esc(label)}</time></div></article>`;
    })
    .join('');
}
let tonightPlanRows = [];
function tonightResults(data) {
  tonightPlanRows = data.plans || [];
  const movies = data.items.filter((row) => row.type === 'movie'),
    tv = data.items.filter((row) => row.type === 'episode');
  function choices(items, title) {
    return items.length
      ? `<section class="tonight-choice-section"><h3>${title}</h3><p class="muted">Choose one watch below, or build a session from the combinations above.</p>${tonightRows(items).replace(/data-shortlist-add="(\d+)"/g, (_, index) => `data-shortlist-add="${workbenchItems.indexOf(items[Number(index)])}"`)}</section>`
      : '';
  }
  const planCards = tonightPlanRows.map(
    (plan, index) =>
      `<article class="tonight-session"><div class="session-posters">${plan.items
        .slice(0, 3)
        .map(
          (item) =>
            `<a href="${mediaRoute(item)}" ${item.tmdb ? `data-session-title="${esc(item.tmdb)}" data-type="${esc(item.type)}" data-season="${esc(item.season ?? '')}" data-episode="${esc(item.episode ?? '')}"` : ''} aria-label="${esc(item.title)}">${item.poster ? `<img src="${esc(item.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-release-art>` : `<span>${esc(item.title.charAt(0))}</span>`}</a>`
        )
        .join(
          ''
        )}</div><div><p class="eyebrow">${plan.kind === 'episodes' ? 'TV RUN' : plan.kind === 'movies' ? 'MOVIE NIGHT' : 'MIXED SESSION'}</p><h4>${esc(plan.title)}</h4><strong>${Math.ceil(plan.runtime)} min <small>&middot; ${Math.floor(plan.remaining)} min spare</small></strong><p>${esc(plan.reason)}</p><details><summary>${plan.items.length} watches in order</summary><ol>${plan.items.map((item) => `<li>${item.tmdb ? `<a href="${mediaRoute(item)}" data-session-title="${esc(item.tmdb)}" data-type="${esc(item.type)}" data-season="${esc(item.season ?? '')}" data-episode="${esc(item.episode ?? '')}">${esc(item.title)}</a>` : esc(item.title)} <small>${Math.ceil(item.runtime)} min</small></li>`).join('')}</ol></details><button class="secondary" data-shortlist-session="${index}">Shortlist this session</button></div></article>`
  );
  const leading = [],
    more = [],
    types = new Set();
  tonightPlanRows.forEach((plan, index) => {
    if (!types.has(plan.kind) && plan.kind !== 'mixed') {
      types.add(plan.kind);
      leading.push(planCards[index]);
    } else more.push(planCards[index]);
  });
  if (!leading.length && more.length) leading.push(more.shift());
  const plans =
    leading.join('') +
    (more.length
      ? `<details class="session-more"><summary>More session ideas (${more.length})</summary><div class="tonight-sessions">${more.join('')}</div></details>`
      : '');
  return (
    (plans
      ? `<section><h3>Make a night of it</h3><p class="muted">Sessions fit within your ${Number(data.minutes)} minutes. Review the sequence and leave time for breaks; runtimes are estimates.</p><div class="tonight-sessions">${plans}</div></section>`
      : '<p class="muted">No connected multi-watch session fits this time. Try more time or a broader genre.</p>') +
    choices(movies, 'Single movies') +
    choices(tv, 'One TV episode') +
    (!movies.length && !tv.length
      ? '<div class="empty"><h3>No available watches fit.</h3><p>Try more time, another genre or include watched movies.</p></div>'
      : '')
  );
}
function mediaRoute(item) {
  const type = item.type === 'movie' ? 'movie' : item.type === 'episode' ? 'episode' : 'show',
    id = type === 'episode' ? item.show_tmdb || item.tmdb : item.tmdb;
  return id
    ? '#/title/' +
        type +
        '/' +
        encodeURIComponent(id) +
        (type === 'episode'
          ? '/' + encodeURIComponent(item.season) + '/' + encodeURIComponent(item.episode)
          : '')
    : '#/explore/workbench/tonight';
}
const tonightRowsBeforeSessions = tonightRows;
tonightRows = function (items) {
  if (new Set(items.map((row) => row.type)).size > 1)
    return [
      ['movie', 'Movies'],
      ['episode', 'TV episodes'],
      ['session', 'Watch sessions'],
    ]
      .map(([type, title]) => {
        const group = items.filter((row) => row.type === type);
        return group.length
          ? `<section class="tonight-choice-section"><h3>${title}</h3>${tonightRows(group).replace(/data-shortlist-add="(\d+)"/g, (_, index) => `data-shortlist-add="${items.indexOf(group[Number(index)])}"`)}</section>`
          : '';
      })
      .join('');
  if (!items.some((row) => row.type === 'session')) return tonightRowsBeforeSessions(items);
  return (
    '<div class="tonight-grid">' +
    items
      .map((row, index) =>
        row.type === 'session'
          ? `<article class="tonight-card shortlisted-session"><div><p class="eyebrow">SESSION</p><h4>${esc(row.title)}</h4><strong>${Math.ceil(row.runtime)} min</strong><p>${esc(row.reason)}</p><ol>${row.items.map((item) => `<li>${item.tmdb ? `<a href="${mediaRoute(item)}" data-session-title="${esc(item.tmdb)}" data-type="${esc(item.type)}" data-season="${esc(item.season ?? '')}" data-episode="${esc(item.episode ?? '')}">${esc(item.title)}</a>` : esc(item.title)}</li>`).join('')}</ol><button class="text-action" data-shortlist-remove="${esc(row.key)}">Eliminate session</button></div></article>`
          : tonightRowsBeforeSessions([row])
              .replace(/^<div class="tonight-grid">/, '')
              .replace(/<\/div>$/, '')
              .replace('data-shortlist-add="0"', `data-shortlist-add="${index}"`)
      )
      .join('') +
    '</div>'
  );
};
const NOTIFICATION_CATEGORIES = {
  requests: 'Request update',
  releases: 'Release available',
  lists: 'Official list update',
  creators: 'Creator radar',
};
let inboxShowRead = false;
function notificationDate(value) {
  if (!value) return '';
  const date = new Date(typeof value === 'number' ? value * 1000 : value);
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
function notificationMarkup(item, compact = false) {
  const title =
    item.item?.type === 'episode' && item.item.show_title
      ? item.item.show_title + ' - ' + item.title
      : item.title;
  return `<article class="notification-entry ${item.read ? 'is-read' : 'is-unread'}"><span class="notification-dot" aria-label="${item.read ? 'Read' : 'Unread'}"></span><div><div class="notification-meta"><span>${NOTIFICATION_CATEGORIES[item.category] || 'Update'}</span><time>${esc(notificationDate(item.at))}</time></div><button class="notification-title" data-notification-open="${esc(item.id)}">${esc(title)}</button><p>${esc(item.detail)}</p>${!compact && item.item?.type === 'episode' ? `<small>S${esc(item.item.season)} E${esc(item.item.episode)}</small>` : ''}<div class="notification-actions"><button class="text-action" data-notification-open="${esc(item.id)}">Open ${item.category === 'requests' ? 'request' : item.category === 'lists' ? 'list update' : 'title'}</button>${!item.read ? `<button class="secondary" data-notification-read="${esc(item.id)}" aria-label="Mark ${esc(title)} as read">Mark read</button>` : '<span class="muted">Read</span>'}</div></div></article>`;
}
window.renderNotificationPopover = () => {
  const messages = document.querySelector('.workspace-inbox-messages');
  if (!messages) return;
  const unread = (window.notificationEntries || []).filter((row) => !row.read),
    limit = state.companion_preferences?.notification_limit || 5;
  messages.innerHTML = `<div class="notification-popover-heading"><div><strong>Updates</strong><small>${unread.length} unread</small></div><label>Show<select aria-label="Recent notification count" id="notification-limit">${[5, 10, 20].map((n) => `<option value="${n}" ${n === limit ? 'selected' : ''}>${n} latest</option>`).join('')}</select></label></div><div class="notification-recent">${
    unread
      .slice(0, limit)
      .map((row) => notificationMarkup(row, true))
      .join('') ||
    '<div class="notification-empty"><strong>All caught up.</strong><p>New release, request, creator and list updates will appear here.</p></div>'
  }</div><div class="notification-popover-footer">${unread.length ? '<button class="secondary" data-notification-read-recent>Mark shown as read</button>' : ''}<button class="text-action" data-notification-inbox>Open discovery inbox</button></div>`;
};
function notificationInboxMarkup(items) {
  const unread = items.filter((row) => !row.read),
    shown = inboxShowRead ? items : unread;
  return `<div class="notification-inbox-toolbar"><div><strong>${unread.length} unread</strong><span>${items.length} recent updates</span></div><button class="secondary" data-notification-toggle-read>${inboxShowRead ? 'Show unread only' : 'Include read updates'}</button></div><div class="notification-inbox-list">${shown.map((row) => notificationMarkup(row)).join('') || '<div class="empty"><h3>All caught up.</h3><p>No unread updates. Include read updates to revisit recent activity.</p></div>'}</div>`;
}
async function refreshNotificationFeed() {
  const data = await api('companion/inbox', {});
  window.updateWorkspaceInbox(data.items);
  if (
    workspacePanel === 'trakt-explore' &&
    exploreTab === 'workbench' &&
    $('workbench-tool').value === 'inbox'
  ) {
    workbenchItems = data.items;
    $('workbench-results').innerHTML = notificationInboxMarkup(data.items);
    const read = document.querySelector('[data-work-action="inbox-read"]');
    if (read) read.hidden = !data.items.some((row) => !row.read);
  }
  return data.items;
}
async function markNotificationRead(ids) {
  const restoreFocus = Boolean(
    document.activeElement?.closest?.('.notification-entry,.notification-popover-footer')
  );
  if (ids.length) await api('companion/inbox-read', { ids });
  const rows = await refreshNotificationFeed();
  if (restoreFocus)
    (
      document.querySelector('.workspace-inbox[open] [data-notification-read]') ||
      document.querySelector('.notification-inbox-list [data-notification-read]') ||
      document.querySelector('.workspace-inbox>summary')
    )?.focus();
  return rows;
}
async function openNotification(id) {
  const item =
    (window.notificationEntries || []).find((row) => row.id === id) ||
    workbenchItems.find((row) => row.id === id);
  if (!item) return;
  if (!item.read) await markNotificationRead([id]);
  document.querySelector('.workspace-inbox').open = false;
  if (item.category === 'requests') {
    openRequests();
    $('requests-search').value = item.title;
    $('requests-filter').value = '';
    drawRequests();
  } else if (item.category === 'lists') {
    settingsView(false);
    selectListsTab('official');
    loadCollectionUpdates();
    if (item.feed) {
      $('catalogue-source-panel').open = true;
      previewCatalogue(false);
    }
  } else if (item.item?.tmdb)
    openExternalTitle(item.item.type, item.item.tmdb, item.item.season, item.item.episode);
  else if (item.category === 'releases') {
    traktOpen();
    selectExploreTab('watchlist');
  }
}

// Real anchors retain normal browser new-tab/context-menu behavior. SPA navigation
// only handles an unmodified left click; modified clicks never trigger app actions.
function navigationHref(element) {
  const d = element.dataset;
  if (d.releaseTitle) return mediaRoute({ type: d.releaseType, tmdb: d.releaseTitle });
  if (d.requestTitle) {
    const row = requestRows.find((row) => row.id === d.requestTitle);
    if (row) return mediaRoute(row.item);
  }
  if (d.traktItem !== undefined) {
    const item = element.closest('#trakt-calendar-rows')
      ? followedReleaseItems[Number(d.traktItem)]
      : traktPreview?.items[Number(d.traktItem)];
    if (item) return mediaRoute(item);
  }
  if (d.officialOpen) {
    const entry = state.lists.find((row) => row.official_id === d.officialOpen);
    if (entry) return '#/lists/view/' + encodeURIComponent(entry.id) + '?origin=official';
  }
  if (d.sessionTitle)
    return mediaRoute({ type: d.type, tmdb: d.sessionTitle, season: d.season, episode: d.episode });
  if (d.personLink || d.person)
    return '#/projects/person/' + encodeURIComponent(d.personLink || d.person);
  if (d.company) return '#/projects/company/' + encodeURIComponent(d.company);
  if (d.exploreTitle) return mediaRoute({ type: d.type, tmdb: d.exploreTitle });
  if (d.titleTmdb) return mediaRoute({ type: d.titleType, tmdb: d.titleTmdb });
  if (d.episodeShow || d.episodeNeighbor)
    return mediaRoute({
      type: 'episode',
      show_tmdb: d.episodeShow || d.episodeNeighbor,
      season: d.season,
      episode: d.episode,
    });
  if (d.workTitle)
    return mediaRoute({
      type: d.workType,
      tmdb: d.workTitle,
      season: d.workSeason,
      episode: d.workEpisode,
    });
  if (d.openList) return '#/lists/view/' + encodeURIComponent(d.openList) + '?origin=mine';
  if (d.details) {
    const item = current()?.items.find((row) => row.id === d.details);
    if (!item) return null;
    if (item.type === 'season' || (!item.tmdb && !item.show_tmdb))
      return (
        '#/lists/view/' +
        encodeURIComponent(active) +
        '?origin=' +
        listReturnTab +
        '&item=' +
        encodeURIComponent(item.id)
      );
    return mediaRoute(item);
  }
  if (d.show) {
    const item = current()?.items.find((row) => row.id === d.show);
    if (item?.show_tmdb || item?.tmdb)
      return mediaRoute({ type: 'show', tmdb: item.show_tmdb || item.tmdb });
  }
  return null;
}
function installNavigationLinks() {
  for (const button of document.querySelectorAll(
    'button[data-details],button[data-person],button[data-company],button[data-explore-title],button[data-title-tmdb],button[data-episode-show],button[data-episode-neighbor],button[data-work-title],button[data-open-list],button[data-show],button[data-release-title],button[data-request-title],button[data-trakt-item],button[data-official-open]'
  )) {
    const href = navigationHref(button);
    if (!href) continue;
    const link = document.createElement('a');
    for (const attr of button.attributes)
      if (!['type', 'disabled'].includes(attr.name)) link.setAttribute(attr.name, attr.value);
    link.href = href;
    link.innerHTML = button.innerHTML;
    link.dataset.workspaceLink = 'true';
    button.replaceWith(link);
  }
}
if (typeof document.createElement === 'function') {
  const host = document.createElement('div');
  host.id = 'curated-order-controls';
  host.className = 'curated-order-controls';
  host.hidden = true;
  host.innerHTML =
    '<label>Watch order<select id="curated-order"></select></label><p id="curated-order-note" class="muted"></p>';
  document.querySelector('.list-detail-tools').before(host);
  $('curated-order').onchange = () => selectCuratedOrder($('curated-order').value);
  const readyBeforeDiscoveryUpdate = window.onListweavarrReady;
  window.onListweavarrReady = () => {
    readyBeforeDiscoveryUpdate?.();
    window.refreshCuratedOrders();
    window.renderNotificationPopover();
    installNavigationLinks();
  };
  let linksQueued = false;
  new MutationObserver(() => {
    if (linksQueued) return;
    linksQueued = true;
    queueMicrotask(() => {
      linksQueued = false;
      installNavigationLinks();
    });
  }).observe(document.body, { childList: true, subtree: true });
  document.addEventListener(
    'click',
    (event) => {
      const link = event.target.closest(
        'a[data-workspace-link],a[data-session-title],a[data-person-link]'
      );
      if (!link) return;
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
        event.stopImmediatePropagation();
        return;
      }
      event.preventDefault();
    },
    true
  );
  document.addEventListener(
    'auxclick',
    (event) => {
      if (event.target.closest('a[data-workspace-link],a[data-session-title],a[data-person-link]'))
        event.stopImmediatePropagation();
    },
    true
  );
  document.addEventListener('click', (event) => {
    const read = event.target.closest('[data-notification-read]'),
      open = event.target.closest('[data-notification-open]'),
      all = event.target.closest('[data-notification-read-recent]'),
      inbox = event.target.closest('[data-notification-inbox]');
    if (read) task(read, () => markNotificationRead([read.dataset.notificationRead]));
    if (open) task(open, () => openNotification(open.dataset.notificationOpen));
    if (all) {
      const limit = state.companion_preferences?.notification_limit || 5;
      task(all, () =>
        markNotificationRead(
          (window.notificationEntries || [])
            .filter((row) => !row.read)
            .slice(0, limit)
            .map((row) => row.id)
        )
      );
    }
    if (inbox) {
      document.querySelector('.workspace-inbox').open = false;
      traktOpen();
      selectExploreTab('workbench');
      showTool('inbox');
      workAction('inbox');
    }
    if (event.target.closest('[data-notification-toggle-read]')) {
      inboxShowRead = !inboxShowRead;
      $('workbench-results').innerHTML = notificationInboxMarkup(workbenchItems);
    }
    const session = event.target.closest('[data-shortlist-session]');
    if (session) {
      const plan = tonightPlanRows[Number(session.dataset.shortlistSession)];
      if (plan) {
        shortlist.set(plan.key, {
          ...plan,
          type: 'session',
          reason: plan.reason,
          title: plan.title,
        });
        session.textContent = 'Session shortlisted';
        session.disabled = true;
        refreshTonightControls();
        toast('Session added to your shortlist.');
      }
    }
    const title = event.target.closest('[data-session-title]');
    if (title)
      openExternalTitle(
        title.dataset.type,
        title.dataset.sessionTitle,
        title.dataset.season,
        title.dataset.episode
      );
    const person = event.target.closest('[data-person-link]');
    if (person) openDiscovery('person', person.dataset.personLink);
  });
  document.querySelector('.workspace-inbox').addEventListener('toggle', () => {
    if (document.querySelector('.workspace-inbox').open)
      refreshNotificationFeed().catch((error) => toast(error.message));
  });
  document.addEventListener('change', (event) => {
    if (event.target.id === 'notification-limit') {
      const value = Number(event.target.value);
      task(event.target, async () => {
        await api('companion/preferences', { notification_limit: value });
        state.companion_preferences = { ...state.companion_preferences, notification_limit: value };
        window.renderNotificationPopover();
        $('notification-limit')?.focus();
      });
    }
  });
  window.refreshCuratedOrders();
  window.renderNotificationPopover();
  installNavigationLinks();
}

// Failed remote artwork keeps a readable placeholder instead of a broken image.
document.addEventListener(
  'error',
  (event) => {
    const img = event.target;
    if (img.matches?.('[data-release-art]')) {
      if (!img.dataset.retried && img.src.includes('/w342/')) {
        img.dataset.retried = '1';
        img.src = img.src.replace('/w342/', '/w500/');
        return;
      }
      const host = img.parentElement;
      img.remove();
      const placeholder = document.createElement('span');
      placeholder.textContent =
        host.getAttribute('aria-label')?.replace('Details for ', '').charAt(0) || '?';
      host.append(placeholder);
    }
  },
  true
);

let favoritesPreview = [];
$('favorites-open').onclick = () => {
  favoritesPreview = [];
  $('favorites-items').innerHTML = '';
  $('favorites-status').textContent = '';
  $('favorites-save').disabled = true;
  $('favorites-dialog').showModal();
};
$('favorites-preview').onclick = (e) =>
  task(e.target, async () => {
    const data = await api('companion/favorites', { limit: $('favorites-limit').value });
    favoritesPreview = data.items;
    $('favorites-status').textContent = data.note;
    $('favorites-items').innerHTML =
      data.items
        .map(
          (row, index) =>
            `<label class="favorite-preview-row"><input type="checkbox" data-favorite-pick="${index}" checked>${row.poster ? `<img src="${esc(row.poster)}" alt="" loading="lazy">` : ''}<span><strong>${esc(row.title)}</strong><small>${esc(row.reasons.join(' / '))}</small></span></label>`
        )
        .join('') ||
      '<p>No watched titles meet these signals yet. Add personal ratings in Plex or rewatch a favorite.</p>';
    $('favorites-save').disabled = !data.items.length;
  });
$('favorites-save').onclick = (e) =>
  task(e.target, async () => {
    const items = [...document.querySelectorAll('[data-favorite-pick]:checked')].map(
      (input) => favoritesPreview[Number(input.dataset.favoritePick)]
    );
    if (!items.length) throw Error('Choose at least one favorite.');
    const saved = await api('lists/edit', {
      name: 'Favorites',
      description: 'Personal favorites selected from Plex ratings and repeat plays.',
      items,
    });
    replaceList(saved.entry);
    $('favorites-dialog').close();
    openSavedList(saved.entry.id);
    toast('Favorites list created.');
  });
// Keep existing handlers, but give maintenance its own spacious, grouped dialog.
if (typeof document.createElement === 'function') {
  const menu = document.querySelector('.list-tools-menu');
  if (menu) {
    const host = menu.querySelector(':scope > div'),
      dialog = document.createElement('dialog');
    dialog.id = 'list-management-dialog';
    dialog.innerHTML =
      '<div class="section-heading"><div><p class="eyebrow">MANAGE COLLECTION</p><h2>List tools</h2></div><button class="secondary" data-close="list-management-dialog">Close</button></div><p class="muted">Choose a task. Your list stays in place when you close this panel.</p>';
    const groups = [
      ['Edit & share', ['list-manage', 'list-add-entries', 'list-share']],
      ['Watch order', ['list-watch-paths', 'list-episode-orders']],
      ['Plex & watched progress', ['playlist-open', 'progress-refresh']],
      [
        'Source & metadata',
        [
          'refresh-list',
          'resolve-metadata',
          'follow-list',
          'check-followed',
          'metadata-retry-all',
          'list-health-check',
        ],
      ],
      ['Publisher tools', ['list-publish-official']],
      ['Remove list', ['list-delete']],
    ];
    for (const [name, ids] of groups) {
      const section = document.createElement('section');
      section.className = 'list-tool-group';
      section.innerHTML = '<h3>' + name + '</h3>';
      for (const id of ids) if ($(id)) section.append($(id));
      dialog.append(section);
    }
    if (host?.querySelector('.list-maintenance')) {
      const legacy = host.querySelector('.list-maintenance');
      legacy.hidden = true;
      dialog.append(legacy);
    }
    dialog.querySelector('[data-close]').onclick = () => dialog.close();
    document.body.append(dialog);
    const button = document.createElement('button');
    button.className = 'secondary';
    button.textContent = 'Manage list';
    button.onclick = () => {
      const publish = $('list-publish-official');
      publish.hidden = !state.curator_mode;
      publish.closest('section').hidden = !state.curator_mode;
      dialog.showModal();
    };
    dialog.addEventListener('click', (event) => {
      if (event.target.closest('button') && !event.target.closest('[data-close]')) dialog.close();
    });
    menu.replaceWith(button);
  }
}
