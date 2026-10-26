"""Supplemental metadata, matched by external IDs. No account/library writes."""
import copy
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import providers

CACHE = Path(__file__).parent / 'data' / 'provider-cache' / 'supplemental'
HOSTS = {'www.wikidata.org', 'query.wikidata.org', 'graphql.anilist.co', 'api4.thetvdb.com'}
USER_AGENT = 'ReelCheck/0.1 (personal local media metadata workbench)'
_tokens = {}
_token_lock = threading.Lock()
_cooldowns = {}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Metadata provider redirected unexpectedly. Try again later.')


def request_json(url, payload=None, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Unsupported metadata endpoint.')
    if _cooldowns.get(parsed.hostname, 0) > time.time():
        raise ValueError('Metadata provider is rate limited. Try again later.')
    request_headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', **(headers or {})}
    raw = None
    if payload is not None:
        raw = json.dumps(payload).encode()
        request_headers['Content-Type'] = 'application/json'
    try:
        req = urllib.request.Request(url, data=raw, headers=request_headers)
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
            data = response.read(6_000_001)
        if len(data) > 6_000_000:
            raise ValueError('Metadata response is too large.')
        return json.loads(data)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            _cooldowns[parsed.hostname] = time.time() + 60
        raise ValueError('Metadata provider is rate limited. Try again later.' if exc.code == 429 else
                         'Metadata provider denied access. Check its connection settings.' if exc.code in (401, 403) else
                         'Metadata record is unavailable.' if exc.code == 404 else 'Metadata provider is temporarily unavailable.') from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ValueError('Metadata provider could not be reached. Try again later.') from None


def cached(key, fetch, ttl=86400):
    file = CACHE / (hashlib.sha256(key.encode()).hexdigest() + '.json')
    try:
        if time.time() - file.stat().st_mtime < ttl:
            return json.loads(file.read_text('utf-8'))
    except (OSError, ValueError):
        pass
    result = fetch()
    CACHE.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix('.' + str(threading.get_ident()) + '.tmp')
    temp.write_text(json.dumps(result), 'utf-8')
    temp.replace(file)
    return result


def safe_link(url, hosts=None):
    try:
        parsed = urllib.parse.urlsplit(str(url))
        if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and parsed.port in (None, 443) and (not hosts or parsed.hostname in hosts):
            return str(url)
    except ValueError:
        pass
    return None


def claims(entity, prop):
    values = []
    for statement in entity.get('claims', {}).get(prop, []):
        if statement.get('rank') == 'deprecated':
            continue
        snak = statement.get('mainsnak', {})
        if snak.get('snaktype') == 'value':
            value = snak.get('datavalue', {}).get('value')
            if value not in values:
                values.append(value)
    return values


def entity_ids(entity, prop):
    return list(dict.fromkeys(v['id'] for v in claims(entity, prop) if isinstance(v, dict) and re.fullmatch(r'Q[1-9]\d*', v.get('id', ''))))


def series_neighbors(entity, prop, context=None):
    direct = entity_ids(entity, prop)
    if direct and context is None:
        return direct
    values = []
    for statement in entity.get('claims', {}).get('P179', []):
        if statement.get('rank') == 'deprecated':
            continue
        group = statement.get('mainsnak', {}).get('datavalue', {}).get('value', {})
        if context and group.get('id') != context:
            continue
        for snak in statement.get('qualifiers', {}).get(prop, []):
            value = snak.get('datavalue', {}).get('value', {})
            if isinstance(value, dict) and re.fullmatch(r'Q[1-9]\d*', value.get('id', '')):
                values.append(value['id'])
    return list(dict.fromkeys(values))


def wd_entity(qid):
    if not re.fullmatch(r'Q[1-9]\d*', str(qid)):
        raise ValueError('Invalid Wikidata identifier.')
    data = cached('wd:' + qid, lambda: request_json('https://www.wikidata.org/wiki/Special:EntityData/' + qid + '.json'))
    entity = data.get('entities', {}).get(qid)
    if not entity or entity.get('missing') is not None:
        raise ValueError('Wikidata record is unavailable.')
    return entity


def wd_query(query):
    url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode({'query': query, 'format': 'json'})
    return cached('sparql:' + query, lambda: request_json(url, headers={'Accept': 'application/sparql-results+json'}))['results']['bindings']


def wd_row(qid, entity, relationship):
    movie, show = claims(entity, 'P4947'), claims(entity, 'P4983')
    kind = 'movie' if len(movie) == 1 and not show else 'show' if len(show) == 1 and not movie else None
    identifier = str((movie if kind == 'movie' else show)[0]) if kind else None
    if not str(identifier or '').isdigit():
        identifier, kind = None, None
    return {'key': (('movie' if kind == 'movie' else 'tv') + ':' + identifier) if kind else 'wikidata:' + qid,
            'type': kind, 'tmdb': identifier, 'title': entity.get('labels', {}).get('en', {}).get('value', qid),
            'relationship': relationship, 'provider': 'Wikidata', 'url': 'https://www.wikidata.org/wiki/' + qid}


def wikidata(qid):
    entity = wd_entity(qid)
    link = 'https://www.wikidata.org/wiki/' + qid
    result = {'provider': 'Wikidata', 'status': 'matched', 'url': link, 'identity': wd_row(qid, entity, 'Current title'), 'facts': [], 'links': [], 'connections': [], 'franchise': [], 'sequence': [], 'notes': []}
    aliases = [r['value'] for r in entity.get('aliases', {}).get('en', [])]
    if aliases:
        result['facts'].append({'label': 'Alternate titles', 'value': ', '.join(aliases[:12])})
    description = entity.get('descriptions', {}).get('en', {}).get('value')
    if description:
        result['facts'].append({'label': 'Wikidata description', 'value': description})
    for url in claims(entity, 'P856')[:3]:
        if safe_link(url):
            result['links'].append({'label': 'Official website', 'url': url})
    result['anilist_id'] = next((str(v) for v in claims(entity, 'P8729') if str(v).isdigit()), None)
    related_properties = [('P144', 'Based on'), ('P4969', 'Adaptation'), ('P2512', 'Spin-off'), ('P179', 'Series'), ('P8345', 'Franchise')]
    targets = [(target, label) for prop, label in related_properties for target in entity_ids(entity, prop)[:4]]
    def relation(pair):
        target, label = pair
        try:
            return wd_row(target, wd_entity(target), label)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        result['connections'] = [r for r in pool.map(relation, targets) if r]
    # Only an unbranched explicit follows/followed-by chain is displayed as a sequence.
    seen, before, after = {qid}, [], []
    contexts = []
    if not entity_ids(entity, 'P155') and not entity_ids(entity, 'P156'):
        for statement in entity.get('claims', {}).get('P179', []):
            if statement.get('rank') != 'deprecated' and any(statement.get('qualifiers', {}).get(prop) for prop in ('P155', 'P156')):
                context = statement.get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('id')
                if re.fullmatch(r'Q[1-9]\d*', str(context)):
                    contexts.append(context)
    contexts = list(dict.fromkeys(contexts))
    ambiguous = len(contexts) > 1
    context = contexts[0] if len(contexts) == 1 else None
    for prop, output in [('P155', before), ('P156', after)]:
        if ambiguous:
            break
        node = entity
        for _ in range(6):
            ids = series_neighbors(node, prop, context)
            if len(ids) != 1:
                ambiguous |= len(ids) > 1
                break
            target = ids[0]
            if target in seen:
                ambiguous = True
                break
            seen.add(target)
            try:
                node = wd_entity(target)
            except ValueError:
                result['notes'].append('Some sequence records could not be loaded.')
                break
            output.append(wd_row(target, node, 'Preceding installment' if prop == 'P155' else 'Following installment'))
    if (before or after) and not ambiguous:
        result['sequence'] = list(reversed(before)) + [dict(wd_row(qid, entity, 'Current title'), current=True)] + after
        result['sequence_note'] = 'Wikidata follows / followed-by order, up to six neighboring entries each way. This does not establish story chronology.'
    elif ambiguous:
        result['connections'].extend(before + after)
        pairs = [(target, label) for prop, label in [('P155', 'Previous installment (provider order)'), ('P156', 'Next installment (provider order)')]
                 for target in series_neighbors(entity, prop)[:4] if target != qid]
        with ThreadPoolExecutor(max_workers=4) as pool:
            result['connections'].extend(r for r in pool.map(relation, pairs) if r)
        result['notes'].append('Sequence branches or conflicts were found; no single watch order was inferred.')
    # Franchise membership is distinct from sequence and fictional continuity.
    groups = entity_ids(entity, 'P8345')[:2] or entity_ids(entity, 'P179')[:2]
    if groups:
        values = ' '.join('wd:' + q for q in groups)
        query = '''SELECT DISTINCT ?item ?movie ?show ?label WHERE { VALUES ?group { %s }
          { ?item wdt:P8345 ?group } UNION { ?item wdt:P179 ?group }
          OPTIONAL { ?item wdt:P4947 ?movie } OPTIONAL { ?item wdt:P4983 ?show }
          FILTER(BOUND(?movie) || BOUND(?show))
          OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
          } ORDER BY ?item LIMIT 41''' % values
        try:
            records = wd_query(query)
            result['notes'].append('Franchise results include up to 40 mapped movies and shows; franchise membership does not imply shared continuity.')
            def member(binding):
                target = binding['item']['value'].rsplit('/', 1)[-1]
                if not re.fullmatch(r'Q[1-9]\d*', target) or target == qid:
                    return None
                movie, show = binding.get('movie', {}).get('value'), binding.get('show', {}).get('value')
                media = 'movie' if movie and not show else 'show' if show and not movie else None
                tmdb = movie if media == 'movie' else show if media == 'show' else None
                if not str(tmdb or '').isdigit():
                    return None
                return {'key': ('movie' if media == 'movie' else 'tv') + ':' + tmdb, 'type': media, 'tmdb': tmdb, 'title': binding.get('label', {}).get('value', target),
                        'relationship': 'Franchise / series member', 'provider': 'Wikidata', 'url': 'https://www.wikidata.org/wiki/' + target}
            result['franchise'] = [r for r in map(member, records[:40]) if r]
        except ValueError as exc:
            result['notes'].append('Franchise lookup: ' + str(exc))
            # Entity reads are a separate service from SPARQL. Only explicit "has part"
            # statements on a known franchise qualify; never infer from shared people/tags.
            members = []
            for group in groups:
                try:
                    members.extend(entity_ids(wd_entity(group), 'P527'))
                except ValueError:
                    continue
            members = list(dict.fromkeys(members))[:40]
            with ThreadPoolExecutor(max_workers=4) as pool:
                fallback = [r for r in pool.map(relation, [(target, 'Explicit franchise / series member') for target in members if target != qid]) if r]
            result['franchise'] = fallback
            if fallback:
                result['notes'].append('Showing explicit franchise has-part statements as a fallback; coverage may be partial.')
    return result


ANILIST_QUERY = '''query ($id:Int!) { Media(id:$id,type:ANIME) { id title { romaji english native }
  synonyms format status source episodes duration averageScore meanScore genres
  studios(isMain:true) { nodes { name } } siteUrl
  relations { edges { relationType(version:2) node { id type format title { romaji english } siteUrl } } }
} }'''


def anilist(identifier):
    if not str(identifier).isdigit():
        raise ValueError('Invalid AniList identifier.')
    response = cached('anilist:' + str(identifier), lambda: request_json('https://graphql.anilist.co', {'query': ANILIST_QUERY, 'variables': {'id': int(identifier)}}))
    data = (response.get('data') or {}).get('Media')
    if not data or response.get('errors'):
        raise ValueError('AniList record is unavailable.')
    result = {'provider': 'AniList', 'status': 'matched', 'url': 'https://anilist.co/anime/' + str(identifier), 'facts': [], 'links': [], 'connections': [], 'franchise': [], 'sequence': [], 'notes': []}
    names = list(dict.fromkeys(v for v in list((data.get('title') or {}).values()) + data.get('synonyms', []) if v))
    for label, value in [('Alternate titles', ', '.join(names[:12])), ('Format', data.get('format')), ('Status', data.get('status')),
                         ('Source material', data.get('source')), ('Episodes', data.get('episodes')), ('Episode length', str(data['duration']) + ' minutes' if data.get('duration') else None),
                         ('Animation studios', ', '.join(r['name'] for r in (data.get('studios') or {}).get('nodes', []))), ('Genres', ', '.join(data.get('genres') or [])),
                         ('AniList score', str(data['averageScore']) + ' / 100' if data.get('averageScore') is not None else None)]:
        if value is not None and value != '':
            result['facts'].append({'label': label, 'value': str(value).replace('_', ' ')})
    for edge in (data.get('relations') or {}).get('edges', []):
        node = edge.get('node') or {}
        if not str(node.get('id', '')).isdigit():
            continue
        relation_type = edge.get('relationType', 'OTHER')
        result['connections'].append({'key': 'anilist:' + str(node['id']), 'title': node.get('title', {}).get('english') or node.get('title', {}).get('romaji') or 'Untitled',
                                      'relationship': relation_type.replace('_', ' ').title(), 'relation_code': relation_type, 'provider': 'AniList',
                                      'anilist': str(node['id']), 'url': 'https://anilist.co/' + ('manga/' if node.get('type') == 'MANGA' else 'anime/') + str(node['id'])})
    result['notes'].append('AniList relationships describe anime entries, which can represent individual seasons. They are not automatically mapped to an entire Plex show.')
    return result


def tvdb_call(path, settings):
    cfg = settings.get('tvdb', {})
    key, pin = str(cfg.get('key') or ''), str(cfg.get('pin') or '')
    if not key:
        raise ValueError('Add a TheTVDB project API key in Connections.')
    if not re.fullmatch(r'/(?:movies/\d+/extended|series/\d+/extended|lists/\d+/extended|search/remoteid/tt\d+)', path):
        raise ValueError('Invalid TheTVDB endpoint.')
    identity = hashlib.sha256((key + '\0' + pin).encode()).hexdigest()
    def token():
        with _token_lock:
            saved = _tokens.get(identity)
            if saved and saved[1] > time.time():
                return saved[0]
            result = request_json('https://api4.thetvdb.com/v4/login', {'apikey': key, **({'pin': pin} if pin else {})})
            value = (result.get('data') or {}).get('token')
            if not value:
                raise ValueError('TheTVDB did not authorize this connection.')
            _tokens[identity] = (value, time.time() + 86400)
            return value
    return cached('tvdb:' + identity + path, lambda: request_json('https://api4.thetvdb.com/v4' + path, headers={'Authorization': 'Bearer ' + token()}))['data']


def tvdb(kind, external, settings):
    identifier = external.get('tvdb_id') if kind == 'show' else None
    entity_kind = 'series' if kind == 'show' else 'movies'
    if not identifier:
        imdb = str(external.get('imdb_id') or '')
        if not re.fullmatch(r'tt\d+', imdb):
            return {'provider': 'TheTVDB', 'status': 'unmatched', 'notes': ['No exact TheTVDB or IMDb identifier is available.']}
        found = tvdb_call('/search/remoteid/' + imdb, settings)
        candidates = [r.get('series' if kind == 'show' else 'movie') for r in found]
        candidates = [r for r in candidates if r and str(r.get('id', '')).isdigit()]
        if len(candidates) != 1:
            return {'provider': 'TheTVDB', 'status': 'unmatched', 'notes': ['No unique exact TheTVDB match.']}
        identifier = candidates[0]['id']
    if not str(identifier).isdigit():
        raise ValueError('Invalid TheTVDB identifier.')
    data = tvdb_call('/' + entity_kind + '/' + str(identifier) + '/extended', settings)
    result = {'provider': 'TheTVDB', 'status': 'matched', 'url': 'https://thetvdb.com/dereferrer/' + ('series/' if kind == 'show' else 'movie/') + str(identifier),
              'facts': [], 'links': [], 'connections': [], 'franchise': [], 'sequence': [], 'notes': []}
    aliases = [r.get('name') for r in data.get('aliases', []) if isinstance(r, dict) and r.get('name')]
    for label, value in [('Alternate titles', ', '.join(aliases[:12])), ('Original language', data.get('originalLanguage')),
                         ('Original country', data.get('originalCountry')), ('TheTVDB overview', data.get('overview'))]:
        if value:
            result['facts'].append({'label': label, 'value': str(value)})
    official = [r for r in data.get('lists', []) if r.get('isOfficial') is True and str(r.get('id', '')).isdigit()]
    pending = []
    for listing in official[:3]:
        full = tvdb_call('/lists/' + str(listing['id']) + '/extended', settings)
        # Recheck the fetched list; custom user lists are never promoted to confirmed membership.
        if full.get('isOfficial') is not True:
            continue
        result['links'].append({'label': listing.get('name') or 'Official franchise list', 'url': 'https://thetvdb.com/lists/' + str(listing['id'])})
        for item in sorted(full.get('entities', []), key=lambda r: r.get('order') or 0):
            media, item_id = ('show', item.get('seriesId')) if item.get('seriesId') else ('movie', item.get('movieId'))
            if not str(item_id or '').isdigit() or (media == kind and str(item_id) == str(identifier)):
                continue
            if len(pending) < 40:
                pending.append((media, item_id, listing.get('name') or 'Official franchise member'))
    def member(args):
        media, item_id, label = args
        try:
            record = tvdb_call(('/series/' if media == 'show' else '/movies/') + str(item_id) + '/extended', settings)
        except ValueError:
            return None
        remote = [r for r in record.get('remoteIds', []) if 'themoviedb' in re.sub(r'[^a-z]', '', str(r.get('sourceName', '')).lower()) and str(r.get('id', '')).isdigit()]
        tmdb = str(remote[0]['id']) if len(remote) == 1 else None
        return {'key': ('movie' if media == 'movie' else 'tv') + ':' + tmdb if tmdb else 'tvdb:' + media + ':' + str(item_id), 'type': media if tmdb else None,
                'tmdb': tmdb, 'title': record.get('name') or 'Untitled', 'relationship': label, 'provider': 'TheTVDB',
                'url': 'https://thetvdb.com/dereferrer/' + ('series/' if media == 'show' else 'movie/') + str(item_id)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        result['franchise'] = [r for r in pool.map(member, pending) if r]
    if len(result['franchise']) < len(pending):
        result['notes'].append('Some franchise records could not be loaded.')
    if official:
        result['notes'].append('Up to three official franchise lists, 40 entries in total. List order is not assumed to be story chronology.')
    return result


def enrich(kind, identifier, settings):
    if kind not in ('movie', 'show') or not str(identifier).isdigit() or int(identifier) < 1:
        raise ValueError('Choose an exact TMDB movie or parent show ID.')
    external = providers.cached_tmdb(('movie/' if kind == 'movie' else 'tv/') + str(identifier) + '/external_ids', settings)
    output = {'sources': [], 'scope': 'movie' if kind == 'movie' else 'parent show'}
    def attempt(name, work):
        try:
            return work()
        except ValueError as exc:
            return {'provider': name, 'status': 'unavailable', 'notes': [str(exc)]}
        except (KeyError, TypeError, AttributeError):
            return {'provider': name, 'status': 'unavailable', 'notes': ['Metadata provider returned an unexpected record format.']}
    qid = str(external.get('wikidata_id') or '')
    wd = attempt('Wikidata', lambda: wikidata(qid)) if re.fullmatch(r'Q[1-9]\d*', qid) else {'provider': 'Wikidata', 'status': 'unmatched', 'notes': ['TMDB has no exact Wikidata link for this title.']}
    identity = wd.get('identity') or {}
    if identity.get('tmdb') and (identity.get('tmdb') != str(identifier) or identity.get('type') != kind):
        wd = {'provider': 'Wikidata', 'status': 'unmatched', 'notes': ['The provider cross-references conflict. Supplemental matches were not attached.']}
    output['sources'].append(wd)
    # No title-search matching: AniList season records and TMDB whole-show records may differ in scope.
    anime_id = wd.get('anilist_id')
    with ThreadPoolExecutor(max_workers=2) as pool:
        anime_job = pool.submit(attempt, 'AniList', lambda: anilist(anime_id)) if anime_id else None
        tvdb_job = pool.submit(attempt, 'TheTVDB', lambda: tvdb(kind, external, settings)) if settings.get('tvdb', {}).get('key') else None
        output['sources'].append(anime_job.result() if anime_job else {'provider': 'AniList', 'status': 'unmatched', 'notes': ['No exact AniList cross-reference is available.']})
        output['sources'].append(tvdb_job.result() if tvdb_job else {'provider': 'TheTVDB', 'status': 'not connected', 'notes': ['Optional: add your project API key and subscription PIN in Connections.']})
    # Stamp verified current identity for display and deduplicate source-local records.
    output['current'] = {'type': kind, 'tmdb': str(identifier)}
    # Artwork and release dates still come from TMDB, using only exact mapped IDs.
    mapped = {}
    for source in output['sources']:
        for row in source.get('sequence', []) + source.get('franchise', []) + source.get('connections', []):
            if row.get('tmdb') and row.get('type') in ('movie', 'show'):
                mapped.setdefault(row['key'], []).append(row)
    def artwork(rows):
        first = rows[0]
        try:
            data = providers.cached_tmdb(('movie/' if first['type'] == 'movie' else 'tv/') + first['tmdb'], settings)
            for row in rows:
                row['poster'] = providers.image_url(data.get('poster_path'))
                row['year'] = (data.get('release_date') or data.get('first_air_date') or '')[:4]
        except ValueError:
            pass
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(artwork, list(mapped.values())[:60]))
    return copy.deepcopy(output)
