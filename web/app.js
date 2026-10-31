// SPDX-License-Identifier: AGPL-3.0-only
/* Poster art is layered in the browser; original posters and Plex are untouched. */
function posterArt(url, row) {
  const show = row.type !== 'movie',
    id = show
      ? row.show_tmdb || (row.related_type === 'show' ? row.related_id : null) || row.tmdb
      : null;
  return `<span class="poster-stack" ${id ? `data-poster-show="${esc(id)}"` : ''}><img class="poster-base" src="${esc(url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></span>`;
}
(() => {
  if (typeof MutationObserver === 'undefined' || typeof IntersectionObserver === 'undefined')
    return;
  const cache = new Map(),
    pending = new Map(),
    queue = [];
  let active = 0;
  function paint(el, data) {
    if (!el.isConnected || el.querySelector('.poster-status')) return;
    const label = [data.network, data.status_label].filter(Boolean).join(' · ');
    el.title = label;
    if (data.status_asset) {
      const img = document.createElement('img');
      img.className = 'poster-overlay poster-status';
      img.src = '/poster-overlays/status-top-left/' + data.status_asset;
      img.alt = data.status_label;
      el.append(img);
    }
    if (data.network_asset) {
      const img = document.createElement('img');
      img.className = 'poster-overlay poster-network';
      img.src = '/poster-overlays/network-top-left/' + encodeURIComponent(data.network_asset);
      img.alt = data.network || 'Network';
      el.append(img);
    } else if (data.network) {
      const badge = document.createElement('span');
      badge.className = 'poster-network-text';
      badge.textContent = data.network;
      el.append(badge);
    }
  }
  function run() {
    while (active < 3 && queue.length) {
      const id = queue.shift();
      active++;
      api('poster-info', { tmdb: id })
        .then((data) => {
          cache.set(id, data);
          for (const el of pending.get(id) || []) paint(el, data);
        })
        .catch(() => {})
        .finally(() => {
          pending.delete(id);
          active--;
          run();
        });
    }
  }
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target,
          id = el.dataset.posterShow;
        observer.unobserve(el);
        if (cache.has(id)) {
          paint(el, cache.get(id));
          continue;
        }
        if (pending.has(id)) pending.get(id).push(el);
        else {
          pending.set(id, [el]);
          queue.push(id);
          run();
        }
      }
    },
    { rootMargin: '100px' }
  );
  function scan() {
    for (const el of document.querySelectorAll('[data-poster-show]:not([data-poster-observed])')) {
      el.dataset.posterObserved = 'true';
      observer.observe(el);
    }
  }
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  scan();
})();

let state = { lists: [], settings: {} },
  active = '',
  filter = 'all',
  selected = new Set(),
  busy = false;
const $ = (id) => document.getElementById(id);
const esc = (v) =>
  String(v ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]
  );
function mediaCandidateMarkup(row, index, attribute = 'data-request-choice') {
  return `<button type="button" class="request-candidate" ${attribute}="${index}" ${attribute === 'data-request-choice' ? 'aria-pressed="false"' : ''}>${row.poster ? `<img src="${esc(row.poster)}" alt="" loading="lazy">` : '<span class="candidate-placeholder" aria-hidden="true">?</span>'}<span><strong>${esc(row.title)}</strong><small>${esc(row.year || 'Year unknown')} &middot; ${row.type === 'show' ? 'TV show' : 'Movie'} &middot; TMDB ${esc(row.tmdb)}${row.direct_scope?.season != null ? ' · S' + esc(row.direct_scope.season) + (row.direct_scope.episode != null ? ' E' + esc(row.direct_scope.episode) : '') : ''}${attribute === 'data-list-add' ? ' · Add to list' : ''}</small><span class="candidate-overview">${esc(row.overview || 'No synopsis available. Open the title on TMDB to verify its identity.')}</span></span></button>`;
}
function requestCandidateMarkup(row, index) {
  return mediaCandidateMarkup(row, index);
}

const current = () => state.lists.find((l) => l.id === active);

const extraRatingsCache = new Map(),
  extraRatingsPending = new Map(),
  directRatingsCache = new Map();
