/* SPDX-License-Identifier: AGPL-3.0-only */
/* Portrait resume row. Uses only our DOM; never stretches a virtualized Plex grid. */
(function (root) {
  'use strict';
  function isHome(hash) {
    return /^(?:#!?\/(?:home)?(?:\?.*)?)?$/.test(hash || '');
  }
  function findHomeContainer(document) {
    const page = document.querySelector('[class*="PageContent-pageContentScroller-"]');
    // Plex can apply both page and scroller classes to the same element.
    // querySelector searches descendants only, so retain the page itself.
    if (page) return page.querySelector('[class*="Scroller-scroller-"]') || page;
    const hub = document.querySelector('[class*="HubCell-hubCell-"], [class*="Hub-hub-"]');
    return hub?.closest('[class*="PageContent-innerPageContent-"]') || hub?.parentElement;
  }
  function findHomePlacement(document) {
    const heading = Array.from(
      document.querySelectorAll('h1,h2,h3,[role="heading"],[class*="Hub"],[class*="hub"]')
    ).find((element) => element.textContent.trim() === 'Continue Watching');
    if (heading) {
      let hub = heading.closest('[class*="HubCell-hubCell-"], [class*="Hub-hub-"]');
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
  function mount(api, core, storage) {
    console.info('[Listweavarr Playlist Companion] home component mounted');
    const section = document.createElement('section');
    section.setAttribute('aria-label', 'Continue Playlists');
    section.className = 'lw-playlist-home';
    const style = document.createElement('style');
    style.textContent =
      '.lw-playlist-home{padding:22px 24px;color:#eee;font:14px system-ui}.lw-playlist-home header{display:flex;align-items:center;gap:16px;margin-bottom:16px}.lw-playlist-home h2{font-size:23px;margin:0;flex:1}.lw-playlist-cards{display:flex;gap:20px;overflow-x:auto;padding:4px 4px 16px}.lw-playlist-card{width:168px;flex:none}.lw-playlist-cover{display:flex;align-items:center;justify-content:center;width:168px;height:252px;border-radius:6px;overflow:hidden;background:linear-gradient(145deg,#34312c,#131313);color:#e5a00d;font-size:44px;border:0;padding:0;cursor:pointer}.lw-playlist-cover:hover,.lw-playlist-cover:focus-visible{outline:2px solid #e5a00d;outline-offset:2px}.lw-playlist-cover img{width:100%;height:100%;object-fit:contain}.lw-playlist-card h3{font-size:15px;margin:10px 0 5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lw-playlist-card p{font-size:12px;line-height:1.5;color:#bbb;margin:4px 0;overflow-wrap:anywhere}.lw-playlist-home button.lw-text{background:none;border:0;color:#c8c8c8;cursor:pointer;padding:3px 0;font:inherit}.lw-playlist-home button.lw-text:hover{color:#e5a00d}.lw-playlist-home progress{width:100%;height:4px;accent-color:#e5a00d}.lw-playlist-home [role=status]{font-size:13px;color:#bbb}';
    document.head.append(style);
    style.textContent +=
      '.lw-playlist-poster{position:relative;width:168px;height:252px}.lw-playlist-home button.lw-playlist-edit{position:absolute;right:8px;top:8px;display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;border:0;background:#000c;color:#eee;opacity:0;pointer-events:none;cursor:pointer;transition:opacity .15s}.lw-playlist-poster:hover .lw-playlist-edit,.lw-playlist-poster:focus-within .lw-playlist-edit{opacity:1;pointer-events:auto}.lw-playlist-home button.lw-playlist-edit:hover{color:#e5a00d}.lw-playlist-home input[type=file]{display:none!important}';
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
    function render() {
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
        const saved = core.load(storage, selection);
        if (!saved) continue;
        if (saved.completed && saved.entryNumber === saved.totalEntries) continue;
        const article = document.createElement('article');
        article.className = 'lw-playlist-card';
        const cover = document.createElement('button');
        const poster = document.createElement('div');
        poster.className = 'lw-playlist-poster';
        poster.append(cover);
        cover.className = 'lw-playlist-cover';
        cover.textContent = selection.title.slice(0, 1).toUpperCase();
        cover.setAttribute('aria-label', 'Resume ' + selection.title);
        cover.onclick = async () => {
          cover.disabled = true;
          status.textContent = 'Preparing playlist…';
          try {
            const result = await api.start(selection, true);
            status.textContent = 'Resuming ' + result.title;
          } catch (error) {
            status.textContent = error.message || 'Could not resume this playlist';
          } finally {
            cover.disabled = false;
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
        if (saved.totalEntries) {
          const meter = document.createElement('progress');
          meter.max = saved.totalEntries;
          meter.value = saved.entryNumber - 1;
          meter.setAttribute('aria-label', 'Playlist items before this entry');
          article.append(meter);
        }
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/jpeg,image/png,image/webp';
        input.hidden = true;
        input.style.setProperty('display', 'none', 'important');
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
          event.stopPropagation();
          input.click();
        };
        poster.append(choose);
        input.onchange = async () => {
          const file = input.files?.[0];
          if (!file) return;
          if (!/^image\/(?:jpeg|png|webp)$/.test(file.type) || file.size > 5 * 1024 * 1024) {
            status.textContent = 'Choose a JPG, PNG or WebP under 5 MB.';
            return;
          }
          try {
            await artwork(selection, file);
            dirty = true;
            schedule();
          } catch (error) {
            status.textContent = error.message;
          }
        };
        article.append(input);
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
        rows = (await api.playlists())
          .filter((row) => row.bookmark)
          .sort((a, b) => (b.bookmark.updatedAt || 0) - (a.bookmark.updatedAt || 0));
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
      if (diagnosticCount < 3) layoutDiagnostic();
      if (!isHome(location.hash)) {
        section.remove();
        return;
      }
      const placement = findHomePlacement(document);
      if (
        placement &&
        (!section.isConnected ||
          section.parentElement !== placement.container ||
          (placement.hub
            ? section.previousElementSibling !== placement.hub
            : placement.container.firstChild !== section))
      ) {
        placement.container.insertBefore(section, placement.before);
        console.info('[Listweavarr Playlist Companion] Continue Playlists row attached');
      }
      if (section.isConnected && dirty) refresh();
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
    observer.observe(document.getElementById('plex') || document.body, {
      childList: true,
      subtree: true,
    });
    const changed = () => {
      dirty = true;
      schedule();
    };
    root.addEventListener('hashchange', changed);
    root.addEventListener('listweavarr-playlist-progress', changed);
    attach();
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearTimeout(retryTimer);
      observer.disconnect();
      root.removeEventListener('hashchange', changed);
      root.removeEventListener('listweavarr-playlist-progress', changed);
      releaseImages();
      section.remove();
      style.remove();
    };
  }
  if (typeof module !== 'undefined' && module.exports)
    module.exports = { isHome, findHomeContainer, findHomePlacement };
  else root.ListweavarrPlaylistHome = { mount };
})(globalThis);
