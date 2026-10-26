// SPDX-License-Identifier: AGPL-3.0-only
/* Focused maintenance views; no changes until a reviewed action is chosen. */
let collectionUpdateRows = new Map(),
  collectionUpdateSequence = 0,
  healthSequence = 0;
function updateDifference(label, values) {
  return values.length
    ? `<details class="update-difference"><summary>${esc(label)} (${values.length})</summary><ul>${values
        .slice(0, 80)
        .map((value) => `<li>${esc(value)}</li>`)
        .join(
          ''
        )}</ul>${values.length > 80 ? '<p class="muted">Showing the first 80 titles.</p>' : ''}</details>`
    : '';
}
async function loadCollectionUpdates() {
  const sequence = ++collectionUpdateSequence;
  $('official-updates-panel').hidden = false;
  $('official-items').hidden = true;
  $('official-updates-status').textContent = 'Checking the installed official catalogue...';
  $('official-update-items').innerHTML = '';
  try {
    const result = await api('explore/official/updates', {});
    if (sequence !== collectionUpdateSequence) return;
    collectionUpdateRows = new Map(
      [...result.lists, ...result.recent].map((row) => [row.list_id, row])
    );
    $('official-updates-status').textContent =
      `${result.lists.length ? result.lists.length + ' updates available.' : 'Your personal copies are up to date.'} This compares personal copies with the installed catalogue. Use Get catalogue updates above to fetch a newer source. Authoring originals use Publish official update.`;
    $('official-update-items').innerHTML = [...result.lists, ...result.recent]
      .map(
        (row) =>
          `<article class="collection-update" data-collection-update="${esc(row.list_id)}"><header><div><h3>${esc(row.name)}</h3><p class="muted">Installed v${row.installed_version} / Official v${row.version}</p></div><span class="collection-update-badge">${row.available ? 'Update available' : 'Recently updated'}</span></header>${row.available ? `<p>${row.added.length} titles only in the official version / ${row.removed.length} only in your copy / ${row.changed} shared entries differ${row.order_changed ? ' / ordering differs' : ''}.</p>${updateDifference('Only in the official version', row.added)}${updateDifference('Only in your copy', row.removed)}<p class="muted">${row.has_baseline ? 'Preserve mode keeps your renamed details, edited entries and deliberate removals. Personal additions appear after the official sequence.' : 'This older copy has no original snapshot. Preserve mode keeps existing entries and details, adds new official entries, and removes nothing.'}</p><label>Apply as<select data-update-mode><option value="merge">Preserve my personal changes</option><option value="replace">Use official version exactly</option></select></label><p class="muted">Official mode replaces list membership, ordering, name, description and poster. Plex playlists and downloads are not changed. Undo restores the previous list.</p><div class="collection-update-actions"><button class="primary" data-collection-apply="${esc(row.list_id)}">Apply reviewed update</button><button class="text-action" data-collection-skip="${esc(row.list_id)}">Skip this version</button>${row.can_rollback ? `<button class="text-action" data-collection-undo="${esc(row.list_id)}">Undo previous update</button>` : ''}</div>` : `<p class="muted">Undo restores the list from before its last official update. Later list edits will be replaced; matching entries keep their latest Plex and request status.</p><button class="secondary" data-collection-undo="${esc(row.list_id)}">Undo last update</button>`}</article>`
      )
      .join('');
  } catch (error) {
    if (sequence === collectionUpdateSequence)
      $('official-updates-status').textContent = error.message;
  }
}
$('official-updates-open').onclick = (e) => task(e.target, loadCollectionUpdates);
$('official-updates-close').onclick = () => {
  ++collectionUpdateSequence;
  $('official-updates-panel').hidden = true;
  $('official-items').hidden = false;
};
$('official-update-items').onclick = (e) => {
  const button = e.target.closest(
    '[data-collection-apply],[data-collection-skip],[data-collection-undo]'
  );
  if (!button) return;
  task(button, async () => {
    const id =
        button.dataset.collectionApply ||
        button.dataset.collectionSkip ||
        button.dataset.collectionUndo,
      row = collectionUpdateRows.get(id);
    if (!row) return;
    const action = button.dataset.collectionSkip
      ? 'skip'
      : button.dataset.collectionUndo
        ? 'rollback'
        : 'update';
    const result = await api('explore/official/' + action, {
      list_id: id,
      revision: row.revision,
      version: row.version,
      confirmed: true,
      mode:
        button.closest('[data-collection-update]').querySelector('[data-update-mode]')?.value ||
        'merge',
    });
    const index = state.lists.findIndex((entry) => entry.id === id);
    if (index >= 0) state.lists[index] = result.entry;
    render();
    await loadCollectionUpdates();
    toast(
      action === 'skip'
        ? 'This official version was skipped.'
        : action === 'rollback'
          ? 'Previous list restored.'
          : 'Official update applied.'
    );
  });
};
$('list-health-check').onclick = (e) =>
  task(e.target, async () => {
    const id = active,
      sequence = ++healthSequence;
    $('list-health-panel').hidden = false;
    $('list-health-panel').open = true;
    $('list-health-status').textContent = 'Checking list structure...';
    $('list-health-results').innerHTML = '';
    try {
      const result = await api('explore/official/health', { list_id: id });
      if (sequence !== healthSequence || id !== active) return;
      $('list-health-heading').textContent =
        `List health / ${result.total ? result.total + ' review notes' : 'No structural issues found'}`;
      $('list-health-status').textContent = result.note;
      $('list-health-results').innerHTML =
        result.issues
          .map(
            (issue) =>
              `<div class="collection-health-note"><span class="eyebrow">${esc(issue.code)}${issue.positions.length ? ' / entries ' + issue.positions.join(', ') : ''}</span><b>${esc(issue.title)}</b><p>${esc(issue.message)}</p></div>`
          )
          .join('') + (result.truncated ? '<p class="muted">Showing the first 300 notes.</p>' : '');
    } catch (error) {
      if (sequence === healthSequence) $('list-health-status').textContent = error.message;
    }
  });
