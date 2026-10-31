// SPDX-License-Identifier: AGPL-3.0-only
/* A deliberate collection workflow, not extra buttons on every title card. */
let collectionListId = null,
  collectionSavedTarget = null,
  collectionToken = null,
  collectionSequence = 0;
$('list-updates').addEventListener('click', (e) => {
  const button = e.target.closest('[data-review-collection]');
  if (!button) return;
  openSavedList(button.dataset.reviewCollection);
  $('collection-open').click();
});
function invalidateCollection() {
  ++collectionSequence;
  collectionToken = null;
  $('collection-apply').disabled = true;
  $('collection-members').innerHTML = '';
}
$('collection-title').oninput = invalidateCollection;
$('collection-library').onchange = invalidateCollection;
$('collection-open').onclick = (e) =>
  task(e.target, async () => {
    collectionListId = active;
    collectionSavedTarget = current()?.plex_collection || null;
    $('collection-unlink').hidden = !collectionSavedTarget;
    invalidateCollection();
    const sequence = collectionSequence;
    $('collection-status').textContent = 'Loading library choices. No Plex changes have been made.';
    $('collection-library').innerHTML = '';
    $('collection-preview').disabled = true;
    $('collection-title').value = current()?.name || '';
    $('collection-dialog').showModal();
    try {
      const result = await api('collections/options', { list_id: collectionListId });
      if (sequence !== collectionSequence) return;
      $('collection-title').disabled = !!result.saved;
      $('collection-library').disabled = !!result.saved;
      $('collection-library').innerHTML = result.libraries
        .map((row) => `<option value="${esc(row.id)}">${esc(row.title)}</option>`)
        .join('');
      if (result.saved) {
        $('collection-title').value = result.saved.title;
        $('collection-library').value = result.saved.section;
      }
      $('collection-status').textContent = result.saved
        ? 'Linked collection: preview its current contents and proposed changes. Its identity and Home visibility will be retained.'
        : 'Choose a library and title, then preview. A matching name alone never authorizes replacing an existing collection.';
      if (result.attention)
        $('collection-status').textContent =
          result.attention + ' Preview the current collection before continuing.';
      $('collection-preview').disabled = !result.libraries.length;
    } catch (error) {
      $('collection-status').textContent = error.message;
    }
  }).finally(() => {
    $('collection-apply').disabled = true;
  });
$('collection-preview').onclick = (e) =>
  task(e.target, async () => {
    invalidateCollection();
    const sequence = collectionSequence;
    $('collection-status').textContent = 'Reading Plex and building a read-only preview…';
    try {
      const plan = await api('collections/preview', {
        list_id: collectionListId,
        title: $('collection-title').value,
        section: $('collection-library').value,
      });
      if (sequence !== collectionSequence) return;
      collectionToken = plan.token;
      $('collection-status').textContent =
        `${plan.library}: ${plan.before_count} → ${plan.after_count} members; ${plan.added} added, ${plan.removed} removed${plan.reordered ? ', order changes' : ''}. ${plan.omitted} unmatched/unavailable entries omitted; ${plan.deduplicated} repeated entries included once. ${plan.updating ? 'This updates the saved collection in place.' : 'This creates a new collection.'} Review expires after 15 minutes.`;
      $('collection-members').innerHTML = plan.entries
        .slice(0, 200)
        .map((row) => `<li>${esc(row.title)} — ${esc(row.reason)}</li>`)
        .join('');
      if (plan.entries.length > 200)
        $('collection-status').textContent += ' First 200 entries shown.';
      $('collection-apply').disabled = !plan.after_count;
    } catch (error) {
      if (sequence === collectionSequence) $('collection-status').textContent = error.message;
    }
  });
$('collection-apply').onclick = (e) =>
  task(e.target, async () => {
    if (!collectionToken) return;
    const token = collectionToken;
    collectionToken = null;
    $('collection-apply').disabled = true;
    $('collection-preview').disabled = true;
    try {
      const result = await api('collections/apply', {
        list_id: collectionListId,
        token,
        confirmed: true,
      });
      replaceList(result.entry);
      $('collection-dialog').close();
      toast(
        result.publication.warning ||
          `Plex collection saved with ${result.publication.count} members.`
      );
    } catch (error) {
      $('collection-status').textContent =
        error.message +
        ' Check Plex and preview again before retrying; no request will be automatically repeated.';
    } finally {
      $('collection-apply').disabled = true;
      $('collection-preview').disabled = false;
    }
  }).finally(() => {
    $('collection-apply').disabled = true;
  });

$('collection-unlink').onclick = (e) =>
  task(e.target, async () => {
    if (
      !collectionSavedTarget ||
      !confirm(
        'Unlink this collection? It stays in Plex unchanged. You can then create a separate collection from this list.'
      )
    )
      return;
    const result = await api('collections/unlink', {
      list_id: collectionListId,
      expected: collectionSavedTarget,
      confirmed: true,
    });
    replaceList(result.entry);
    $('collection-dialog').close();
    toast('Collection unlinked. Its Plex contents were not changed.');
  });