const ratingSources = [
  ['tmdb', 'TMDB', 10],
  ['imdb', 'IMDb', 10],
  ['tomatoes', 'Rotten Tomatoes critics', 100],
  ['popcorn', 'Rotten Tomatoes audience', 100],
  ['metacritic', 'Metacritic critics', 100],
  ['metacriticuser', 'Metacritic users', 10],
  ['trakt', 'Trakt', 10],
  ['letterboxd', 'Letterboxd', 5],
  ['myanimelist', 'MyAnimeList', 10],
  ['rogerebert', 'Roger Ebert', 4],
  ['mdblist', 'MDBList aggregate', 100],
];
function ratingIdentity(row) {
  const type = row.type || 'movie',
    tmdb = row.tmdb || (type === 'show' || type === 'movie' ? row.related_id : null),
    imdb = row.imdb || String(row.imdb_url || '').match(/tt\d+/)?.[0];
  return {
    type,
    tmdb,
    imdb,
    key: ['season', 'episode'].includes(type)
      ? [type, row.show_tmdb || row.related_id, row.season, row.episode].join(':')
      : type + ':' + (tmdb ? 'tmdb:' + tmdb : 'imdb:' + imdb),
  };
}
function availableRatings(row) {
  const identity = ratingIdentity(row),
    scores = [...(extraRatingsCache.get(identity.key)?.ratings || [])];
  for (const direct of directRatingsCache.get(identity.key) || []) {
    const index = scores.findIndex((r) => r.source === direct.source);
    if (index >= 0) scores[index] = direct;
    else scores.push(direct);
  }
  if (Number.isFinite(row.rating) && row.rating > 0) {
    const direct = {
      source: 'tmdb',
      label: 'TMDB',
      value: row.rating,
      maximum: 10,
      score: row.rating,
      votes: row.vote_count,
      via: 'TMDB',
    };
    const index = scores.findIndex((r) => r.source === 'tmdb');
    if (index >= 0) scores[index] = direct;
    else scores.unshift(direct);
  }
  return scores.filter((r) => Number.isFinite(Number(r.value)) && Number(r.value) > 0);
}
function preferredRating(row, strict = false) {
  const scores = availableRatings(row),
    main = state.rating_preferences?.main || 'tmdb';
  return (
    scores.find((r) => r.source === main) ||
    (strict ? null : scores.find((r) => r.source === 'tmdb') || scores[0]) ||
    null
  );
}
function ratingText(score) {
  return (
    score.label +
    ' ' +
    Number(score.value).toFixed(score.maximum === 100 ? 0 : 1) +
    (['tomatoes', 'popcorn'].includes(score.source) ? '%' : ' / ' + score.maximum)
  );
}
function ratingContents(row, full = false) {
  if (row.upcoming && Number(row.vote_count || 0) < 30)
    return full
      ? '<span class="muted">Not yet rated · unreleased title, too few votes</span>'
      : 'Not yet rated';
  const scores = availableRatings(row),
    main = state.rating_preferences?.main || 'tmdb',
    display = state.rating_preferences?.display || 'all',
    status = extraRatingsCache.get(ratingIdentity(row).key);
  if (!full) {
    const score = preferredRating(row);
    return score
      ? `<span title="${esc(score.via || score.label)}${score.source !== main ? '; preferred source unavailable, showing fallback' : ''}">${esc(ratingText(score))}</span>`
      : row.upcoming
        ? 'Not yet rated'
        : 'Not rated';
  }
  const selected = display === 'all' ? scores : scores.filter((r) => display.includes(r.source));
  const order = state.rating_preferences?.order || [
    main,
    ...ratingSources.map((r) => r[0]).filter((s) => s !== main),
  ];
  selected.sort((a, b) => order.indexOf(a.source) - order.indexOf(b.source));
  return `<div class="rating-comparison">${selected.map((r) => `<span class="rating-chip ${r.source === main ? 'rating-main' : ''}" title="${esc(r.via || r.label)}${r.votes != null ? '; ' + Number(r.votes).toLocaleString() + ' votes' : ''}"><span>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.label)}</a>` : esc(r.label)}${r.source === main ? ' &middot; Main' : ''}</span><strong>${Number(r.value).toFixed(r.maximum === 100 ? 0 : 1)}${['tomatoes', 'popcorn'].includes(r.source) ? '%' : ' / ' + r.maximum}</strong></span>`).join('') || '<span class="muted">No scores available from the selected sources.</span>'}</div><details class="rating-attribution"><summary>Rating source notes</summary><small class="muted">${scores.some((r) => r.via === 'MDBList') ? 'Additional scores via MDBList. Critic approval percentages and average user ratings measure different things. ' : ''}${!scores.some((r) => r.source === main) ? 'Preferred rating unavailable. ' : ''}${esc(status?.error || status?.note || (!state.settings.mdblist?.configured ? 'Connect MDBList under Settings / Connections for more rating sources.' : ''))}</small></details>`;
}
function ratingWidget(row, full = false) {
  const data = Object.fromEntries(
    [
      'type',
      'tmdb',
      'imdb',
      'imdb_url',
      'related_id',
      'show_tmdb',
      'season',
      'episode',
      'rating',
      'vote_count',
      'upcoming',
    ]
      .filter((k) => row[k] != null)
      .map((k) => [k, row[k]])
  );
  return `<span class="rating-widget" data-rating-row="${esc(JSON.stringify(data))}" data-rating-full="${full ? 'true' : 'false'}">${ratingContents(data, full)}</span>`;
}
function repaintRatings() {
  for (const el of document.querySelectorAll('[data-rating-row]'))
    el.innerHTML = ratingContents(
      JSON.parse(el.dataset.ratingRow),
      el.dataset.ratingFull === 'true'
    );
}
async function ensureRatings(rows) {
  if (!state.settings.mdblist?.configured) return;
  const unique = new Map(
    rows
      .map((r) => {
        const i = ratingIdentity(r);
        return [i.key, i];
      })
      .filter(
        ([key, r]) =>
          ['movie', 'show'].includes(r.type) && (r.tmdb || r.imdb) && !extraRatingsCache.has(key)
      )
  );
  for (const batch of Array.from(unique.values()).reduce((chunks, r, n) => {
    if (n % 20 === 0) chunks.push([]);
    chunks.at(-1).push(r);
    return chunks;
  }, [])) {
    const fresh = batch.filter((r) => !extraRatingsPending.has(r.key));
    const promises = batch.map((r) => extraRatingsPending.get(r.key)).filter(Boolean);
    if (fresh.length) {
      const pending = api('ratings', { items: fresh })
        .then((data) => {
          for (const item of data.items) extraRatingsCache.set(item.key, item);
        })
        .catch((e) => {
          for (const item of fresh)
            extraRatingsCache.set(item.key, { ratings: [], error: e.message });
        })
        .finally(() => {
          for (const item of fresh) extraRatingsPending.delete(item.key);
          repaintRatings();
        });
      for (const item of fresh) extraRatingsPending.set(item.key, pending);
      promises.push(pending);
    }
    await Promise.all(promises);
  }
}
(() => {
  if (typeof MutationObserver === 'undefined') return;
  const observer = new IntersectionObserver(
    (entries) => {
      const rows = [];
      for (const entry of entries) {
        if (entry.isIntersecting) {
          observer.unobserve(entry.target);
          rows.push(JSON.parse(entry.target.dataset.ratingRow));
        }
      }
      if (rows.length) ensureRatings(rows);
    },
    { rootMargin: '100px' }
  );
  const scan = () => {
    for (const el of document.querySelectorAll('[data-rating-row]:not([data-rating-observed])')) {
      el.dataset.ratingObserved = 'true';
      observer.observe(el);
    }
  };
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
})();
function managerIsConfigured(service) {
  return Boolean(
    state.settings[service]?.configured ||
      (typeof workflowManagers !== 'undefined' &&
        workflowManagers.instances.some((r) => r.service === service && r.enabled && r.configured))
  );
}

function requestRouteMarkup(options, service, prefix) {
  const routes = options.routes || [
    {
      id: 'primary',
      name: 'Primary ' + service,
      tier: 'standard',
      enabled: true,
      configured: true,
    },
  ];
  return `<label>Manager route<select id="${prefix}-route" data-manager-route="${service}" data-route-prefix="${prefix}" data-loaded-route="${esc(options.route || 'primary')}">${routes.map((route) => `<option value="${esc(route.id)}" ${route.id === (options.route || 'primary') ? 'selected' : ''} ${!route.enabled || !route.configured ? 'disabled' : ''}>${esc(route.name)} - ${route.tier === '4k' ? '4K' : 'Standard'}</option>`).join('')}</select></label>`;
}

function ratingPreferencesMarkup() {
  const prefs = state.rating_preferences || { main: 'tmdb', display: 'all' },
    order = [...new Set([...(prefs.order || [prefs.main]), ...ratingSources.map((r) => r[0])])];
  return `<div class="connection rating-preferences"><h2>Ratings</h2><p class="muted">Check the sources to show on title pages and arrange their order. The first checked source is your preferred score on compact cards; an available fallback is used when needed.</p><label class="preference-check rating-all-toggle"><span>Show all sources</span><input id="rating-display-all" type="checkbox" ${prefs.display === 'all' ? 'checked' : ''}></label><div class="rating-order"><div class="rating-order-heading"><h3>Display order</h3><span>Show</span></div><ol id="rating-order-list">${order
    .map((source, index, all) => {
      const label = ratingSources.find((r) => r[0] === source)?.[1] || source;
      return `<li data-rating-order="${source}"><span>${label}</span><button type="button" class="secondary" data-rating-move="-1" aria-label="Move ${esc(label)} up" ${index === 0 ? 'disabled' : ''}>&#8593;</button><button type="button" class="secondary" data-rating-move="1" aria-label="Move ${esc(label)} down" ${index === all.length - 1 ? 'disabled' : ''}>&#8595;</button><label class="rating-row-check"><span class="sr">Show ${esc(label)} on title pages</span><input type="checkbox" data-rating-display="${source}" ${prefs.display === 'all' || prefs.display.includes(source) ? 'checked' : ''}></label></li>`;
    })
    .join(
      ''
    )}</ol></div><button type="button" id="rating-preferences-save" class="secondary">Save rating preferences</button><p id="rating-preferences-status" class="muted" role="status"></p></div>`;
}

function ratingConnectionMarkup() {
  return `<div class="connection"><h2>MDBList - additional ratings</h2><p class="muted">IMDb, Rotten Tomatoes critics and audience, Letterboxd, Metacritic and other scores when available. An API key is required; caching reduces requests. Episode and season scores are never replaced with a series score.</p><label>API key<input name="mdblist-key" type="password" autocomplete="new-password" placeholder="${state.settings.mdblist?.configured ? 'Saved - leave blank to keep' : 'MDBList API key'}"></label><a href="https://mdblist.com/preferences/" target="_blank" rel="noopener noreferrer">Get an MDBList API key</a> <button type="button" class="secondary" data-test="mdblist">Test connection</button></div>`;
}
document.addEventListener?.('click', (e) => {
  const button = e.target.closest('[data-rating-move]');
  if (!button) return;
  const row = button.closest('[data-rating-order]'),
    other =
      Number(button.dataset.ratingMove) < 0 ? row.previousElementSibling : row.nextElementSibling;
  if (!other) return;
  if (Number(button.dataset.ratingMove) < 0) row.parentNode.insertBefore(row, other);
  else row.parentNode.insertBefore(other, row);
  const rows = [...row.parentNode.children];
  rows.forEach((li, index) => {
    li.querySelector('[data-rating-move="-1"]').disabled = index === 0;
    li.querySelector('[data-rating-move="1"]').disabled = index === rows.length - 1;
  });
  button.focus();
});
function syncRatingDisplay() {
  document.querySelectorAll('[data-rating-display]').forEach((input) => {
    input.disabled = false;
  });
}
document.addEventListener?.('change', (e) => {
  if (e.target.id === 'rating-display-all')
    document
      .querySelectorAll('[data-rating-display]')
      .forEach((input) => (input.checked = e.target.checked));
  if (e.target.matches?.('[data-rating-display]')) {
    $('rating-display-all').checked = [...document.querySelectorAll('[data-rating-display]')].every(
      (input) => input.checked
    );
  }
});
function ratingPreferencesFromRows(rows) {
  const order = rows.map((row) => row.dataset.ratingOrder),
    enabled = rows
      .filter((row) => row.querySelector('[data-rating-display]').checked)
      .map((row) => row.dataset.ratingOrder);
  if (!enabled.length) throw Error('Choose at least one rating source.');
  return { order, main: enabled[0], display: enabled.length === order.length ? 'all' : enabled };
}
document.addEventListener?.('click', (e) => {
  const button = e.target.closest('#rating-preferences-save');
  if (!button) return;
  task(button, async () => {
    let prefs;
    try {
      prefs = ratingPreferencesFromRows([...document.querySelectorAll('[data-rating-order]')]);
    } catch (error) {
      $('rating-preferences-status').textContent = error.message;
      return;
    }
    state.rating_preferences = await api('ratings/preferences', prefs);
    repaintRatings();
    render();
    $('rating-preferences-status').textContent = 'Rating preferences saved.';
  });
});

const metadataCache = new Map();
const metadataKey = (i) =>
  JSON.stringify([
    i.type,
    i.tmdb,
    i.tvdb,
    i.imdb,
    i.show_tmdb,
    i.show_tvdb,
    i.show_imdb,
    i.season,
    i.episode,
    i.title,
  ]);
let metadataObserver,
  metadataTimer,
  metadataRetryTimer,
  metadataLoading = false,
  sortLoading = false;
const metadataQueue = new Map(),
  visibleMetadata = new Map(),
  metadataAttempts = new Map();
function metadataNeedsLoad(item) {
  const key = metadataKey(item),
    value = metadataCache.get(key);
  return (
    !value ||
    Boolean(
      value.error && (metadataAttempts.get(key) || 0) < 3 && (value.retry_at || 0) <= Date.now()
    )
  );
}
function storeListMetadata(item, details, error) {
  const key = metadataKey(item),
    existing = metadataCache.get(key);
  if (!details && existing && !existing.error) return;
  if (existing && !existing.error && !existing.summary_only) return;
  if (details) {
    metadataCache.set(key, details);
    metadataAttempts.delete(key);
  } else {
    const attempts = metadataAttempts.get(key) || 1;
    metadataCache.set(key, {
      error: error || 'Metadata response was incomplete.',
      retry_at: Date.now() + Math.min(1000 * 4 ** (attempts - 1), 16000),
    });
  }
}
function scheduleMetadataRetries() {
  clearTimeout(metadataRetryTimer);
  if (sortLoading || !state.settings.tmdb?.configured) return;
  let delay = Infinity;
  for (const q of visibleMetadata.values()) {
    const cached = metadataCache.get(q.key);
    if (q.listId === active && cached?.error && (metadataAttempts.get(q.key) || 0) < 3)
      delay = Math.min(delay, Math.max(0, (cached.retry_at || 0) - Date.now()));
  }
  if (Number.isFinite(delay))
    metadataRetryTimer = setTimeout(
      () => {
        for (const q of visibleMetadata.values())
          if (q.listId === active && metadataNeedsLoad(q.item)) metadataQueue.set(q.item.id, q);
        loadVisibleMetadata();
      },
      Math.max(delay, 100)
    );
}
function observeMetadata() {
  metadataObserver?.disconnect();
  metadataQueue.clear();
  visibleMetadata.clear();
  clearTimeout(metadataRetryTimer);
  if (sortLoading || !state.settings.tmdb?.configured) return;
  const listId = active;
  metadataObserver = new IntersectionObserver(
    (records) => {
      if (listId !== active) return;
      for (const record of records) {
        const item = current()?.items.find((i) => i.id === record.target.dataset.entry);
        if (!item) continue;
        const key = metadataKey(item);
        if (!record.isIntersecting) {
          visibleMetadata.delete(key);
          metadataQueue.delete(item.id);
          continue;
        }
        const q = { item, listId, key };
        visibleMetadata.set(key, q);
        if (metadataNeedsLoad(item)) metadataQueue.set(item.id, q);
      }
      clearTimeout(metadataTimer);
      metadataTimer = setTimeout(loadVisibleMetadata, 100);
      scheduleMetadataRetries();
    },
    { rootMargin: '350px' }
  );
  document.querySelectorAll('[data-entry]').forEach((el) => metadataObserver.observe(el));
}
async function loadVisibleMetadata() {
  if (metadataLoading || sortLoading || !metadataQueue.size) return;
  metadataLoading = true;
  const batch = [...metadataQueue.values()]
    .filter((q) => q.listId === active && metadataNeedsLoad(q.item))
    .slice(0, 12);
  batch.forEach((q) => {
    metadataQueue.delete(q.item.id);
    metadataAttempts.set(q.key, (metadataAttempts.get(q.key) || 0) + 1);
  });
  try {
    if (batch.length) {
      const result = await api('metadata', {
        list_id: batch[0].listId,
        ids: batch.map((q) => q.item.id),
      });
      for (const q of batch) {
        const item = result.items.find((r) => r.id === q.item.id);
        storeListMetadata(q.item, item?.details, item?.error);
        if (active === q.listId) {
          paintMetadata(q.item);
          metadataHealth();
        }
      }
    }
  } catch (e) {
    for (const q of batch) {
      storeListMetadata(q.item, null, e.message);
      if (active === q.listId) {
        paintMetadata(q.item);
        metadataHealth();
      }
    }
  } finally {
    metadataLoading = false;
    if (
      !sortLoading &&
      ['rating', 'date', 'runtime'].some((field) => $('sort').value.startsWith(field))
    )
      render();
    for (const [id, q] of metadataQueue)
      if (q.listId !== active || !metadataNeedsLoad(q.item)) metadataQueue.delete(id);
    if (metadataQueue.size) setTimeout(loadVisibleMetadata, 50);
    scheduleMetadataRetries();
  }
}
function metadataFailureText(item) {
  return (metadataAttempts.get(metadataKey(item)) || 0) < 3
    ? 'Metadata temporarily unavailable · retrying automatically…'
    : 'Metadata unavailable · retry loading';
}
function metadataRetryButton(item) {
  return `<button class="person-link" data-retry-metadata="${esc(item.id)}">Retry metadata</button>`;
}
function paintMetadata(item) {
  const m = metadataCache.get(metadataKey(item));
  if (!m) return;
  for (const element of document.querySelectorAll('[data-entry]')) {
    if (element.dataset.entry !== item.id) continue;
    if (isIgnored({ ...item, ...m })) {
      element.remove();
      continue;
    }
    const overview = element.querySelector('.entry-overview');
    if (m.error)
      overview.innerHTML = esc(metadataFailureText(item)) + ' ' + metadataRetryButton(item);
    else
      overview.textContent =
        (m.overview_scope === 'series' ? 'Series: ' : '') +
        (m.overview || 'No synopsis available.');
    const rating = element.querySelector('.entry-rating');
    rating.innerHTML = m.error ? '' : ratingWidget({ ...item, ...m });
    const parent = element.querySelector('[data-show]');
    if (parent && m.show_title) parent.textContent = m.show_title;
    const art = element.querySelector('.entry-art');
    if (m.poster) art.innerHTML = posterArt(m.poster, { ...item, ...m });
  }
}
function toast(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => ($('toast').hidden = true), 7000);
}
async function api(path, body) {
  const response = await fetch('/api/' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Listweavarr-Token': state.csrf },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Request failed');
  return result;
}
for (const [id, revoke] of [
  ['playlist-artwork-pair', false],
  ['playlist-artwork-revoke', true],
]) {
  $(id).onclick = async () => {
    $(id).disabled = true;
    try {
      const result = await api('playlist-companion/pair', { revoke });
      $('playlist-artwork-code').value = revoke
        ? ''
        : JSON.stringify({
            url: location.origin,
            token: result.token,
            progressToken: result.progressToken,
            serverId: result.serverId,
          });
      $('playlist-artwork-label').hidden = revoke;
      $('playlist-artwork-status').textContent = revoke
        ? 'Artwork pairing revoked. Cached images remain on paired devices.'
        : `Copy this pairing into Plex’s companion settings. ${result.mapped} existing playlists matched by exact item order. Creating another pairing revokes the previous one.`;
    } catch (error) {
      $('playlist-artwork-status').textContent = error.message;
    } finally {
      $(id).disabled = false;
    }
  };
}
async function task(button, fn) {
  if (busy) return;
  busy = true;
  button.disabled = true;
  $('sort').disabled = true;
  updateSelection();
  button.setAttribute?.('aria-busy', 'true');
  try {
    await fn();
  } catch (e) {
    toast(e.message);
  } finally {
    busy = false;
    button.removeAttribute?.('aria-busy');
    button.disabled = false;
    $('sort').disabled = false;
    updateSelection();
  }
}
function sortEntries(items, mode) {
  if (!mode || mode === 'original') return items;
  const [field, direction] = mode.split('-'),
    sign = direction === 'desc' ? -1 : 1;
  const value = (i) => {
    const m = metadataCache.get(metadataKey(i));
    if (field === 'title') return i.title.toLocaleLowerCase();
    if (field === 'rating') return preferredRating({ ...i, ...m }, true)?.score ?? null;
    if (field === 'runtime') return m?.runtime ?? null;
    if (field === 'date') return m?.release_date || null;
    return null;
  };
  return [...items].sort((a, b) => {
    const x = value(a),
      y = value(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * sign;
  });
}
function ignoredTokens(row, parent = false) {
  const kind = parent ? 'show' : row.type || 'movie',
    suffix = ['season', 'episode'].includes(kind)
      ? ':' + (row.season ?? '') + ':' + (row.episode ?? '')
      : '';
  const keys = [];
  for (const provider of ['tmdb', 'imdb', 'tvdb']) {
    const value = row[(parent || ['season', 'episode'].includes(kind) ? 'show_' : '') + provider];
    if (value) keys.push(kind + ':' + provider + ':' + value + suffix);
  }
  const title = row[parent ? 'show_title' : 'title'];
  if (title)
    keys.push(
      kind +
        ':title:' +
        title.toLowerCase().replace(/[^a-z0-9]/g, '') +
        ':' +
        (row.year || '') +
        suffix
    );
  return keys;
}
function isIgnored(row) {
  const keys = new Set([
    ...ignoredTokens(row),
    ...(['season', 'episode'].includes(row.type) ? ignoredTokens(row, true) : []),
  ]);
  return (state.ignored_titles || []).some((r) => r.tokens.some((k) => keys.has(k)));
}
function ignoreButton(row) {
  row = Object.fromEntries(
    [
      'type',
      'title',
      'year',
      'tmdb',
      'imdb',
      'tvdb',
      'show_tmdb',
      'show_imdb',
      'show_tvdb',
      'show_title',
      'season',
      'episode',
    ]
      .filter((k) => row[k] != null)
      .map((k) => [k, row[k]])
  );
  return `<button class="ignore-title" data-ignore-title="${esc(JSON.stringify(row))}" title="Hide this title across lists and Explore">Ignore title</button>`;
}
function drawIgnored() {
  $('ignored-items').innerHTML =
    (state.ignored_titles || [])
      .map(
        (r) =>
          `<div class="ignored-row"><span>${esc(r.title)} <small>${esc(r.type)}</small></span><button class="secondary" data-restore-title="${esc(r.id)}">Restore</button></div>`
      )
      .join('') || '<p>No ignored titles.</p>';
}
async function updateIgnored(body, remove = false) {
  const result = await api(remove ? 'ignore/remove' : 'ignore/add', body);
  state.ignored_titles = result.ignored_titles;
  for (const button of document.querySelectorAll('[data-ignore-title]')) {
    if (isIgnored(JSON.parse(button.dataset.ignoreTitle)))
      button.closest('.explore-card')?.remove();
  }
  for (const id of [...selected]) {
    const row = current()?.items.find((r) => r.id === id);
    if (row && isIgnored(row)) selected.delete(id);
  }
  render();
  drawIgnored();
  if (workspacePanel === 'discovery-dialog' && discoveryContext) drawDiscovery();
  if (typeof exploreHomeLoaded !== 'undefined') {
    exploreHomeLoaded = false;
    for (const [key, row] of explorePicks) if (isIgnored(row)) explorePicks.delete(key);
    if (workspacePanel === 'trakt-explore') await loadExploreHome();
  }
  if (typeof traktPreview !== 'undefined' && traktPreview) traktRenderPreview();
}
document.addEventListener?.(
  'click',
  (e) => {
    const ignore = e.target.closest('[data-ignore-title]'),
      restore = e.target.closest('[data-restore-title]'),
      manage = e.target.closest('[data-manage-ignored]');
    if (ignore) {
      e.preventDefault();
      e.stopImmediatePropagation();
      task(ignore, () => updateIgnored({ item: JSON.parse(ignore.dataset.ignoreTitle) }));
    } else if (restore)
      task(restore, () => updateIgnored({ id: restore.dataset.restoreTitle }, true));
    else if (manage) {
      drawIgnored();
      settingsView(false);
      selectListsTab('ignored');
    }
  },
  true
);
$('ignored-close').onclick = () => selectListsTab('mine');
function matchesMovieYear(i) {
  if (i.type !== 'movie') return true;
  const low = Number($('year-from').value) || 0,
    high = Number($('year-to').value) || 9999;
  if (!$('year-from').value && !$('year-to').value) return true;
  const m = metadataCache.get(metadataKey(i)),
    year = Number((m?.release_date || i.year || '').toString().slice(0, 4));
  return !!year && year >= low && year <= high;
}
function visible() {
  return sortEntries(
    (current()?.items || []).filter((i) => {
      const s = i.status || 'unchecked';
      return (
        matchesMovieYear(i) &&
        !isIgnored({ ...i, ...metadataCache.get(metadataKey(i)) }) &&
        (filter === 'all' ||
          (filter === 'missing' && ['missing', 'partial'].includes(s)) ||
          (filter === 'available' && s === 'available') ||
          (filter === 'review' && ['unmatched', 'review', 'unchecked'].includes(s))) &&
        (i.title + ' ' + (i.show_title || ''))
          .toLowerCase()
          .includes($('search').value.toLowerCase())
      );
    }),
    $('sort').value
  );
}
async function applySort() {
  if (busy || !current()) return;
  const mode = $('sort').value,
    listId = active;
  if (mode === 'original' || mode.startsWith('title')) {
    render();
    $('sort-progress').textContent = 'View sorted. Playlists retain the selected watch order.';
    return;
  }
  if (!state.settings.tmdb?.configured) {
    $('sort').value = 'original';
    toast('Connect TMDB before sorting by ratings, release dates, or runtimes.');
    return;
  }
  busy = true;
  sortLoading = true;
  $('sort').disabled = true;
  metadataObserver?.disconnect();
  metadataQueue.clear();
  const items = current().items.filter(
    (i) => !metadataCache.get(metadataKey(i)) || metadataCache.get(metadataKey(i)).error
  );
  let next = 0,
    completed = 0,
    failed = 0,
    lastSortRender = 0;
  const progress = () => {
    $('sort-progress').textContent =
      `Sorting by ${mode.split('-')[0]}: ${completed}/${items.length} remaining titles checked. Results update as metadata arrives; unknown values stay last.`;
  };
  progress();
  render();
  try {
    async function worker() {
      while (next < items.length && active === listId) {
        const start = next;
        next += 20;
        const batch = items.slice(start, start + 20);
        try {
          const result = await api('metadata', { list_id: listId, ids: batch.map((i) => i.id) });
          for (const entry of result.items) {
            const item = batch.find((i) => i.id === entry.id);
            if (!item) continue;
            const key = metadataKey(item);
            if (entry.details) metadataCache.set(key, entry.details);
            else {
              failed++;
              if (!metadataCache.get(key) || metadataCache.get(key).error)
                metadataCache.set(key, { error: entry.error });
            }
          }
        } catch (e) {
          failed += batch.length;
          for (const item of batch) storeListMetadata(item, null, e.message);
        }
        completed += batch.length;
        if (active === listId) {
          progress();
          if (Date.now() - lastSortRender >= 250) {
            lastSortRender = Date.now();
            render();
          } else {
            for (const item of batch) paintMetadata(item);
            metadataHealth();
          }
        }
      }
    }
    await Promise.all([worker(), worker()]);
    if (
      active === listId &&
      mode.startsWith('rating') &&
      (state.rating_preferences?.main || 'tmdb') !== 'tmdb'
    ) {
      $('sort-progress').textContent =
        'Loading preferred-source ratings for this list. Missing scores stay last.';
      await ensureRatings(
        current().items.map((i) => ({ ...i, ...metadataCache.get(metadataKey(i)) }))
      );
    }
    if (active === listId)
      $('sort-progress').textContent = failed
        ? `Sorted available metadata. ${failed} titles could not be loaded; unknown values appear last. Select the sort again to retry.`
        : 'Sort complete. Unrated or unknown values appear last. Playlists retain the selected watch order.';
  } finally {
    busy = false;
    sortLoading = false;
    $('sort').disabled = false;
    if (active === listId) render();
    else updateSelection();
  }
}
$('sort').onchange = applySort;
const requestable = (i) =>
  ['missing', 'partial'].includes(i.status) && !activityFor(i)?.prevent_duplicate;
function updateSelection() {
  const tray = $('review').closest?.('.request-bar');
  if (tray) tray.hidden = !selected.size;
  $('selection-count').textContent = selected.size + ' selected';
  $('review').disabled = busy || !selected.size;
  $('review-top').disabled = busy || !selected.size;
  const chosen = (current()?.items || []).filter((item) => selected.has(item.id));
  const services = [
    ...new Set(chosen.map((item) => (item.type === 'movie' ? 'Radarr' : 'Sonarr'))),
  ];
  const addLabel = selected.size
    ? `Add ${selected.size} to ${services.join(' / ')}`
    : 'Add selected to Radarr / Sonarr';
  $('review-top').textContent = addLabel;
  $('review').textContent = addLabel;
  $('selection-clear').disabled = busy || !selected.size;
  $('compare').disabled = busy || !current();
  $('refresh-list').disabled = busy || !current()?.source;
  $('resolve-metadata').disabled = busy || !current() || !state.settings.tmdb?.configured;
  $('playlist-open').disabled = busy || !current()?.items.some((i) => i.plex_keys?.length);
  $('list-select').disabled = busy;
  $('source-note').textContent = current()?.warnings?.length
    ? `${current().warnings.length} metadata warnings · entries retained for review`
    : current()?.source
      ? 'Linked list · refresh keeps your corrections'
      : '';
  $('request-summary').textContent = selected.size
    ? `${selected.size} entries selected. Choose a profile and destination before sending.`
    : 'Use Add beside a missing title, or select titles to add together.';
  const eligible = visible().filter(requestable);
  const selectLabel = $('select-all').closest?.('label');
  if (selectLabel) selectLabel.hidden = !current();
  $('select-all').disabled = busy || !eligible.length;
  $('select-all-label').textContent = `Select all missing (${eligible.length})`;
  $('selection-help').textContent = eligible.length
    ? 'Select all includes every matching missing or partial entry, including those below the screen. Search and year filters apply. Already requested items are skipped.'
    : visible().some((item) => ['missing', 'partial'].includes(item.status))
      ? 'These missing entries are already requested or managed. Check download progress for their current status.'
      : 'No requestable missing entries match this view. Compare with Plex to refresh availability.';
  $('selection-count').hidden = !eligible.length && !selected.size;
  $('select-all').checked = eligible.length > 0 && eligible.every((i) => selected.has(i.id));
  $('select-all').indeterminate =
    eligible.some((i) => selected.has(i.id)) && !$('select-all').checked;
}
function row(i) {
  const rank = current().items.indexOf(i) + 1,
    m = metadataCache.get(metadataKey(i));
  const type =
    i.type === 'episode'
      ? `EPISODE · S${i.season ?? '?'} E${i.episode ?? '?'}`
      : i.type === 'season'
        ? `SEASON ${i.season ?? '?'}`
        : i.type.toUpperCase();
  const overview = m
    ? m.overview || (m.error && metadataFailureText(i)) || 'No synopsis available.'
    : state.settings.tmdb?.configured
      ? 'Loading synopsis…'
      : 'Connect TMDB to see descriptions and ratings.';
  const rating = m && !m.error ? ratingWidget({ ...i, ...m }) : '';
  const service = i.type === 'movie' ? 'Radarr' : 'Sonarr';
  return `<article class="entry" data-entry="${i.id}"><input type="checkbox" aria-label="Select ${esc(i.title)}" data-item="${i.id}" ${selected.has(i.id) ? 'checked' : ''} ${requestable(i) ? '' : 'disabled'}><span class="rank">${String(rank).padStart(2, '0')}</span><button class="entry-art" data-details="${i.id}" aria-label="Details for ${esc(i.title)}">${m?.poster ? posterArt(m.poster, { ...i, ...m }) : `<span>${esc(i.title.charAt(0))}</span>`}</button><div class="entry-copy"><div class="entry-title"><button data-details="${i.id}" class="title-link">${esc(i.title)}</button> ${i.year ? `<span class="muted">(${esc(i.year)})</span>` : ''}</div><div class="entry-kicker">${i.is_new ? '<span class="badge available">New in source</span> ' : ''}${esc(type)}${i.type !== 'movie' ? ` · <button class="show-link" data-show="${i.id}">${esc(m?.show_title || i.show_title || (i.type === 'show' ? 'Explore full show' : 'View full show'))}</button>` : ''} <span class="entry-rating">${rating}</span></div><p class="entry-overview">${esc(overview)}${m?.error ? ' ' + metadataRetryButton(i) : ''}</p><div class="entry-meta">${esc(i.detail || 'Compare with Plex to check availability')} · <button class="edit-entry" data-edit="${i.id}" aria-label="Correct ${esc(i.title)}">Correct match</button> ${window.watchBadgeFor?.(i) || ''} ${activityBadge(i)}</div></div><div class="entry-controls">${ignoreButton({ ...i, ...m })}<span class="badge ${esc(i.status || 'unchecked')}">${esc({ unchecked: 'Not checked', available: 'In Plex', missing: 'Missing', partial: 'Partial', review: 'Review match', unmatched: 'Unmatched', upcoming: 'Not aired' }[i.status || 'unchecked'])}</span>${requestable(i) ? `<button class="primary add-one" data-add="${i.id}">+ Add to ${service}</button>` : ''}</div></article>`;
}
function renderGroups(items) {
  const groups = new Map();
  for (const item of items) {
    const tvdb = item.type === 'show' ? item.tvdb : item.show_tvdb;
    const tmdb = item.type === 'show' ? item.tmdb : item.show_tmdb;
    const key =
      item.type === 'movie'
        ? `movie:${item.id}`
        : tvdb
          ? 'tvdb:' + tvdb
          : tmdb
            ? 'tmdb:' + tmdb
            : (item.show_title || item.title).toLowerCase();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return [...groups.values()]
    .map((group) => {
      if (group[0].type === 'movie') return row(group[0]);
      const seasons = new Map(),
        wholeShow = [];
      for (const item of group) {
        if (item.type === 'show') {
          wholeShow.push(item);
          continue;
        }
        const season = item.season ?? '?';
        if (!seasons.has(season)) seasons.set(season, []);
        seasons.get(season).push(item);
      }
      const content =
        wholeShow.map(row).join('') +
        [...seasons]
          .map(
            ([season, entries]) =>
              `<details open class="season-group"><summary>Season ${esc(season)} · ${entries.length} list entries</summary>${entries.map(row).join('')}</details>`
          )
          .join('');
      return `<details open class="group"><summary>${esc(group[0].show_title || group[0].title)} · ${group.length} list entries</summary>${content}</details>`;
    })
    .join('');
}
function renderListUpdates() {
  const list = current();
  if (!list) {
    $('list-updates').innerHTML = '';
    return;
  }
  const report = list.refresh_report,
    changes = list.availability_report || [];
  $('list-updates').innerHTML =
    (report
      ? `<details class="list-update-report"><summary>Last source refresh: ${report.added.length} added, ${report.removed.length} removed${report.order_changed ? ' / order changed' : ''}${report.changed.length ? ' / ' + report.changed.length + ' scope changes' : ''}</summary>${[
          ['Added', report.added],
          ['Removed', report.removed],
          ['Changed scope', report.changed],
        ]
          .map(([label, rows]) =>
            rows.length
              ? `<h4>${label}</h4><ul>${rows.map((title) => `<li>${esc(title)}</li>`).join('')}</ul>`
              : ''
          )
          .join(
            ''
          )}<p>Compare with Plex to update availability after refreshing the source.</p></details>`
      : '') +
    (changes.length
      ? `<details class="list-update-report"><summary>${changes.length} availability changes since the previous comparison</summary><ul>${changes.map((r) => `<li>${esc(r.title)}: ${esc(r.from)} &rarr; ${esc(r.to)}</li>`).join('')}</ul></details>`
      : '') +
    (list.warnings?.length
      ? `<details class="list-update-report"><summary>${list.warnings.length} import notes / matching guidance</summary><ul>${list.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></details>`
      : '') +
    (list.playlist_needs_update
      ? `<p class="metadata-error">Your linked Plex playlist has updates to review. <button class="secondary" data-review-publication="${esc(list.id)}">Review Plex update</button></p>`
      : '');
}
function render() {
  const all = state.lists.flatMap((l) => l.items);
  $('list-count').textContent = state.lists.length;
  $('item-count').textContent = all.length;
  $('available-count').textContent = all.filter((i) => i.status === 'available').length;
  $('missing-count').textContent = all.filter(requestable).length;
  $('list-select').innerHTML =
    '<option value="">Choose a list</option>' +
    state.lists.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
  $('list-select').value = active;
  $('activity-list-select').innerHTML = $('list-select').innerHTML;
  $('activity-list-select').value = active;
  $('active-name').textContent = current()?.name || 'My lists';
  $('list-context').textContent = current()
    ? `${current().items.length} entries in this collection. Explore titles, check Plex, or review missing items.`
    : 'Import a list to start building your collection.';
  const items = visible();
  if (!current())
    $('entries').innerHTML =
      '<div class="empty"><div class="symbol">▤</div><h2>A place for every watchlist.</h2><p>Import a public list URL, CSV, or JSON to begin.<br>Movies, shows, seasons, and individual episodes welcome.</p></div>';
  else if (!items.length)
    $('entries').innerHTML =
      '<div class="empty"><h2>No entries match this view.</h2><p>Try a different search, year range or availability filter.</p><button type="button" class="secondary" data-reset-list-filters>Clear search &amp; filters</button></div>';
  else
    $('entries').innerHTML =
      $('view').value === 'group' ? renderGroups(items) : items.map(row).join('');
  $('source-note').title = (current()?.warnings || []).join('\n');
  renderListUpdates();
  window.renderTraktSavedInfo?.();
  updateSelection();
  observeMetadata();
  metadataHealth();
}
let workspacePanel = 'workspace',
  listScroll = 0,
  titleScroll = 0;
let titleBackStack = [],
  externalTitle = null;
function scrollWorkspace(top = 0) {
  if (window.scrollTo) window.scrollTo({ top, behavior: 'instant' });
}
function openWorkspacePanel(id) {
  if (workspacePanel === 'workspace') listScroll = window.scrollY || 0;
  if (workspacePanel === 'title-dialog') titleScroll = window.scrollY || 0;
  workspacePanel = id;
  for (const panel of [
    'workspace',
    'settings',
    'title-dialog',
    'discovery-dialog',
    'trakt-explore',
    'requests-page',
  ])
    $(panel).hidden = panel !== id;
  $('breadcrumb').textContent =
    id === 'discovery-dialog'
      ? 'EXPLORE PROJECTS'
      : id === 'title-dialog'
        ? 'TITLE DETAILS'
        : current()?.name || 'MY LISTS';
  $('trakt-nav').classList.toggle('active', id === 'trakt-explore');
  $('requests-nav').classList.toggle('active', id === 'requests-page');
  scrollWorkspace();
  $(id).focus?.({ preventScroll: true });
}
function closeWorkspacePanel(id) {
  if (id === 'discovery-dialog') {
    ++discoverySequence;
    if (discoveryReturnPage) {
      const page = discoveryReturnPage;
      discoveryReturnPage = null;
      restoreBrowsePage(page);
    } else {
      openWorkspacePanel('title-dialog');
      $('breadcrumb').textContent = $('title-heading')?.textContent || 'TITLE DETAILS';
      scrollWorkspace(titleScroll);
    }
  } else if (titleBackStack.length) {
    restoreBrowsePage(titleBackStack.pop());
  } else {
    ++titleSequence;
    externalTitle = null;
    openWorkspacePanel('workspace');
    scrollWorkspace(listScroll);
  }
}
let listsTab = 'mine',
  officialLoaded = false;
function setTabGroup(attribute, name, panelFor) {
  document.querySelectorAll('[' + attribute + ']').forEach((button) => {
    const selected = button.getAttribute(attribute) === name;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(panelFor(button.getAttribute(attribute))).hidden = !selected;
  });
}
function bindTabKeys(attribute, select) {
  const buttons = [...document.querySelectorAll('[' + attribute + ']')];
  buttons.forEach((button, index) => {
    button.onclick = () => select(button.getAttribute(attribute));
    button.onkeydown = (e) => {
      const next =
        e.key === 'ArrowRight'
          ? (index + 1) % buttons.length
          : e.key === 'ArrowLeft'
            ? (index + buttons.length - 1) % buttons.length
            : e.key === 'Home'
              ? 0
              : e.key === 'End'
                ? buttons.length - 1
                : null;
      if (next !== null) {
        e.preventDefault();
        select(buttons[next].getAttribute(attribute));
        buttons[next].focus();
      }
    };
  });
}
function selectListsTab(name) {
  if (!['mine', 'official', 'ignored', 'downloads'].includes(name)) return;
  listsTab = name;
  setTabGroup(
    'data-lists-tab',
    name,
    (key) =>
      ({
        mine: 'lists-mine',
        official: 'lists-official',
        ignored: 'ignored-dialog',
        downloads: 'activity-panel',
      })[key]
  );
  if (name === 'ignored') drawIgnored();
  if (name === 'official') loadOfficialLists();
  if (name === 'downloads')
    loadActivity().catch((e) => ($('activity-status').textContent = e.message));
  if (!$('workspace').hidden)
    $('breadcrumb').textContent =
      'LISTS / ' +
      {
        mine: 'MY LISTS',
        official: 'OFFICIAL LISTS',
        ignored: 'IGNORED TITLES',
        downloads: 'DOWNLOAD PROGRESS',
      }[name];
}
let officialCatalogue = [];
async function loadOfficialLists() {
  if (officialLoaded) {
    drawOfficialCatalogue();
    return;
  }
  $('official-status').textContent = 'Loading official catalogue...';
  try {
    const data = await api('explore/official', {});
    $('official-status').textContent = data.note;
    officialCatalogue = data.lists;
    officialLoaded = true;
    drawOfficialCatalogue();
  } catch (e) {
    $('official-status').textContent = e.message;
  }
}
bindTabKeys('data-lists-tab', selectListsTab);
$('official-items').onclick = (e) => {
  const button = e.target.closest('[data-official-open]');
  if (button)
    task(button, async () => {
      const result = await api('explore/official/open', {
        official_id: button.dataset.officialOpen,
      });
      replaceList(result.entry);
    });
};
$('activity-list-select').onchange = (e) => {
  active = e.target.value;
  localStorage.setItem('reelcheck-active-list', active);
  selected.clear();
  render();
  loadActivity().catch((error) => ($('activity-status').textContent = error.message));
};
let settingsTab = 'preferences';
function selectSettingsTab(name) {
  if (!['preferences', 'connections', 'requests', 'notifications', 'backups'].includes(name))
    return;
  settingsTab = name;
  document.querySelectorAll('[data-settings-tab]').forEach((button) => {
    const selected = button.dataset.settingsTab === name;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $('settings-' + button.dataset.settingsTab).hidden = !selected;
  });
  if (!$('settings').hidden) $('breadcrumb').textContent = 'SETTINGS / ' + name.toUpperCase();
}
document.querySelectorAll('[data-settings-tab]').forEach((button) => {
  button.onclick = () => selectSettingsTab(button.dataset.settingsTab);
  button.onkeydown = (e) => {
    const names = ['preferences', 'connections', 'requests', 'notifications', 'backups'],
      index = names.indexOf(settingsTab);
    let next;
    if (e.key === 'ArrowRight') next = names[(index + 1) % names.length];
    else if (e.key === 'ArrowLeft') next = names[(index + names.length - 1) % names.length];
    else if (e.key === 'Home') next = names[0];
    else if (e.key === 'End') next = names[names.length - 1];
    if (next) {
      e.preventDefault();
      selectSettingsTab(next);
      $('settings-tab-' + next).focus();
    }
  };
});
document.addEventListener?.('click', (e) => {
  const link = e.target.closest('[data-settings-open]');
  if (link) {
    settingsView(true);
    selectSettingsTab(link.dataset.settingsOpen);
    window.scrollTo?.(0, 0);
  }
});
function settingsView(show) {
  $('title-save').hidden = true;
  titleBackStack = [];
  externalTitle = null;
  ++titleSequence;
  ++discoverySequence;
  openWorkspacePanel(show ? 'settings' : 'workspace');
  $('settings-nav').classList.toggle('active', show);
  $('library-nav').classList.toggle('active', !show);
  $('breadcrumb').textContent = show
    ? 'SETTINGS / ' + settingsTab.toUpperCase()
    : current()?.name || 'MY LISTS';
}

const renderConnectionsBeforeRatings = renderArr;
renderArr = function () {
  renderConnectionsBeforeRatings();
  $('connection-fields').insertAdjacentHTML('beforeend', ratingConnectionMarkup());
  $('rating-preferences-host').innerHTML = ratingPreferencesMarkup();
  syncRatingDisplay();
};
function renderPlex() {
  const login = state.plex_login || {},
    cfg = state.settings.plex || {};
  $('plex-account').textContent = login.signed_in
    ? `Signed in as ${login.account}`
    : 'Connect your Plex account to find your servers.';
  $('plex-connected').textContent = cfg.configured
    ? `Connected to ${cfg.server_name || 'Plex'} · ${cfg.url}`
    : 'No server selected yet.';
  $('plex-signin').textContent = login.signed_in
    ? 'Sign in with another account'
    : 'Sign in with Plex';
  $('plex-disconnect').hidden = !login.signed_in && !cfg.configured;
  $('plex-load-servers').hidden = !login.signed_in;
  $('plex-check-login').hidden = !login.pending;
  $('plex-test').hidden = !cfg.configured;
  if (!login.signed_in) $('plex-server-picker').hidden = true;
}
function renderArr() {
  $('connection-fields').innerHTML =
    ['radarr', 'sonarr']
      .map((service) => {
        const cfg = state.settings[service] || {};
        return `<div class="connection"><h2>${service === 'radarr' ? 'Radarr · movies' : 'Sonarr · television'}</h2><div class="fields"><label>Server address<input type="url" name="${service}-url" value="${esc(cfg.url)}" placeholder="http://192.168.1.20:${service === 'radarr' ? '7878' : '8989'}"></label><label>API key<input type="password" autocomplete="new-password" name="${service}-key" placeholder="${cfg.configured ? 'Saved · leave blank to keep' : 'Enter your key'}"></label></div><button type="button" class="secondary" data-test="${service}">Test connection</button></div>`;
      })
      .join('') +
    `<div class="connection"><h2>TMDB · optional metadata</h2><p class="muted">Resolve IMDb episode IDs, find parent-show TVDB IDs, and check season completeness. Letterboxd movie imports work without this.</p><label>API Read Access Token<input name="tmdb-key" type="password" autocomplete="new-password" placeholder="${state.settings.tmdb?.configured ? 'Saved · leave blank to keep' : 'TMDB API Read Access Token (Bearer token)'}"></label><button type="button" class="secondary" data-test="tmdb">Test connection</button></div><div class="connection"><h2>Trakt - public chronological lists</h2><p class="muted">Import ranked movies, shows, seasons, and episodes using the official API. Public lists need a Client ID, without a client secret or account sign-in.</p><label>Client ID<input name="trakt-key" type="password" autocomplete="new-password" placeholder="${state.settings.trakt?.configured ? 'Saved - leave blank to keep' : 'Trakt application Client ID'}"></label><button type="button" class="secondary" data-test="trakt">Test connection</button></div>`;
}
async function refreshConnections() {
  showPageCache.clear();
  const fresh = await (await fetch('/api/state')).json();
  state.settings = fresh.settings;
  extraRatingsCache.clear();
  extraRatingsPending.clear();
  repaintRatings();
  ensureRatings(
    [...document.querySelectorAll('[data-rating-row]')].map((el) =>
      JSON.parse(el.dataset.ratingRow)
    )
  );
  state.plex_login = fresh.plex_login;
  renderPlex();
  observeMetadata();
}
async function loadPlexServers() {
  const data = await api('plex/servers', {});
  $('plex-servers').innerHTML = data.servers
    .map((s) => `<option value="${esc(s.id)}">${esc(s.name)}${s.owned ? '' : ' (shared)'}</option>`)
    .join('');
  $('plex-server-picker').hidden = false;
  $('plex-connect').disabled = !data.servers.length;
  $('plex-server-message').textContent = data.servers.length
    ? 'Choose a server, then connect.'
    : 'No accessible Plex servers were found. Check the account and server sharing settings.';
}
async function finishPlexLogin() {
  const status = await api('plex/status', {});
  await refreshConnections();
  if (status.signed_in) {
    await loadPlexServers();
    toast('Signed in. Choose your Plex server.');
  } else {
    toast('Plex has not completed sign-in yet. Finish on Plex, then check again.');
  }
}
$('plex-signin').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('plex/start', {});
    window.location.assign(result.url);
  });
$('plex-check-login').onclick = (e) => task(e.target, finishPlexLogin);
$('plex-load-servers').onclick = (e) => task(e.target, loadPlexServers);
$('plex-connect').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('plex/connect', {
      server_id: $('plex-servers').value,
      url: $('plex-address').value,
    });
    await refreshConnections();
    toast('Connected to ' + result.name);
  });
$('plex-disconnect').onclick = (e) =>
  task(e.target, async () => {
    await api('plex/disconnect', {});
    await refreshConnections();
    toast('Plex disconnected from Listweavarr.');
  });
$('plex-test').onclick = (e) =>
  task(e.target, async () => {
    await api('test', { service: 'plex' });
    toast('Plex connection successful.');
  });
$('settings-nav').onclick = () => settingsView(true);
$('library-nav').onclick = () => {
  settingsView(false);
  selectListsTab('mine');
};
$('settings-form').onsubmit = (e) => {
  e.preventDefault();
  task(e.submitter, async () => {
    const form = new FormData(e.target),
      body = {};
    for (const s of ['sonarr', 'radarr', 'tmdb', 'trakt', 'tvdb', 'mdblist', 'prowlarr'])
      body[s] = {
        url:
          s === 'tmdb'
            ? 'https://api.themoviedb.org'
            : s === 'trakt'
              ? 'https://api.trakt.tv'
              : s === 'tvdb'
                ? 'https://api4.thetvdb.com'
                : s === 'mdblist'
                  ? 'https://api.mdblist.com'
                  : form.get(s + '-url'),
        key: form.get(s + '-key'),
        ...(s === 'tvdb' ? { pin: form.get('tvdb-pin') } : {}),
      };
    await api('settings', body);
    await refreshConnections();
    renderArr();
    toast('Connections saved.');
  });
};
$('connection-fields').onclick = (e) => {
  const b = e.target.closest('[data-test]');
  if (b)
    task(b, async () => {
      const service = b.dataset.test;
      const form = new FormData($('settings-form'));
      const config = {
        url:
          service === 'tmdb'
            ? 'https://api.themoviedb.org'
            : service === 'trakt'
              ? 'https://api.trakt.tv'
              : service === 'tvdb'
                ? 'https://api4.thetvdb.com'
                : service === 'mdblist'
                  ? 'https://api.mdblist.com'
                  : String(form.get(service + '-url') || '').trim(),
        key: String(form.get(service + '-key') || '').trim(),
        ...(service === 'tvdb' ? { pin: String(form.get('tvdb-pin') || '').trim() } : {}),
      };
      await api('test', { service, config });
      toast('Connection successful: ' + service + '. Save connections to keep your changes.');
    });
};
$('import-open').onclick = () => {
  $('import-replace').checked = false;
  $('import-replace').disabled = !current();
  $('import-dialog').showModal();
};
document
  .querySelectorAll('[data-close]')
  .forEach(
    (b) =>
      (b.onclick = () =>
        ['title-dialog', 'discovery-dialog'].includes(b.dataset.close)
          ? closeWorkspacePanel(b.dataset.close)
          : $(b.dataset.close).close())
  );
function replaceList(list) {
  selectListsTab('mine');
  showPageCache.clear();
  const index = state.lists.findIndex((l) => l.id === list.id);
  if (index < 0) state.lists.push(list);
  else state.lists[index] = list;
  active = list.id;
  localStorage.setItem('reelcheck-active-list', active);
  $('sort').value = 'original';
  selected.clear();
  render();
}
async function pollImport(id) {
  localStorage.setItem('reelcheck-import', id);
  while (true) {
    const response = await fetch('/api/job?id=' + encodeURIComponent(id));
    const job = await response.json();
    if (!response.ok) {
      localStorage.removeItem('reelcheck-import');
      throw Error(job.error);
    }
    $('import-progress').textContent = job.message;
    if (job.status === 'error') {
      localStorage.removeItem('reelcheck-import');
      throw Error(job.message);
    }
    if (job.status === 'complete') {
      localStorage.removeItem('reelcheck-import');
      replaceList(job.result);
      $('import-dialog').close();
      $('import-form').reset();
      toast(
        `${job.result.items.length} entries imported${job.result.warnings?.length ? '; ' + job.result.warnings.length + ' need metadata review' : ''}.`
      );
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
$('import-form').onsubmit = (e) => {
  e.preventDefault();
  task(e.submitter, async () => {
    const file = $('import-file').files[0],
      url = $('import-url').value.trim();
    if (!url && !file) throw Error('Paste a list URL or choose a CSV/JSON file.');
    if (url && file) throw Error('Import a URL or a file, one at a time.');
    if (file?.size > 7_000_000) throw Error('Please import a file smaller than 7 MB.');
    const body = {
      name: new FormData(e.target).get('name'),
      url,
      import_options: { order: $('import-order').value, seasons: $('import-seasons').value },
    };
    if (file && $('import-replace').checked) {
      if (!active) throw Error('Choose the saved list to update first.');
      body.list_id = active;
    }
    if (file)
      Object.assign(body, {
        content: await file.text(),
        format: file.name.toLowerCase().endsWith('.json') ? 'json' : 'csv',
      });
    const job = await api('import/start', body);
    await pollImport(job.job_id);
  });
};
$('refresh-list').onclick = (e) =>
  task(e.target, async () => {
    $('import-dialog').showModal();
    const job = await api('import/start', { list_id: active });
    await pollImport(job.job_id);
  });
$('resolve-metadata').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('resolve', { list_id: active });
    replaceList(result.entry);
    toast(
      result.warnings.length
        ? `${result.warnings.length} entries still need metadata review.`
        : 'Metadata resolved. Compare with Plex to update availability.'
    );
  });
let editingId = '';
let titleSequence = 0,
  openedItem = '';
function addOne(id) {
  if (busy) return;
  const item = current()?.items.find((i) => i.id === id);
  if (!item || !requestable(item)) return;
  selected.clear();
  selected.add(id);
  document
    .querySelectorAll('[data-item]')
    .forEach((input) => (input.checked = input.dataset.item === id));
  updateSelection();
  $('review').click();
}
function personLink(p) {
  return /^\d+$/.test(String(p.id || ''))
    ? `<button class="person-link" data-person="${p.id}">${esc(p.name)}</button>`
    : esc(p.name);
}
function companyLink(p) {
  return /^\d+$/.test(String(p.id || ''))
    ? `<button class="person-link" data-company="${p.id}">${esc(p.name)}</button>`
    : esc(p.name);
}
function sortPeople(people) {
  const numeric = (v) => (Number.isFinite(Number(v)) ? Math.max(0, Number(v)) : 0);
  return [...people].sort(
    (a, b) =>
      Number(Boolean(b.photo)) - Number(Boolean(a.photo)) ||
      numeric(b.episode_count) - numeric(a.episode_count) ||
      numeric(b.popularity) - numeric(a.popularity)
  );
}
function episodeCredit(p, crew = false) {
  return Number(p.episode_count) > 0
    ? `<span class="episode-credit" ${crew ? 'title="Largest episode count among the credited director and producer roles; overlapping roles are not added together."' : ''}>${Number(p.episode_count)} episode${Number(p.episode_count) === 1 ? '' : 's'}${crew ? ' in largest role' : ''}</span>`
    : '';
}
function crewStrip(m) {
  const people = new Map();
  for (const [entries, role] of [
    [m.director_people || [], 'Director'],
    [m.producer_people || [], 'Producer'],
  ])
    for (const p of entries) {
      const key = p.id ? 'id:' + p.id : 'name:' + p.name;
      if (!people.has(key)) people.set(key, { ...p, roles: [] });
      const person = people.get(key),
        job = p.job || role;
      if (!person.roles.includes(job)) person.roles.push(job);
      if (!person.photo && p.photo) person.photo = p.photo;
      person.episode_count = Math.max(
        Number(person.episode_count) || 0,
        Number(p.episode_count) || 0
      );
      person.popularity = Math.max(Number(person.popularity) || 0, Number(p.popularity) || 0);
    }
  // Preserve older metadata that has names but no person IDs.
  if (!m.director_people?.length)
    for (const name of m.directors || []) people.set('name:' + name, { name, roles: ['Director'] });
  if (!people.size) return '';
  return `<section class="cast-section portrait-cast crew-section"><h3>Directors & producers</h3><div class="cast-strip" aria-label="Director and producer portraits">${sortPeople(
    [...people.values()]
  )
    .map(
      (p) =>
        `<div class="cast-person">${p.id ? `<button class="cast-photo" data-person="${esc(p.id)}" aria-label="View ${esc(p.name)}">${p.photo ? `<img src="${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy">` : '<span>No photo</span>'}</button>` : '<div class="cast-photo">No photo</div>'}<strong>${personLink(p)}</strong><span>${esc(p.roles.join(', '))}</span>${episodeCredit(p, true)}</div>`
    )
    .join('')}</div></section>`;
}
function renderTitle(item, m) {
  const rating = m.rating != null ? `${Number(m.rating).toFixed(1)} / 10` : 'Not rated';
  const facts = [
    ['Released / aired', m.release_date],
    ['Runtime', m.runtime ? m.runtime + ' minutes' : null],
    ['Status', m.status],
    ['Original language', m.language],
    ['Country', m.countries?.join(', ')],
    ['Network', m.networks?.join(', ')],
    ['Seasons', m.seasons],
    ['Episodes', m.episodes],
  ].filter(([, v]) => v != null && v !== '');
  $('breadcrumb').textContent = m.title;
  $('title-content').innerHTML =
    `<div class="title-hero">${m.backdrop ? `<img class="hero-image" src="${esc(m.backdrop)}" alt="" referrerpolicy="no-referrer">` : ''}<div class="title-layout">${m.poster ? `<div class="title-poster">${posterArt(m.poster, { ...item, ...m })}</div>` : '<div class="title-poster poster-empty">Film</div>'}<div class="title-information"><p class="eyebrow">${esc(m.show_title || item.type.toUpperCase())}</p><h2 id="title-heading">${esc(m.title)}</h2><div class="title-rating">${ratingWidget({ ...item, ...m }, true)}<span>${esc(m.release_date?.slice(0, 4) || '')} ${m.runtime ? ' / ' + m.runtime + ' min' : ''}</span></div><div class="genre-tags">${(m.genres || []).map((g) => `<span>${esc(g)}</span>`).join('')}</div><p class="hero-synopsis full-synopsis">${esc(m.overview || 'No synopsis available.')}</p><div class="title-main-actions" aria-label="Library actions"></div><div class="title-links">${m.trailer ? `<a class="primary" href="${esc(m.trailer.url)}" target="_blank" rel="noopener noreferrer">${m.trailer.scope === 'series' ? 'Watch series trailer' : 'Watch trailer'} &#8599;</a>` : '<span class="muted">No trailer available.</span>'}<a href="${esc(m.tmdb_url)}" target="_blank" rel="noopener noreferrer">TMDB &#8599;</a>${m.imdb_url ? `<a href="${esc(m.imdb_url)}" target="_blank" rel="noopener noreferrer">IMDb &#8599;</a>` : ''}</div>${m.tagline ? `<p class="tagline">${esc(m.tagline)}</p>` : ''}<dl class="title-facts persistent-facts">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}<div><dt>Studio / production company</dt><dd>${(m.studios || []).map(companyLink).join(', ') || 'Not listed'}</dd></div>${m.creator_people?.length ? `<div><dt>Series creator</dt><dd>${m.creator_people.map(personLink).join(', ')}</dd></div>` : ''}</dl></div></div></div>
<div id="title-coverage-slot"></div>${crewStrip(m)}${
      m.cast?.length
        ? `<section class="cast-section portrait-cast"><h3>Cast</h3><div class="cast-strip" aria-label="Cast portraits">${sortPeople(
            m.cast
          )
            .map(
              (c) =>
                `<div class="cast-person">${c.id ? `<button class="cast-photo" data-person="${esc(c.id)}" aria-label="View ${esc(c.name)}">${c.photo ? `<img src="${esc(c.photo)}" alt="${esc(c.name)}" loading="lazy">` : '<span>No photo</span>'}</button>` : c.photo ? `<img class="cast-photo" src="${esc(c.photo)}" alt="${esc(c.name)}" loading="lazy">` : '<div class="cast-photo">No photo</div>'}<strong>${personLink(c)}</strong><span>${esc(c.character || '')}</span>${episodeCredit(c)}</div>`
            )
            .join('')}</div></section>`
        : ''
    }
  ${m.related_id ? `<section id="title-relationships" class="related-section" hidden><div class="section-heading"><div><p class="eyebrow">KEEP EXPLORING</p><h3>Connections & watch order</h3></div><button class="secondary" data-related="${esc(m.related_id)}" data-kind="${esc(m.related_type)}">Browse & select related titles</button></div><div id="related-preview" class="relationship-sections" role="status">Loading related titles...</div></section>` : ''}`;
  if (window.loadTraktTitleExtras) {
    $('title-content')
      .querySelector('.title-rating')
      .insertAdjacentHTML('beforeend', '<span id="trakt-title-rating" class="muted"></span>');
    $('title-content').insertAdjacentHTML(
      'beforeend',
      '<section id="trakt-title-extras" class="related-section"></section>'
    );
  }
  if (window.loadSupplementalMetadata) {
    $('title-content')
      .querySelector('.title-information')
      .insertAdjacentHTML('beforeend', '<div id="supplemental-metadata"></div>');
  }
  if (m.related_id) {
    loadRelatedPreview(m, titleSequence);
    window.loadTraktTitleExtras?.(item, m, titleSequence);
  }
}
function relationshipTile(r) {
  if (isIgnored(r)) return '';
  return `<button class="related-card ${r.current ? 'current-title-card' : ''}" data-title-tmdb="${esc(r.tmdb)}" data-title-type="${esc(r.type)}" ${r.current ? 'aria-current="true"' : ''}>${r.poster ? posterArt(r.poster, r) : ''}<strong>${esc(r.title)}</strong>${ratingWidget(r)}<small>${r.position ? r.position + '. ' : ''}${esc(r.relationship || r.group || 'Related title')}${r.year ? ' · ' + esc(r.year) : ''}</small></button>`;
}
async function loadRelatedPreview(m, sequence) {
  try {
    const data = await api('discover', { kind: m.related_type, identifier: m.related_id });
    if (sequence !== titleSequence) return;
    const slot = $('related-preview');
    if (!slot) return;
    const sections = data.sections || {
      sequence: { items: [] },
      franchise: { items: [] },
      related: { items: data.items },
    };
    const block = (heading, section, empty) =>
      !section.items.some((r) => !r.current)
        ? ''
        : `<section class="relationship-block"><div class="section-heading"><h3>${heading}</h3>${section.name ? `<span class="muted">${esc(section.name)}</span>` : ''}</div>${section.items.length ? `<p class="muted relationship-note">${esc(section.note || 'Recommendations; connections are not confirmed.')}${section.source ? ` <a href="${esc(section.source)}" target="_blank" rel="noopener noreferrer">Order source ↗</a>` : ''}</p><div class="related-preview" tabindex="0" role="region" aria-label="${esc(heading)} titles">${section.items.map(relationshipTile).join('')}</div>` : `<p class="muted relationship-note">${empty}</p>`}</section>`;
    slot.innerHTML =
      block(
        'Sequels & prequels',
        sections.sequence,
        'No verified story sequence is available for this title yet.'
      ) +
      block(
        'Confirmed universe / franchise',
        sections.franchise,
        'No additional confirmed franchise members are available from the current metadata.'
      );
    $('title-relationships').hidden = !slot.innerHTML;
    window.setKeepExploringTitles?.(sequence, [
      ...sections.sequence.items,
      ...sections.franchise.items,
    ]);
    window.setExplorationRecommendations?.(sequence, sections.related.items);
    window.loadSupplementalMetadata?.(m, sequence, data);
  } catch (e) {
    if (sequence === titleSequence && $('related-preview'))
      $('related-preview').textContent = e.message;
  }
}
let discoveryContext = null,
  discoverySequence = 0,
  discoverySelected = new Set(),
  discoveryReturnPage = null;
async function openDiscovery(kind, identifier) {
  discoveryReturnPage = captureBrowsePage();
  const seq = ++discoverySequence;
  discoveryContext = null;
  discoverySelected.clear();
  $('discovery-sort').value = kind === 'person' ? 'date-desc' : 'original';
  $('discovery-search').value = '';
  $('discovery-type').value = '';
  $('discovery-note').textContent = '';
  $('discovery-save').disabled = true;
  $('discovery-save').hidden = true;
  $('person-profile').innerHTML = '';
  $('discovery-title').textContent = 'Explore projects';
  $('discovery-content').innerHTML = '<p role="status">Loading projects from TMDB...</p>';
  openWorkspacePanel('discovery-dialog');
  try {
    const data = await api('discover', { kind, identifier });
    if (seq !== discoverySequence) return;
    discoveryContext = { kind, identifier, data };
    $('discovery-title').textContent = data.profile ? 'Filmography' : data.name;
    $('discovery-note').textContent = data.note;
    renderPersonProfile(data);
    $('breadcrumb').textContent = data.name;
    drawDiscovery();
  } catch (e) {
    if (seq === discoverySequence)
      $('discovery-content').innerHTML = `<p class="metadata-error">${esc(e.message)}</p>`;
  }
}
function renderPersonProfile(data) {
  const p = data.profile;
  if (!p) {
    $('person-profile').innerHTML = '';
    return;
  }
  $('person-profile').innerHTML =
    `<div class="person-profile">${p.photo ? `<img class="person-portrait" src="${esc(p.photo)}" alt="${esc(data.name)}" referrerpolicy="no-referrer">` : '<div class="person-portrait portrait-empty">No portrait</div>'}<div><p class="eyebrow">${esc(p.department || 'FILM & TELEVISION')}</p><h3>${esc(data.name)}</h3><p class="person-dates">${p.birthday ? 'Born ' + esc(p.birthday) : ''}${p.birthplace ? ' / ' + esc(p.birthplace) : ''}${p.deathday ? ' / Died ' + esc(p.deathday) : ''}</p><div class="person-biography"><p>${esc(p.biography || 'No biography is available from TMDB.')}</p></div>${p.biography ? '<button class="person-link" id="biography-toggle" aria-expanded="false">More biography</button>' : ''}</div></div>`;
  const toggle = $('biography-toggle');
  if (toggle)
    toggle.onclick = () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
      toggle.textContent = expanded ? 'More biography' : 'Less biography';
      $('person-profile')
        .querySelector('.person-biography')
        .classList.toggle('expanded', !expanded);
    };
}
function sortProjects(items, order) {
  if (!order || order === 'original') return [...items];
  const [field, direction] = order.split('-'),
    sign = direction === 'desc' ? -1 : 1;
  const value = (r) =>
    field === 'date'
      ? r.release_date || r.year || null
      : field === 'rating'
        ? (preferredRating(r, true)?.score ?? null)
        : field === 'role'
          ? r.roles?.join(', ') || null
          : field === 'type'
            ? r.type
            : r.title;
  return [...items].sort((a, b) => {
    const x = value(a),
      y = value(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (
      sign *
      (typeof x === 'number'
        ? x - y
        : String(x).localeCompare(String(y), undefined, { sensitivity: 'base', numeric: true }))
    );
  });
}
function drawDiscovery() {
  const data = discoveryContext?.data;
  if (!data) return;
  const query = $('discovery-search').value.toLowerCase(),
    type = $('discovery-type').value;
  const rows = sortProjects(
    data.items.filter(
      (r) =>
        !isIgnored(r) &&
        (!type || r.type === type) &&
        (r.title + ' ' + r.roles.join(' ')).toLowerCase().includes(query)
    ),
    $('discovery-sort').value
  );
  $('discovery-count').textContent =
    `${rows.length} visible / ${data.items.length} projects / ${discoverySelected.size} selected`;
  $('discovery-content').innerHTML =
    rows
      .map(
        (r, n) =>
          `<article class="project-row"><input type="checkbox" aria-label="Select ${esc(r.title)}" data-project="${esc(r.key)}" ${discoverySelected.has(r.key) ? 'checked' : ''}><span class="rank">${String(n + 1).padStart(2, '0')}</span><button class="project-poster" data-title-tmdb="${esc(r.tmdb)}" data-title-type="${esc(r.type)}" aria-label="View ${esc(r.title)}">${r.poster ? posterArt(r.poster, r) : '<span>No poster</span>'}</button><div class="project-copy"><button class="title-link" data-title-tmdb="${esc(r.tmdb)}" data-title-type="${esc(r.type)}">${esc(r.title)}</button><p class="project-meta">${r.type === 'movie' ? 'Movie' : 'TV'} &middot; ${esc(r.year || 'Date unknown')} &middot; ${ratingWidget(r)}</p><p class="project-overview">${esc(r.overview || 'No synopsis available.')}</p>${r.roles.length ? `<p class="project-role">${esc(r.roles.join(', '))}</p>` : ''}</div><span class="project-group">${ignoreButton(r)} ${esc(r.group)}</span></article>`
      )
      .join('') || '<p>No matching projects.</p>';

  $('discovery-save').hidden = !discoverySelected.size;
  $('discovery-save').disabled = !discoverySelected.size;
  $('discovery-save').textContent = `Save ${discoverySelected.size} selected & compare with Plex`;
}
$('discovery-search').oninput = drawDiscovery;
$('discovery-type').onchange = drawDiscovery;
$('discovery-sort').onchange = drawDiscovery;
$('discovery-content').onchange = (e) => {
  const key = e.target.dataset.project;
  if (!key) return;
  e.target.checked ? discoverySelected.add(key) : discoverySelected.delete(key);
  drawDiscovery();
};
$('discovery-all').onclick = () => {
  const q = $('discovery-search').value.toLowerCase(),
    t = $('discovery-type').value;
  for (const r of discoveryContext?.data.items || [])
    if (
      !isIgnored(r) &&
      (!t || r.type === t) &&
      (r.title + ' ' + r.roles.join(' ')).toLowerCase().includes(q)
    )
      discoverySelected.add(r.key);
  drawDiscovery();
};
$('discovery-none').onclick = () => {
  discoverySelected.clear();
  drawDiscovery();
};
$('discovery-save').onclick = (e) =>
  task(e.target, async () => {
    if (!discoveryContext) return;
    const result = await api('discover/save', {
      kind: discoveryContext.kind,
      identifier: discoveryContext.identifier,
      keys: [...discoverySelected],
    });
    replaceList(result.entry);
    closeWorkspacePanel('discovery-dialog');
    closeWorkspacePanel('title-dialog');
    toast('Saved and compared with Plex. Select missing titles to review downloads.');
  });
async function openTitle(id) {
  externalTitle = null;
  titleBackStack = [];
  const item = current()?.items.find((i) => i.id === id);
  if (!item) return;
  if (item.type === 'show') return openParent(id);
  const seq = ++titleSequence,
    listId = active;
  openedItem = id;
  $('title-save').hidden = true;
  $('parent-request').hidden = true;
  $('title-content').innerHTML =
    typeof loadingTitleMarkup === 'function'
      ? loadingTitleMarkup(item.type, item.tmdb || item.show_tmdb, {
          ...item,
          ...metadataCache.get(metadataKey(item)),
        })
      : `<h2 id="title-heading">${esc(item.title)}</h2><p role="status">Loading title details…</p>`;
  $('title-add').hidden = !requestable(item);
  $('title-add').textContent = item.type === 'movie' ? 'Add to Radarr →' : 'Add to Sonarr →';
  openWorkspacePanel('title-dialog');
  try {
    let details = metadataCache.get(metadataKey(item));
    if (!details || details.error || details.summary_only)
      details = await api('details', { list_id: listId, item_id: id });
    metadataCache.set(metadataKey(item), details);
    if (seq === titleSequence) {
      renderTitle(item, details);
      if (item.type !== 'movie')
        $('title-content').innerHTML =
          `<div class="parent-breadcrumb"><button class="show-link" data-show="${id}">← ${esc(details.show_title || item.show_title || 'View full show')} · all seasons & Plex coverage</button></div>` +
          $('title-content').innerHTML;
      paintMetadata(item);
    }
  } catch (e) {
    if (seq === titleSequence)
      $('title-content').innerHTML =
        `<h2 id="title-heading">${esc(item.title)}</h2><p class="metadata-error">Title details could not be loaded.</p><details><summary>Provider response</summary><p>${esc(e.message)}</p></details><button class="secondary" data-title-retry-item="${esc(id)}">Retry details</button><div class="title-main-actions" aria-label="Library actions"></div>`;
  }
}
let activeShowContext = null,
  showRequestScope = null;
function coverageMarkup(data) {
  return `<section class="show-coverage"><div class="coverage-heading"><div><p class="eyebrow">YOUR PLEX LIBRARY</p><h3>${data.available} episodes available · ${data.missing} aired episodes missing</h3><p class="muted">${esc(data.libraries.join(', ') || 'No confirmed episodes in Plex')}. Whole-show requests exclude specials.</p></div>${data.coverage_known && data.missing ? '<button class="primary" data-show-scope="show">Request missing from whole show</button>' : data.coverage_known ? '<span class="title-owned">All aired episodes in Plex</span>' : ''}</div>${!data.coverage_known ? '<p class="metadata-error">Coverage could not be confirmed. Check the Plex connection or correct the show match before requesting.</p>' : ''}${data.seasons.map((s) => `<details class="coverage-season"><summary><span>${esc(s.name)}</span><span class="muted">${s.available} in Plex · ${s.aired} aired · ${s.missing} missing</span></summary>${data.coverage_known && s.missing ? `<div class="season-request"><button class="secondary" data-show-scope="season" data-season="${s.number}">Request ${s.missing} missing episode${s.missing === 1 ? '' : 's'} from this season</button></div>` : ''}<ul class="coverage-episodes">${s.episodes.map((e) => `<li><span><small>S${e.season} E${e.episode}</small> <button class="episode-title-link" data-episode-show="${esc(data.show?.tmdb || '')}" data-season="${e.season}" data-episode="${e.episode}">${esc(e.title)}</button></span><span class="badge ${e.status}">${esc({ available: 'In Plex', missing: 'Missing', upcoming: 'Not aired', unknown: 'Unknown' }[e.status])}</span></li>`).join('')}</ul></details>`).join('')}</section>`;
}
const showPageCache = new Map();
function recentShowPage(key) {
  const cached = showPageCache.get(key);
  if (cached && Date.now() - cached.time < 180000) return cached.data;
  showPageCache.delete(key);
  return null;
}
async function openParent(id, refresh = false) {
  externalTitle = null;
  const item = current()?.items.find((i) => i.id === id);
  if (!item) return;
  const listId = active,
    key = listId + ':' + metadataKey(item),
    seq = ++titleSequence;
  if (refresh) showPageCache.delete(key);
  openedItem = id;
  activeShowContext = null;
  $('title-save').hidden = true;
  $('title-add').hidden = true;
  $('parent-request').hidden = true;
  openWorkspacePanel('title-dialog');
  let complete = false;
  const paint = (data) => {
    activeShowContext = { itemId: id, listId, data };
    renderTitle(data.show, data.details);
    placeCoverage(data);
    $('parent-request').hidden = !data.coverage_known || !data.missing;
    $('parent-request').textContent = `Request ${data.missing} missing episodes · whole show`;
  };
  const cached = recentShowPage(key);
  if (cached) {
    paint(cached);
    return;
  }
  const parentKey = metadataKey({
    type: 'show',
    tmdb: item.type === 'show' ? item.tmdb : item.show_tmdb,
    title: item.show_title || item.title,
  });
  const preview =
    metadataCache.get(parentKey) ||
    (item.type === 'show' ? metadataCache.get(metadataKey(item)) : null);
  const paintPreview = (m) => {
    renderTitle({ type: 'show' }, m);
    $('title-coverage-slot').innerHTML =
      '<p class="muted" role="status">Checking seasons against Plex...</p>';
  };
  if (preview && !preview.error) paintPreview(preview);
  else {
    $('title-content').innerHTML =
      `<h2 id="title-heading">${esc(item.show_title || item.title)}</h2><p class="muted" role="status">Loading show details...</p>`;
    api('details', { list_id: listId, item_id: id, parent: true })
      .then((m) => {
        metadataCache.set(parentKey, m);
        if (seq === titleSequence && !complete) paintPreview(m);
      })
      .catch(() => {});
  }
  try {
    const data = await api('show', { list_id: listId, item_id: id });
    complete = true;
    showPageCache.set(key, { data, time: Date.now() });
    metadataCache.set(parentKey, data.details);
    if (seq !== titleSequence) return;
    paint(data);
  } catch (e) {
    complete = true;
    if (seq === titleSequence) {
      if ($('title-coverage-slot'))
        $('title-coverage-slot').innerHTML =
          `<p class="metadata-error">${esc(e.message)}</p><button class="secondary" data-refresh-show>Retry Plex check</button>`;
      else $('title-content').innerHTML = `<p class="metadata-error">${esc(e.message)}</p>`;
    }
  }
}

function placeCoverage(data, allowRequests = true) {
  const markup =
    (allowRequests
      ? '<div class="coverage-refresh"><span class="muted">Plex status cached for up to 3 minutes. Requests recheck availability.</span><button class="secondary" data-refresh-show>Refresh Plex status</button></div>'
      : '') + coverageMarkup(data);
  const slot = $('title-coverage-slot');
  if (slot)
    slot.innerHTML = allowRequests
      ? markup
      : markup.replaceAll('data-show-scope=', 'data-external-scope=');
}
function captureBrowsePage() {
  return {
    panel: workspacePanel,
    html: $('title-content').innerHTML,
    openedItem,
    externalTitle,
    showContext: activeShowContext,
    scroll: window.scrollY || 0,
    titleHidden: $('title-add').hidden,
    parentHidden: $('parent-request').hidden,
    parentText: $('parent-request').textContent,
    addText: $('title-add').textContent,
    saveDisabled: $('title-save').disabled,
    breadcrumb: $('breadcrumb').textContent,
  };
}
function restoreBrowsePage(page) {
  ++titleSequence;
  openedItem = page.openedItem;
  externalTitle = page.externalTitle;
  activeShowContext = page.showContext;
  $('title-content').innerHTML = page.html;
  $('title-add').hidden = page.titleHidden;
  $('title-add').textContent = page.addText;
  $('parent-request').hidden = page.parentHidden;
  $('parent-request').textContent = page.parentText;
  $('title-save').hidden = !externalTitle;
  $('title-save').disabled = page.saveDisabled;
  openWorkspacePanel(page.panel);
  $('breadcrumb').textContent = page.breadcrumb;
  scrollWorkspace(page.scroll);
}
async function openExternalTitle(type, tmdb, season, episode) {
  if (!['movie', 'show', 'episode'].includes(type) || !/^\d+$/.test(String(tmdb))) return;
  if (
    type === 'episode' &&
    (!Number.isInteger(Number(season)) ||
      Number(season) < 0 ||
      !Number.isInteger(Number(episode)) ||
      Number(episode) < 1)
  )
    return;
  titleBackStack.push(captureBrowsePage());
  const seq = ++titleSequence;
  externalTitle = {
    type,
    tmdb,
    ...(type === 'episode' ? { season: Number(season), episode: Number(episode) } : {}),
  };
  activeShowContext = null;
  openedItem = '';
  $('title-add').hidden = true;
  $('parent-request').hidden = true;
  $('title-save').hidden = false;
  $('title-save').disabled = true;
  openWorkspacePanel('title-dialog');
  $('title-content').innerHTML =
    typeof loadingTitleMarkup === 'function'
      ? loadingTitleMarkup(type, tmdb)
      : '<p role="status">Loading title details...</p>';
  const titleBody = { ...externalTitle },
    cacheKey = 'external:' + tmdb;
  let titleComplete = false;
  if (type === 'show' && !recentShowPage(cacheKey))
    api('title', { ...titleBody, metadata_only: true })
      .then((data) => {
        if (seq === titleSequence && !titleComplete) {
          renderTitle(data.item, data.details);
          $('title-coverage-slot').innerHTML =
            '<p class="muted" role="status">Checking seasons against Plex...</p>';
        }
      })
      .catch(() => {});
  try {
    const data =
      (type === 'show' ? recentShowPage(cacheKey) : null) || (await api('title', titleBody));
    titleComplete = true;
    if (type === 'show') showPageCache.set(cacheKey, { data, time: Date.now() });
    if (seq !== titleSequence) return;
    renderTitle(data.item, data.details);
    if (type === 'episode')
      $('title-content').innerHTML =
        `<div class="parent-breadcrumb"><button class="show-link" data-title-tmdb="${esc(tmdb)}" data-title-type="show">${esc(data.details.show_title || 'Full show')} &middot; Season ${Number(season)}, Episode ${Number(episode)} &middot; View all seasons</button></div>` +
        $('title-content').innerHTML;
    if (data.show) placeCoverage(data.show, false);
    $('title-save').disabled = false;
  } catch (e) {
    titleComplete = true;
    if (seq === titleSequence)
      $('title-content').innerHTML =
        (typeof loadingTitleMarkup === 'function'
          ? loadingTitleMarkup(type, tmdb).replace(
              'Loading details and library availability…',
              'Details unavailable.'
            )
          : '<h2 id="title-heading">Title details</h2>') +
        `<p class="metadata-error">This title could not be loaded. Retry the provider check.</p><details><summary>Provider response</summary><p>${esc(e.message)}</p></details><button class="secondary" data-title-retry-external>Retry details</button>`;
  }
}
$('title-save').onclick = (e) =>
  task(e.target, async () => {
    if (!externalTitle) return;
    const result = await api('title/save', externalTitle);
    replaceList(result.entry);
    settingsView(false);
    toast('Saved and compared with Plex. Review missing titles before downloading.');
  });
$('discovery-content').onclick = (e) => {
  const title = e.target.closest('[data-title-tmdb]');
  if (title) openExternalTitle(title.dataset.titleType, title.dataset.titleTmdb);
};
async function reviewShowScope(button) {
  if (!activeShowContext) return;
  if (!managerIsConfigured('sonarr')) {
    toast('Connect Sonarr under Settings / Connections before requesting seasons or shows.');
    return;
  }
  const scope = button.dataset.showScope,
    season = Number(button.dataset.season),
    context = activeShowContext;
  const missing =
    scope === 'show'
      ? context.data.missing
      : context.data.seasons.find((s) => s.number === season)?.missing;
  if (!missing) return;
  const options = await api('options', { list_id: context.listId, services: ['sonarr'] });
  showRequestScope = { ...context, scope, season };
  $('show-request-title').textContent =
    context.data.details.title + (scope === 'season' ? ` · Season ${season}` : ' · whole show');
  $('show-request-description').textContent =
    `Request ${missing} aired episodes missing from Plex. Episodes already in Plex or already downloaded in Sonarr are skipped. Whole-show requests exclude specials. Coverage is checked again when you confirm.`;
  $('show-request-options').innerHTML =
    `${requestRouteMarkup(options.sonarr, 'sonarr', 'show')}<label>Quality profile<select id="show-profile">${options.sonarr.profiles.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label><label>Destination<select id="show-root">${options.sonarr.roots.map((r) => `<option value="${esc(r.path)}">${esc(r.path)}</option>`).join('')}</select></label>`;
  if (options.sonarr.defaults?.profile) $('show-profile').value = options.sonarr.defaults.profile;
  if (options.sonarr.defaults?.root) $('show-root').value = options.sonarr.defaults.root;
  $('show-request-result').textContent = '';
  $('show-request-submit').hidden = false;
  closeWorkspacePanel('title-dialog');
  $('show-request-dialog').showModal();
}
$('title-content').onclick = (e) => {
  if (e.target.closest('[data-refresh-show]')) {
    if (openedItem) openParent(openedItem, true);
    return;
  }
  const episode = e.target.closest('[data-episode-show]');
  if (episode) {
    openExternalTitle(
      'episode',
      episode.dataset.episodeShow,
      episode.dataset.season,
      episode.dataset.episode
    );
    return;
  }
  const title = e.target.closest('[data-title-tmdb]');
  if (title) {
    openExternalTitle(title.dataset.titleType, title.dataset.titleTmdb);
    return;
  }
  const company = e.target.closest('[data-company]');
  if (company) {
    openDiscovery('company', company.dataset.company);
    return;
  }
  const person = e.target.closest('[data-person]');
  if (person) {
    openDiscovery('person', person.dataset.person);
    return;
  }
  const related = e.target.closest('[data-related]');
  if (related) {
    openDiscovery(related.dataset.kind, related.dataset.related);
    return;
  }
  const show = e.target.closest('[data-show]');
  if (show) {
    e.preventDefault();
    openParent(show.dataset.show);
    return;
  }
  const scope = e.target.closest('[data-show-scope]');
  if (scope && !busy) task(scope, () => reviewShowScope(scope));
};
$('show-request-submit').onclick = (e) =>
  task(e.target, async () => {
    const scope = showRequestScope;
    if (!scope) return;
    const result = await api('show/request', {
      list_id: scope.listId,
      item_id: scope.itemId,
      scope: scope.scope,
      season: scope.season,
      profile: $('show-profile').value,
      root: $('show-root').value,
      route: $('show-route')?.value || 'primary',
    });
    showPageCache.clear();
    if (result.entry) {
      const index = state.lists.findIndex((r) => r.id === result.entry.id);
      if (index >= 0) state.lists[index] = result.entry;
    }
    loadActivity().catch((e) => ($('activity-status').textContent = e.message));
    $('show-request-result').textContent = result.message;
    $('show-request-submit').hidden = true;
    $('show-request-dialog').close();
    toast(result.message || 'Request submitted.');
  });
$('parent-request').onclick = (e) => task(e.target, () => reviewShowScope(e.target));
$('title-add').onclick = () => {
  closeWorkspacePanel('title-dialog');
  addOne(openedItem);
};
$('review-top').onclick = () => $('review').click();
$('entries').onclick = (e) => {
  const retry = e.target.closest('[data-retry-metadata]');
  if (retry) {
    const item = current()?.items.find((i) => i.id === retry.dataset.retryMetadata);
    if (item) {
      metadataCache.delete(metadataKey(item));
      metadataAttempts.delete(metadataKey(item));
      render();
    }
    return;
  }
  if (busy) return;
  const add = e.target.closest('[data-add]');
  if (add) {
    addOne(add.dataset.add);
    return;
  }
  const parent = e.target.closest('[data-show]');
  if (parent) {
    e.preventDefault();
    openParent(parent.dataset.show);
    return;
  }
  const detail = e.target.closest('[data-details]');
  if (detail) {
    openTitle(detail.dataset.details);
    return;
  }
  const button = e.target.closest('[data-edit]');
  if (!button) return;
  const item = current().items.find((i) => i.id === button.dataset.edit);
  editingId = item.id;
  $('edit-title').textContent = item.title;
  const fields = [
    'title',
    'year',
    'tmdb',
    'imdb',
    ...(item.type === 'movie' ? [] : ['tvdb']),
    ...(item.type === 'season' || item.type === 'episode'
      ? [
          'show_title',
          'show_tmdb',
          'show_tvdb',
          'show_imdb',
          'season',
          ...(item.type === 'episode' ? ['episode'] : []),
        ]
      : []),
  ];
  $('edit-fields').innerHTML = fields
    .map(
      (k) =>
        `<label>${esc(k.replaceAll('_', ' '))}<input name="${k}" value="${esc(item[k] || '')}" ${k === 'title' ? 'required' : ''}></label>`
    )
    .join('');
  $('identify-query').value = item.show_title || item.title;
  $('identify-choice').innerHTML = '<option value="">Choose a result</option>';
  $('match-query').value = item.show_title || item.title;
  $('match-choice').innerHTML = '<option value="">Keep current matching</option>';
  $('edit-dialog').showModal();
};
let identifyResults = [];
$('identify-search').onclick = (e) =>
  task(e.target, async () => {
    const data = await api('identify', {
      list_id: active,
      item_id: editingId,
      query: $('identify-query').value,
    });
    identifyResults = data.results;
    $('identify-choice').innerHTML =
      '<option value="">Choose a result</option>' +
      data.results
        .map(
          (r) =>
            `<option value="${r.id}">${esc(r.title)} (${esc(r.year || 'Unknown year')})</option>`
        )
        .join('');
    if (!data.results.length) toast('No results. Try another title.');
  });
$('identify-choice').onchange = (e) => {
  const result = identifyResults.find((r) => String(r.id) === e.target.value),
    item = current()?.items.find((r) => r.id === editingId);
  if (!result || !item) return;
  const child = ['season', 'episode'].includes(item.type);
  const idInput = document.querySelector(
    `#edit-fields input[name="${child ? 'show_tmdb' : 'tmdb'}"]`
  );
  if (idInput) idInput.value = result.id;
  if (child) {
    const titleInput = document.querySelector('#edit-fields input[name="show_title"]');
    if (titleInput) titleInput.value = result.title;
  }
};
$('match-search').onclick = (e) =>
  task(e.target, async () => {
    const result = await api('matches', {
      list_id: active,
      item_id: editingId,
      query: $('match-query').value,
    });
    $('match-choice').innerHTML =
      '<option value="">Choose a Plex match</option>' +
      result.matches
        .map(
          (m) =>
            `<option value="${esc(m.key)}">${esc(m.title)} (${esc(m.year || '?')}) · ${esc(m.library)}</option>`
        )
        .join('');
    if (!result.matches.length) toast('No matching Plex titles found. Try a shorter title.');
  });
