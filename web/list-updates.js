// SPDX-License-Identifier: AGPL-3.0-only
// Source checks are read-only. Schedules are explicit and off for new lists.
let linkedUpdateState = null;
const updateTime = (value) => (value ? new Date(value * 1000).toLocaleString() : 'Not yet');
function renderLinkedUpdates(result) {
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
      ${review?.changed ? '<p class="muted">Review these changes before using Refresh source on the list. This check has not applied them.</p>' : ''}</article>`;
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
