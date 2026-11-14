// SPDX-License-Identifier: AGPL-3.0-only
// Account authorization and Home PINs stay server-side; browser gets cookies.
const el = (id) => document.getElementById(id);
let pollTimer,
  checking = false,
  selectedProfile = null;
async function authPost(path, body = {}) {
  const response = await fetch('/api/auth/' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Sign-in failed.');
  return result;
}
function showProfiles(profiles) {
  clearTimeout(pollTimer);
  el('home-profiles').hidden = false;
  el('plex-sign-in').hidden = true;
  el('sign-in').hidden = true;
  el('profile-choices').replaceChildren();
  el('plex-status').textContent = 'Choose your Plex Home profile.';
  for (const profile of profiles) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = profile.name + (profile.protected ? ' (PIN required)' : '');
    button.onclick = () => {
      selectedProfile = profile;
      el('profile-pin').value = '';
      el('profile-pin-form').hidden = !profile.protected;
      el('profile-pin').required = profile.protected;
      if (profile.protected) {
        el('profile-pin-label').textContent = 'PIN for ' + profile.name;
        el('profile-pin').focus();
      } else chooseProfile();
    };
    el('profile-choices').append(button);
  }
}
async function chooseProfile() {
  if (!selectedProfile) return;
  el('profile-submit').disabled = true;
  el('plex-status').textContent = 'Verifying profile and connecting its library...';
  try {
    await authPost('profiles/select', {
      profile_id: selectedProfile.id,
      pin: el('profile-pin').value,
    });
    el('profile-pin').value = '';
    window.location.replace('/');
  } catch (error) {
    el('plex-status').textContent = error.message;
  } finally {
    el('profile-submit').disabled = false;
  }
}
el('profile-pin-form').onsubmit = (event) => {
  event.preventDefault();
  chooseProfile();
};
async function checkPlex() {
  if (checking) return;
  checking = true;
  clearTimeout(pollTimer);
  try {
    const result = await authPost('plex/check');
    if (result.profiles) showProfiles(result.profiles);
    else {
      el('plex-status').textContent = 'Finish signing in on Plex, then choose a Home profile here.';
      pollTimer = setTimeout(checkPlex, 2000);
    }
  } catch (error) {
    el('plex-status').textContent = error.message;
  } finally {
    checking = false;
  }
}
el('plex-start').onclick = async () => {
  el('plex-start').disabled = true;
  el('plex-status').textContent = 'Opening Plex sign-in...';
  try {
    const result = await authPost('plex/start');
    if (!result.url.startsWith('https://app.plex.tv/auth#?'))
      throw Error('Invalid Plex sign-in address.');
    el('plex-link').href = result.url;
    el('plex-link').hidden = false;
    el('plex-check').hidden = false;
    window.location.assign(result.url);
  } catch (error) {
    el('plex-status').textContent = error.message;
  } finally {
    el('plex-start').disabled = false;
  }
};
el('plex-check').onclick = checkPlex;
el('sign-in').onsubmit = async (event) => {
  event.preventDefault();
  el('submit').disabled = true;
  el('status').textContent = 'Signing in...';
  try {
    await authPost('login', { password: el('password').value });
    el('password').value = '';
    window.location.replace('/');
  } catch (error) {
    el('status').textContent = error.message;
  } finally {
    el('submit').disabled = false;
  }
};
(async () => {
  try {
    const response = await fetch('/api/auth/status', { cache: 'no-store' });
    const data = await response.json();
    el('plex-sign-in').hidden = !data.plex_enabled;
    el('sign-in').hidden = !data.password_enabled;
    el('password-recovery').hidden = !data.password_enabled;
    if (location.pathname === '/profiles' && data.plex_enabled && data.authenticated) {
      showProfiles((await authPost('profiles/start')).profiles);
    } else if (location.hash === '#owner-plex' && data.plex_enabled) checkPlex();
    else if (!data.enabled)
      el('plex-status').textContent = 'Plex sign-in is not enabled for this installation.';
  } catch (error) {
    el('plex-status').textContent = error.message;
  }
})();
