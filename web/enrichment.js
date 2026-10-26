// SPDX-License-Identifier: AGPL-3.0-only
/* Supplemental providers load independently from title details and Plex coverage. */
const enrichmentCache = new Map();
let supplementalContext = null;
const supplementalSafeURL = (url) => {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && !u.username && !u.password ? u.href : null;
  } catch {
    return null;
  }
};
function supplementalLink(url, label) {
  const safe = supplementalSafeURL(url);
  return safe
    ? `<a href="${esc(safe)}" target="_blank" rel="noopener noreferrer">${esc(label)} &#8599;</a>`
    : esc(label);
}
function supplementalTile(row) {
  if (row.tmdb && ['movie', 'show'].includes(row.type)) {
    const tile = relationshipTile(row);
    return row.provider
      ? `<div class="supplemental-tile">${tile}<div class="supplemental-tile-source">${supplementalLink(row.url, row.provider)}</div></div>`
      : tile;
  }
  return `<article class="related-card supplemental-external"><strong>${esc(row.title)}</strong><small>${esc(row.relationship || 'Connection')} · ${esc(row.provider || '')}</small>${supplementalLink(row.url, 'View source')}</article>`;
}
function supplementalRows(rows) {
  return rows
    .map(
      (r) =>
        `<div class="supplemental-connection"><div>${r.tmdb && ['movie', 'show'].includes(r.type) ? `<button class="person-link" data-title-tmdb="${esc(r.tmdb)}" data-title-type="${esc(r.type)}">${esc(r.title)}</button>` : supplementalLink(r.url, r.title)}<small>${esc(r.relationship)} · ${esc(r.provider)}</small></div></div>`
    )
    .join('');
}
function uniqueRelations(rows) {
  const seen = new Set();
  return rows.filter((r) => !seen.has(r.key) && seen.add(r.key));
}
window.loadSupplementalMetadata = async (m, sequence, original) => {
  supplementalContext = { m, sequence, original };
  const key = (m.related_type === 'show' ? 'tv' : 'movie') + ':' + m.related_id;
  const host = $('supplemental-metadata');
  if (host)
    host.innerHTML =
      '<p class="muted supplemental-status" role="status">Checking additional metadata sources…</p>';
  try {
    const cacheKey = key + ':' + Boolean(state.settings.tvdb?.configured);
    if (!enrichmentCache.has(cacheKey))
      enrichmentCache.set(
        cacheKey,
        api('enrichment', { type: m.related_type, tmdb: m.related_id }).catch((e) => {
          enrichmentCache.delete(cacheKey);
          throw e;
        })
      );
    const result = await enrichmentCache.get(cacheKey);
    if (sequence !== titleSequence) return;
    const sources = result.sources || [];
    if (host)
      host.innerHTML = `<details class="supplemental-details"><summary>Additional title information <span>${sources.filter((s) => s.status === 'matched').length} sources matched</span></summary><p class="muted">${result.scope === 'parent show' ? 'Information below describes the parent show. ' : ''}Values retain their provider labels and may use different season or title scopes.</p><button class="secondary" data-refresh-supplemental>Retry additional sources</button>${sources.map((s) => `<section class="supplemental-source"><div class="supplemental-source-heading"><strong>${supplementalLink(s.url, s.provider)}</strong><span class="muted">${esc(s.status)}</span></div>${s.facts?.length ? `<dl class="title-facts">${s.facts.map((f) => `<div><dt>${esc(f.label)}</dt><dd>${esc(f.value)}</dd></div>`).join('')}</dl>` : ''}${s.links?.length ? `<div class="title-links">${s.links.map((l) => supplementalLink(l.url, l.label)).join('')}</div>` : ''}${(s.notes || []).map((note) => `<p class="muted supplemental-status">${esc(note)}</p>`).join('')}</section>`).join('')}</details>`;
    if (!original) return;
    const base = original.sections;
    if (!base) return;
    const sequences = sources.filter((s) => s.sequence?.length);
    let sequenceData = base.sequence;
    if (!sequenceData.items.length && sequences.length) {
      const s = sequences[0];
      sequenceData = { name: s.provider, source: s.url, note: s.sequence_note, items: s.sequence };
    }
    const anime = sources.find((s) => s.provider === 'AniList');
    const animeSequence = (anime?.connections || []).filter((r) =>
      ['PREQUEL', 'SEQUEL'].includes(r.relation_code)
    );
    if (!sequenceData.items.length && animeSequence.length) {
      sequenceData = {
        name: 'AniList relationships',
        source: anime.url,
        note: 'Immediate prequel and sequel links supplied by AniList. These can represent seasons; this is a partial provider order, not a full chronological timeline.',
        items: [
          ...animeSequence.filter((r) => r.relation_code === 'PREQUEL'),
          {
            key,
            type: m.related_type,
            tmdb: String(m.related_id),
            title: m.title,
            poster: m.poster,
            current: true,
            relationship: 'Current title',
          },
          ...animeSequence.filter((r) => r.relation_code === 'SEQUEL'),
        ],
      };
    }
    const sequenceKeys = new Set(sequenceData.items.map((r) => r.key));
    const franchise = uniqueRelations([
      ...base.franchise.items,
      ...sources.flatMap((s) => s.franchise || []),
    ]).filter((r) => r.key !== key && !sequenceKeys.has(r.key));
    const confirmed = new Set([...sequenceKeys, ...franchise.map((r) => r.key), key]);
    const connections = uniqueRelations(sources.flatMap((s) => s.connections || [])).filter(
      (r) => r.key !== key && !confirmed.has(r.key)
    );
    const block = (heading, section, empty) =>
      !section.items.some((r) => !r.current && r.tmdb && ['movie', 'show'].includes(r.type))
        ? ''
        : `<section class="relationship-block"><div class="section-heading"><h3>${heading}</h3>${section.name ? `<span class="muted">${esc(section.name)}</span>` : ''}</div><p class="muted relationship-note">${esc(section.items.length ? section.note || 'Provider-supplied relationships.' : empty)} ${section.source ? supplementalLink(section.source, 'Source') : ''}</p>${
            section.items.length
              ? `<div class="related-preview" tabindex="0" role="region" aria-label="${esc(heading)} titles">${section.items
                  .filter((r) => r.tmdb && ['movie', 'show'].includes(r.type))
                  .map(supplementalTile)
                  .join('')}</div>`
              : ''
          }</section>`;
    const alternateSequences = sequences.filter(
      (s) => s.provider !== sequenceData.name && s.sequence.some((r) => !sequenceKeys.has(r.key))
    );
    window.setExplorationRecommendations?.(sequence, base.related.items);
    window.setKeepExploringTitles?.(sequence, [
      ...sequenceData.items,
      ...franchise,
      ...connections,
      ...alternateSequences.flatMap((s) => s.sequence),
    ]);
    $('related-preview').innerHTML =
      block(
        'Sequels & prequels',
        sequenceData,
        'No verified sequence is available from the connected sources.'
      ) +
      (alternateSequences.length
        ? `<details class="supplemental-more"><summary>Other provider series orders</summary>${alternateSequences
            .map(
              (s) =>
                `<h4>${esc(s.provider)}</h4><p class="muted relationship-note">${esc(s.sequence_note)}</p><div class="related-preview">${s.sequence
                  .filter((row) => row.tmdb && ['movie', 'show'].includes(row.type))
                  .map(supplementalTile)
                  .join('')}</div>`
            )
            .join('')}</details>`
        : '') +
      block(
        'Confirmed universe / franchise',
        {
          name: 'Provider-confirmed membership',
          items: franchise,
          note: 'TMDB collections, Wikidata series/franchise membership, and official TheTVDB lists. Membership does not necessarily mean the same fictional continuity.',
        },
        'No additional confirmed franchise members are available.'
      ) +
      (connections.length
        ? `<details class="supplemental-more"><summary>Spin-offs, adaptations & other connections (${connections.length})</summary><p class="muted relationship-note">Connections retain their exact provider labels. An adaptation or shared character does not establish a shared universe.</p>${supplementalRows(connections)}</details>`
        : '');
    const references = uniqueRelations([
      ...sequenceData.items,
      ...franchise,
      ...connections,
      ...alternateSequences.flatMap((row) => row.sequence),
    ]).filter((row) => !row.tmdb || !['movie', 'show'].includes(row.type));
    if (references.length)
      $('related-preview').insertAdjacentHTML(
        'beforeend',
        `<details class="source-only-connections"><summary>Source references (${references.length})</summary><p class="muted">These records do not have a confirmed playable title match.</p>${supplementalRows(references)}</details>`
      );
    $('title-relationships').hidden = !$('related-preview').innerHTML;
  } catch (e) {
    if (sequence === titleSequence && host)
      host.innerHTML = `<p class="muted supplemental-status">Additional metadata: ${esc(e.message)}</p>`;
  }
};
$('title-content').addEventListener('click', (e) => {
  const button = e.target.closest('[data-refresh-supplemental]');
  if (button && supplementalContext?.sequence === titleSequence) {
    const context = supplementalContext;
    enrichmentCache.clear();
    task(button, () =>
      window.loadSupplementalMetadata(context.m, context.sequence, context.original)
    );
  }
});
const refreshConnectionsBeforeSupplemental = refreshConnections;
refreshConnections = async function () {
  enrichmentCache.clear();
  return refreshConnectionsBeforeSupplemental();
};

// Extend the existing connection form without exposing saved keys or PINs.
const renderConnectionsBeforeSupplemental = renderArr;
renderArr = function () {
  renderConnectionsBeforeSupplemental();
  $('connection-fields').insertAdjacentHTML(
    'beforeend',
    `<div class="connection"><h2>Additional metadata</h2><p class="muted">Wikidata and AniList work automatically when exact cross-references are available. No account is required.</p><h3>TheTVDB · optional</h3><p class="muted">Use your project API key and, when required by your access plan, a subscriber PIN. Adds official franchise lists and alternate title information.</p><label>Project API key<input name="tvdb-key" type="password" autocomplete="new-password" placeholder="${state.settings.tvdb?.configured ? 'Saved · leave blank to keep' : 'TheTVDB project API key'}"></label><label>Subscriber PIN (if required)<input name="tvdb-pin" type="password" autocomplete="new-password" placeholder="Leave blank to keep any saved PIN"></label><button type="button" class="secondary" data-test="tvdb">Test connection</button></div>`
  );
};
if (state.csrf) renderArr();