const openListBeforeHealth = openSavedList;
openSavedList = function (id) {
  ++healthSequence;
  $('list-health-panel').hidden = true;
  openListBeforeHealth(id);
};

let cataloguePreviewToken = null,
  catalogueFeedSequence = 0;
function clearCataloguePreview() {
  ++catalogueFeedSequence;
  cataloguePreviewToken = null;
  $('catalogue-feed-install').hidden = true;
  $('catalogue-feed-review').innerHTML = '';
}
$('catalogue-source-url').oninput = clearCataloguePreview;
$('catalogue-source-file').onchange = clearCataloguePreview;
$('catalogue-source-panel').ontoggle = async () => {
  if (!$('catalogue-source-panel').open) return;
  try {
    const result = await api('explore/official/feed-source', {});
    if (!$('catalogue-source-url').value) $('catalogue-source-url').value = result.url;
  } catch (error) {
    $('catalogue-feed-status').textContent = error.message;
  }
};
$('catalogue-source-save').onclick = (e) =>
  task(e.target, async () => {
    try {
      await api('explore/official/feed-source', { url: $('catalogue-source-url').value.trim() });
      $('catalogue-feed-status').textContent = 'Catalogue source saved locally.';
    } catch (error) {
      $('catalogue-feed-status').textContent = error.message;
    }
  });
