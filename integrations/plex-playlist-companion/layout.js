/* SPDX-License-Identifier: AGPL-3.0-only */
/* Run before Plex's main chunk. Change the shared metric, not DOM heights:
 * Plex's cards AND virtualized row calculations then use the same ratio. */
(function (root) {
  'use strict';
  const builds = [
    'main-8792-e90a21a5fe7ae941e8eb-plex-4.160.0-75ddd7b.js',
    'main-8792-681b145bfe8a22701a49-plex-4.147.1-4ca0656.js',
    'main-8792-0fadf59092c873ab638b-plex-4.163.0-8246fd2.js',
  ];
  function supported(document) {
    return Array.from(document.scripts).some((script) =>
      builds.some((build) => script.src.endsWith('/' + build))
    );
  }
  function installSafety(view, storage) {
    if (view.__listweavarrCompanionSafety) return view.__listweavarrCompanionSafety;
    let memory = false;
    const disabled = () => {
      try {
        return storage.getItem('playlist-companion:disabled') === 'true';
      } catch {
        return memory;
      }
    };
    const toggle = () => {
      memory = !disabled();
      try {
        storage.setItem('playlist-companion:disabled', String(memory));
      } catch {}
      view.location.reload();
    };
    view.addEventListener(
      'keydown',
      (event) => {
        if (
          event.ctrlKey &&
          event.altKey &&
          event.shiftKey &&
          !event.metaKey &&
          !event.repeat &&
          (event.code === 'KeyL' || event.key?.toLowerCase() === 'l')
        ) {
          event.preventDefault();
          event.stopImmediatePropagation();
          toggle();
        }
      },
      true
    );
    return (view.__listweavarrCompanionSafety = { disabled, toggle });
  }
  function wrapFactory(original, enabled) {
    return function (module, exports, require) {
      if (!enabled()) return original(module, exports, require);
      const scratch = { exports: {} };
      original(scratch, scratch.exports, require);
      const native = scratch.exports;
      // Version strings are diagnostic only. If the module contract changes,
      // leave that native module unchanged instead of assuming its numeric ID.
      const metric = Object.getOwnPropertyDescriptor(native, 'Ay');
      if (
        !metric?.get ||
        typeof native.Ay !== 'function' ||
        native.Ay('movie') !== 2 / 3 ||
        native.Ay('playlist') !== 1
      ) {
        module.exports = native;
        return;
      }
      for (const key of Reflect.ownKeys(native)) {
        const descriptor = Object.getOwnPropertyDescriptor(native, key);
        if (key === 'Ay')
          descriptor.get = () => (type, subtype, options) =>
            type === 'playlist' &&
            !['audio', 'photo'].includes(subtype) &&
            !options?.displayImageType
              ? 2 / 3
              : native.Ay(type, subtype, options);
        Object.defineProperty(exports, key, descriptor);
      }
      root.__listweavarrPlaylistLayout = { installed: true };
    };
  }
  function install(chunks, enabled) {
    const seen = new WeakSet();
    function decorate(push) {
      return function (...entries) {
        for (const entry of entries) {
          const factories = entry?.[1];
          const factory = factories?.[77981];
          if (typeof factory === 'function' && !seen.has(factory)) {
            const wrapped = wrapFactory(factory, enabled);
            seen.add(wrapped);
            factories[77981] = wrapped;
          }
        }
        return push.apply(this, entries);
      };
    }
    // Webpack replaces push during startup. Each wrapper captures its delegate
    // rather than a mutable reference, so Webpack's parent callback cannot recurse.
    let push = decorate(chunks.push);
    Object.defineProperty(chunks, 'push', {
      configurable: true,
      get: () => push,
      set: (next) => {
        push = decorate(next);
      },
    });
  }
  if (typeof module !== 'undefined' && module.exports)
    module.exports = { install, supported, builds, installSafety };
  else {
    root.ListweavarrPlaylistBuilds = builds;
    const safety = installSafety(root, localStorage);
    if (safety.disabled()) return;
    const chunks = (root.webpackChunkplex_web_client ||= []);
    install(
      chunks,
      () => !safety.disabled() && localStorage.getItem('playlist-companion:portrait') !== 'false'
    );
  }
})(globalThis);