$('edit-form').onsubmit = (e) => {
  e.preventDefault();
  task(e.submitter, async () => {
    const result = await api('correct', {
      list_id: active,
      item_id: editingId,
      fields: Object.fromEntries(new FormData(e.target)),
      plex_key: $('match-choice').value,
    });
    replaceList(result);
    $('edit-dialog').close();
    toast('Correction saved. Compare with Plex to apply it.');
  });
};
let publicationToken = null;
let publicationListId = null;
let originalPlaylistPlan = '';
async function reviewLinkedPlaylist(id) {
  publicationToken = null;
  publicationListId = id;
  const plan = await api('publications/preview', { list_id: id });
  publicationToken = plan.token;
  originalPlaylistPlan = `${plan.after_count} available movies/episodes. ${plan.omitted} entries omitted. Creating a separate playlist keeps the existing one.`;
  $('playlist-title').value = plan.title;
  $('playlist-title').disabled = true;
  $('playlist-replace-label').hidden = false;
  $('playlist-replace').checked = true;
  $('playlist-plan').textContent =
    `${plan.before_count} → ${plan.after_count} playable items: ${plan.added} added, ${plan.removed} removed${plan.reordered ? ', order changed' : ''}. ${plan.omitted} entries omitted. Review this update before applying it to your linked playlist.`;
  $('playlist-preview-items').innerHTML =
    `<details><summary>Review order and omitted entries</summary><ol>${plan.entries.map((row) => `<li>${esc(row.title)} / ${row.count} playable items${row.count ? '' : ' / omitted'}</li>`).join('')}</ol></details>`;
  $('playlist-form').querySelector('[type=submit]').disabled = !plan.after_count;
  $('playlist-dialog').showModal();
}
$('playlist-open').onclick = (e) =>
  task(e.target, async () => {
    publicationToken = null;
    publicationListId = active;
    $('playlist-title').disabled = false;
    const plan = await api('playlist/preview', { list_id: active });
    $('playlist-preview-items').innerHTML =
      `<details><summary>Review selected watch order and omitted entries</summary><ol>${(plan.entries || []).map((r) => `<li><strong>${esc(r.title)}</strong> / ${esc(r.type)} / ${r.count ? r.count + ' playable item(s)' : 'Omitted: ' + esc(r.status)}${r.status === 'partial' ? ' / incomplete scope' : ''}<small>${esc(r.detail)}</small></li>`).join('')}</ol></details>`;
    $('playlist-title').value = plan.name;
    $('playlist-form').querySelector('[type=submit]').disabled =
      !plan.count || !!plan.duplicate_count;
    $('playlist-replace-label').hidden = !current().playlist;
    $('playlist-replace').checked = false;
    $('playlist-plan').textContent =
      `${plan.count} available movies/episodes in ${plan.watch_order ? plan.watch_order + ' watch order' : 'original list order'}. ${plan.omitted} entries currently have no confirmed available items and will be omitted. Availability is checked again before creation.`;
    originalPlaylistPlan = $('playlist-plan').textContent;
    if (plan.duplicate_count) {
      $('playlist-plan').textContent +=
        ` ${plan.duplicate_count} repeated Plex items need review in List health before publishing. Plex may collapse those occurrences.`;
      originalPlaylistPlan = $('playlist-plan').textContent;
    }
    $('playlist-dialog').showModal();
  });
