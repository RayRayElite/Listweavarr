/* SPDX-License-Identifier: AGPL-3.0-only */
/* Portrait resume row. Uses only our DOM; never stretches a virtualized Plex grid. */
(function (root) {
  'use strict';
  const ROW_SELECTOR =
    '[class*="VirtualHubScroller-hub-"], [class*="HubCell-hubCell-"], [class*="Hub-hub-"]';
  function isHome(hash) {
    const route = (hash || '')
      .replace(/^#/, '')
      .replace(/^!/, '')
      .split('?')[0]
      .replace(/^\/+|\/+$/g, '');
    return route === '' || route === 'home';
  }
  function posterMultiplier(storage) {
    return storage.getItem('playlist-companion:portrait') === 'false' ? 1 : 1.5;
  }
  function playlistHref(selection) {
    return (
      '#!/server/' +
      encodeURIComponent(selection.serverId) +
      '/playlist?key=' +
      encodeURIComponent('/playlists/' + selection.playlistId)
    );
  }
  function itemHref(selection, saved) {
    return saved.completed || !saved.ratingKey
      ? playlistHref(selection)
      : '#!/server/' +
          encodeURIComponent(selection.serverId) +
          '/details?key=' +
          encodeURIComponent('/library/metadata/' + saved.ratingKey);
  }
  // Native hubs reserve extra height for their longest metadata. Measure the
  // visible content rather than stacking another full hub margin below it.
  function nativeRowMetrics(hub, section, view = root, multiplier = 1.5) {
    if (!hub || !view.getComputedStyle) return;
    const images = Array.from(hub.querySelectorAll('img'))
      .map((image) => image.getBoundingClientRect())
      .filter(
        (rect) =>
          rect.width >= 80 &&
          rect.width <= 350 &&
          rect.height / rect.width > 1.3 &&
          rect.height / rect.width < 1.8
      );
    const poster = images[0];
    if (poster) {
      section.style.setProperty('--lw-poster-width', poster.width + 'px');
      section.style.setProperty('--lw-poster-height', poster.width * multiplier + 'px');
      const inset = Math.max(0, Math.min(80, poster.left - section.getBoundingClientRect().left));
      section.style.setProperty('--lw-row-inset', inset + 'px');
      const next = images.find(
        (rect) => rect.left > poster.left && Math.abs(rect.top - poster.top) < 5
      );
      const gap = next && next.left - poster.left - poster.width;
      if (gap >= 8 && gap <= 48) section.style.setProperty('--lw-card-gap', gap + 'px');
    }
    const heading = Array.from(hub.querySelectorAll('h1,h2,h3,[role="heading"]')).find(
      (element) => element.textContent.trim() === 'Continue Watching'
    );
    if (heading) {
      const font = view.getComputedStyle(heading);
      section.style.setProperty('--lw-heading-font', font.fontFamily);
      section.style.setProperty('--lw-heading-size', font.fontSize);
      section.style.setProperty('--lw-heading-weight', font.fontWeight);
    }
    const bounds = hub.getBoundingClientRect();
    const bottoms = Array.from(hub.querySelectorAll('img,a,span,p,small'))
      .filter(
        (element) =>
          element.tagName === 'IMG' || (!element.children.length && element.textContent.trim())
      )
      .map((element) => element.getBoundingClientRect())
      .filter(
        (rect) =>
          rect.width && rect.height && rect.top >= bounds.top && rect.bottom <= bounds.bottom + 1
      )
      .map((rect) => rect.bottom);
    if (!bottoms.length) return;
    section.style.marginTop = '0px';
    const excess = section.getBoundingClientRect().top - Math.max(...bottoms) - 32;
    section.style.marginTop = -Math.max(0, Math.min(excess, 160)) + 'px';
  }
  function findHomeContainer(document) {
    const page = document.querySelector('[class*="PageContent-pageContentScroller-"]');
    // Plex can apply both page and scroller classes to the same element.
    // querySelector searches descendants only, so retain the page itself.
    if (page)
      return page.matches?.('[class*="Scroller-scroller-"]')
        ? page
        : page.querySelector('[class*="Scroller-scroller-"]') || page;
    const hub = document.querySelector(ROW_SELECTOR);
    return hub?.closest('[class*="PageContent-innerPageContent-"]') || hub?.parentElement;
  }
  function rowPreference(storage) {
    try {
      const value = JSON.parse(storage.getItem('playlist-companion:home-position') || '{}');
      return {
        mode: ['top', 'after-continue', 'after-row', 'bottom'].includes(value.mode)
          ? value.mode
          : 'after-continue',
        index:
          Number.isInteger(value.index) && value.index >= 1 && value.index <= 100 ? value.index : 1,
      };
    } catch {
      return { mode: 'after-continue', index: 1 };
    }
  }
  function findHomePlacement(document, preference = { mode: 'after-continue' }) {
    if (preference.mode !== 'after-continue') {
      const selector = ROW_SELECTOR;
      const hubs = Array.from(document.querySelectorAll(selector)).filter(
        (hub) => !hub.closest?.('.lw-playlist-home') && !hub.parentElement?.closest?.(selector)
      );
      if (hubs.length) {
        if (preference.mode === 'top')
          return {
            container: hubs[0].parentElement,
            before: hubs[0],
            hub: null,
            reference: hubs[0],
          };
        const hub =
          preference.mode === 'bottom'
            ? hubs[hubs.length - 1]
            : hubs[Math.min(hubs.length - 1, Math.max(0, (preference.index || 1) - 1))];
        return { container: hub.parentElement, before: hub.nextSibling, hub };
      }
      const container = findHomeContainer(document);
      return container
        ? {
            container,
            before: preference.mode === 'top' ? container.firstChild : null,
            hub: null,
            atEnd: preference.mode !== 'top',
          }
        : null;
    }
    const heading = Array.from(
      document.querySelectorAll('h1,h2,h3,[role="heading"],[class*="Hub"],[class*="hub"]')
    ).find((element) => element.textContent.trim() === 'Continue Watching');
    if (heading) {
      let hub = heading.closest(ROW_SELECTOR);
      if (!hub) {
        for (
          let parent = heading.parentElement;
          parent && parent !== document.body;
          parent = parent.parentElement
        ) {
          if (
            parent.querySelector(
              'img,[class*="MetadataPosterCard-"],[class*="PosterCard-"],[class*="MetadataPosterCardLink-"]'
            )
          ) {
            hub = parent;
            break;
          }
        }
      }
      // Never insert between a native heading and its cards while they load.
      return hub?.parentElement
        ? { container: hub.parentElement, before: hub.nextSibling, hub }
        : null;
    }
    const container = findHomeContainer(document);
    return container ? { container, before: container.firstChild, hub: null } : null;
  }
  // Move complete sibling hubs, never their virtualized cards. Unknown or
  // absolutely positioned layouts are left untouched. Keeping real DOM order
  // also keeps sequential keyboard focus aligned with what is displayed.
  const anonymousRows = new WeakMap();
  const anonymousCounts = new Map();
  function rowSource(heading) {
    const link = heading?.querySelector('a');
    const href = link?.getAttribute?.('href') || link?.href || '';
    try {
      const url = new URL(href, 'https://app.plex.tv/desktop/');
      const route = url.hash.replace(/^#!?/, '') || url.pathname;
      const [path, query = ''] = route.split('?');
      const params = new URLSearchParams(query || url.search);
      const values = [
        'key',
        'source',
        'sectionId',
        'librarySectionID',
        'hubIdentifier',
        'type',
        'context',
        'contentDirectoryID',
        'directoryId',
        'directoryKey',
      ].flatMap((key) => (params.has(key) ? [[key, params.get(key)]] : []));
      const safe = path + '?' + new URLSearchParams(values).toString();
      const decoded = decodeURIComponent(safe);
      return {
        identity: href ? safe : '',
        server: path.match(/\/server\/([^/]+)/)?.[1] || '',
        section:
          decoded.match(/\/library\/sections\/(\d+)/)?.[1] ||
          params.get('sectionId') ||
          params.get('librarySectionID') ||
          (/^\d+$/.test(params.get('source') || '') ? params.get('source') : ''),
      };
    } catch {
      return { identity: '', server: '', section: '' };
    }
  }
  function screenOrder(rows) {
    return [...rows].sort((a, b) => {
      const first = a.element.getBoundingClientRect?.(),
        second = b.element.getBoundingClientRect?.();
      return first && second ? first.top - second.top : 0;
    });
  }
  function nativeRows(document, view = root) {
    const container = findHomeContainer(document);
    if (!container) return [];
    const hubs = Array.from(
      document.querySelectorAll('[class*="VirtualHubScroller-hub-"], [class*="Hub-hub-"]')
    ).filter((hub) => !hub.closest?.('.lw-playlist-home'));
    const rows = hubs.flatMap((element) => {
      const heading = element.querySelector('h1,h2,h3,[role="heading"]');
      const title = (heading?.textContent || heading?.getAttribute?.('aria-label') || '').trim();
      const wrappers = [];
      let ancestor = element.parentElement;
      while (ancestor && ancestor !== container) {
        wrappers.push(ancestor);
        ancestor = ancestor.parentElement;
      }
      if (
        ancestor !== container ||
        !title ||
        title.length > 300 ||
        (element.getClientRects && !element.getClientRects().length) ||
        ['absolute', 'fixed'].includes(view.getComputedStyle?.(element).position)
      )
        return [];
      return [{ element, title, key: title, container, wrappers, source: rowSource(heading) }];
    });
    const names = new Map();
    for (const row of rows) names.set(row.title, (names.get(row.title) || 0) + 1);
    for (const row of rows) {
      if (row.source.identity) row.key = JSON.stringify([row.title, row.source.identity]);
      if (names.get(row.title) <= 1) continue;
      if (!row.source.identity) {
        if (!anonymousRows.has(row.element)) {
          const index = (anonymousCounts.get(row.title) || 0) + 1;
          anonymousCounts.set(row.title, index);
          anonymousRows.set(row.element, index);
        }
        row.key = JSON.stringify([row.title, 'unidentified', anonymousRows.get(row.element)]);
      }
      row.label =
        row.title +
        ' / ' +
        (row.source.section
          ? 'Library ' + row.source.section
          : 'source ' + (anonymousRows.get(row.element) || ''));
    }
    return rows;
  }
  function resolveRowOrder(rows, order) {
    const result = [];
    for (const key of order) {
      const matches = rows.some((row) => row.key === key)
        ? [key]
        : rows.filter((row) => row.title === key).map((row) => row.key);
      for (const value of matches.length ? matches : [key])
        if (!result.includes(value)) result.push(value);
    }
    return result;
  }
  function applyNativeOrder(rows, order) {
    const rank = new Map(order.map((key, index) => [key, index]));
    const groups = new Map();
    for (const row of rows) {
      const parent = row.element.parentElement;
      if (!groups.has(parent)) groups.set(parent, []);
      groups.get(parent).push(row);
    }
    // Preserve React ownership: reorder siblings only. Cross-container visual
    // ordering is handled by a reversible flex/display:contents layer below.
    for (const [parent, group] of groups) {
      const sorted = [...group].sort(
        (a, b) => (rank.get(a.key) ?? 10000) - (rank.get(b.key) ?? 10000)
      );
      for (let index = 0; index < sorted.length; index++) {
        const live = Array.from(parent.children).filter((element) =>
          group.some((row) => row.element === element)
        );
        if (live[index] !== sorted[index].element)
          parent.insertBefore(sorted[index].element, live[index]);
      }
    }
  }
  function nativeVisualOrder(rows, order) {
    if (!rows.length) return { restore() {}, rank: new Map() };
    const rank = new Map(order.map((key, index) => [key, index]));
    const sorted = [...rows].sort(
      (a, b) => (rank.get(a.key) ?? 10000) - (rank.get(b.key) ?? 10000)
    );
    const positions = new Map(sorted.map((row, index) => [row.key, index * 2]));
    const originals = [];
    const seen = new Map();
    function set(element, key, value) {
      if (!seen.has(element)) seen.set(element, new Set());
      if (!seen.get(element).has(key)) {
        originals.push([element, key, element.style.getPropertyValue(key)]);
        seen.get(element).add(key);
      }
      element.style.setProperty(key, value);
    }
    set(rows[0].container, 'display', 'flex');
    set(rows[0].container, 'flex-direction', 'column');
    for (const row of rows) {
      for (const wrapper of row.wrappers) set(wrapper, 'display', 'contents');
      set(row.element, 'order', String(positions.get(row.key)));
      set(row.element, 'flex-shrink', '0');
    }
    return {
      rank: positions,
      restore() {
        for (const [element, key, value] of originals) {
          if (value) element.style.setProperty(key, value);
          else if (element.style.removeProperty) element.style.removeProperty(key);
          else element.style.setProperty(key, '');
        }
      },
    };
  }
  function mount(api, core, storage) {
    console.info('[Listweavarr Playlist Companion] home component mounted');
    const section = document.createElement('section');
    section.setAttribute('aria-label', 'Continue Playlists');
    section.className = 'lw-playlist-home';
    const style = document.createElement('style');
    style.textContent = `
      .lw-playlist-home{padding:0 var(--lw-row-inset,24px) 24px;color:#eee;font:14px system-ui}
      .lw-playlist-home header{display:flex;align-items:center;gap:16px;margin-bottom:14px}
      .lw-playlist-home h2{font-family:var(--lw-heading-font,inherit);font-size:var(--lw-heading-size,22px);font-weight:var(--lw-heading-weight,600);margin:0;flex:1}
      .lw-playlist-cards{display:flex;align-items:flex-start;gap:var(--lw-card-gap,20px);overflow-x:auto;padding:4px 3px 8px}
      .lw-playlist-card{width:var(--lw-poster-width,168px);flex:none;display:grid;grid-template-rows:var(--lw-poster-height,252px) 22px 36px 18px 4px;gap:6px}
      .lw-playlist-poster{position:relative;width:100%;height:100%;border-radius:5px}
      .lw-playlist-cover{position:relative;display:flex;align-items:center;justify-content:center;width:100%;height:100%;border-radius:5px;overflow:hidden;background:linear-gradient(145deg,#34312c,#131313);color:#e5a00d;font-size:44px;border:0;padding:0;cursor:pointer;text-decoration:none}
      .lw-playlist-cover:after{content:'';position:absolute;inset:0;background:#0005;opacity:0;transition:opacity .15s;pointer-events:none}
      .lw-playlist-poster:hover .lw-playlist-cover:after,.lw-playlist-poster:focus-within .lw-playlist-cover:after{opacity:1}
      .lw-playlist-poster:hover,.lw-playlist-poster:focus-within{outline:2px solid #e5a00d;outline-offset:1px}
      .lw-playlist-cover img{width:100%;height:100%;object-fit:cover}
      .lw-playlist-card h3{font-size:15px;line-height:22px;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .lw-playlist-card h3 a,.lw-playlist-card p a{color:inherit;text-decoration:none}
      .lw-playlist-card a:hover{color:#fff;text-decoration:none}
      .lw-playlist-card p{font-size:12px;line-height:18px;color:#bbb;margin:0;overflow:hidden}
      .lw-playlist-caption{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:anywhere}
      .lw-playlist-position{white-space:nowrap;text-overflow:ellipsis}
      .lw-playlist-home button.lw-text{background:none;border:0;color:#c8c8c8;cursor:pointer;padding:3px 0;font:inherit}
      .lw-playlist-home button.lw-text:hover{color:#e5a00d}
      .lw-playlist-home progress{display:block;align-self:end;width:100%;height:3px;margin:0;accent-color:#e5a00d}
      .lw-playlist-home [role=status]{font-size:13px;color:#bbb}
      .lw-playlist-home [role=status]:empty{display:none}
      .lw-playlist-home button.lw-playlist-edit,.lw-playlist-home button.lw-playlist-play{position:absolute;z-index:2;display:flex;align-items:center;justify-content:center;border-radius:50%;color:#eee;opacity:0;pointer-events:none;cursor:pointer;transition:opacity .15s}
      .lw-playlist-home button.lw-playlist-play{left:50%;top:50%;transform:translate(-50%,-50%);width:46px;height:46px;border:2px solid #eee;background:#0009;padding:9px}
      .lw-playlist-home button.lw-playlist-edit{left:7px;bottom:7px;width:32px;height:32px;border:0;background:#0009}
      .lw-playlist-poster:hover .lw-playlist-edit,.lw-playlist-poster:focus-within .lw-playlist-edit,.lw-playlist-poster:hover .lw-playlist-play,.lw-playlist-poster:focus-within .lw-playlist-play{opacity:1;pointer-events:auto}
      .lw-playlist-home button.lw-playlist-edit:hover,.lw-playlist-home button.lw-playlist-play:hover{color:#e5a00d;border-color:#e5a00d}
      .lw-playlist-menu{position:absolute;right:7px;bottom:7px;z-index:5;font-size:14px}
      .lw-playlist-menu summary{list-style:none;cursor:pointer;border-radius:50%;background:#000b;color:#fff;width:32px;height:32px;text-align:center;font-size:24px;line-height:25px;opacity:0}
      .lw-playlist-menu summary::-webkit-details-marker{display:none}
      .lw-playlist-poster:hover .lw-playlist-menu summary,.lw-playlist-poster:focus-within .lw-playlist-menu summary,.lw-playlist-menu[open] summary{opacity:1}
      .lw-playlist-card[data-pinned=true] .lw-playlist-poster:before{content:'Pinned';position:absolute;left:6px;top:6px;z-index:2;padding:3px 6px;background:#000b;color:#e5a00d;border-radius:3px;font-size:11px;pointer-events:none}
      .lw-playlist-menu-options{position:absolute;right:-7px;bottom:38px;width:var(--lw-poster-width,168px);max-height:calc(var(--lw-poster-height,252px) - 50px);overflow:auto;background:#282828;border:1px solid #555;border-radius:6px;padding:6px;box-shadow:0 8px 24px #0009}
      .lw-playlist-menu-options button,.lw-playlist-menu-options a{display:block;width:100%;border:0;background:none;color:#eee;text-align:left;padding:10px;font:inherit;cursor:pointer;text-decoration:none;border-radius:3px;box-sizing:border-box}
      .lw-playlist-menu-options button:hover,.lw-playlist-menu-options a:hover{background:#444;color:#e5a00d}
      .lw-playlist-editor{background:#252525;color:#eee;border:1px solid #555;border-radius:8px;padding:24px;width:420px;max-width:90vw;font:14px system-ui}
      .lw-playlist-editor::backdrop{background:#0009}
      .lw-playlist-editor button{background:#383838;color:#eee;border:1px solid #666;border-radius:4px;padding:10px 16px;margin:12px 8px 0 0;cursor:pointer}
      .lw-playlist-editor input[type=file]{display:none!important}
    `;
    document.head.append(style);
    const nativeDefaults = new WeakMap();
    let nativeSequence = 0,
      reordered = false,
      nativeVisual = null;
    const orderDialog = document.createElement('dialog');
    orderDialog.className = 'lw-playlist-editor';
    orderDialog.setAttribute('aria-label', 'Arrange Plex Home rows');
    orderDialog.style.cssText = 'width:600px;max-height:80vh;overflow:auto';
    document.body.append(orderDialog);
    const orderStorageKey = () => 'playlist-companion:home-order:v1:' + (api.profile?.() || '');
    const companionKey = 'companion:continue-playlists';
    function companionRow(rows) {
      if (!section.isConnected || !rows.length) return null;
      const container = rows[0].container,
        wrappers = [];
      let ancestor = section.parentElement;
      while (ancestor && ancestor !== container) {
        wrappers.push(ancestor);
        ancestor = ancestor.parentElement;
      }
      return ancestor === container
        ? {
            element: section,
            title: 'Continue Playlists',
            label: 'Continue Playlists',
            key: companionKey,
            container,
            wrappers,
          }
        : null;
    }
    function nativeOrder() {
      try {
        const value = JSON.parse(storage.getItem(orderStorageKey()) || '[]');
        return Array.isArray(value) &&
          value.length <= 100 &&
          value.every((key) => typeof key === 'string' && key.length <= 2000)
          ? value
          : [];
      } catch {
        return [];
      }
    }
    function orderedNativeRows() {
      const found = nativeRows(document);
      for (const row of found)
        if (!nativeDefaults.has(row.element)) nativeDefaults.set(row.element, nativeSequence++);
      return found.sort((a, b) => nativeDefaults.get(a.element) - nativeDefaults.get(b.element));
    }
    root.ListweavarrPlaylistHome.openOrder = () => {
      if (!isHome(location.hash)) {
        location.hash = '#!/';
        return false;
      }
      const native = nativeRows(document);
      const own = companionRow(native);
      const rows = screenOrder(own ? [...native, own] : native);
      if (!rows.length)
        console.info(
          '[Listweavarr Playlist Companion] native row scan ' +
            JSON.stringify({
              container: findHomeContainer(document)?.className || '',
              candidates: Array.from(document.querySelectorAll(ROW_SELECTOR))
                .slice(0, 25)
                .map((element) => ({
                  cls: element.className,
                  parent: element.parentElement?.className,
                  heading: !!element.querySelector('h1,h2,h3,[role="heading"]'),
                  keyLength: (
                    element.querySelector('h1,h2,h3,[role="heading"]')?.textContent || ''
                  ).trim().length,
                  rects: element.getClientRects().length,
                  nested: !!element.parentElement?.closest?.(ROW_SELECTOR),
                  position: root.getComputedStyle?.(element).position,
                })),
              headingParents: Array.from(document.querySelectorAll('h2'))
                .filter((element) => !element.closest?.('.lw-playlist-home'))
                .slice(0, 8)
                .map((element) => ({
                  parent: element.parentElement?.className,
                  grandparent: element.parentElement?.parentElement?.className,
                })),
            })
        );
      const profile = api.profile?.() || '';
      let draft = rows.map((row) => row.key);
      const labels = new Map(rows.map((row) => [row.key, row.label || row.title || row.key]));
      if (api.sections)
        api
          .sections()
          .then((sections) => {
            if (!orderDialog.open || (api.profile?.() || '') !== profile) return;
            for (const row of rows) {
              if (row.source?.section) {
                const match = sections.find(
                  (source) =>
                    source.serverId === row.source.server && source.id === row.source.section
                );
                if (match) labels.set(row.key, row.title + ' / ' + match.title);
              }
            }
            draw();
          })
          .catch(() => {});
      function draw() {
        orderDialog.replaceChildren();
        const heading = document.createElement('h2');
        heading.textContent = 'Arrange Plex Home rows';
        const note = document.createElement('p');
        note.textContent = rows.length
          ? 'Reorder the loaded native rows. Scroll Home to load more rows first. New rows follow saved rows. This editor includes Continue Playlists. Its separate placement setting applies when no full Home order is saved. Saved per profile on this client. Rows keep their Plex containers; sequential Tab navigation across Continue Watching can retain the native Plex order.'
          : 'No identifiable Home rows loaded yet. Close this window and let Home finish loading. Unnamed and unsupported rows are left unchanged.';
        orderDialog.append(heading, note);
        draft.forEach((key, index) => {
          const line = document.createElement('div');
          line.style.cssText =
            'display:flex;align-items:center;gap:8px;border-bottom:1px solid #444';
          const label = document.createElement('span');
          label.style.flex = '1';
          label.textContent = labels.get(key) || key;
          line.append(label);
          for (const [name, delta] of [
            ['Up', -1],
            ['Down', 1],
          ]) {
            const button = document.createElement('button');
            button.textContent = name;
            button.disabled = index + delta < 0 || index + delta >= draft.length;
            button.setAttribute('aria-label', name + ' ' + (labels.get(key) || key));
            button.onclick = () => {
              [draft[index], draft[index + delta]] = [draft[index + delta], draft[index]];
              draw();
            };
            line.append(button);
          }
          orderDialog.append(line);
        });
        for (const [name, action] of [
          [
            'Save order',
            () => {
              if ((api.profile?.() || '') !== profile) {
                note.textContent = 'Profile changed. Reopen this window.';
                return;
              }
              const previous = nativeOrder();
              storage.setItem(
                orderStorageKey(),
                JSON.stringify([...draft, ...previous.filter((key) => !draft.includes(key))])
              );
              orderDialog.close();
              schedule();
            },
          ],
          [
            'Restore default',
            () => {
              if ((api.profile?.() || '') !== profile) {
                note.textContent = 'Profile changed. Reopen this window.';
                return;
              }
              storage.setItem(orderStorageKey(), '[]');
              applyNativeOrder(
                orderedNativeRows(),
                orderedNativeRows().map((row) => row.key)
              );
              orderDialog.close();
              schedule();
            },
          ],
          ['Cancel', () => orderDialog.close()],
        ]) {
          const button = document.createElement('button');
          button.textContent = name;
          button.disabled = name === 'Save order' && !rows.length;
          button.onclick = action;
          orderDialog.append(button);
        }
      }
      draw();
      orderDialog.showModal();
      return true;
    };
    let disposed = false,
      loading = false,
      dirty = true,
      rows = [],
      urls = [],
      timer,
      retryTimer;
    let retries = 0;
    let lastLayout = '',
      diagnosticCount = 0;
    async function artwork(selection, blob) {
      return blob
        ? root.ListweavarrPlaylistArtwork.set(selection, blob)
        : root.ListweavarrPlaylistArtwork.get(selection);
    }
    function releaseImages() {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls = [];
    }
    function text(tag, value) {
      const element = document.createElement(tag);
      element.textContent = value;
      return element;
    }
    let editSelection;
    const editDialog = document.createElement('dialog');
    editDialog.className = 'lw-playlist-editor';
    editDialog.setAttribute('aria-label', 'Edit playlist poster');
    const editHeading = text('h2', 'Edit playlist poster');
    const editNote = text(
      'p',
      'Choose a JPG, PNG or WebP under 5 MB. This poster is used by the companion and synced to paired clients when sync is enabled.'
    );
    const editStatus = text('p', '');
    editStatus.setAttribute('role', 'status');
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    input.hidden = true;
    const pick = text('button', 'Choose poster');
    pick.type = 'button';
    pick.onclick = () => input.click();
    const done = text('button', 'Done');
    done.type = 'button';
    done.onclick = () => editDialog.close();
    editDialog.append(editHeading, editNote, input, editStatus, pick, done);
    document.body.append(editDialog);
    input.onchange = async () => {
      const file = input.files?.[0],
        selection = editSelection;
      if (!file || !selection) return;
      if (!/^image\/(?:jpeg|png|webp)$/.test(file.type) || file.size > 5000000) {
        editStatus.textContent = 'Choose a JPG, PNG or WebP under 5 MB.';
        return;
      }
      pick.disabled = true;
      try {
        await artwork(selection, file);
        editDialog.close();
        dirty = true;
        schedule();
      } catch (error) {
        editStatus.textContent = error.message || 'Could not save this poster.';
      } finally {
        pick.disabled = false;
        input.value = '';
      }
    };
    function render() {
      rows = core.orderPlaylists(rows, storage);
      releaseImages();
      section.replaceChildren();
      const header = document.createElement('header');
      header.append(text('h2', 'Continue Playlists'));
      const diagnostics = text('button', '⚙');
      diagnostics.className = 'lw-text';
      diagnostics.title = 'Playlist companion settings';
      diagnostics.setAttribute('aria-label', 'Playlist companion settings');
      diagnostics.onclick = () => root.__listweavarrPlaylistCompanion?.openSettings?.();
      header.append(diagnostics);
      const cards = document.createElement('div');
      cards.className = 'lw-playlist-cards';
      const status = text('p', '');
      status.setAttribute('role', 'status');
      section.append(header, cards, status);
      for (const selection of rows) {
        const actual = core.load(storage, selection),
          pinned = core.isPinned(storage, selection);
        if ((!actual || actual.dismissed) && !pinned) continue;
        const finished = actual?.completed && actual.entryNumber === actual.totalEntries;
        if (finished && !pinned) continue;
        const saved =
          actual && !finished
            ? actual
            : {
                offsetMs: 0,
                completed: false,
                totalEntries: selection.count,
                entryNumber: 0,
                itemTitle: finished ? 'Finished / play again' : 'Start playlist',
              };
        const article = document.createElement('article');
        article.className = 'lw-playlist-card';
        const cover = document.createElement('a');
        const poster = document.createElement('div');
        poster.className = 'lw-playlist-poster';
        poster.append(cover);
        cover.className = 'lw-playlist-cover';
        cover.textContent = selection.title.slice(0, 1).toUpperCase();
        cover.setAttribute('aria-label', 'Open ' + selection.title);
        cover.href = playlistHref(selection);
        const play = document.createElement('button');
        play.type = 'button';
        play.className = 'lw-playlist-play';
        const playLabel = actual && !finished ? 'Resume' : 'Start';
        play.setAttribute('aria-label', playLabel + ' ' + selection.title);
        play.title = playLabel + ' playlist';
        const playSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        playSvg.setAttribute('viewBox', '0 0 24 24');
        playSvg.setAttribute('width', '24');
        playSvg.setAttribute('height', '24');
        playSvg.setAttribute('aria-hidden', 'true');
        const triangle = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        triangle.setAttribute('d', 'M7 4v16l14-8z');
        triangle.setAttribute('fill', 'currentColor');
        playSvg.append(triangle);
        play.append(playSvg);
        poster.append(play);
        play.onclick = async (event) => {
          event.preventDefault();
          event.stopPropagation();
          play.disabled = true;
          status.textContent = 'Preparing playlist…';
          try {
            const result = await api.start(selection, Boolean(actual) && !finished);
            status.textContent = 'Resuming ' + result.title;
          } catch (error) {
            status.textContent = error.message || 'Could not resume this playlist';
          } finally {
            play.disabled = false;
          }
        };
        article.append(
          poster,
          text('h3', selection.title),
          text(
            'p',
            saved.completed
              ? 'Up next: ' +
                  (saved.nextShowTitle ? saved.nextShowTitle + ' · ' : '') +
                  (saved.nextTitle || 'Next playlist item')
              : (saved.showTitle ? saved.showTitle + ' · ' : '') + (saved.itemTitle || 'Saved item')
          ),
          text(
            'p',
            saved.completed
              ? `Ready for item ${saved.entryNumber + 1} of ${saved.totalEntries}`
              : `${Math.floor(saved.offsetMs / 60000)}:${String(Math.floor(saved.offsetMs / 1000) % 60).padStart(2, '0')}${saved.entryNumber ? ' · ' + saved.entryNumber + ' of ' + saved.totalEntries : ''}`
          )
        );
        const title = article.querySelector('h3'),
          titleLink = text('a', selection.title);
        titleLink.href = playlistHref(selection);
        title.title = selection.title + (pinned ? ' (Pinned)' : '');
        if (pinned) article.setAttribute('data-pinned', 'true');
        title.replaceChildren(titleLink);
        const metadata = article.querySelectorAll('p');
        const caption = metadata[0];
        caption.className = 'lw-playlist-caption';
        caption.title = caption.textContent;
        const itemLink = text('a', caption.textContent);
        itemLink.href = itemHref(selection, saved);
        caption.replaceChildren(itemLink);
        metadata[1].className = 'lw-playlist-position';
        if (saved.totalEntries) {
          const meter = document.createElement('progress');
          meter.max = saved.totalEntries;
          meter.value = Math.max(0, saved.entryNumber - 1);
          meter.setAttribute('aria-label', 'Playlist items before this entry');
          article.append(meter);
        }
        const choose = document.createElement('button');
        choose.className = 'lw-playlist-edit';
        choose.setAttribute('aria-label', 'Edit poster for ' + selection.title);
        choose.title = 'Edit poster';
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('width', '18');
        svg.setAttribute('height', '18');
        svg.setAttribute('aria-hidden', 'true');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', 'M16 3l5 5-12 12-6 1 1-6L16 3zm-1 2l5 5');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', 'currentColor');
        path.setAttribute('stroke-width', '1.8');
        path.setAttribute('stroke-linejoin', 'round');
        svg.append(path);
        choose.append(svg);
        choose.onclick = (event) => {
          event.preventDefault();
          event.stopPropagation();
          editSelection = selection;
          editHeading.textContent = 'Edit ' + selection.title;
          editStatus.textContent = '';
          input.value = '';
          if (!editDialog.open) editDialog.showModal();
        };
        poster.append(choose);
        const menu = document.createElement('details');
        menu.className = 'lw-playlist-menu';
        const trigger = text('summary', '\u2026');
        trigger.title = 'Playlist options';
        trigger.setAttribute('aria-label', 'Options for ' + selection.title);
        const options = document.createElement('div');
        options.className = 'lw-playlist-menu-options';
        const open = text('a', 'Open playlist');
        open.href = playlistHref(selection);
        const edit = text('button', 'Edit poster');
        edit.type = 'button';
        edit.onclick = (event) => {
          menu.open = false;
          choose.onclick(event);
        };
        const remove = text('button', 'Remove from Continue Playlists');
        remove.type = 'button';
        remove.onclick = (event) => {
          event.preventDefault();
          event.stopPropagation();
          core.unpin(storage, selection);
          core.dismiss(storage, selection);
          render();
        };
        menu.addEventListener('keydown', (event) => {
          if (event.key === 'Escape') {
            menu.open = false;
            trigger.focus();
          }
        });
        menu.addEventListener('toggle', () => {
          if (menu.open)
            for (const other of cards.querySelectorAll('.lw-playlist-menu')) {
              if (other !== menu) other.open = false;
            }
        });
        const pin = text('button', pinned ? 'Unpin playlist' : 'Pin to front');
        pin.type = 'button';
        pin.onclick = (event) => {
          event.preventDefault();
          pinned ? core.unpin(storage, selection) : core.pin(storage, selection);
          render();
        };
        options.append(open, edit, pin);
        if (pinned) {
          const index = core.pins(storage, selection).indexOf(core.storageKey(selection));
          for (const [label, direction] of [
            ['Move pin left', -1],
            ['Move pin right', 1],
          ]) {
            const move = text('button', label);
            move.type = 'button';
            move.disabled =
              direction < 0 ? index === 0 : index === core.pins(storage, selection).length - 1;
            move.onclick = (event) => {
              event.preventDefault();
              core.movePin(storage, selection, direction);
              render();
            };
            options.append(move);
          }
        }
        options.append(remove);
        menu.append(trigger, options);
        poster.append(menu);
        cards.append(article);
        (async () => {
          let blob;
          try {
            blob = await artwork(selection);
          } catch {}
          if (!blob) {
            try {
              blob = await api.poster(selection);
            } catch {}
          }
          if (!blob || !cover.isConnected || disposed) return;
          const url = URL.createObjectURL(blob);
          urls.push(url);
          const image = document.createElement('img');
          image.src = url;
          image.alt = '';
          cover.replaceChildren(image);
        })();
      }
      if (!cards.children.length)
        status.textContent =
          'Start a video playlist using Plex’s normal Play button to track it here.';
    }
    async function refresh() {
      if (loading || disposed || !isHome(location.hash)) return;
      loading = true;
      dirty = false;
      try {
        rows = core.orderPlaylists(
          (await api.playlists()).filter((row) => row.bookmark || core.isPinned(storage, row)),
          storage
        );
        render();
        if (!rows.length && retries++ < 10) {
          clearTimeout(retryTimer);
          retryTimer = setTimeout(() => {
            dirty = true;
            schedule();
          }, 3000);
        }
      } catch {
        dirty = true;
      } finally {
        loading = false;
      }
    }
    function attach() {
      if (disposed) return;
      const width = parseFloat(section.style.getPropertyValue?.('--lw-poster-width')) || 168;
      section.style.setProperty('--lw-poster-height', width * posterMultiplier(storage) + 'px');
      if (diagnosticCount < 3) layoutDiagnostic();
      if (!isHome(location.hash)) {
        nativeVisual?.restore();
        nativeVisual = null;
        section.remove();
        return;
      }
      const native = orderedNativeRows();
      const preference = resolveRowOrder(native, nativeOrder());
      nativeVisual?.restore();
      nativeVisual = null;
      section.style.setProperty('order', '');
      if (preference.length) {
        applyNativeOrder(native, preference);
        const own = companionRow(native);
        nativeVisual = nativeVisualOrder(
          own && preference.includes(companionKey) ? [...native, own] : native,
          preference
        );
        reordered = true;
      } else if (reordered) {
        applyNativeOrder(native, []);
        reordered = false;
      }
      const placement = findHomePlacement(document, rowPreference(storage));
      if (
        placement &&
        (!section.isConnected ||
          section.parentElement !== placement.container ||
          (placement.hub
            ? section.previousElementSibling !== placement.hub
            : placement.reference
              ? section.nextElementSibling !== placement.reference
              : placement.atEnd
                ? placement.container.lastElementChild !== section
                : placement.container.firstChild !== section))
      ) {
        placement.container.insertBefore(section, placement.before);
        console.info('[Listweavarr Playlist Companion] Continue Playlists row attached');
      }
      if (nativeVisual) {
        const sorted = [...nativeVisual.rank.entries()].sort((a, b) => a[1] - b[1]);
        const pref = rowPreference(storage);
        let position = -1;
        if (preference.includes(companionKey)) position = nativeVisual.rank.get(companionKey) ?? -1;
        else if (pref.mode === 'bottom') position = sorted.length * 2 + 1;
        else if (pref.mode === 'after-row')
          position = (sorted[Math.min(sorted.length - 1, pref.index - 1)]?.[1] ?? -2) + 1;
        else if (pref.mode === 'after-continue')
          position =
            (nativeVisual.rank.get(
              native.find((row) => row.title === 'Continue Watching')?.key || 'Continue Watching'
            ) ?? -2) + 1;
        section.style.setProperty('order', String(position));
        section.style.setProperty('flex-shrink', '0');
      }
      if (section.isConnected && dirty) refresh();
      if (section.isConnected && (placement?.reference || placement?.hub))
        nativeRowMetrics(
          placement.reference || placement.hub,
          section,
          root,
          posterMultiplier(storage)
        );
    }
    function layoutDiagnostic() {
      if (disposed) return;
      const first = location.hash.split('?')[0].split('/').filter(Boolean)[1] || '';
      const route = ['', 'home', 'media', 'server', 'discover', 'watchlist', 'desktop'].includes(
        first
      )
        ? first
        : 'other';
      const classes = Array.from(
        new Set(
          Array.from(document.querySelectorAll('[class]'))
            .flatMap((element) => Array.from(element.classList))
            .filter((name) => /^(?:Hub|Home|Page|Scroll|Directory)/.test(name))
        )
      ).slice(0, 35);
      const signature = JSON.stringify({ home: isHome(location.hash), route, classes });
      if (signature !== lastLayout && diagnosticCount++ < 12) {
        lastLayout = signature;
        console.info('[Listweavarr Playlist Companion] home layout ' + signature);
      }
    }
    function schedule() {
      if (timer || disposed) return;
      timer = setTimeout(() => {
        timer = null;
        attach();
      }, 100);
    }
    const observer = new MutationObserver(schedule);
    // Plex's logo can replace its React root without changing the Home hash.
    // Observe the stable body so replacement roots cannot strand our observer.
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
    const changed = () => {
      dirty = true;
      schedule();
    };
    root.addEventListener('hashchange', changed);
    root.addEventListener('popstate', changed);
    const logoClicked = (event) => {
      if (event.target.closest?.('[class*="NavBar-logoContainer-"]')) changed();
    };
    document.addEventListener('click', logoClicked, true);
    root.addEventListener('listweavarr-playlist-progress', changed);
    root.addEventListener('resize', schedule);
    root.addEventListener('listweavarr-playlist-settings', changed);
    attach();
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearTimeout(retryTimer);
      observer.disconnect();
      root.removeEventListener('hashchange', changed);
      root.removeEventListener('popstate', changed);
      document.removeEventListener('click', logoClicked, true);
      root.removeEventListener('listweavarr-playlist-progress', changed);
      root.removeEventListener('resize', schedule);
      root.removeEventListener('listweavarr-playlist-settings', changed);
      releaseImages();
      section.remove();
      style.remove();
      editDialog.remove();
      orderDialog.remove();
      nativeVisual?.restore();
      delete root.ListweavarrPlaylistHome.openOrder;
    };
  }
  if (typeof module !== 'undefined' && module.exports)
    module.exports = {
      isHome,
      findHomeContainer,
      findHomePlacement,
      playlistHref,
      itemHref,
      nativeRowMetrics,
      mount,
      rowPreference,
      nativeRows,
      applyNativeOrder,
      nativeVisualOrder,
      screenOrder,
      rowSource,
      resolveRowOrder,
      posterMultiplier,
    };
  else root.ListweavarrPlaylistHome = { mount, rowPreference };
})(globalThis);
