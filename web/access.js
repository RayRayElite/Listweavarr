// SPDX-License-Identifier: AGPL-3.0-only
async function loadOwnerAccess() {
  try {
    const response = await fetch('/api/auth/status', { cache: 'no-store' });
    const result = await response.json();
    if (!response.ok) throw Error('Access settings could not be checked.');
    $('owner-access-status').textContent = result.enabled
      ? result.plex_enabled
        ? 'Plex sign-in enabled. Active profile: ' + (result.profile?.name || 'Owner') + '.'
        : 'Owner password sign-in is enabled. This browser is signed in.'
      : 'Local access mode. Owner sign-in is not enabled.';
    $('owner-sign-out').hidden = !result.enabled || !result.authenticated;
    window.ownerAccessEnabled = result.enabled;
  } catch (error) {
    $('owner-access-status').textContent = error.message;
  }
}
const settingsBeforeOwnerAccess = loadWorkflowSettings;
loadWorkflowSettings = async function () {
  if (state.active_profile?.role !== 'member') await settingsBeforeOwnerAccess();
  await loadOwnerAccess();
};
$('owner-sign-out').onclick = (e) =>
  task(e.target, async () => {
    await api('auth/logout', {});
    window.location.reload();
  });

$('owner-plex-id-find').onclick = (event) =>
  task(event.target, async () => {
    try {
      const result = await api('owner/plex-account', {});
      window.verifiedOwnerAccount = result;
      $('owner-plex-enable').hidden = Boolean(window.ownerAccessEnabled);
      $('owner-plex-id-result').textContent =
        'Verified ' +
        result.account +
        '. Operator setting: LISTWEAVARR_OWNER_PLEX_ID=' +
        result.id +
        '. You can enable household sign-in below, or use this setting in your server environment. This lookup does not change access.';
    } catch (error) {
      $('owner-plex-id-result').textContent = error.message;
    }
  });
$('profile-switch').onclick = () => window.location.assign('/profiles');
function applyHouseholdProfileUI() {
  const profile = state.active_profile,
    member = profile?.role === 'member';
  $('profile-switch').hidden = !profile || profile.user_id === 'owner';
  if (profile) $('profile-switch').textContent = profile.name || 'Switch profile';
  $('requests-nav').hidden = member;
  $('owner-plex-id-find').hidden = member;
  for (const tab of ['requests', 'notifications', 'backups'])
    $('settings-tab-' + tab).hidden = member;
  const downloads = document.querySelector('[data-lists-tab=downloads]');
  if (downloads) downloads.hidden = member;
  if (member) {
    for (const control of document.querySelectorAll('#settings-form input,#settings-form button'))
      control.disabled = true;
    $('plex-signin').hidden = true;
    $('plex-check-login').hidden = true;
    $('plex-test').hidden = true;
  }
}
const renderBeforeProfiles = render;
render = function () {
  renderBeforeProfiles();
  applyHouseholdProfileUI();
};

$('owner-plex-enable').onclick = (event) =>
  task(event.target, async () => {
    const account = window.verifiedOwnerAccount;
    if (!account) return;
    if (
      !window.confirm(
        'Enable Plex household sign-in for ' +
          account.account +
          '? Existing lists stay in the owner workspace. Family profiles get separate personal state. This browser will then choose a Home profile.'
      )
    )
      return;
    try {
      await api('owner/plex-enable', { account_id: account.id });
      window.location.assign('/profiles');
    } catch (error) {
      $('owner-plex-id-result').textContent = error.message;
    }
  });

window.addEventListener('pageshow', (event) => {
  if (event.persisted) {
    document.documentElement.style.visibility = 'hidden';
    window.location.reload();
  }
});
