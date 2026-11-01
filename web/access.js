// SPDX-License-Identifier: AGPL-3.0-only
async function loadOwnerAccess() {
  try {
    const response = await fetch('/api/auth/status', { cache: 'no-store' });
    const result = await response.json();
    if (!response.ok) throw Error('Access settings could not be checked.');
    $('owner-access-status').textContent = result.enabled
      ? 'Owner sign-in is enabled. This browser is signed in.'
      : 'Local access mode. Owner sign-in is not enabled.';
    $('owner-sign-out').hidden = !result.enabled || !result.authenticated;
  } catch (error) {
    $('owner-access-status').textContent = error.message;
  }
}
const settingsBeforeOwnerAccess = loadWorkflowSettings;
loadWorkflowSettings = async function () {
  await settingsBeforeOwnerAccess();
  await loadOwnerAccess();
};
$('owner-sign-out').onclick = (e) =>
  task(e.target, async () => {
    await api('auth/logout', {});
    window.location.reload();
  });
