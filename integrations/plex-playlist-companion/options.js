/* SPDX-License-Identifier: AGPL-3.0-only */
const status = document.getElementById('status');
async function render() {
  const { origins = [] } = await chrome.storage.local.get('origins');
  const list = document.getElementById('servers');
  list.replaceChildren();
  for (const origin of origins) {
    const item = document.createElement('li'),
      name = document.createElement('span'),
      remove = document.createElement('button');
    name.textContent = origin;
    remove.textContent = 'Remove';
    remove.onclick = async () => {
      await chrome.permissions.remove({ origins: [origin + '/*'] });
      await chrome.storage.local.set({ origins: origins.filter((value) => value !== origin) });
      render();
    };
    item.append(name, remove);
    list.append(item);
  }
}
document.getElementById('server-form').onsubmit = async (event) => {
  event.preventDefault();
  try {
    const url = new URL(document.getElementById('origin').value);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      !['/', '/web', '/web/'].includes(url.pathname)
    )
      throw Error('Use the Plex server address, without credentials or query parameters.');
    const granted = await chrome.permissions.request({ origins: [url.origin + '/*'] });
    if (!granted) throw Error('Server access was not granted.');
    const { origins = [] } = await chrome.storage.local.get('origins');
    await chrome.storage.local.set({ origins: [...new Set([...origins, url.origin])] });
    status.textContent = 'Enabled. Reload the Plex Web tab.';
    render();
  } catch (error) {
    status.textContent = error.message;
  }
};
render();
