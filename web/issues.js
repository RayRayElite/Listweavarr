// SPDX-License-Identifier: AGPL-3.0-only
/* Human observations live separately from availability, request and watched state. */
let issueRows = [],
  issuePage = 1,
  issueSequence = 0,
  issueScope = null,
  issueEditor = null,
  issueEditorInitial = '',
  issueQueryTimer = null;
let issueTitleContext = null;
const ISSUE_CATEGORIES = {
  playback: 'Playback problem',
  edition: 'Wrong edition',
  subtitles: 'Subtitles',
  audio: 'Audio',
  metadata: 'Metadata / numbering',
  other: 'Other',
};
function issueItemLabel(item) {
  return (
    (item.show_title ? item.show_title + ' / ' : '') +
    item.title +
    (item.type === 'episode'
      ? ` / S${item.season} E${item.episode}`
      : item.type === 'season'
        ? ` / Season ${item.season}`
        : item.year
          ? ` (${item.year})`
          : '')
  );
}
function issueItemHref(row) {
  const item = row.item;
  if (item.type !== 'season' && (item.tmdb || item.show_tmdb)) return mediaRoute(item);
  if (row.list_id && row.item_id)
    return (
      '#/lists/view/' + encodeURIComponent(row.list_id) + '?item=' + encodeURIComponent(row.item_id)
    );
  if (item.type === 'season' && item.show_tmdb)
    return mediaRoute({ type: 'show', tmdb: item.show_tmdb });
  return '';
}
function issueCards(rows) {
  return rows
    .map((row) => {
      const href = issueItemHref(row),
        label = issueItemLabel(row.item);
      const art = row.item.poster
        ? `<img src="${esc(row.item.poster)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
        : `<span>${esc(row.item.title.charAt(0))}</span>`;
      return `<article class="issue-card" data-priority="${esc(row.severity)}">${href ? `<a class="issue-poster" href="${esc(href)}" aria-label="Details for ${esc(label)}">${art}</a>` : `<div class="issue-poster">${art}</div>`}<div class="issue-copy"><p class="eyebrow">${esc(ISSUE_CATEGORIES[row.category])} / ${esc(row.status)}${row.severity !== 'normal' ? ' / ' + esc(row.severity) + ' priority' : ''}</p><h3>${href ? `<a href="${esc(href)}">${esc(label)}</a>` : esc(label)}</h3><p class="issue-note-copy">${esc(row.note)}</p><p class="muted">Updated ${esc(new Date(row.updated_at * 1000).toLocaleString())}${row.requests.length ? ' / ' + row.requests.length + ' related requests' : ''}</p></div><button class="secondary" data-issue-edit="${esc(row.id)}">Edit / ${row.status === 'open' ? 'resolve' : 'reopen'}</button></article>`;
    })
    .join('');
}
async function loadIssues(more = false) {
  const seq = ++issueSequence,
    page = more ? issuePage + 1 : 1;
  $('issue-status').textContent = 'Loading notes...';
  try {
    const data = await api('issues/list', {
      page,
      query: $('issue-query').value,
      status: $('issue-filter-status').value || 'open',
      category: $('issue-filter-category').value || 'all',
      ...(issueScope || {}),
    });
    if (seq !== issueSequence) return;
    issuePage = page;
    issueRows = more ? [...issueRows, ...data.items] : data.items;
    $('issue-open-count').textContent = `${data.open_count} open`;
    $('issue-rows').innerHTML =
      issueCards(issueRows) ||
      '<div class="empty"><h3>No matching issues.</h3><p>Open a title and choose Issues to record a playback, subtitle, audio or edition problem.</p></div>';
    $('issue-more').hidden = !data.has_more;
    $('issue-status').textContent =
      data.total + ' matching issues. Notes do not change library availability.';
  } catch (error) {
    if (seq === issueSequence) $('issue-status').textContent = error.message;
  }
}
function openIssueNotebook(scope = null) {
  issueScope = scope;
  openRequests();
  selectRequestSection('issues');
}
const selectRequestBeforeIssues = selectRequestSection;
selectRequestSection = function (name) {
  $('issue-notebook-panel').hidden = name !== 'issues';
  if (name !== 'issues') return selectRequestBeforeIssues(name);
  requestSection = 'issues';
  if ($('request-queue-panel')) $('request-queue-panel').hidden = true;
  $('activity-panel').hidden = true;
  document.querySelectorAll('[data-request-section]').forEach((button) => {
    const selected = button.dataset.requestSection === 'issues';
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  $('breadcrumb').textContent = 'REQUESTS / ISSUE NOTEBOOK';
  $('issue-new').textContent = issueScope
    ? 'Add issue for this entry'
    : 'Find a title to add an issue';
  $('issue-scope').hidden = !issueScope;
  $('issue-scope').innerHTML = issueScope
    ? `<span>For ${esc(issueItemLabel(issueScope.item))}</span><button class="text-action" data-clear-issue-scope>Show all titles</button>`
    : '';
  loadIssues();
};
function issueFormSnapshot() {
  return JSON.stringify(
    ['issue-category', 'issue-severity', 'issue-state', 'issue-note'].map((id) => $(id).value)
  );
}
function canLeaveIssueEditor() {
  return (
    !$('issue-editor').open ||
    issueFormSnapshot() === issueEditorInitial ||
    typeof window.confirm !== 'function' ||
    window.confirm('Discard unsaved issue changes?')
  );
}
function closeIssueEditor() {
  if (!canLeaveIssueEditor()) return;
  $('issue-editor').close();
}
function openIssueEditor(row = null) {
  if (!row && !issueScope) return openGlobalSearch();
  issueEditor = row || { ...issueScope };
  $('issue-editor-heading').textContent = row ? 'Edit issue' : 'Record an issue';
  $('issue-editor-title').textContent = issueItemLabel(issueEditor.item);
  $('issue-category').value = row?.category || 'playback';
  $('issue-severity').value = row?.severity || 'normal';
  $('issue-state').value = row?.status || 'open';
  $('issue-note').value = row?.note || '';
  $('issue-editor-status').textContent = '';
  $('issue-related').innerHTML = row?.requests?.length
    ? `<details><summary>Related requests for this exact scope (${row.requests.length})</summary>${row.requests.map((request) => `<p><a href="#/requests?title=${encodeURIComponent(request.title)}">${esc(request.title)}</a> / ${esc(request.service)} / ${esc(REQUEST_LABELS[request.status] || request.status)}</p>`).join('')}</details>`
    : '';
  issueEditorInitial = issueFormSnapshot();
  $('issue-editor').showModal();
  $('issue-note').focus();
}
$('issue-editor-close').onclick = closeIssueEditor;
$('issue-editor').addEventListener('cancel', (event) => {
  event.preventDefault();
  closeIssueEditor();
});
$('issue-new').onclick = () => openIssueEditor();
$('issue-scope').onclick = (event) => {
  if (event.target.closest('[data-clear-issue-scope]')) {
    issueScope = null;
    selectRequestSection('issues');
  }
};
$('issue-refresh').onclick = () => loadIssues();
$('issue-more').onclick = (event) => task(event.target, () => loadIssues(true));
$('issue-filter-status').onchange = () => loadIssues();
$('issue-filter-category').onchange = () => loadIssues();
$('issue-query').oninput = () => {
  clearTimeout(issueQueryTimer);
  ++issueSequence;
  issueQueryTimer = setTimeout(() => loadIssues(), 300);
};
$('issue-rows').onclick = (event) => {
  const button = event.target.closest('[data-issue-edit]');
  if (button) openIssueEditor(issueRows.find((row) => row.id === button.dataset.issueEdit));
};
$('issue-form').onsubmit = (event) => {
  event.preventDefault();
  task($('issue-save'), async () => {
    try {
      const saved = await api('issues/save', {
        ...issueEditor,
        category: $('issue-category').value,
        severity: $('issue-severity').value,
        status: $('issue-state').value,
        note: $('issue-note').value,
      });
      issueEditor = saved;
      issueEditorInitial = issueFormSnapshot();
      $('issue-editor').close();
      await loadIssues();
      toast('Issue saved. Media and download requests are unchanged.');
    } catch (error) {
      $('issue-editor-status').textContent = error.message;
    }
  });
};
const renderTitleBeforeIssues = renderTitle;
renderTitle = function (item, metadata) {
  const result = renderTitleBeforeIssues(item, metadata);
  const row =
    !externalTitle && openedItem === item.id
      ? current()?.items.find((row) => row.id === item.id && row.type === item.type)
      : null;
  issueTitleContext = {
    item: { ...item, title: metadata.title || item.title },
    ...(row ? { list_id: active, item_id: row.id } : {}),
  };
  $('title-issues').textContent = 'Issues';
  return result;
};
$('title-issues').onclick = () => {
  if (issueTitleContext) openIssueNotebook(issueTitleContext);
};
if (typeof document.createElement === 'function') {
  const page = $('requests-page'),
    tabs = page.querySelector('.workspace-tabs');
  page.append($('issue-notebook-panel'));
  const button = document.createElement('button');
  button.id = 'request-issues-tab';
  button.type = 'button';
  button.setAttribute('role', 'tab');
  button.setAttribute('aria-controls', 'issue-notebook-panel');
  button.setAttribute('aria-selected', 'false');
  button.tabIndex = -1;
  button.dataset.requestSection = 'issues';
  button.textContent = 'Issues';
  tabs.append(button);
  tabs.onclick = (event) => {
    const button = event.target.closest('[data-request-section]');
    if (!button) return;
    if (button.dataset.requestSection === 'downloads') openRequestDownloads();
    else selectRequestSection(button.dataset.requestSection);
  };
  tabs.onkeydown = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const names = ['requests', 'downloads', 'issues'],
      index = names.indexOf(requestSection);
    const target =
      event.key === 'Home'
        ? names[0]
        : event.key === 'End'
          ? names[2]
          : names[(index + (event.key === 'ArrowLeft' ? 2 : 1)) % 3];
    if (target === 'downloads') openRequestDownloads();
    else selectRequestSection(target);
    tabs.querySelector(`[data-request-section="${target}"]`).focus();
  };
}