$('playlist-replace').onchange = (e) =>
  task(e.target, async () => {
    publicationToken = null;
    const submit = $('playlist-form').querySelector('[type=submit]');
    $('playlist-title').disabled = e.target.checked;
    if (!e.target.checked) {
      $('playlist-plan').textContent = originalPlaylistPlan;
      submit.disabled = false;
      return;
    }
    submit.disabled = true;
    $('playlist-plan').textContent =
      'Reading the saved Plex playlist and comparing current availability…';
    const plan = await api('publications/preview', { list_id: publicationListId });
    publicationToken = plan.token;
    $('playlist-title').value = plan.title;
    $('playlist-plan').textContent =
      `${plan.before_count} → ${plan.after_count} playable items: ${plan.added} added, ${plan.removed} removed${plan.reordered ? ', retained items reordered' : ''}. ${plan.omitted} list entries omitted. The playlist title is preserved. Review expires after 15 minutes; changes in Plex or this list require a fresh preview.`;
    $('playlist-preview-items').innerHTML =
      `<details><summary>Review proposed list order and omissions</summary><ol>${plan.entries.map((row) => `<li>${esc(row.title)} / ${row.count} playable item(s)${row.count ? '' : ' / omitted'}</li>`).join('')}</ol></details>`;
    submit.disabled = !plan.after_count;
  });
