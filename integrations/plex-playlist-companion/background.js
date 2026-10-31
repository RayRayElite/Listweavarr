/* SPDX-License-Identifier: AGPL-3.0-only */
/* Local Plex origins are opt-in; never request access to every site. */
const files = [
  'layout.js',
  'bookmarks.js',
  'plex-adapter.js',
  'artwork.js',
  'settings.js',
  'home.js',
  'runtime.js',
];
async function register() {
  const { origins = [] } = await chrome.storage.local.get('origins');
  await chrome.scripting.unregisterContentScripts();
  const scripts = [];
  for (let i = 0; i < origins.length; i++) {
    const origin = origins[i];
    if (await chrome.permissions.contains({ origins: [origin + '/*'] }))
      scripts.push({
        id: 'plex-server-' + i,
        matches: [origin + '/web/*'],
        js: files,
        world: 'MAIN',
        runAt: 'document_start',
        persistAcrossSessions: true,
      });
  }
  if (scripts.length) await chrome.scripting.registerContentScripts(scripts);
}
chrome.runtime.onInstalled.addListener(register);
chrome.runtime.onStartup.addListener(register);
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.origins) register();
});
chrome.permissions.onRemoved.addListener(register);
