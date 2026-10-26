// SPDX-License-Identifier: AGPL-3.0-only
// Source checks are read-only. Schedules are explicit and off for new lists.
let linkedUpdateState = null;
const linkedOrderPreviews = new Map();
function linkedOrderMarkup(id) {
  const preview = linkedOrderPreviews.get(id);
  return `<h4>Exact proposed order (${preview.items.length} entries)</h4><ol>${preview.items
    .slice(0, preview.visible)
    .map(
      (item) =>
        `<li>${esc(item.show_title ? item.show_title + ' / ' : '')}${esc(item.title || 'Untitled')}${item.season != null ? ' / S' + esc(item.season) : ''}${item.episode != null ? ' E' + esc(item.episode) : ''} <span class="muted">${item.previous_position ? '(previously #' + esc(item.previous_position) + ')' : '(new)'}</span></li>`
    )
    .join(
      ''
    )}</ol>${preview.visible < preview.items.length ? `<button class="secondary" data-update-more="${esc(id)}">Show 100 more</button>` : ''}<p>This replaces this saved list's membership and order with the checked version, including the removals shown above. Surviving watch-path entries keep their order; removed entries leave those paths. One undo is retained. Plex and downloads are unchanged.</p><button class="primary" data-update-apply="${esc(id)}" data-token="${esc(preview.token)}">Apply this checked version</button>`;
}
const updateTime = (value) => (value ? new Date(value * 1000).toLocaleString() : 'Not yet');
function renderLinkedUpdates(result) {
  linkedOrderPreviews.clear();
  linkedUpdateState = result;
  $('list-updates-pause').textContent = result.paused
    ? 'Resume scheduled checks'
    : 'Pause scheduled checks';
  $('list-updates-status').textContent = result.running
    ? 'A source check is running. Reopen this panel to see its result.'
    : result.paused
      ? 'Scheduled checks paused. Manual checks remain available.'
      : 'Checks are read-only. Enable a daily or weekly schedule for each linked list.';
  $('list-updates-rows').innerHTML =
    result.lists
      .map((row) => {
        const schedule = row.schedule,
          review = row.review;
        const details = (label, items) =>
          items?.length
            ? `<details><summary>${label}</summary><ol>${items.map((item) => `<li>${esc(item.show_title ? item.show_title + ' / ' : '')}${esc(item.title || 'Untitled')}${item.season != null ? ' / S' + esc(item.season) : ''}${item.episode != null ? ' E' + esc(item.episode) : ''}</li>`).join('')}</ol></details>`
            : '';
        return `<article class="collection-health-note"><h3>${esc(row.name)}</h3>
      <p>${review ? (review.changed ? `${review.added} added / ${review.removed} removed${review.reordered ? ' / order changed' : ''}` : 'No membership or order changes found.') : 'Source has not been checked here yet.'}</p>
      <p class="muted">Last success: ${esc(updateTime(schedule.last_success))} / Next: ${schedule.interval && schedule.interval !== 'off' ? esc(updateTime(schedule.next_run)) + (result.paused ? ' (paused)' : '') : 'Manual only'}</p>
      ${schedule.last_error ? `<p role="status">${esc(schedule.last_error)}${schedule.failures ? ' Retry attempts: ' + esc(schedule.failures) : ''}</p>` : ''}
      ${details('Added titles', review?.added_items)}${details('Removed titles', review?.removed_items)}
      ${review?.reordered ? '<p class="muted">The relative order of retained titles changed.</p>' : ''}
      ${review?.details_truncated ? '<p class="muted">Showing the first 200 entries per change type.</p>' : ''}
      <label>Check frequency<select data-update-frequency="${esc(row.id)}">${[
        ['off', 'Manual only'],
        ['daily', 'Daily'],
        ['weekly', 'Weekly'],
      ]
        .map(
          ([value, label]) =>
            `<option value="${value}"${(schedule.interval || 'off') === value ? ' selected' : ''}>${label}</option>`
        )
        .join('')}</select></label>
      <button class="secondary" data-update-check="${esc(row.id)}"${result.running ? ' disabled' : ''}>Check now</button>
      ${row.apply_token ? `<button class="secondary" data-update-preview="${esc(row.id)}" data-token="${esc(row.apply_token)}">Review exact update</button><div data-update-order="${esc(row.id)}"></div>` : ''}
      ${row.undo_token ? `<button class="secondary" data-update-undo="${esc(row.id)}" data-token="${esc(row.undo_token)}">Undo last source update</button>` : ''}</article>`;
      })
      .join('') ||
    '<p>No supported linked lists yet. Import a list from Trakt, IMDb, Letterboxd, MDBList or ChronoCanon to start.</p>';
}
$('list-updates-open').onclick = (event) =>
  task(event.target, async () => {
    renderLinkedUpdates(await api('list-updates/status', {}));
    $('list-updates-dialog').showModal();
  });
$('list-updates-pause').onclick = (event) =>
  task(event.target, async () => {
    renderLinkedUpdates(await api('list-updates/pause', { paused: !linkedUpdateState.paused }));
  });
$('list-updates-rows').addEventListener('change', async (event) => {
  const select = event.target.closest('[data-update-frequency]');
  if (!select) return;
  select.disabled = true;
  try {
    renderLinkedUpdates(
      await api('list-updates/schedule', {
        list_id: select.dataset.updateFrequency,
        interval: select.value,
      })
    );
  } catch (error) {
    toast(error.message);
    select.disabled = false;
  }
});
$('list-updates-rows').addEventListener('click', (event) => {
  const action = event.target.closest(
    '[data-update-preview], [data-update-apply], [data-update-undo], [data-update-more]'
  );
  if (action) {
    const mode = action.dataset.updatePreview
      ? 'preview'
      : action.dataset.updateApply
        ? 'apply'
        : action.dataset.updateUndo
          ? 'undo'
          : 'more';
    const id =
      action.dataset.updatePreview ||
      action.dataset.updateApply ||
      action.dataset.updateUndo ||
      action.dataset.updateMore;
    return task(action, async () => {
      if (mode === 'preview' || mode === 'more') {
        if (mode === 'preview')
          linkedOrderPreviews.set(id, {
            ...(await api('list-updates/preview', { list_id: id, token: action.dataset.token })),
            visible: 100,
          });
        else linkedOrderPreviews.get(id).visible += 100;
        action.closest('article').querySelector('[data-update-order]').innerHTML =
          linkedOrderMarkup(id);
      } else {
        const result = await api('list-updates/' + mode, {
          list_id: id,
          token: action.dataset.token,
        });
        if (result.workspace) {
          state = result.workspace;
          render();
        }
        linkedOrderPreviews.delete(id);
        renderLinkedUpdates(result);
        toast(
          mode === 'apply'
            ? 'Checked source version applied. Plex and downloads unchanged.'
            : 'Source update undone.'
        );
      }
    });
  }
  const button = event.target.closest('[data-update-check]');
  if (!button) return;
  task(button, async () => {
    $('list-updates-status').textContent =
      'Checking this source. Large lists may take longer; you can close this panel.';
    try {
      await api('list-updates/check', { list_id: button.dataset.updateCheck });
    } finally {
      renderLinkedUpdates(await api('list-updates/status', {}));
    }
  });
});