$('playlist-form').onsubmit = (e) => {
  e.preventDefault();
  task(e.submitter, async () => {
    const replacing = $('playlist-replace').checked;
    if (replacing && !publicationToken) throw Error('Review this Plex update before saving.');
    const result = await api(replacing ? 'publications/apply' : 'playlist/create', {
      list_id: publicationListId,
      token: publicationToken,
      title: $('playlist-title').value,
      replace: $('playlist-replace').checked,
    });
    const saved = state.lists.find((row) => row.id === publicationListId);
    if (saved) {
      saved.playlist = { ...result, server: state.settings.plex?.url };
      saved.playlist_needs_update = false;
    }
    publicationToken = null;
    renderListUpdates();
    if (typeof drawListCatalogue === 'function') drawListCatalogue();
    if (typeof drawOfficialCatalogue === 'function') drawOfficialCatalogue();
    $('playlist-dialog').close();
    toast(result.warning || `Saved “${result.title}” in Plex with ${result.count} items.`);
  });
};
const activityCache = new Map();
let activitySequence = 0,
  backupCandidate = null,
  backupFingerprint = null;
function activityFor(item) {
  return activityCache.get(active + ':' + item.id);
}
function activityBadge(item) {
  const status = activityFor(item);
  return status
    ? `<span class="manager-progress ${esc(status.state)}" title="${esc(status.label)}">${esc(status.label)}${status.percent != null ? ' ' + status.percent + '%' : ''}</span>`
    : item.request_log
      ? '<span class="manager-progress requested">Request submitted</span>'
      : '';
}
function metadataHealth() {
  const items = current()?.items || [],
    failed = items.filter((i) => metadataCache.get(metadataKey(i))?.error);
  $('metadata-health').hidden = !items.length;
  $('metadata-health-summary').textContent = failed.length
    ? failed.length + ' metadata failures - retry available'
    : 'Metadata: ' +
      items.filter(
        (i) => metadataCache.has(metadataKey(i)) && !metadataCache.get(metadataKey(i)).error
      ).length +
      ' / ' +
      items.length +
      ' loaded';
  $('metadata-health-status').textContent = failed.length
    ? failed
        .slice(0, 5)
        .map((i) => i.title + ': ' + metadataCache.get(metadataKey(i)).error)
        .join(' | ')
    : 'Titles load as they become visible. Sorting by metadata checks the full list. Missing provider artwork or ratings are not necessarily errors.';
  $('metadata-retry-all').disabled = !failed.length;
}
function recentDownloadRequests(rows, now = Date.now() / 1000) {
  return rows
    .filter(
      (r) =>
        (r.updated_at || r.created_at || 0) >= now - 30 * 86400 &&
        !['pending', 'awaiting_approval', 'declined', 'cancelled'].includes(r.status)
    )
    .sort((a, b) => (b.updated_at || b.created_at) - (a.updated_at || a.created_at));
}
async function loadActivity() {
  const sequence = ++activitySequence;
  $('activity-status').textContent = 'Checking recent requests across all lists...';
  const result = await api('requests/refresh', {});
  if (sequence !== activitySequence) return;
  requestRows = result.items || [];
  requestNotices = result.notifications || [];
  const rows = recentDownloadRequests(requestRows);
  $('activity-items').innerHTML =
    rows
      .map(
        (r) =>
          `<article class="request-history-row">${requestArtwork(r)}<div class="request-history-copy"><span class="request-state">${esc(REQUEST_LABELS[r.status] || r.status)}${r.percent != null ? ' &middot; ' + esc(r.percent) + '%' : ''}</span><button class="title-link" data-request-title="${esc(r.id)}">${esc(r.item.title)}</button><p class="muted">${esc(r.service)} &middot; Requested ${esc(new Date((r.updated_at || r.created_at) * 1000).toLocaleDateString())}</p><p>${esc(r.message || '')}</p>${r.percent != null ? `<progress max="100" value="${Number(r.percent) || 0}" aria-label="Download progress"></progress>` : ''}</div></article>`
      )
      .join('') ||
    '<div class="empty"><h3>No recent download requests.</h3><p>Confirmed requests from the last 30 days appear here, across all lists.</p></div>';
  $('activity-status').textContent = [
    ...(result.warnings || []),
    'Recent requests only - last 30 days. Imported manager libraries are not scanned.',
  ].join(' ');
}
$('activity-refresh').onclick = (e) => task(e.target, loadActivity);
$('activity-compare').onclick = () => $('compare').click();

