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
  function wrapFactory(original, enabled) {
    return function (module, exports, require) {
      if (!enabled()) return original(module, exports, require);
      const scratch = { exports: {} };
      original(scratch, scratch.exports, require);
      const native = scratch.exports;
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
    module.exports = { install, supported, builds };
  else {
    root.ListweavarrPlaylistBuilds = builds;
    const chunks = (root.webpackChunkplex_web_client ||= []);
    install(
      chunks,
      () => supported(document) && localStorage.getItem('playlist-companion:portrait') !== 'false'
    );
  }
})(globalThis);
