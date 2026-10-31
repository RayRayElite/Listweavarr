// SPDX-License-Identifier: AGPL-3.0-only
/* Public catalogue cards only. IndexedDB avoids localStorage's small poster
 * quota; failure/private browsing never prevents opening the live catalogue. */
function officialCardSnapshot(data) {
  if (!data || !Array.isArray(data.lists) || data.lists.length > 250) return null;
  return {
    version: data.version,
    note: data.note || '',
    lists: data.lists
      .filter((r) => typeof r.id === 'string' && typeof r.name === 'string')
      .map((r) =>
        Object.fromEntries(
          [
            'id',
            'name',
            'description',
            'version',
            'count',
            'poster',
            'playlist_poster',
            'kind',
            'provider',
            'updated_at',
          ]
            .filter((k) => r[k] !== undefined)
            .map((k) => [k, r[k]])
        )
      ),
  };
}
function officialCardCache(value) {
  return new Promise((resolve) => {
    if (!globalThis.indexedDB) return resolve(null);
    let done = false,
      db;
    const finish = (result) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      db?.close();
      resolve(result);
    };
    const timer = setTimeout(() => finish(null), 1500);
    try {
      const open = indexedDB.open('listweavarr-catalogue-cards', 1);
      open.onupgradeneeded = () => open.result.createObjectStore('cards');
      open.onerror = open.onblocked = () => finish(null);
      open.onsuccess = () => {
        db = open.result;
        if (done) return db.close();
        const tx = db.transaction('cards', value ? 'readwrite' : 'readonly');
        const request = value
          ? tx.objectStore('cards').put(officialCardSnapshot(value), 'official')
          : tx.objectStore('cards').get('official');
        let result = null;
        request.onsuccess = () => {
          result = value ? value : officialCardSnapshot(request.result);
        };
        tx.oncomplete = () => finish(result);
        tx.onerror = tx.onabort = () => finish(null);
      };
    } catch {
      finish(null);
    }
  });
}