$('metadata-retry-all').onclick = (e) =>
  task(e.target, async () => {
    if (!current()) return;
    const listId = active,
      items = current().items.filter((i) => metadataCache.get(metadataKey(i))?.error);
    for (let index = 0; index < items.length; index += 20) {
      const batch = items.slice(index, index + 20);
      for (const item of batch) {
        metadataCache.delete(metadataKey(item));
        metadataAttempts.delete(metadataKey(item));
      }
      try {
        const result = await api('metadata', { list_id: listId, ids: batch.map((i) => i.id) });
        for (const item of batch) {
          const entry = result.items.find((r) => r.id === item.id);
          storeListMetadata(item, entry?.details, entry?.error || 'Metadata was not returned.');
        }
      } catch (error) {
        for (const item of batch) storeListMetadata(item, null, error.message);
      }
      if (active !== listId) return;
      $('metadata-health-status').textContent =
        'Retried ' + Math.min(index + 20, items.length) + ' / ' + items.length;
    }
    render();
  });
$('backup-export').onclick = (e) =>
  task(e.target, async () => {
    const data = await api('backup/export', {}),
      blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      url = URL.createObjectURL(blob),
      link = document.createElement('a');
    link.href = url;
    link.download = 'listweavarr-backup-' + new Date().toISOString().slice(0, 10) + '.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $('backup-status').textContent = 'Portable backup downloaded without credentials.';
  });
