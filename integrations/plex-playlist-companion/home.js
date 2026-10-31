/* SPDX-License-Identifier: AGPL-3.0-only */
/* Portrait resume row. Uses only our DOM; never stretches a virtualized Plex grid. */
(function (root) {
  'use strict';
  function isHome(hash) {
    return /^(?:#!?\/(?:home)?(?:\?.*)?)?$/.test(hash || '');
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
  function nativeRowMetrics(hub, section, view = root) {
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
      section.style.setProperty('--lw-poster-height', poster.width * 1.5 + 'px');
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
      .lw-playlist-editor{background:#252525;color:#eee;border:1px solid #555;border-radius:8px;padding:24px;width:420px;max-width:90vw;font:14px system-ui}
      .lw-playlist-editor::backdrop{background:#0009}
      .lw-playlist-editor button{background:#383838;color:#eee;border:1px solid #666;border-radius:4px;padding:10px 16px;margin:12px 8px 0 0;cursor:pointer}
      .lw-playlist-editor input[type=file]{display:none!important}
    `;
    document.head.append(style);
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
        play.setAttribute('aria-label', 'Resume ' + selection.title);
        play.title = 'Resume playlist';
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
            const result = await api.start(selection, true);
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
        title.title = selection.title;
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
          meter.value = saved.entryNumber - 1;
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
      if (section.isConnected && placement?.hub) nativeRowMetrics(placement.hub, section);
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
    root.addEventListener('resize', schedule);
    attach();
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearTimeout(retryTimer);
      observer.disconnect();
      root.removeEventListener('hashchange', changed);
      root.removeEventListener('listweavarr-playlist-progress', changed);
      root.removeEventListener('resize', schedule);
      releaseImages();
      section.remove();
      style.remove();
      editDialog.remove();
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
    };
  else root.ListweavarrPlaylistHome = { mount };
})(globalThis);
