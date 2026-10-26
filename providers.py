"""Public list adapters. Provider IDs are kept separate from display titles."""
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import threading
import title_relationships
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

CACHE = Path(__file__).parent / 'data' / 'provider-cache'
_tmdb_cache_locks = {}
_tmdb_cache_guard = threading.Lock()
HOSTS = {'letterboxd.com', 'www.letterboxd.com', 'mdblist.com', 'www.mdblist.com', 'www.imdb.com', 'imdb.com', 'chronocanon.com', 'www.chronocanon.com', 'trakt.tv', 'www.trakt.tv', 'app.trakt.tv', 'api.themoviedb.org'}

def import_options(options=None):
    options=options or {}
    order=options.get('order','source');seasons=options.get('seasons','separate')
    if order not in ('source','title_asc','title_desc','year_asc','year_desc'):raise ValueError('Choose a valid import sort order.')
    if seasons not in ('separate','shows'):raise ValueError('Choose separate seasons or whole shows.')
    return {'order':order,'seasons':seasons}

def arrange_import(rows,options):
    options=import_options(options);result=[];seen=set()
    for original in rows:
        row=dict(original)
        if options['seasons']=='shows' and row['type']=='season':
            ids={p:str(row['show_'+p]) for p in ('tmdb','tvdb','imdb') if row.get('show_'+p)}
            if not ids or not row.get('show_title'):raise ValueError('A season needs its exact parent-show match before it can be combined into a show.')
            row={'type':'show','title':row['show_title'],**ids}
            provider=next(p for p in ('tmdb','tvdb','imdb') if p in ids)
            row['source_key']='combined-show:'+provider+':'+ids[provider]
        if options['seasons']=='shows' and row['type']=='show':
            keys={(p,str(row[p])) for p in ('tmdb','tvdb','imdb') if row.get(p)}
            if seen.intersection(keys):continue
            seen.update(keys)
        result.append(row)
    order=options['order']
    if order.startswith('title_'):
        result.sort(key=lambda r:(int(r.get('season') or 0),int(r.get('episode') or 0)))
        result.sort(key=lambda r:(r.get('show_title') if r['type'] in ('season','episode') else r['title']).casefold(),reverse=order.endswith('desc'))
    elif order.startswith('year_'):
        known=[r for r in result if str(r.get('year','')).isdigit()];unknown=[r for r in result if not str(r.get('year','')).isdigit()]
        result=sorted(known,key=lambda r:int(r['year']),reverse=order.endswith('desc'))+unknown
    return result


def validate_url(url):
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use an https:// list URL from Letterboxd, MDBList, IMDb, ChronoCanon, or Trakt.')
    return parsed


class ProviderRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = validate_url(newurl)
        if target.hostname.replace('www.', '') != urllib.parse.urlparse(req.full_url).hostname.replace('www.', ''):
            raise ValueError('The provider redirected to a different website. Import an exported file instead.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, token=None):
    validate_url(url)
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; ReelCheck/0.2; personal list importer)', 'Accept': 'application/json' if token else 'text/html'}
    if token:
        if urllib.parse.urlparse(url).hostname != 'api.themoviedb.org':
            raise ValueError('Metadata credentials may only be sent to TMDB.')
        headers['Authorization'] = 'Bearer ' + token
    try:
        with urllib.request.build_opener(ProviderRedirects()).open(urllib.request.Request(url, headers=headers), timeout=25) as response:
            raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError('Provider response is too large.')
        text = raw.decode('utf-8')
        if any(marker in text.lower() for marker in ('window.awswaf', 'awswafcookiedomainlist', 'cf-chl-', '<title>just a moment')):
            raise ValueError('This provider returned a bot-check page. Import its CSV/JSON export instead.')
        return text
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ValueError(f'Provider returned HTTP {code}. The list may be private, unavailable, or rate limited. Try an exported file.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('Could not reach the list provider. Check your connection and retry.') from None


class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, attrs or {}, []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def has_class(self, name):
        return name in self.attrs.get('class', '').split()


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def title_year(value):
    match = re.match(r'^(.*?)\s*\((\d{4})\)\s*$', value.strip())
    return (match[1].strip(), match[2]) if match else (value.strip(), '')


def parse_letterboxd(text):
    nodes = list(Document(text).root.walk())
    heading = next((n.text().strip() for n in nodes if n.tag == 'h1' and n.has_class('title-1')), '')
    entries = []
    for n in nodes:
        a = n.attrs
        if 'data-list-index' not in a:
            continue
        link = a.get('data-item-link') or a.get('data-target-link') or a.get('data-target')
        if not link or not re.fullmatch(r'/film/[^/]+/', link):
            raise ValueError('Letterboxd returned an unfamiliar film link; import was stopped to preserve accuracy.')
        value = a.get('data-item-name') or a.get('data-item-full-display-name')
        if not value:
            value = next((x.attrs.get('alt') for x in n.walk() if x.tag == 'img'), '')
        title, year = title_year(value)
        entries.append({'type': 'movie', 'title': title, 'year': year, 'source_key': 'letterboxd:' + link, 'source_url': 'https://letterboxd.com' + link})
    next_page = next((n.attrs['href'] for n in nodes if n.tag == 'a' and n.has_class('next') and n.attrs.get('href')), None)
    return heading, entries, next_page


def film_ids(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    if path.exists() and time.time() - path.stat().st_mtime < 7*86400:
        return json.loads(path.read_text('utf-8'))
    text = fetch(url)
    nodes = list(Document(text).root.walk())
    ids = {}
    for node in nodes:
        href = node.attrs.get('href', '')
        match = re.search(r'themoviedb\.org/movie/(\d+)', href)
        if match:
            ids['tmdb'] = match[1]
        match = re.search(r'imdb\.com/title/(tt\d+)', href)
        if match:
            ids['imdb'] = match[1]
        if node.tag == 'body' and node.attrs.get('data-tmdb-id'):
            ids['tmdb'] = node.attrs['data-tmdb-id']
    if not ids:
        raise ValueError('No provider IDs found on this Letterboxd film page.')
    path.write_text(json.dumps(ids), 'utf-8')
    return ids


def letterboxd(url, progress):
    base = re.fullmatch(r'/([^/]+)/list/([^/]+)/?', urllib.parse.urlparse(url).path)
    if not base:
        raise ValueError('Use a Letterboxd list URL, such as https://letterboxd.com/user/list/list-name/.')
    url = 'https://letterboxd.com' + base[0].rstrip('/') + '/'
    source = url
    seen, entries, name = set(), [], ''
    for page in range(1, 201):
        if url in seen:
            raise ValueError('Provider pagination repeated. No incomplete list was saved.')
        seen.add(url)
        progress(f'Reading Letterboxd page {page}…')
        heading, rows, next_page = parse_letterboxd(fetch(url))
        name = name or heading
        if not rows:
            raise ValueError('No list entries found. The list may be private, empty, or its page format has changed.')
        entries.extend(rows)
        if not next_page:
            break
        url = urllib.parse.urljoin(source, next_page)
        if not urllib.parse.urlparse(url).path.startswith(base[0].rstrip('/') + '/'):
            raise ValueError('Provider returned an unexpected pagination link.')
    else:
        raise ValueError('This list exceeds the 200-page import limit.')
    warnings = []
    def resolve(row):
        try:
            return film_ids(row['source_url']), None
        except ValueError as exc:
            return {}, str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, (row, (ids, error)) in enumerate(zip(entries, pool.map(resolve, entries)), 1):
            row.update(ids)
            if error:
                warnings.append(row['title'] + ': ' + error)
            progress(f'Resolving film IDs · {index}/{len(entries)}', index, len(entries))
    return {'name': name or 'Letterboxd list', 'source': source, 'items': entries, 'warnings': warnings}


def parse_mdblist(text):
    nodes = list(Document(text).root.walk())
    entries = []
    for card in nodes:
        if not card.has_class('card') or not card.attrs.get('data-media-id'):
            continue
        kind = card.attrs.get('data-mediatype')
        if kind not in ('movie', 'show'):
            raise ValueError('This MDBList contains season/episode entries requiring structured export. Import JSON to preserve their exact scope.')
        children = list(card.walk())
        title_node = next((n for n in children if n.has_class('movie-title')), None)
        if not title_node:
            raise ValueError('An MDBList entry is missing its title. Import was stopped.')
        title, year = title_year(title_node.attrs.get('title') or title_node.text())
        row = {'type': kind, 'title': title, 'year': year, 'source_key': 'mdblist:' + kind + ':' + card.attrs['data-media-id']}
        for n in children:
            href = n.attrs.get('href', '')
            match = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', href)
            if match and match[1] == ('movie' if kind == 'movie' else 'tv'):
                row['tmdb'] = match[2]
            match = re.search(r'imdb\.com/title/(tt\d+)', href)
            if match:
                row['imdb'] = match[1]
        entries.append(row)
    return entries


def mdblist(url, progress):
    parsed = validate_url(url)
    if not re.fullmatch(r'/lists/[^/]+/[^/]+/?', parsed.path):
        raise ValueError('Use a public MDBList /lists/user/list-name URL.')
    url = 'https://mdblist.com' + parsed.path.rstrip('/')
    progress('Reading the ordered MDBList entries…')
    text = fetch(url)
    count = re.search(r'Items:\s*([\d,]+)', text)
    if not count:
        raise ValueError('MDBList did not expose its total item count; no incomplete list was saved.')
    expected = int(count[1].replace(',', ''))
    entries = parse_mdblist(text)
    nodes = list(Document(text).root.walk())
    headings = [n.text().strip() for n in nodes if n.tag == 'h3']
    page = 1
    while len(entries) < expected and page < 500:
        progress(f'Reading MDBList page {page+1} · {len(entries)}/{expected} entries')
        query = urllib.parse.urlencode({'append': 'yes', 'filter': '', 'new_items': 'false', 'show_hidden': 'false', 'item_filter': '', 'mediatype': '', 'sort': '', 'sortorder': 'asc', 'q_current_page': page})
        rows = parse_mdblist(fetch(url + '?' + query))
        if not rows or any(r['source_key'] in {i['source_key'] for i in entries} for r in rows):
            raise ValueError('MDBList pagination returned missing or repeated entries; no incomplete list was saved.')
        entries.extend(rows)
        page += 1
    if not entries or len(entries) != expected:
        raise ValueError('MDBList did not expose the complete list. Import a structured export instead; no partial list was saved.')
    return {'name': headings[1] if len(headings) > 1 else 'MDBList', 'source': url, 'items': entries, 'warnings': []}


def imdb(url, progress):
    if not re.fullmatch(r'/list/ls\d+/?', urllib.parse.urlparse(url).path):
        raise ValueError('Use an IMDb /list/ls123456789/ URL.')
    progress('Reading IMDb list…')
    pages, seen, rows, total, name = [url], set(), [], None, 'IMDb list'
    while pages:
        page = pages.pop(0)
        if page in seen or len(seen) >= 200:
            raise ValueError('IMDb pagination repeated or exceeded the limit. Use CSV; no partial list was saved.')
        seen.add(page)
        parsed = parse_imdb(fetch(page))
        rows.extend(parsed['items'])
        name = parsed['name'] or name
        if parsed['total'] is not None:
            if not 0 < parsed['total'] <= 20000:
                raise ValueError('Import an IMDb list containing 1–20,000 titles.')
            if total is not None and total != parsed['total']:
                raise ValueError('IMDb list changed during import. Retry or use CSV.')
            total = parsed['total']
        progress(f'Reading IMDb: {len(rows)} entries…')
        if parsed['next']:
            following = urllib.parse.urljoin(page, parsed['next'])
            target = validate_url(following)
            if target.hostname.replace('www.', '') != 'imdb.com' or target.path.rstrip('/') != urllib.parse.urlparse(url).path.rstrip('/'):
                raise ValueError('IMDb returned an invalid next page.')
            pages.append(following)
    positions = [r.pop('_position') for r in rows]
    if total is None or sorted(positions) != list(range(1, total + 1)):
        raise ValueError('IMDb did not expose the complete ordered list. Export its CSV and import that file; no partial list was saved.')
    rows = [r for _, r in sorted(zip(positions, rows), key=lambda pair: pair[0])]
    occurrences = {}
    for row in rows:
        key = row['imdb']; occurrences[key] = occurrences.get(key, 0) + 1
        row['source_key'] = f'imdb:{key}:{occurrences[key]}'
    return {'name': name, 'source': url, 'items': rows, 'warnings': []}


def json_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_objects(child)


def page_json(text):
    """Read embedded JSON/React flight data as data, without running page scripts."""
    roots, chunks = [], []
    for node in Document(text).root.walk():
        if node.tag != 'script':
            continue
        value = node.text().strip()
        try:
            if node.attrs.get('type') in ('application/ld+json', 'application/json') or node.attrs.get('id') == '__NEXT_DATA__':
                roots.append(json.loads(value))
            elif value.startswith('self.__next_f.push('):
                packet = json.loads(value[len('self.__next_f.push('):].rstrip(';')[:-1])
                if len(packet) == 2 and packet[0] == 1 and isinstance(packet[1], str):
                    chunks.append(packet[1])
        except (ValueError, TypeError):
            continue
    for line in ''.join(chunks).splitlines():
        payload = line.partition(':')[2]
        if payload.startswith(('{', '[')):
            try:
                roots.append(json.loads(payload))
            except ValueError:
                continue
    return roots


def parse_imdb(text):
    objects = [obj for root in page_json(text) for obj in json_objects(root)]
    lists = [o for o in objects if o.get('@type') == 'ItemList' and isinstance(o.get('itemListElement'), list)]
    if not lists:
        raise ValueError('IMDb did not expose structured list data. Export its CSV and import that file.')
    data = max(lists, key=lambda o: len(o['itemListElement']))
    rows = []
    kinds = {'Movie': 'movie', 'TVMovie': 'movie', 'TVSeries': 'show', 'TVEpisode': 'episode', 'TVSeason': 'season'}
    for listing in data['itemListElement']:
        item = listing.get('item', {})
        identifier = re.search(r'tt\d+', str(item.get('url') or item.get('@id') or ''))
        kind = kinds.get(item.get('@type'))
        if not identifier or not kind or not item.get('name'):
            raise ValueError('An IMDb entry lacks an exact title ID or supported type. Use its CSV export.')
        row = {'type': kind, 'title': item['name'], 'imdb': identifier[0], '_position': int(listing.get('position', 0))}
        year = re.search(r'\d{4}', str(item.get('datePublished', '')))
        if year:
            row['year'] = year[0]
        if kind in ('season', 'episode'):
            row['metadata_unresolved'] = True
            series = item.get('partOfSeries') or {}
            parent = re.search(r'tt\d+', str(series.get('url') or series.get('@id') or ''))
            if parent:
                row.update(show_imdb=parent[0], show_title=series.get('name', ''))
            season = item.get('seasonNumber') or (item.get('partOfSeason') or {}).get('seasonNumber')
            episode = item.get('episodeNumber')
            if season is not None:
                row['season'] = str(season)
            if episode is not None:
                row['episode'] = str(episode)
            if parent and season is not None and (kind == 'season' or episode is not None):
                row.pop('metadata_unresolved')
        rows.append(row)
    next_link = next((n.attrs.get('href') for n in Document(text).root.walk() if n.tag in ('a', 'link') and 'next' in n.attrs.get('rel', '').split()), None)
    total = data.get('numberOfItems')
    return {'items': rows, 'total': int(total) if total is not None else None, 'name': data.get('name', ''), 'next': next_link}


def chronocanon(url, progress):
    parsed = urllib.parse.urlparse(url)
    if not re.fullmatch(r'/franchise/[a-z0-9-]+/?', parsed.path):
        raise ValueError('Use a ChronoCanon /franchise/name URL.')
    progress('Reading ChronoCanon timelines…')
    roots = page_json(fetch(url))
    candidates = [o for root in roots for o in json_objects(root) if isinstance(o.get('timelines'), list) and any(isinstance(t, dict) and 'events' in t for t in o['timelines'])]
    if not candidates:
        raise ValueError('ChronoCanon did not expose its complete timeline data. No list was saved.')
    timelines = candidates[0]['timelines']
    selected = urllib.parse.parse_qs(parsed.query).get('timeline', [None])[0]
    timeline = {'id': 'all', 'name': 'All timelines (source order)', 'events': [e for t in timelines for e in t['events']]} if selected in (None, 'all') else next((t for t in timelines if t.get('id') == selected), None)
    if not timeline:
        raise ValueError('Unknown timeline. Available choices: ' + ', '.join(t['id'] for t in timelines))
    events = timeline.get('events', [])
    if not events or any(not isinstance(e.get('watchOrder'), (int, float)) for e in events):
        raise ValueError('ChronoCanon timeline has no complete watch order.')
    if len({e['watchOrder'] for e in events}) != len(events):
        raise ValueError('ChronoCanon watch order contains ambiguous positions.')
    rows, warnings = [], []
    for event in sorted(events, key=lambda e: e['watchOrder']):
        media = event.get('media') or {}
        kind = {'film': 'movie', 'show': 'show'}.get(media.get('type'))
        if not kind or not event.get('id'):
            raise ValueError('This timeline contains unsupported media; no entries were silently skipped.')
        row = {'type': kind, 'title': event['title'], 'source_key': 'chronocanon:' + event['id'], 'source_url': url}
        year = re.search(r'\d{4}', str(media.get('releaseDate') or event.get('label', '')))
        if year:
            row['year'] = year[0]
        # A regional/season story block is not permission to request an entire series.
        if kind == 'show':
            row.update(type='season', show_title=media.get('title') or event['title'], metadata_unresolved=True)
        rows.append(row)
        warnings.append(event['title'] + ': confirm exact ' + ('movie ID' if kind == 'movie' else 'parent show and season scope') + '; ChronoCanon supplies no provider IDs.')
    source = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode({'timeline': timeline['id']}), fragment=''))
    warnings.insert(0, 'Timeline: ' + timeline['name'] + '. Other choices: ' + ', '.join(t['id'] for t in timelines))
    return {'name': parsed.path.rstrip('/').split('/')[-1].replace('-', ' ').title() + ' · ' + timeline['name'], 'source': source, 'items': rows, 'warnings': warnings}


class TraktRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Trakt API redirected unexpectedly; no credentials were forwarded.')


def trakt_get(path, settings):
    client_id = settings.get('trakt', {}).get('key', '').strip()
    if not client_id:
        raise ValueError('Save your Trakt Client ID under Connections before importing a Trakt list.')
    if not path.startswith('/') or path.startswith('//') or '\\' in path or '#' in path:
        raise ValueError('Invalid Trakt API path.')
    request = urllib.request.Request('https://api.trakt.tv' + path, headers={
        'trakt-api-key': client_id, 'trakt-api-version': '2', 'Accept': 'application/json', 'User-Agent': 'ReelCheck/0.3'})
    try:
        with urllib.request.build_opener(TraktRedirects()).open(request, timeout=30) as response:
            raw = response.read(10_000_001)
            headers = {k.lower(): v for k, v in response.headers.items()}
        if len(raw) > 10_000_000:
            raise ValueError('Trakt response is too large.')
        return json.loads(raw), headers
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code in (401, 403):
            raise ValueError('Trakt rejected this Client ID or its access to this list. Check the registration and whether the list is public.') from None
        if code == 429:
            raise ValueError('Trakt rate limit reached. Wait before retrying; your saved list was not replaced.') from None
        raise ValueError(f'Trakt returned HTTP {code}. Check the public list URL and retry.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('Could not reach the Trakt API. Check your connection and retry.') from None
    except json.JSONDecodeError:
        raise ValueError('Trakt returned an invalid JSON response.') from None


def trakt_row(item):
    kind = item.get('type')
    if kind not in ('movie', 'show', 'season', 'episode'):
        raise ValueError('Trakt list contains unsupported media; no entries were silently skipped.')
    media = item.get(kind) or {}
    ids = media.get('ids') or {}
    title = media.get('title') or (f"Season {media.get('number')}" if kind == 'season' else None)
    if not title or not str(item.get('id', '')).isdigit():
        raise ValueError('Trakt returned an entry without a stable list-item ID or title.')
    row = {'type': kind, 'title': title, 'source_key': 'trakt:' + str(item['id'])}
    for provider in ('tmdb', 'tvdb', 'imdb'):
        if ids.get(provider):
            row[provider] = str(ids[provider])
    if media.get('year'):
        row['year'] = str(media['year'])
    if kind in ('season', 'episode'):
        show = item.get('show') or {}
        row['show_title'] = show.get('title') or ''
        for provider in ('tmdb', 'tvdb', 'imdb'):
            if (show.get('ids') or {}).get(provider):
                row['show_' + provider] = str(show['ids'][provider])
        row['season'] = str(media.get('season') if kind == 'episode' else media.get('number'))
        if kind == 'episode':
            row['episode'] = str(media.get('number'))
        if not row['season'].isdigit() or (kind == 'episode' and not row['episode'].isdigit()):
            raise ValueError('Trakt returned incomplete TV numbering; no partial list was saved.')
        if not any(row.get('show_' + p) for p in ('tmdb', 'tvdb', 'imdb')):
            row['metadata_unresolved'] = True
    return row


def verify_trakt_shortfall(base, original, settings):
    """Cross-check stale all-item totals against independently paginated types."""
    verified=[]
    for kind in ('movies','shows','seasons','episodes','people'):
        page=1;pages=None;total=None;typed=[]
        while pages is None or page<=pages:
            items,headers=trakt_get(base+'/items/'+kind+'?'+urllib.parse.urlencode({'page':page,'limit':100}),settings)
            try:
                count=int(headers['x-pagination-item-count']);last=int(headers['x-pagination-page-count']);current=int(headers['x-pagination-page'])
            except (KeyError,TypeError,ValueError):raise ValueError('Trakt category totals could not be verified. No partial list was saved.') from None
            if current!=page or not 0<=count<=20000 or not 0<=last<=200 or (count>0 and last<1) or (total is not None and (total!=count or pages!=last)) or not isinstance(items,list) or (count>0 and not items):
                raise ValueError('Trakt category pagination was inconsistent. No partial list was saved.')
            total=count;pages=last;typed.extend(items);page+=1
        if len(typed)!=total or len({item.get('id') for item in typed})!=total:
            raise ValueError('Trakt did not return every unique category entry. No partial list was saved.')
        verified.extend(typed)
    if len({item.get('id') for item in verified})!=len(verified) or {item.get('id'):item for item in verified}!={item.get('id'):item for item in original}:
        raise ValueError('Trakt category entries disagree with the main list. Retry; no partial list was saved.')
    return len(verified)


def trakt(url, progress, settings):
    parsed = urllib.parse.urlparse(url)
    match = re.fullmatch(r'/users/([^/]+)/lists/([^/]+)/?', parsed.path)
    numeric = re.fullmatch(r'/lists/(\d+)/?', parsed.path)
    if match:
        base = '/users/' + urllib.parse.quote(urllib.parse.unquote(match[1]), safe='') + '/lists/' + urllib.parse.quote(urllib.parse.unquote(match[2]), safe='')
    elif numeric:
        base = '/lists/' + numeric[1]
    else:
        raise ValueError('Use a public Trakt /users/name/lists/list-name or /lists/123 URL.')
    metadata, _ = trakt_get(base, settings)
    total = metadata.get('item_count')
    if not isinstance(total, int) or not 0 < total <= 20000:
        raise ValueError('Trakt list must report 1–20,000 items.')
    rows, pages, page = [], None, 1
    while pages is None or page <= pages:
        progress(f'Reading Trakt page {page}: {len(rows)}/{total} entries…')
        items, headers = trakt_get(base + '/items?' + urllib.parse.urlencode({'page': page, 'limit': 100}), settings)
        try:
            page_count = int(headers['x-pagination-page-count'])
            item_count = int(headers['x-pagination-item-count'])
            page_number = int(headers['x-pagination-page'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Trakt did not confirm pagination totals. No partial list was saved.') from None
        if item_count != total or page_number != page or not 0 < page_count <= 200 or (pages is not None and pages != page_count):
            raise ValueError('Trakt list changed or pagination was inconsistent. Retry; no partial list was saved.')
        pages = page_count
        if not isinstance(items, list) or not items:
            raise ValueError('Trakt returned an empty or invalid page before the list was complete.')
        rows.extend(items)
        page += 1
    ranks = [r.get('rank') for r in rows]
    # Rank values are ordering hints, not pagination counters. Real public lists
    # can contain gaps and tied ranks even when every unique item is returned.
    if not rows or len(rows)>total or any(type(rank) is not int or rank<1 for rank in ranks) or len({r.get('id') for r in rows}) != len(rows):
        raise ValueError('Trakt did not return every unique ranked list entry. No partial list was saved.')
    shortfall=total-len(rows)
    if shortfall:verify_trakt_shortfall(base,rows,settings)
    result = [trakt_row(item) for item in sorted(rows, key=lambda r: (r['rank'],int(r.get('id',0))))]
    # Detect edits during pagination, even when the item count stays unchanged.
    after, _ = trakt_get(base, settings)
    if after.get('item_count') != total or after.get('updated_at') != metadata.get('updated_at'):
        raise ValueError('Trakt list changed during import. Retry; no partial list was saved.')
    warnings=[r['title'] + ': exact parent-show IDs need matching.' for r in result if r.get('metadata_unresolved')]
    if shortfall:warnings.append(f'Trakt reports {total} items but exposes only {len(rows)}. All five media categories independently confirmed these same entries. {shortfall} reported items are unavailable through the API; their identities cannot be determined. Recheck the source later.')
    if len(set(ranks))!=len(rows):warnings.append('Trakt reports tied source ranks. All unique entries were imported; ties use stable list-item ID order. Choose alphabetical import order if preferred.')
    return {'name': metadata.get('name') or 'Trakt list', 'source': 'https://trakt.tv' + parsed.path.rstrip('/'), 'source_version': after.get('updated_at'), 'items': result,'warnings':warnings}


def import_url(url, progress=lambda *args: None, settings=None):
    host = validate_url(url).hostname.replace('www.', '')
    if host in ('trakt.tv','app.trakt.tv'):
        return trakt(url, progress, settings or {})
    adapter = {'letterboxd.com': letterboxd, 'mdblist.com': mdblist, 'imdb.com': imdb, 'chronocanon.com': chronocanon}.get(host)
    if not adapter:
        raise ValueError('This list provider is not supported yet. Import CSV or JSON instead.')
    return adapter(url, progress)


def tmdb(path, settings):
    token = settings.get('tmdb', {}).get('key', '')
    if not token:
        raise ValueError('Add a TMDB API Read Access Token under Connections to resolve episode metadata.')
    return json.loads(fetch('https://api.themoviedb.org/3/' + path, token))


def enrich(row, settings):
    """Exact ID lookups only. No automatic title-search guesses."""
    row = dict(row)
    if not settings.get('tmdb', {}).get('key'):
        return row
    if row['type'] != 'movie':
        prefix = 'show_' if row['type'] in ('episode', 'season') else ''
        if not row.get(prefix + 'tmdb'):
            for provider in ('tvdb', 'imdb'):
                external = row.get(prefix + provider)
                if not external:
                    continue
                found = tmdb('find/' + urllib.parse.quote(str(external), safe='') + '?external_source=' + provider + '_id', settings)
                shows = found.get('tv_results', [])
                if len(shows) == 1:
                    row[prefix + 'tmdb'] = str(shows[0]['id'])
                    row.setdefault('show_title' if prefix else 'title', shows[0].get('name', row['title']))
                    break
    if row.get('imdb') and (not row.get('tmdb') or row.get('metadata_unresolved')):
        result = tmdb('find/' + row['imdb'] + '?external_source=imdb_id', settings)
        choices = [(kind, item) for key, kind in [('movie_results', 'movie'), ('tv_results', 'show'), ('tv_episode_results', 'episode')] for item in result.get(key, [])]
        if len(choices) == 1:
            kind, item = choices[0]
            if row['type'] == 'episode' and kind != 'episode':
                raise ValueError('This IMDb ID is not an episode ID. Confirm the exact episode or enter its parent-show ID and coordinates.')
            if row['type'] == 'season':
                if kind != 'show':
                    raise ValueError('A season needs the exact parent-show ID and season number.')
                row.update(show_tmdb=str(item['id']), show_imdb=row['imdb'])
                row.pop('imdb', None)
                if row.get('season') not in ('', None):
                    row.pop('metadata_unresolved', None)
            else:
                row.update(type=kind, tmdb=str(item['id']))
                row.pop('metadata_unresolved', None)
            if kind == 'episode':
                row.update(show_tmdb=str(item['show_id']), season=str(item['season_number']), episode=str(item['episode_number']))
    parent_id = row.get('show_tmdb') if row['type'] in ('episode', 'season') else row.get('tmdb') if row['type'] == 'show' else None
    if parent_id and not (row.get('show_tvdb') if row['type'] in ('episode', 'season') else row.get('tvdb')):
        ids = tmdb('tv/' + str(parent_id) + '/external_ids', settings)
        prefix = 'show_' if row['type'] in ('episode', 'season') else ''
        for provider in ('tvdb', 'imdb'):
            if ids.get(provider + '_id'):
                row[prefix + provider] = str(ids[provider + '_id'])
    return row


def parent_show(row, settings):
    """Resolve a parent without mistaking an episode ID for the show ID."""
    row = enrich(row, settings)
    prefix = 'show_' if row['type'] in ('episode', 'season') else ''
    result = {'type': 'show', 'title': row.get('show_title') or row['title']}
    for provider in ('tmdb', 'tvdb', 'imdb'):
        if row.get(prefix + provider):
            result[provider] = row[prefix + provider]
    if not result.get('tmdb'):
        raise ValueError('The parent show could not be resolved. Add its TMDB, TVDB, or IMDb ID using Correct match.')
    return result


def cached_tmdb(path, settings):
    # Coalesce simultaneous episode requests for the same parent/season.
    with _tmdb_cache_guard:
        lock = _tmdb_cache_locks.setdefault(path, threading.Lock())
    with lock:
        return _cached_tmdb(path, settings)


def peek_tmdb(path):
    """Read already-cached metadata without making a network request."""
    file = CACHE / 'tmdb' / (hashlib.sha256(path.encode()).hexdigest() + '.json')
    try:
        result = json.loads(file.read_text('utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def _cached_tmdb(path, settings):
    folder = CACHE / 'tmdb'
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / (hashlib.sha256(path.encode()).hexdigest() + '.json')
    if file.exists() and time.time() - file.stat().st_mtime < 86400:
        try:
            return json.loads(file.read_text('utf-8'))
        except (OSError, ValueError):
            pass
    result = tmdb(path, settings)
    temp = file.with_suffix('.' + str(threading.get_ident()) + '.tmp')
    temp.write_text(json.dumps(result), 'utf-8')
    temp.replace(file)
    return result


def image_url(path, size='w342'):
    if isinstance(path, str) and re.fullmatch(r'/[A-Za-z0-9_.-]+', path):
        return 'https://image.tmdb.org/t/p/' + size + path
    return None


def list_details(row, settings):
    """Small list summary. Reuse one cached season response across its episodes."""
    row = dict(row)
    if not settings.get('tmdb', {}).get('key'):
        raise ValueError('Connect TMDB to load title metadata.')
    kind = row['type']
    if not row.get('tmdb') or (kind in ('season', 'episode') and not row.get('show_tmdb')):
        row = enrich(row, settings)
    identifier = row.get('tmdb') if kind in ('movie', 'show') else row.get('show_tmdb')
    if not str(identifier or '').isdigit():
        raise ValueError('This entry needs an exact TMDB title or parent-show ID.')
    path = ('movie/' if kind == 'movie' else 'tv/') + str(identifier)
    try:
        parent = cached_tmdb(path, settings)
    except ValueError as exc:
        if kind=='movie' and row.get('imdb') and '404' in str(exc):
            found=cached_tmdb('find/'+row['imdb']+'?external_source=imdb_id',settings)
            if len(found.get('tv_results',[]))==1 and not found.get('movie_results'):
                raise ValueError('This imported movie ID identifies a TV title. Use Correct match to select TV show, then compare again; retrying this movie ID will not fix it.') from None
        raise
    data = parent
    if kind in ('season', 'episode'):
        if not str(row.get('season', '')).isdigit() or (kind == 'episode' and not str(row.get('episode', '')).isdigit()):
            raise ValueError('This entry needs exact season and episode numbers.')
        season = cached_tmdb(path + '/season/' + str(row['season']), settings)
        data = season
        if kind == 'episode':
            data = next((e for e in season.get('episodes', []) if str(e.get('episode_number')) == str(int(row['episode']))), None)
            if data is None:
                raise ValueError('This episode is not available in TMDB season metadata.')
    runtime = data.get('runtime')
    if runtime is None and kind != 'movie':
        runtime = next(iter(parent.get('episode_run_time') or []), None)
    return {'summary_only': True, 'tmdb': str(identifier) if kind in ('movie','show') else row.get('tmdb'), 'show_tmdb': str(identifier) if kind != 'movie' else None, 'type': kind, 'title': data.get('title') or data.get('name') or row['title'],
            'show_title': parent.get('name') if kind != 'movie' else None,
            'overview': data.get('overview') or (parent.get('overview') if kind in ('season', 'episode') else '') or '',
            'overview_scope': 'series' if kind in ('season', 'episode') and not data.get('overview') else 'title',
            'poster': image_url(data.get('poster_path') or parent.get('poster_path')),
            'rating': data.get('vote_average') if data.get('vote_count') else None, 'vote_count': data.get('vote_count', 0),
            'release_date': data.get('release_date') or data.get('air_date') or data.get('first_air_date'), 'runtime': runtime}


def title_details(row, settings):
    """Fetch an exact movie/show/season/episode, never guess from a display title."""
    row = dict(row)
    if not settings.get('tmdb', {}).get('key'):
        raise ValueError('Save a TMDB API Read Access Token under Connections to view title details.')
    if not row.get('tmdb') or (row['type'] in ('episode', 'season') and not row.get('show_tmdb')):
        row = enrich(row, settings)
    kind = row['type']
    parent = None
    if kind == 'movie':
        if not str(row.get('tmdb', '')).isdigit():
            raise ValueError('This movie needs a TMDB or IMDb ID. Use Correct match to identify it.')
        path = 'movie/' + str(row['tmdb'])
    else:
        show_id = row.get('tmdb') if kind == 'show' else row.get('show_tmdb')
        if not str(show_id or '').isdigit():
            raise ValueError('This entry needs a parent-show TMDB ID. Use Resolve metadata or Correct match.')
        path = 'tv/' + str(show_id)
        if kind in ('season', 'episode'):
            if not str(row.get('season', '')).isdigit() or (kind == 'episode' and not str(row.get('episode', '')).isdigit()):
                raise ValueError('Resolve this episode’s season and episode numbers first.')
            parent = cached_tmdb(path + '?append_to_response=videos,credits', settings)
            path += '/season/' + str(row['season'])
            if kind == 'episode':
                path += '/episode/' + str(row['episode'])
    extras = 'videos,credits,external_ids' + (',aggregate_credits' if kind == 'show' else '')
    data = cached_tmdb(path + '?append_to_response=' + extras, settings)
    context = parent or data
    videos = [v for v in data.get('videos', {}).get('results', []) if v.get('site') == 'YouTube' and v.get('type') == 'Trailer' and re.fullmatch(r'[A-Za-z0-9_-]{6,64}', v.get('key', ''))]
    trailer_scope = 'title'
    if not videos and parent:
        videos = [v for v in parent.get('videos', {}).get('results', []) if v.get('site') == 'YouTube' and v.get('type') == 'Trailer' and re.fullmatch(r'[A-Za-z0-9_-]{6,64}', v.get('key', ''))]
        trailer_scope = 'series'
    videos.sort(key=lambda v: (not v.get('official', False), v.get('iso_639_1') != 'en'))
    trailer = videos[0] if videos else None
    credits = data.get('credits') or context.get('credits', {})
    if kind == 'show' and 'aggregate_credits' in data:
        aggregate = data['aggregate_credits']
        credits = {
            'cast': [dict(c, character=' / '.join(dict.fromkeys(r['character'] for r in c.get('roles', []) if r.get('character'))) or c.get('character', '')) for c in aggregate.get('cast', [])],
            'crew': [dict(c, job=j['job'], episode_count=j.get('episode_count')) for c in aggregate.get('crew', []) for j in (c.get('jobs') or [{'job': c.get('job')}]) if j.get('job')],
        }
    cast = credits.get('cast') or data.get('guest_stars', [])
    if kind == 'episode':
        combined = {}
        for person in cast + data.get('guest_stars', []):
            key = person.get('id') or person.get('name')
            if key not in combined:
                combined[key] = person
        cast = list(combined.values())
    runtime = data.get('runtime') or (context.get('episode_run_time') or [None])[0]
    if kind == 'season':
        runtime = None
    rating = data.get('vote_average') if data.get('vote_count', 1) and data.get('vote_average', 0) > 0 else None
    external = data.get('external_ids', {})
    imdb_id = data.get('imdb_id') or external.get('imdb_id') or row.get('imdb')
    return {
        'title': data.get('title') or data.get('name') or row['title'],
        'original_title': data.get('original_title') or data.get('original_name'),
        'show_title': context.get('name') if parent else None,
        'type': kind, 'tagline': data.get('tagline') or '',
        'overview': data.get('overview') or (parent or {}).get('overview') or '',
        'overview_scope': 'series' if not data.get('overview') and parent else 'title',
        'rating': rating, 'vote_count': data.get('vote_count'), 'rating_source': 'TMDB',
        'poster': image_url(data.get('poster_path') or context.get('poster_path')),
        'backdrop': image_url(data.get('backdrop_path') or data.get('still_path') or context.get('backdrop_path'), 'w1280'),
        'release_date': data.get('release_date') or data.get('air_date') or data.get('first_air_date'),
        'last_air_date': data.get('last_air_date'), 'runtime': runtime,
        'genres': [g['name'] for g in context.get('genres', [])],
        'status': data.get('status') or context.get('status'),
        'language': data.get('original_language') or context.get('original_language'),
        'countries': [c['name'] for c in context.get('production_countries', [])],
        'networks': [n['name'] for n in context.get('networks', [])],
        'seasons': data.get('number_of_seasons'),
        'episodes': data.get('number_of_episodes') or (len(data['episodes']) if 'episodes' in data else None),
        'creator_people': [{'id': c.get('id'), 'name': c.get('name')} for c in context.get('created_by', [])],
        'studios': [{'id': c.get('id'), 'name': c.get('name')} for c in context.get('production_companies', [])],
        'producer_people': [{'id': c.get('id'), 'name': c.get('name'), 'job': c.get('job'), 'photo': image_url(c.get('profile_path')), 'episode_count': c.get('episode_count'), 'popularity': c.get('popularity', 0)} for c in credits.get('crew', []) if c.get('job') in ('Producer', 'Executive Producer', 'Co-Producer')],
        'director_people': [{'id': c.get('id'), 'name': c.get('name'), 'photo': image_url(c.get('profile_path')), 'episode_count': c.get('episode_count'), 'popularity': c.get('popularity', 0)} for c in credits.get('crew', []) if c.get('job') == 'Director'],
        'related_type': 'movie' if kind == 'movie' else 'show',
        'related_id': str(row.get('tmdb') if kind in ('movie', 'show') else row.get('show_tmdb')),
        'cast': [{'id': c.get('id'), 'name': c.get('name'), 'character': c.get('character'), 'photo': image_url(c.get('profile_path')), 'episode_count': c.get('total_episode_count', c.get('episode_count')), 'popularity': c.get('popularity', 0)} for c in cast],
        'directors': list(dict.fromkeys(c['name'] for c in credits.get('crew', []) if c.get('job') == 'Director')),
        'creators': [c['name'] for c in context.get('created_by', [])],
        'trailer': {'url': 'https://www.youtube.com/watch?v=' + trailer['key'], 'name': trailer.get('name', 'Trailer'), 'scope': trailer_scope} if trailer else None,
        'tmdb_url': 'https://www.themoviedb.org/' + path,
        'imdb_url': 'https://www.imdb.com/title/' + imdb_id + '/' if imdb_id and re.fullmatch(r'tt\d+', imdb_id) else None,
    }


def discovery(kind, identifier, settings):
    """Return deduplicated, provider-identified projects; never infer universe membership."""
    if not str(identifier).isdigit() or int(identifier) <= 0:
        raise ValueError('A valid TMDB identifier is required.')
    identifier = str(int(identifier))
    groups = []
    profile = None
    relationship_collection = None
    if kind == 'person':
        person = cached_tmdb('person/' + identifier, settings)
        credits = cached_tmdb('person/' + identifier + '/combined_credits', settings)
        name = person.get('name') or 'Person'
        profile = {'photo': image_url(person.get('profile_path')), 'biography': person.get('biography') or '', 'department': person.get('known_for_department'), 'birthday': person.get('birthday'), 'deathday': person.get('deathday'), 'birthplace': person.get('place_of_birth')}
        groups = [('Filmography', credits.get('cast', []) + credits.get('crew', []))]
        note = 'Movie and TV credits listed by TMDB, including guest appearances and crew work. Credits may be incomplete.'
    elif kind == 'company':
        company = cached_tmdb('company/' + identifier, settings)
        name = company.get('name') or 'Studio'
        for media in ('movie', 'tv'):
            data = cached_tmdb('discover/' + media + '?with_companies=' + identifier + '&sort_by=popularity.desc&page=1', settings)
            groups.append(('Studio projects', [dict(r, media_type=media) for r in data.get('results', [])]))
        note = 'TMDB production-company credits. Showing the first page of popular movies and TV shows for this studio; this is not its complete catalogue.'
    elif kind in ('movie', 'show'):
        path = ('movie/' if kind == 'movie' else 'tv/') + identifier
        title = cached_tmdb(path, settings)
        name = 'Related to ' + (title.get('title') or title.get('name') or 'this title')
        collection = title.get('belongs_to_collection') if kind == 'movie' else None
        if collection and str(collection.get('id', '')).isdigit():
            data = cached_tmdb('collection/' + str(collection['id']), settings)
            relationship_collection = data
            groups.append((data.get('name') or 'TMDB collection', [dict(r, media_type='movie') for r in data.get('parts', [])]))
        recommendations = cached_tmdb(path + '/recommendations?page=1', settings)
        groups.append(('Recommendations - not confirmed universe members', [dict(r, media_type='movie' if kind == 'movie' else 'tv') for r in recommendations.get('results', [])]))
        note = 'Named collections are TMDB movie groupings. Recommendations are the first page of suggestions, not confirmed sequels or shared-universe titles. Cross-media universes may need a curated list. Sorted by release date, not story chronology.'
    else:
        raise ValueError('Unknown discovery type.')
    rows = {}
    for group, projects in groups:
        for r in projects:
            media = r.get('media_type')
            if media not in ('movie', 'tv') or not str(r.get('id', '')).isdigit():
                continue
            if kind in ('movie', 'show') and media == ('movie' if kind == 'movie' else 'tv') and str(r['id']) == identifier:
                continue
            key = media + ':' + str(r['id'])
            role = r.get('character') or r.get('job')
            if key in rows:
                if role and role not in rows[key]['roles']:
                    rows[key]['roles'].append(role)
                continue
            date = r.get('release_date') or r.get('first_air_date') or ''
            rows[key] = {'key': key, 'type': 'movie' if media == 'movie' else 'show', 'tmdb': str(r['id']), 'title': r.get('title') or r.get('name') or 'Untitled', 'year': date[:4], 'release_date': date, 'poster': image_url(r.get('poster_path')), 'overview': r.get('overview') or '', 'rating': r.get('vote_average') if r.get('vote_count') else None, 'group': group, 'roles': [role] if role else []}
    result = {'name': name, 'note': note, 'profile': profile, 'items': sorted(rows.values(), key=lambda r: (r['group'].startswith('Recommendations'), r['release_date'] or '9999', r['title']))}
    if kind in ('movie', 'show'):
        result['sections'] = title_relationships.sections(kind, identifier, title, relationship_collection, result['items'], settings, cached_tmdb, image_url)
    return result