$('backup-local-refresh').onclick = (e) =>
  task(e.target, async () => {
    const data = await api('backup/list', {});
    $('backup-local').innerHTML =
      '<option value="">Choose a rolling backup</option>' +
      data.files.map((file) => `<option value="${esc(file)}">${esc(file)}</option>`).join('');
    $('backup-status').textContent = data.files.length + ' local backups available.';
  });
function clearBackupPreview() {
  backupCandidate = null;
  backupFingerprint = null;
  $('backup-review').hidden = true;
}
$('backup-upload').onchange = clearBackupPreview;
$('backup-local').onchange = clearBackupPreview;
$('backup-cancel').onclick = clearBackupPreview;
$('backup-preview').onclick = (e) =>
  task(e.target, async () => {
    clearBackupPreview();
    const file = $('backup-upload').files?.[0],
      local = $('backup-local').value;
    if (file) {
      if (file.size > 7_500_000) throw Error('Choose a backup smaller than 7.5 MB.');
      backupCandidate = { document: JSON.parse(await file.text()) };
    } else if (local) backupCandidate = { file: local };
    else throw Error('Choose an uploaded or local backup first.');
    const data = await api('backup/preview', backupCandidate);
    backupFingerprint = data.fingerprint;
    $('backup-summary').textContent =
      data.summary.lists +
      ' lists, ' +
      data.summary.items +
      ' entries, ' +
      data.summary.ignored +
      ' ignored titles, ' +
      data.summary.tracked +
      ' tracked releases.';
    $('backup-review').hidden = false;
  });