async function previewCatalogue(fromFile = false) {
  clearCataloguePreview();
  const sequence = catalogueFeedSequence;
  $('catalogue-feed-status').textContent = 'Reading and validating the catalogue...';
  try {
    let body;
    if (fromFile) {
      const file = $('catalogue-source-file').files[0];
      if (!file) throw Error('Select an official catalogue JSON file.');
      if (file.size > 30000000) throw Error('Catalogue files must be smaller than 30 MB.');
      body = { document: JSON.parse(await file.text()) };
    } else body = { url: $('catalogue-source-url').value.trim() };
    const result = await api('explore/official/feed-preview', body);
    if (sequence !== catalogueFeedSequence) return;
    cataloguePreviewToken = result.token;
    const summary = result.summary;
    $('catalogue-feed-review').innerHTML =
      `<h3>Catalogue preview</h3><p>${summary.added.length} new lists / ${summary.updated.length} newer versions / ${summary.unchanged} unchanged / ${summary.older.length} older versions skipped.</p>${summary.added.map((row) => `<div class="collection-health-note"><b>${esc(row.name)}</b> / new v${row.version} / ${row.entries} entries</div>`).join('')}${summary.updated.map((row) => `<div class="collection-health-note"><b>${esc(row.name)}</b> / v${row.from} &rarr; v${row.to} / ${row.entries} entries</div>`).join('')}<p class="muted">${summary.kept_local} local catalogue entries absent from this source will be kept. Working lists, personal edits, Plex playlists and downloads are not changed.</p>`;
    $('catalogue-feed-status').textContent =
      summary.added.length || summary.updated.length
        ? 'Review the lists above, then install when ready.'
        : 'This source has no newer entries to install.';
    $('catalogue-feed-install').hidden = !(summary.added.length || summary.updated.length);
  } catch (error) {
    if (sequence === catalogueFeedSequence) $('catalogue-feed-status').textContent = error.message;
  }
}
$('catalogue-source-check').onclick = (e) => task(e.target, () => previewCatalogue(false));
$('catalogue-file-preview').onclick = (e) => task(e.target, () => previewCatalogue(true));
$('catalogue-feed-install').onclick = (e) =>
  task(e.target, async () => {
    if (!cataloguePreviewToken) return;
    try {
      const result = await api('explore/official/feed-install', {
        token: cataloguePreviewToken,
        confirmed: true,
      });
      clearCataloguePreview();
      officialLoaded = false;
      await loadOfficialLists();
      await loadCollectionUpdates();
      $('catalogue-feed-status').textContent =
        `Catalogue installed: ${result.summary.added.length} new lists, ${result.summary.updated.length} updated versions. Personal copy updates can now be reviewed below.`;
    } catch (error) {
      $('catalogue-feed-status').textContent = error.message;
    }
  });
$('catalogue-download').onclick = (e) =>
  task(e.target, async () => {
    try {
      const data = await api('explore/official/feed-export', {});
      const url = URL.createObjectURL(
          new Blob([JSON.stringify(data)], { type: 'application/json' })
        ),
        link = document.createElement('a');
      link.href = url;
      link.download = 'official-lists.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      $('catalogue-feed-status').textContent =
        'Catalogue exported. Host this file at a public raw JSON URL to distribute updates; publishing a list itself does not upload it.';
    } catch (error) {
      $('catalogue-feed-status').textContent = error.message;
    }
  });

const loadOfficialBeforeFeedCheck = loadOfficialLists;
let officialFeedChecked = false;
loadOfficialLists = async function () {
  await loadOfficialBeforeFeedCheck();
  if (officialFeedChecked) return;
  officialFeedChecked = true;
  try {
    const data = await api('explore/official/feed-check', {});
    if (data.count) {
      $('official-updates-open').textContent = 'Updates available (' + data.count + ')';
      $('official-status').textContent =
        data.count +
        ' catalogue updates available. Review and download when you choose; your copies and Plex playlists are unchanged.';
    }
  } catch (error) {
    $('official-status').textContent += ' Update check unavailable: ' + error.message;
  }
};

$('catalogue-manifest-download').onclick = (e) =>
  task(e.target, async () => {
    const data = await api('explore/official/feed-manifest', {}),
      url = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' })),
      link = document.createElement('a');
    link.href = url;
    link.download = 'official-lists.manifest.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('Host the manifest beside official-lists.json for lightweight update notices.');
  });