$('backup-restore').onclick = (e) =>
  task(e.target, async () => {
    if (!backupCandidate || !backupFingerprint) throw Error('Preview the backup first.');
    state = await api('backup/restore', {
      ...backupCandidate,
      fingerprint: backupFingerprint,
      mode: $('backup-mode').value,
    });
    active = state.lists[0]?.id || '';
    selected.clear();
    metadataCache.clear();
    activityCache.clear();
    extraRatingsCache.clear();
    showPageCache.clear();
    clearBackupPreview();
    render();
    renderArr();
    renderPlex();
    window.onListweavarrReady?.();
    $('backup-status').textContent =
      'Workspace restored. Connections retained. Compare restored lists with Plex.';
  });
function setEntrySize(value, persist = true) {
  const number = Number(value),
    size =
      Number.isFinite(number) && number > 0
        ? Math.max(100, Math.min(200, Math.round(number / 5) * 5))
        : 100;
  $('entry-size').value = String(size);
  $('entry-size-value').textContent = size + '%';
  $('settings-entry-size').value = String(size);
  $('settings-entry-size-value').textContent = size + '%';
  $('entry-size').setAttribute?.('aria-valuetext', size + ' percent');
  $('entries').style?.setProperty('--entry-scale', String(size / 100));
  $('entries').style?.setProperty('--entry-overview-lines', size > 100 ? '3' : '2');
  $('entries').setAttribute?.('data-entry-expanded', size >= 150 ? 'true' : 'false');
  $('entry-size-reset').disabled = size === 100;
  if (persist) {
    try {
      localStorage.setItem('reelcheck-entry-size', String(size));
    } catch {}
  }
}
$('entry-size').oninput = (e) => setEntrySize(e.target.value);
$('settings-entry-size').oninput = (e) => setEntrySize(e.target.value);
$('entry-size-reset').onclick = () => setEntrySize(100);
try {
  setEntrySize(localStorage.getItem('reelcheck-entry-size'), false);
} catch {
  setEntrySize(100, false);
}
$('list-select').onchange = (e) => {
  active = e.target.value;
  ++activitySequence;
  $('activity-items').innerHTML = '';
  $('activity-status').textContent = 'Open or refresh progress to check this list.';
  localStorage.setItem('reelcheck-active-list', active);
  $('sort').value = 'original';
  selected.clear();
  render();
  window.onListweavarrListChanged?.();
};
$('search').oninput = render;
$('year-from').oninput = render;
$('year-to').oninput = render;
$('year-clear').onclick = () => {
  $('year-from').value = '';
  $('year-to').value = '';
  render();
};
$('view').onchange = render;
document.querySelectorAll('[data-filter]').forEach(
  (b) =>
    (b.onclick = () => {
      filter = b.dataset.filter;
      document
        .querySelectorAll('[data-filter]')
        .forEach((x) => x.classList.toggle('active', x === b));
      render();
    })
);
$('entries').onchange = (e) => {
  if (e.target.dataset.item) {
    e.target.checked ? selected.add(e.target.dataset.item) : selected.delete(e.target.dataset.item);
    updateSelection();
  }
};
$('select-all').onchange = (e) => {
  visible()
    .filter(requestable)
    .forEach((i) => (e.target.checked ? selected.add(i.id) : selected.delete(i.id)));
  render();
};
$('selection-clear').onclick = () => {
  selected.clear();
  render();
};
$('compare').onclick = (e) =>
  task(e.target, async () => {
    showPageCache.clear();
    const result = await api('compare', { list_id: active });
    state.lists[state.lists.findIndex((l) => l.id === active)] = result;
    selected.clear();
    render();
    toast('Plex comparison complete.');
  });
$('review').onclick = (e) =>
  task(e.target, async () => {
    const items = current().items.filter((i) => selected.has(i.id));
    const services = [...new Set(items.map((i) => (i.type === 'movie' ? 'radarr' : 'sonarr')))];
    const options = await api('options', { list_id: active, services });
    $('review-items').innerHTML = items
      .map(
        (i) =>
          `<div class="review-row">${esc(i.title)} <span class="muted">· ${esc(i.type)}${i.season !== undefined ? ' · S' + esc(i.season) : ''}${i.episode !== undefined ? ' E' + esc(i.episode) : ''}</span></div>`
      )
      .join('');
    $('request-options').innerHTML = services
      .map(
        (s) =>
          `<h3>${s === 'radarr' ? 'Radarr' : 'Sonarr'}</h3>${requestRouteMarkup(options[s], s, s)}<label>Quality profile<select id="${s}-profile" required>${options[s].profiles.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label><label>Destination<select id="${s}-root" required>${options[s].roots.map((r) => `<option value="${esc(r.path)}">${esc(r.path)}</option>`).join('')}</select></label>`
      )
      .join('');
    for (const service of services) {
      if (options[service].defaults?.profile)
        $(service + '-profile').value = options[service].defaults.profile;
      if (options[service].defaults?.root)
        $(service + '-root').value = options[service].defaults.root;
    }
    $('request-results').innerHTML = '';
    $('submit-requests').hidden = false;
    $('review-dialog').showModal();
  });
$('submit-requests').onclick = (e) =>
  task(e.target, async () => {
    const options = {};
    for (const s of ['radarr', 'sonarr'])
      if ($(s + '-profile'))
        options[s] = {
          profile: $(s + '-profile').value,
          root: $(s + '-root').value,
          route: $(s + '-route')?.value || 'primary',
        };
    const result = await api('request', { list_id: active, ids: [...selected], options });
    $('request-results').innerHTML = result.results
      .map(
        (r) =>
          `<div class="result ${r.ok ? '' : 'error'}"><strong>${esc(r.title)}</strong><br>${esc(r.message)}</div>`
      )
      .join('');
    $('submit-requests').hidden = true;
    if (result.entry) {
      const index = state.lists.findIndex((r) => r.id === result.entry.id);
      if (index >= 0) state.lists[index] = result.entry;
    }
    selected.clear();
    render();
    if (result.results.length && result.results.every((r) => r.ok)) {
      $('review-dialog').close();
      toast('Requests submitted.');
    }
    loadActivity().catch((e) => ($('activity-status').textContent = e.message));
  });
const reviewRequests = $('review').onclick;
$('review').onclick = (e) => {
  const needed = [
    ...new Set(
      (current()?.items || [])
        .filter((i) => selected.has(i.id))
        .map((i) => (i.type === 'movie' ? 'radarr' : 'sonarr'))
    ),
  ].filter((s) => !managerIsConfigured(s));
  if (needed.length) {
    toast(
      'Connect ' +
        needed.join(' and ') +
        ' under Settings / Connections before reviewing download requests.'
    );
    settingsView(true);
    selectSettingsTab('connections');
    return;
  }
  return reviewRequests(e);
};
fetch('/api/state')
  .then((r) => r.json())
  .then(async (data) => {
    state = data;
    active = state.lists.some((l) => l.id === localStorage.getItem('reelcheck-active-list'))
      ? localStorage.getItem('reelcheck-active-list')
      : state.lists[0]?.id || '';
    render();
    renderArr();
    renderPlex();
    window.onListweavarrReady?.();
    if (window.location.hash === '#plex-login') {
      history.replaceState(null, '', window.location.pathname);
      settingsView(true);
      selectSettingsTab('connections');
      await task($('plex-check-login'), finishPlexLogin);
    } else if (localStorage.getItem('reelcheck-import')) {
      $('import-dialog').showModal();
      await task($('import-form').querySelector('[type=submit]'), () =>
        pollImport(localStorage.getItem('reelcheck-import'))
      );
    }
  })
  .catch((e) => toast(e.message || 'Could not load the local app. Refresh to retry.'));

if (typeof setInterval !== 'undefined')
  setInterval(() => {
    if (!busy && workspacePanel === 'workspace' && !$('activity-panel').hidden)
      loadActivity().catch((e) => ($('activity-status').textContent = e.message));
  }, 90000);
