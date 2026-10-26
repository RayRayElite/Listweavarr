"""ReelCheck: local-only Plex list workbench. Python 3.11+, standard library."""
import copy
import os
import csv
import datetime
import http.client
import ipaddress
import io
import json
import re
import hashlib
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
import providers
import trakt_features
import metadata_sources
import suggestions
import poster_overlays
import ignored_titles
import discord_notify
import manager_routes
import request_ledger
import list_sharing
import text_list_builder
import saved_lists
import release_watch
import activity
import official_lists
import collection_tools
import taste
import companion
import catalogue_feed
import backups
import ratings
import explore
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / 'data'
LOCK = threading.Lock()
SESSION = secrets.token_urlsafe(32)
JOBS = {}
JOBS_LOCK = threading.Lock()


def start_import_job(body):
    job_id = secrets.token_hex(12)
    with JOBS_LOCK:
        # Keep recent jobs available across browser refreshes without growing forever.
        for key in list(JOBS):
            if time.time() - JOBS[key]['created'] > 3600:
                del JOBS[key]
        JOBS[job_id] = {'created': time.time(), 'status': 'running', 'message': 'Starting import…'}

    def progress(message, done=0, total=0):
        with JOBS_LOCK:
            JOBS[job_id].update(message=message, done=done, total=total)

    def run():
        try:
            with LOCK:
                snapshot = read_state()
            previous = next((x for x in snapshot['lists'] if x['id'] == body.get('list_id')), None)
            if body.get('list_id') and not previous:raise ValueError('This saved list was removed. Choose another list.')
            options=providers.import_options(body.get('import_options') if 'import_options' in body else (previous or {}).get('import_options'))
            url = '' if body.get('content') else body.get('url','').strip() or (previous.get('source') if previous else '')
            if previous and not url and not body.get('content'):
                raise ValueError('This list came from a file. Import its updated file instead.')
            if url:
                imported = providers.import_url(url, progress, snapshot['settings'])
                rows, warnings = [], imported['warnings']
                for number, row in enumerate(imported['items'], 1):
                    progress(f'Resolving title identifiers: {number}/{len(imported["items"])}…')
                    try:
                        row = providers.enrich(row, snapshot['settings'])
                    except ValueError as exc:
                        warnings.append(row['title'] + ': ' + str(exc))
                        row['metadata_note'] = str(exc)
                        if row['type'] in ('season', 'episode'):
                            row['metadata_unresolved'] = True
                    rows.append(normalize(row))
            else:
                progress('Reading the imported file…')
                imported = {'name': body.get('name') or 'Imported list', 'source': None}
                rows = import_items(body['content'], body['format'], snapshot['settings'], progress)
                warnings = [r['title'] + ': ' + (r.get('metadata_note') or 'Exact TV scope still needs matching.') for r in rows if r.get('metadata_note') or r.get('metadata_unresolved')]
            rows=[normalize(row) for row in providers.arrange_import(rows,options)]
            entry = {'id': previous['id'] if previous else secrets.token_hex(8), 'name': body.get('name', '').strip() or (previous['name'] if previous else imported['name']), 'items': rows, 'source': imported['source'], 'warnings': warnings, 'updated_at': time.time(), 'import_options':options}
            if imported.get('source_version'):
                entry['source_version'] = imported['source_version']
            if entry['source'] and 'trakt.tv/' in entry['source']:
                entry['followed'] = previous.get('followed', True) if previous else True
            with LOCK:
                state = read_state()
                latest = next((x for x in state['lists'] if x['id'] == entry['id']), None)
                if previous and not latest:raise ValueError('This list was removed during import. It was not recreated.')
                if latest:
                    if previous and latest.get('updated_at')!=previous.get('updated_at'):
                        raise ValueError('This list changed during import. Retry from its current version.')
                    for field in ('poster','description','official_id','official_version','official_authoring','watch_paths','official_base','official_undo'):
                        if field in latest:entry[field]=latest[field]
                    if latest.get('playlist'):
                        entry['playlist'] = latest['playlist']
                    old_items = {i.get('source_key'): i for i in latest['items'] if i.get('source_key')}
                    legacy = {}
                    for old in latest['items']:
                        if not old.get('source_key'):
                            legacy.setdefault(source_identity(old), []).append(old)
                    for row in rows:
                        old = old_items.get(row.get('source_key'))
                        if not old and legacy.get(source_identity(row)):
                            old = legacy[source_identity(row)].pop(0)
                        row['is_new'] = old is None
                        if old:
                            row['id'] = old['id']
                            row.update(old.get('correction', {}))
                            if old.get('correction'):
                                row['correction'] = old['correction']
                            for field in ('plex_override', 'plex_server'):
                                if old.get(field):
                                    row[field] = old[field]
                            if row['type'] in ('season', 'episode') and row.get('season') and (row['type'] == 'season' or row.get('episode')) and any(row.get('show_' + p) for p in ('tmdb', 'tvdb', 'imdb')):
                                row.pop('metadata_unresolved', None)
                    entry['refresh_report'] = refresh_report(latest['items'], rows)
                    entry['comparison_baseline'] = latest.get('comparison_baseline') or {i['id']: i['status'] for i in latest['items'] if i.get('status') not in (None, 'unchecked')}
                    if latest.get('playlist'):
                        entry['playlist_needs_update'] = True
                    state['lists'][state['lists'].index(latest)] = entry
                else:
                    state['lists'].append(entry)
                save_state(state)
            with JOBS_LOCK:
                JOBS[job_id].update(status='complete', message=f'Imported {len(rows)} entries.', result=entry)
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else 'The import failed unexpectedly. Your saved lists were not replaced.'
            with JOBS_LOCK:
                JOBS[job_id].update(status='error', message=message)
    threading.Thread(target=run, daemon=True).start()
    return {'job_id': job_id}


REFRESH_LOCK=threading.Lock()
BACKGROUND_STARTED=False

def refresh_request_state(force=False):
    if not REFRESH_LOCK.acquire(blocking=False):
        with LOCK:return {**request_ledger.public(read_state()),'warnings':['A status refresh is already running.']}
    try:
        with LOCK:snapshot=read_state();request_ledger.migrate(snapshot)
        requests=[r for r in snapshot.get('requests',[]) if r.get('status') not in ('pending','awaiting_approval','declined','cancelled','available')][-100:]
        groups={};updates={};warnings=[]
        for request in requests:groups.setdefault((request['service'],request.get('route','primary')),[]).append(request)
        for (service,route),group in groups.items():
            try:settings=manager_routes.routed(snapshot,service,route)
            except ValueError as exc:
                for request in group:updates[request['id']]={'state':'unavailable','label':str(exc)}
                continue
            items=[]
            for request in group:
                item=dict(request['item'],id=request['id'])
                if item['type']!='movie' and not (item.get('show_tvdb') if item['type'] in ('season','episode') else item.get('tvdb')):
                    try:item=providers.enrich(item,settings);item['id']=request['id']
                    except ValueError:pass
                items.append(item)
            if settings.get('plex',{}).get('key') and items:
                try:items=compare(items,settings)
                except ValueError:warnings.append('Plex availability could not be refreshed.')
            result=activity.summarize(items,settings,arr_call,force);updates.update(result['items']);warnings.extend(result['warnings'])
            for item in items:
                if item.get('status')=='available':updates[item['id']]={'state':'available','label':'Available in Plex','prevent_duplicate':True}
                elif settings.get('_requested_tier')=='4k' and updates.get(item['id'],{}).get('state')=='available':updates[item['id']]={'state':'imported','label':'Manager has a file; awaiting confirmed 4K in Plex'}
        with LOCK:
            state=read_state();request_ledger.migrate(state)
            revisions={r['id']:r.get('updated_at') for r in requests}
            updates={key:value for key,value in updates.items() if any(r['id']==key and r.get('updated_at')==revisions.get(key) for r in state.get('requests',[]))}
            request_ledger.apply_status(state,updates);discord_notify.collect(state);save_state(state)
            return {**request_ledger.public(state),'warnings':list(dict.fromkeys(warnings)),'checked_at':time.time()}
    finally:REFRESH_LOCK.release()

def dispatch_discord_once():
    with LOCK:
        state=read_state();cfg=state.get('discord_notifications',{})
        if not cfg.get('enabled') or not cfg.get('url'):return False
        before=json.dumps([cfg,state.get('notification_outbox',[])],sort_keys=True)
        discord_notify.collect(state);job=discord_notify.next_job(state)
        if job or before!=json.dumps([cfg,state.get('notification_outbox',[])],sort_keys=True):save_state(state)
    if not job:return False
    error=None;wait=0
    try:wait=discord_notify.send(cfg['url'],job['content']) or 0
    except discord_notify.DeliveryError as exc:error=exc
    with LOCK:
        state=read_state();discord_notify.finish(state,job['id'],error)
        if wait:state.setdefault('discord_notifications',{})['next_send_at']=time.time()+wait
        save_state(state)
    return not error

def start_background_tasks():
    global BACKGROUND_STARTED
    if BACKGROUND_STARTED:return
    BACKGROUND_STARTED=True
    def run():
        stop=threading.Event();last_check=0
        while not stop.wait(15):
            try:
                with LOCK:state=read_state()
                if time.time()-last_check>=90 and any(r.get('status') not in ('pending','awaiting_approval','declined','cancelled','available') for r in state.get('requests',[])):
                    refresh_request_state();last_check=time.time()
                for _ in range(5):
                    if not dispatch_discord_once():break
            except Exception:pass  # Keep retries alive without exposing credentials in logs.
    threading.Thread(target=run,daemon=True,name='ReelCheck-status-notifications').start()


def public_state(state):
    auth = state.get('plex_auth', {})
    return {'curator_mode':os.environ.get('REELCHECK_CURATOR_MODE')=='1','lists': state['lists'], 'taste_feedback':state.get('taste_feedback',{}), 'companion_preferences':state.get('companion_preferences',{}), 'ignored_titles':state.get('ignored_titles',[]), 'release_watchlist':state.get('release_watchlist',[]), 'release_region':state.get('release_region','CA'), 'explore_languages':state.get('explore_languages',[]), 'rating_preferences':ratings.preferences(state.get('rating_preferences')), 'rating_sources':[{'source':k,'label':v[0],'maximum':v[1]} for k,v in ratings.SOURCES.items()], 'settings': {
        k: {'url': v.get('url', ''), 'configured': bool(v.get('key')), 'server_name': v.get('server_name', '')}
        for k, v in state['settings'].items()},
        'plex_login': {'signed_in': bool(auth.get('token')), 'pending': bool(auth.get('pin')), 'account': auth.get('account', '')}, 'csrf': SESSION}


def plex_account(state, path, method='GET', fields=None, token=None):
    auth = state.setdefault('plex_auth', {})
    auth.setdefault('client_id', secrets.token_urlsafe(24))
    headers = {'Accept': 'application/json', 'X-Plex-Product': 'ReelCheck',
               'X-Plex-Version': '0.1.0', 'X-Plex-Client-Identifier': auth['client_id'],
               'X-Plex-Platform': 'Windows', 'X-Plex-Device-Name': 'ReelCheck local'}
    if token:
        headers['X-Plex-Token'] = token
    data = urllib.parse.urlencode(fields).encode() if fields is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    request = urllib.request.Request('https://clients.plex.tv' + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError('Plex authorization was denied or expired. Sign in with Plex again.') from None
        if exc.code == 404:
            raise ValueError('This Plex sign-in has expired. Start a new sign-in.') from None
        raise ValueError(f'Plex returned HTTP {exc.code}. Please try again shortly.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('Could not reach plex.tv. Check your internet connection and try again.') from None


def start_plex_login(state):
    pin = plex_account(state, '/api/v2/pins', 'POST', {'strong': 'true'})
    auth = state['plex_auth']
    auth['pin'] = {'id': pin['id'], 'code': pin['code'], 'expires': time.time() + min(int(pin.get('expiresIn', 900)), 900)}
    query = urllib.parse.urlencode({'clientID': auth['client_id'], 'code': pin['code'],
        'context[device][product]': 'ReelCheck', 'forwardUrl': 'http://127.0.0.1:8765/#plex-login'})
    return {'url': 'https://app.plex.tv/auth#?' + query}


def check_plex_login(state):
    auth = state.get('plex_auth', {})
    pin = auth.get('pin')
    if pin:
        if pin['expires'] <= time.time():
            auth.pop('pin', None)
            raise ValueError('Plex sign-in expired. Click Sign in with Plex to try again.')
        response = plex_account(state, '/api/v2/pins/' + str(pin['id']) + '?' + urllib.parse.urlencode({'code': pin['code']}))
        if not response.get('authToken'):
            return {'signed_in': False, 'pending': True}
        token = response['authToken']
        user = plex_account(state, '/api/v2/user', token=token)
        # A different account must never retain the previous account's server credentials.
        state['settings'].pop('plex', None)
        auth.update(token=token, account=user.get('username') or user.get('title') or 'Plex account')
        auth.pop('pin', None)
    return {'signed_in': bool(auth.get('token')), 'pending': False, 'account': auth.get('account', '')}


def plex_servers(state, private=False):
    token = state.get('plex_auth', {}).get('token')
    if not token:
        raise ValueError('Sign in with Plex first.')
    resources = plex_account(state, '/api/v2/resources?includeHttps=1&includeRelay=0', token=token)
    servers = [r for r in resources if 'server' in str(r.get('provides', '')).split(',') and r.get('accessToken')]
    if private:
        return servers
    return {'servers': [{'id': r['clientIdentifier'], 'name': r['name'], 'owned': bool(r.get('owned'))} for r in servers]}


def connect_plex_server(state, server_id, override=''):
    server = next((r for r in plex_servers(state, private=True) if r['clientIdentifier'] == server_id), None)
    if not server:
        raise ValueError('This server is no longer available to your Plex account. Refresh the server list.')
    connections = [c for c in server.get('connections', []) if not c.get('relay')]
    connections.sort(key=lambda c: (not c.get('local'), c.get('protocol') != 'https'))
    if override:
        connections = [{'uri': override.strip().rstrip('/')}]
    for connection in connections:
        try:
            url = connection['uri']
            identity = remote(url, '/', server['accessToken'], plex=True, timeout=5)
            if identity.get('machineIdentifier') != server_id:
                continue
            remote(url, '/library/sections', server['accessToken'], plex=True, timeout=5)
            state['settings']['plex'] = {'url': url, 'key': server['accessToken'], 'server_name': server['name'], 'server_id':server_id}
            return {'name': server['name'], 'url': url}
        except (ValueError, ET.ParseError):
            continue
    raise ValueError('Could not connect to this Plex server. Check that it is running and this computer can reach your NAS. You can also set a server address below after signing in.')


def read_state():
    return json.loads((DATA / 'state.json').read_text('utf-8')) if (DATA / 'state.json').exists() else {'settings': {}, 'lists': []}


def save_state(state, backup=True):
    DATA.mkdir(exist_ok=True)
    current=DATA/'state.json'
    if current.exists() and backup:
        previous=json.loads(current.read_text('utf-8'))
        if backups.export(previous)['data']!=backups.export(state)['data']:
            backups.rolling(DATA/'backups',previous)
    temp = DATA / 'state.tmp'
    temp.write_text(json.dumps(state, indent=2), 'utf-8')
    temp.replace(DATA / 'state.json')


def plex_direct_ip(host):
    """Plex's IPv4 hostnames encode the target IP; only allow unicast LAN IPs."""
    if not host or not host.endswith('.plex.direct'):
        return None
    try:
        address = ipaddress.ip_address(host.split('.')[0].replace('-', '.'))
    except ValueError:
        return None
    if address.version == 4 and address.is_private and not (address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local):
        return str(address)
    return None


class PlexDirectHTTPSConnection(http.client.HTTPSConnection):
    """Bypass broken local DNS while retaining the original TLS hostname/SNI."""
    def connect(self):
        address = plex_direct_ip(self.host)
        if not address:
            raise ValueError('This address is not a local Plex HTTPS hostname.')
        self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
        try:
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise


def plex_direct_request(parsed, path, headers, timeout, method='GET'):
    connection = PlexDirectHTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout)
    try:
        target = (parsed.path.rstrip('/') + path) or '/'
        connection.request(method, target, headers=headers)
        response = connection.getresponse()
        if response.status not in (200, 201, 204):
            raise ValueError(f'Plex server returned HTTP {response.status}.')
        raw = response.read()
        return ET.fromstring(raw) if raw else ET.Element('MediaContainer')
    finally:
        connection.close()


def remote(base, path, key='', payload=None, method=None, plex=False, timeout=45):
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Enter a full http:// or https:// server address without credentials.')
    headers = {'Accept': 'application/xml' if plex else 'application/json'}
    headers['X-Plex-Token' if plex else 'X-Api-Key'] = key
    if payload is not None:
        headers['Content-Type'] = 'application/octet-stream' if isinstance(payload,bytes) else 'application/json'
    req = urllib.request.Request(base.rstrip('/') + path, data=payload if isinstance(payload,bytes) else json.dumps(payload).encode() if payload is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
        return (ET.fromstring(raw) if raw else ET.Element('MediaContainer')) if plex else (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Server returned HTTP {exc.code}. Check the address, API key, and permissions.') from None
    except urllib.error.URLError as exc:
        if plex and parsed.scheme == 'https' and isinstance(exc.reason, socket.gaierror) and plex_direct_ip(parsed.hostname):
            try:
                return plex_direct_request(parsed, path, headers, timeout, method or 'GET')
            except (OSError, http.client.HTTPException):
                raise ValueError('Could not reach the local Plex HTTPS address. Check NAS access and its HTTPS certificate.') from None
        raise ValueError('Could not reach the server. Check its address and network connection.') from None
    except TimeoutError:
        raise ValueError('The server did not respond before the connection timed out.') from None


def refresh_report(before, after):
    old = {r['id']: r for r in before}
    new = {r['id']: r for r in after}
    common_old = [r['id'] for r in before if r['id'] in new]
    common_new = [r['id'] for r in after if r['id'] in old]
    fields = ('type', 'tmdb', 'imdb', 'tvdb', 'show_tmdb', 'show_imdb', 'show_tvdb', 'season', 'episode')
    return {'added': [r['title'] for r in after if r['id'] not in old], 'removed': [r['title'] for r in before if r['id'] not in new],
            'order_changed': common_old != common_new,
            'changed': [r['title'] for r in after if r['id'] in old and any(r.get(k) != old[r['id']].get(k) for k in fields)]}


def source_identity(row):
    if row.get('imdb'):
        return ('imdb', row['imdb'])
    if row.get('tmdb') and row['type'] in ('movie', 'show'):
        return (row['type'], 'tmdb', str(row['tmdb']))
    if row.get('show_tmdb'):
        return (row['type'], str(row['show_tmdb']), str(row.get('season', '')), str(row.get('episode', '')))
    return (row['type'], row['title'].casefold(), row.get('year'))


def normalize(row):
    row = {str(k).lower().strip().replace(' ', '_'): v for k, v in row.items() if k}
    raw_kind = str(row.get('type') or row.get('title_type') or 'movie').lower()
    kind = {'tvseries': 'show', 'tvminiseries': 'show', 'tvepisode': 'episode', 'tvseason': 'season', 'tvmovie': 'movie', 'tvspecial': 'movie', 'tv_season': 'season', 'tv season': 'season', 'tv_series': 'show', 'tv series': 'show', 'tv_miniseries': 'show', 'tv mini series': 'show', 'tv_episode': 'episode', 'tv episode': 'episode', 'tv_movie': 'movie', 'tv movie': 'movie', 'short': 'movie', 'tv_special': 'movie', 'tv special': 'movie'}.get(raw_kind, raw_kind)
    if kind not in ('movie', 'show', 'season', 'episode'):
        raise ValueError('Type must be movie, show, season, or episode.')
    title = str(row.get('title') or row.get('name') or row.get('original_title') or '').strip()
    if not title:
        raise ValueError('Every item needs a title (or Name column).')
    out = {'id': secrets.token_hex(8), 'type': kind, 'title': title}
    if row.get('const'):
        row['imdb'] = row['const']
    if not row.get('imdb') and 'imdb.com/title/tt' in str(row.get('url', '')):
        row['imdb'] = str(row['url']).split('/title/')[1].split('/')[0]
    for field in ('year', 'season', 'episode', 'tmdb', 'tvdb', 'imdb', 'show_tmdb', 'show_tvdb', 'show_imdb', 'show_title', 'source_key', 'source_url', 'metadata_note'):
        value = row.get(field)
        if value not in (None, ''):
            out[field] = str(value).strip()
    if row.get('metadata_unresolved'):
        out['metadata_unresolved'] = True
    if kind in ('season', 'episode') and 'season' not in out and not out.get('metadata_unresolved'):
        raise ValueError('Season and episode entries need a season number.')
    if kind == 'episode' and 'episode' not in out and not out.get('metadata_unresolved'):
        raise ValueError('Episode entries need an episode number.')
    for field in ('season', 'episode', 'year', 'tmdb', 'tvdb', 'show_tmdb', 'show_tvdb'):
        if field in out and (not out[field].isdigit() or int(out[field]) < 0):
            raise ValueError(f'{field} must be a nonnegative integer.')
    return out


def import_items(content, format, settings=None, progress=lambda *args: None):
    if format == 'json':
        rows = json.loads(content)
        if isinstance(rows, dict):
            rows = rows.get('items')
        if not isinstance(rows, list):
            raise ValueError('JSON must contain an array or an object with an items array.')
    else:
        rows = list(csv.DictReader(io.StringIO(content.lstrip('\ufeff'))))
    if not rows:
        raise ValueError('The file contains no items.')
    if len(rows) > 20000:
        raise ValueError('Import at most 20,000 entries at a time.')
    if rows and all(str(r.get('Position') or r.get('position') or '').isdigit() for r in rows):
        rows.sort(key=lambda r: int(r.get('Position') or r.get('position')))
    result, occurrences = [], {}
    for number, row in enumerate(rows, 1):
        progress(f'Resolving file entries: {number}/{len(rows)}…')
        if settings is not None:
            row = {str(k).lower().strip().replace(' ', '_'): v for k, v in row.items() if k}
            if row.get('title_type', '').lower() in ('tv episode', 'tv_episode', 'tvepisode'):
                row.update(type='episode', imdb=row.get('const') or row.get('imdb'), metadata_unresolved=not (row.get('season') and row.get('episode')))
            if row.get('const'):
                row['imdb'] = row['const']
                kind = row.get('title_type', '').lower().replace('_', '').replace(' ', '')
                row.setdefault('type', {'tvseries': 'show', 'tvminiseries': 'show', 'tvepisode': 'episode', 'tvseason': 'season'}.get(kind, 'movie'))
                if row['type'] == 'season' and not row.get('season'):
                    row['metadata_unresolved'] = True
                occurrences[row['const']] = occurrences.get(row['const'], 0) + 1
                row.setdefault('source_key', f"imdb:{row['const']}:{occurrences[row['const']]}")
            try:
                row = providers.enrich(row, settings) if row.get('type') else row
            except ValueError as exc:
                row['metadata_note'] = str(exc)
                if row.get('type') in ('episode', 'season'):
                    row['metadata_unresolved'] = True
        result.append(normalize(row))
    return result


def has_4k(node):
    for media in node.findall('Media'):
        resolution=media.get('videoResolution','').lower()
        if resolution in ('4k','8k','2160','4320'):return True
        try:
            if int(media.get('width','0'))>=3800:return True
        except ValueError:pass
    return False


def plex_catalog(settings):
    cfg = settings.get('plex', {})
    call = lambda path: remote(cfg.get('url', ''), path, cfg.get('key', ''), plex=True)
    sections = call('/library/sections')
    catalog = []
    for section in sections.findall('Directory'):
        kind = section.get('type')
        if kind not in ('movie', 'show'):
            continue
        start = 0
        while True:
            page = call(f'/library/sections/{section.get("key")}/all?includeGuids=1&X-Plex-Container-Start={start}&X-Plex-Container-Size=500')
            nodes = list(page)
            for node in nodes:
                ids = {}
                for guid in node.findall('Guid'):
                    provider, _, ident = guid.get('id', '').partition('://')
                    ids[provider] = ident
                if settings.get('_requested_tier')=='4k' and kind=='movie' and not has_4k(node):continue
                catalog.append({'key': node.get('ratingKey'), 'server_id':sections.get('machineIdentifier') or settings.get('plex',{}).get('server_id'), 'type': kind, 'title': node.get('title'), 'year': node.get('year'), 'ids': ids, 'library': section.get('title'), 'view_count':int(node.get('viewCount','0')),'watched': int(node.get('viewCount', '0')) > 0 or (kind == 'show' and int(node.get('viewedLeafCount') or 0) > 0), 'view_offset': int(node.get('viewOffset', '0')), 'genres': [g.get('tag') for g in node.findall('Genre') if g.get('tag')], 'directors':[g.get('tag') for g in node.findall('Director') if g.get('tag')], 'last_viewed_at': int(node.get('lastViewedAt', '0')), 'added_at': int(node.get('addedAt', '0')), 'user_rating': float(node.get('userRating') or 0), 'runtime':int(node.get('duration'))/60000 if node.get('duration') else None, 'fully_watched':int(node.get('leafCount') or 0)>0 and int(node.get('viewedLeafCount') or 0)>=int(node.get('leafCount') or 0)})
            start += len(nodes)
            if not nodes or start >= int(page.get('totalSize', start)):
                break
    return catalog


def match_item(item, catalog):
    is_tv = item['type'] != 'movie'
    prefix = 'show_' if item['type'] in ('season', 'episode') else ''
    ids = {p: item[prefix+p] for p in ('tmdb', 'tvdb', 'imdb') if item.get(prefix+p)}
    candidates = [m for m in catalog if m['type'] == ('show' if is_tv else 'movie')]
    if ids:
        matches = [m for m in candidates if any(m['ids'].get(p) == v for p, v in ids.items()) and not any(p in m['ids'] and m['ids'][p] != v for p, v in ids.items())]
        if matches:
            return matches, 'provider ID'
        title = item.get('show_title', item['title']) if prefix else item['title']
        legacy = [m for m in candidates if not m['ids'] and m.get('title', '').casefold() == title.casefold()]
        if legacy:
            return legacy, 'title/year candidate'
        return [], 'provider ID'
    title = item.get('show_title', item['title']) if prefix else item['title']
    matches = [m for m in candidates if m['title'].casefold() == title.casefold() and (prefix or not item.get('year') or m.get('year') == item['year'])]
    return matches, 'title/year candidate'


def compare(items, settings):
    catalog = plex_catalog(settings)
    cfg = settings['plex']
    episodes = {}
    metadata = {}
    results = []
    for item in items:
        item = dict(item)
        for field in ('plex_key', 'plex_keys', 'detail', 'status'):
            item.pop(field, None)
        if item.get('metadata_unresolved'):
            results.append(dict(item, status='unmatched', detail='Exact TV scope needed: confirm parent-show IDs and season/episode numbers using Correct match. ' + item.get('metadata_note', '')))
            continue
        if item.get('plex_override') and item.get('plex_server') == cfg['url']:
            matches = [m for m in catalog if m['key'] == item['plex_override'] and m['type'] == ('movie' if item['type'] == 'movie' else 'show')]
            basis = 'confirmed manually'
        else:
            matches, basis = match_item(item, catalog)
        result = dict(item, status='unmatched', detail='No confirmed match', match_basis=basis)
        if len(matches) > 1:
            result['detail'] = 'Multiple Plex matches; review required'
        elif len(matches) == 1:
            match = matches[0]
            result.update(plex_key=match['key'], detail=match['library'])
            if basis not in ('provider ID', 'confirmed manually'):
                result.update(status='review', detail='Title/year match; add provider IDs to confirm')
            elif item['type'] == 'movie':
                result['status'] = 'available'
                result['plex_keys'] = [match['key']]
            else:
                if match['key'] not in episodes:
                    episodes[match['key']] = plex_leaves(settings, match['key'])
                present = episodes[match['key']]
                scope = [n for n in present if (item['type'] == 'show' and int(n['season']) > 0) or (item['type'] != 'show' and n['season'] == str(int(item['season'])))]
                if item['type'] == 'episode':
                    scope = [n for n in scope if n['episode'] == str(int(item['episode']))]
                result['plex_keys'] = [n['key'] for n in scope]
                if item['type'] == 'episode':
                    result['status'] = 'available' if scope else 'missing'
                    if scope:
                        result['plex_key'] = scope[0]['key']
                else:
                    available = {(n['season'], n['episode']) for n in scope}
                    expected, source = expected_episodes(item, match, settings, metadata)
                    if expected is not None:
                        missing = expected - available
                        result.update(status='available' if expected and not missing else 'partial' if available else 'missing', detail=f'{len(expected & available)}/{len(expected)} aired episodes in Plex · {source}', missing_episodes=len(missing))
                        if not expected:
                            result.update(status='upcoming', detail='No aired episodes in this scope yet')
                    else:
                        result.update(status='partial' if available else 'missing', detail=f'{len(available)} episodes in Plex; connect Sonarr or TMDB to verify completeness')
        elif ids_present(item):
            result.update(status='missing', detail='Not found in Plex')
        results.append(result)
    return results


def title_workspace_state(body, snapshot):
    """Read title ownership and existing intent without creating a list or request."""
    kind=body.get('type');identifier=str(body.get('tmdb',''))
    if kind not in ('movie','show','episode') or not identifier.isdigit() or int(identifier)<=0:
        raise ValueError('Choose a valid title.')
    raw={'type':kind,'title':str(body.get('title') or 'Title')[:200]}
    if kind=='episode':
        season=str(body.get('season',''));episode=str(body.get('episode',''))
        if not season.isdigit() or not episode.isdigit() or int(episode)<1:raise ValueError('Choose a valid episode scope.')
        raw.update(show_tmdb=identifier,season=season,episode=episode)
    else:raw['tmdb']=identifier
    item=normalize(raw);settings=snapshot['settings'];cfg=settings.get('plex',{});ownership='unchecked';label='Connect Plex to check your library';plex_url=None
    if cfg.get('key'):
        catalog,_=explore.library(settings,plex_catalog)
        matches,basis=match_item(item,catalog)
        if len(matches)>1 or matches and basis!='provider ID':ownership='review';label='Library match needs review'
        elif matches:
            server_id=matches[0].get('server_id') or cfg.get('server_id');plex_key=matches[0]['key']
            if kind=='movie':ownership='available';label='In your Plex library'
            elif kind=='show':ownership='partial';label='Show in Plex · see episode coverage below'
            else:
                present=plex_leaves(settings,matches[0]['key'])
                owned=any(str(row['season'])==str(int(item['season'])) and str(row['episode'])==str(int(item['episode'])) for row in present)
                ownership='available' if owned else 'missing';label='Episode in Plex' if owned else 'Episode missing from Plex'
                if owned:plex_key=next(row['key'] for row in present if str(row['season'])==str(int(item['season'])) and str(row['episode'])==str(int(item['episode'])))
            if ownership in ('available','partial') and server_id and re.fullmatch(r'[A-Za-z0-9_-]+',str(server_id)):
                plex_url='https://app.plex.tv/desktop/#!/server/'+str(server_id)+'/details?'+urllib.parse.urlencode({'key':'/library/metadata/'+str(plex_key)})
        else:ownership='missing';label='Not in your Plex library'
    path=('movie/' if kind=='movie' else 'tv/')+identifier
    if kind=='episode':path+=f'/season/{int(item["season"])}/episode/{int(item["episode"])}'
    extras='videos,credits,external_ids'+(',aggregate_credits' if kind=='show' else '')
    metadata=providers.peek_tmdb(path+'?append_to_response='+extras) or providers.peek_tmdb(path)
    date=metadata.get('release_date') or metadata.get('first_air_date') or metadata.get('air_date') or ''
    upcoming=bool(date and date>datetime.datetime.now(datetime.timezone.utc).date().isoformat())
    keys=saved_lists.identity_keys(item)
    requests=[row for row in snapshot.get('requests',[]) if keys & saved_lists.identity_keys(row['item']) and row.get('status') not in ('declined','cancelled')]
    request=max(requests,key=lambda row:row.get('updated_at',row.get('created_at',0)),default=None)
    tracked=next((row for row in snapshot.get('release_watchlist',[]) if kind in ('movie','show') and row.get('type','movie')==kind and str(row.get('tmdb'))==identifier and row.get('region')==snapshot.get('release_region','CA')),None)
    return {'item':item,'ownership':ownership,'label':label,'plex_url':plex_url,'upcoming':upcoming,'tracked':bool(tracked),'request':{'id':request['id'],'status':request['status'],'message':request.get('message','')} if request else None,'can_request':ownership=='missing','region':snapshot.get('release_region','CA')}


def plex_leaves(settings, key):
    cfg, start, leaves = settings['plex'], 0, []
    while True:
        tree = remote(cfg['url'], f'/library/metadata/{key}/allLeaves?X-Plex-Container-Start={start}&X-Plex-Container-Size=500', cfg['key'], plex=True)
        nodes = tree.findall('Video')
        for n in nodes:
            if settings.get('_requested_tier')=='4k' and not has_4k(n):continue
            if n.findall('Media') and n.get('parentIndex') is not None and n.get('index') is not None:
                leaves.append({'key': n.get('ratingKey'), 'season': str(int(n.get('parentIndex'))), 'episode': str(int(n.get('index'))), 'watched': int(n.get('viewCount', '0')) > 0, 'view_offset': int(n.get('viewOffset', '0')), 'title': n.get('title', ''), 'runtime':int(n.get('duration'))/60000 if n.get('duration') else None})
        start += len(nodes)
        if not nodes or start >= int(tree.get('totalSize', start)):
            break
    return sorted(leaves, key=lambda n: (int(n['season']), int(n['episode'])))


def expected_episodes(item, match, settings, cache):
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    tvdb = item.get('show_tvdb') or item.get('tvdb') or match['ids'].get('tvdb')
    try:
        if settings.get('sonarr', {}).get('key') and tvdb:
            if 'sonarr_series' not in cache:
                cache['sonarr_series'] = arr_call(settings, 'sonarr', 'series')
            series = next((s for s in cache['sonarr_series'] if str(s.get('tvdbId')) == str(tvdb)), None)
            if series:
                key = ('sonarr', series['id'])
                if key not in cache:
                    cache[key] = arr_call(settings, 'sonarr', f'episode?seriesId={series["id"]}')
                rows = cache[key]
                if rows:
                    scoped = [e for e in rows if (item['type'] == 'show' and e['seasonNumber'] > 0) or (item['type'] == 'season' and e['seasonNumber'] == int(item['season']))]
                    if scoped and all(e.get('airDate') or e.get('airDateUtc') for e in scoped):
                        return {(str(e['seasonNumber']), str(e['episodeNumber'])) for e in scoped if (e.get('airDate') or e['airDateUtc'])[:10] <= today}, 'Sonarr aired metadata'
    except ValueError:
        pass
    tmdb_id = item.get('show_tmdb') or item.get('tmdb') or match['ids'].get('tmdb')
    if tmdb_id and settings.get('tmdb', {}).get('key'):
        try:
            key = ('tmdb-show', tmdb_id)
            if key not in cache:
                cache[key] = providers.tmdb(f'tv/{tmdb_id}', settings)
            seasons = [s['season_number'] for s in cache[key].get('seasons', []) if s['season_number'] > 0] if item['type'] == 'show' else [int(item['season'])]
            rows = []
            for season in seasons:
                key = ('tmdb-season', tmdb_id, season)
                if key not in cache:
                    cache[key] = providers.tmdb(f'tv/{tmdb_id}/season/{season}', settings)['episodes']
                rows.extend(cache[key])
            if rows and all(e.get('air_date') for e in rows):
                return {(str(e['season_number']), str(e['episode_number'])) for e in rows if e['air_date'] <= today}, 'TMDB aired metadata'
        except (ValueError, KeyError):
            pass
    return None, None


def playlist_preview(entry):
    keys, omitted, rows = [], 0, []
    for position, item in enumerate(entry['items'], 1):
        count = 0
        if item.get('status') in ('available', 'partial') and item.get('plex_keys'):
            keys.extend(item['plex_keys'])
            count = len(item['plex_keys'])
        else:
            omitted += 1
        rows.append({'position': position, 'title': item.get('title', 'Untitled'), 'type': item.get('type', 'movie'), 'status': item.get('status', 'unchecked'), 'count': count, 'detail': item.get('detail', '')})
    return {'keys': keys, 'count': len(keys), 'omitted': omitted, 'name': entry['name'], 'entries': rows,
            'fingerprint': hashlib.sha256(json.dumps({'keys':keys,'artwork':hashlib.sha256((entry.get('playlist_poster') or entry.get('poster') or '').encode()).hexdigest()}).encode()).hexdigest()}


def watch_progress(entry, settings):
    catalog = plex_catalog(settings)
    leaves, metadata, rows = {}, {}, []
    for position, item in enumerate(entry['items'], 1):
        result = {'id': item['id'], 'title': item['title'], 'position': position, 'owned': 0, 'watched': 0, 'total': None, 'complete': False, 'state': 'unknown'}
        if item.get('metadata_unresolved'):
            rows.append(result)
            continue
        matches, basis = match_item(item, catalog)
        if item.get('plex_override') and item.get('plex_server') == settings['plex']['url']:
            matches = [m for m in catalog if m['key'] == item['plex_override']]
            basis = 'confirmed manually'
        if not matches:
            result['state'] = 'missing' if ids_present(item) else 'unknown'
            rows.append(result)
            continue
        if basis not in ('provider ID', 'confirmed manually'):
            rows.append(result)
            continue
        if item['type'] == 'movie':
            watched = any(m.get('watched') for m in matches)
            result.update(owned=1, watched=int(watched), total=1, complete=watched, state='watched' if watched else 'in_progress' if any(m.get('view_offset') for m in matches) else 'unwatched')
        else:
            episodes = {}
            for match in matches:
                if match['key'] not in leaves:
                    leaves[match['key']] = plex_leaves(settings, match['key'])
                for episode in leaves[match['key']]:
                    coordinate = (episode['season'], episode['episode'])
                    if coordinate not in episodes or episode.get('watched'):
                        episodes[coordinate] = episode
            scope = [e for e in episodes.values() if (int(e['season']) > 0 if item['type'] == 'show' else e['season'] == str(int(item['season']))) and (item['type'] != 'episode' or e['episode'] == str(int(item['episode'])))]
            watched = sum(bool(e.get('watched')) for e in scope)
            if item['type'] == 'episode':
                total = 1
            else:
                expected, _ = expected_episodes(item, matches[0], settings, metadata)
                total = len(expected) if expected is not None else None
                if expected is not None:
                    scope = [e for e in scope if (e['season'], e['episode']) in expected]
                    watched = sum(bool(e.get('watched')) for e in scope)
            complete = bool(total) and watched >= total
            result.update(owned=len(scope), watched=watched, total=total, complete=complete,
                          state='watched' if complete else 'missing' if not scope else 'in_progress' if watched or any(e.get('view_offset') for e in scope) else 'unwatched')
        rows.append(result)
    return {'items': rows, 'checked_at': time.time(), 'server': settings['plex']['url'],
            'completed': sum(r['complete'] for r in rows), 'entries': len(rows),
            'next': next((r for r in rows if not r['complete']), None),
            'next_available': next((r for r in rows if r['owned'] > r['watched']), None),
            'note': 'Plex watched status for the connected account, in source order. Missing files may have watch history unavailable to this view; overlapping list entries count separately.'}


def release_calendar(state):
    result = trakt_features.calendar(state['settings'], state['lists'])
    if not result['items']:
        return result
    normalized = [normalize(row) for row in result['items']]
    releases = {row['id']: {key:source.get(key) for key in ('release_date','poster','show_title')} for row, source in zip(normalized, result['items'])}
    compared = compare(normalized, state['settings']) if state['settings'].get('plex', {}).get('key') else normalized
    managers = {}
    warnings = []
    for service, endpoint, key in [('radarr', 'movie', 'tmdbId'), ('sonarr', 'series', 'tvdbId')]:
        if state['settings'].get(service, {}).get('key'):
            try:
                managers[service] = {str(r.get(key)): r for r in arr_call(state['settings'], service, endpoint)}
            except ValueError:
                warnings.append(service + ' status is currently unavailable.')
    for row in compared:
        row.update(releases[row['id']])
        service = 'radarr' if row['type'] == 'movie' else 'sonarr'
        identifier = row.get('tmdb') if row['type'] == 'movie' else row.get('show_tvdb')
        managed = managers.get(service, {}).get(str(identifier))
        row['manager_status'] = ('Downloaded in Radarr' if managed and managed.get('hasFile') else 'Managed by ' + service.capitalize() if managed else 'Not managed' if service in managers else 'Not checked')
    result.update(items=compared, warnings=warnings)
    return result


def request_options(state, service, route='primary'):
    settings = manager_routes.routed(state,service,route)
    profiles = arr_call(settings, service, 'qualityprofile')
    roots = arr_call(settings, service, 'rootfolder')
    saved = state.get('request_defaults', {}).get(service if route=='primary' else service+':'+route, {})
    defaults = {}
    if saved.get('server') == settings.get(service, {}).get('url'):
        if str(saved.get('profile')) in {str(p['id']) for p in profiles}:
            defaults['profile'] = str(saved['profile'])
        if saved.get('root') in {r['path'] for r in roots}:
            defaults['root'] = saved['root']
    return {'profiles': profiles, 'roots': roots, 'defaults': defaults,'routes':manager_routes.choices(state,service),'route':route,'tier':manager_routes.config(state,service,route)['tier'],'approval_required':bool(state.get('request_policy',{}).get('require_approval'))}


def remember_request_options(state, service, profile, root, route='primary'):
    state.setdefault('request_defaults', {})[service if route=='primary' else service+':'+route] = {
        'server': manager_routes.config(state,service,route).get('url'),
        'profile': str(profile), 'root': root,
    }


def show_overview(item, settings):
    show = providers.parent_show(item, settings)
    details = providers.title_details(show, settings)
    show['title'] = details['title']
    catalog = plex_catalog(settings)
    matches, basis = match_item(show, catalog)
    if item.get('plex_override') and item.get('plex_server') == settings['plex']['url']:
        matches = [m for m in catalog if m['type'] == 'show' and m['key'] == item['plex_override']]
        basis = 'confirmed manually'
    known = basis in ('provider ID', 'confirmed manually')
    present = set()
    if known:
        for match in matches:
            present.update((n['season'], n['episode']) for n in plex_leaves(settings, match['key']))
    raw = providers.cached_tmdb('tv/' + show['tmdb'] + '?append_to_response=videos,credits,external_ids', settings)
    season_info = raw.get('seasons') or []
    def load_season(season):
        number = season['season_number']
        data = providers.cached_tmdb(f'tv/{show["tmdb"]}/season/{number}', settings)
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        episodes = []
        for episode in data.get('episodes', []):
            coordinate = (str(number), str(episode['episode_number']))
            aired = bool(episode.get('air_date') and episode['air_date'] <= today)
            status = 'unknown' if not known else 'available' if coordinate in present else 'missing' if aired else 'upcoming' if episode.get('air_date') else 'unknown'
            episodes.append({'season': number, 'episode': episode['episode_number'], 'title': episode.get('name', ''), 'air_date': episode.get('air_date'), 'status': status, 'aired': aired})
        # Plex can retain specials/episodes omitted from TMDB. Keep them visible.
        listed = {(str(number), str(e['episode'])) for e in episodes}
        for coordinate in sorted(present - listed, key=lambda c: (int(c[0]), int(c[1]))):
            if coordinate[0] == str(number):
                episodes.append({'season': number, 'episode': int(coordinate[1]), 'title': 'Plex episode (not in TMDB)', 'air_date': None, 'status': 'available', 'aired': False})
        return {'number': number, 'name': season.get('name') or f'Season {number}', 'episodes': sorted(episodes, key=lambda e:e['episode']), 'available': sum(e['status']=='available' for e in episodes), 'aired': sum(e['aired'] for e in episodes), 'missing': sum(e['status']=='missing' for e in episodes)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        seasons = list(pool.map(load_season, season_info))
    return {'show': show, 'details': details, 'coverage_known': known, 'libraries': sorted({m['library'] for m in matches}) if known else [], 'seasons': seasons, 'missing': sum(s['missing'] for s in seasons if s['number']>0), 'available': len([c for c in present if int(c[0])>0])}


def request_show_scope(item, settings, body):
    if item['type'] == 'movie':
        raise ValueError('Choose a television entry first.')
    overview = show_overview(item, settings)
    if not overview['coverage_known']:
        raise ValueError('Confirm the parent-show Plex match before requesting missing episodes.')
    scope = dict(overview['show'])
    if body.get('scope') == 'season':
        number = int(body['season'])
        if number not in [s['number'] for s in overview['seasons']]:
            raise ValueError('This season does not exist in the resolved show.')
        scope.update(type='season', season=str(number), show_tmdb=scope.get('tmdb'), show_tvdb=scope.get('tvdb'), show_imdb=scope.get('imdb'), show_title=scope['title'])
    elif body.get('scope') != 'show':
        raise ValueError('Choose a whole-show or season request.')
    allowed = {(str(e['season']),str(e['episode'])) for s in overview['seasons'] if (s['number']>0 if scope['type']=='show' else str(s['number'])==scope['season']) for e in s['episodes'] if e['status']=='missing'}
    if not allowed:
        return {'message': 'All aired episodes in this scope are already in Plex.'}
    if body.get('defer'):return {'message':'Queued for owner approval','requested_item':scope}
    return {'message': request_item(scope, settings, body['profile'], body['root'], allowed_episodes=allowed),'requested_item':scope}


def create_playlist(entry, settings, title, replace=False):
    title = title.strip()
    if not title or len(title) > 200:
        raise ValueError('Enter a playlist title of 1–200 characters.')
    cfg = settings['plex']
    previous = entry.get('playlist') if replace else None
    if replace:
        if not previous or previous.get('server') != cfg['url'] or not str(previous.get('key', '')).isdigit():
            raise ValueError('There is no saved ReelCheck playlist on this server to replace. Create a new playlist instead.')
        old = remote(cfg['url'], '/playlists/' + previous['key'], cfg['key'], plex=True).find('Playlist')
        if old is None or old.get('title') != previous['title']:
            raise ValueError('The previous playlist was removed or renamed in Plex. Create a new playlist to preserve your changes.')
    # Recheck the catalog immediately before writing to Plex.
    entry['items'] = compare(entry['items'], settings)
    plan = playlist_preview(entry)
    if not plan['keys']:
        raise ValueError('No confirmed available items. Compare the list and resolve matches first.')
    identity = remote(cfg['url'], '/', cfg['key'], plex=True)
    machine = identity.get('machineIdentifier')
    if not machine:
        raise ValueError('Plex did not return its server identity.')
    prefix = f'server://{machine}/com.plexapp.plugins.library/library/metadata/'
    uri = prefix + ','.join(plan['keys'][:100])
    query = urllib.parse.urlencode({'type': 'video', 'title': title, 'smart': '0', 'uri': uri})
    tree = remote(cfg['url'], '/playlists?' + query, cfg['key'], method='POST', plex=True)
    created = tree.find('Playlist')
    if created is None:
        raise ValueError('Plex did not confirm playlist creation. Check Plex before retrying.')
    key = created.get('ratingKey')
    if not key or not key.isdigit():
        raise ValueError('Plex returned an invalid playlist identifier. Check Plex before retrying.')
    try:
        for start in range(100, len(plan['keys']), 100):
            query = urllib.parse.urlencode({'uri': prefix + ','.join(plan['keys'][start:start+100])})
            remote(cfg['url'], f'/playlists/{key}/items?' + query, cfg['key'], method='PUT', plex=True)
        actual, start = [], 0
        while True:
            tree = remote(cfg['url'], f'/playlists/{key}/items?X-Plex-Container-Start={start}&X-Plex-Container-Size=500', cfg['key'], plex=True)
            nodes = tree.findall('Video')
            actual.extend(n.get('ratingKey') for n in nodes)
            start += len(nodes)
            if not nodes or start >= int(tree.get('totalSize', start)):
                break
        if actual != plan['keys']:
            raise ValueError('Plex did not preserve the requested item order.')
    except ValueError as exc:
        raise ValueError(f'A new playlist “{title}” was created, but could not be fully verified: {exc} Any previous playlist was preserved. Check Plex before retrying.') from None
    warning = ''
    if entry.get('playlist_poster') or entry.get('poster'):
        try:
            upload_playlist_poster(key,entry.get('playlist_poster') or entry['poster'],cfg)
        except (ValueError,ET.ParseError):
            warning = 'Playlist saved, but Plex did not confirm its poster. Your list image is retained; recreate the playlist to retry.'
    if previous:
        try:
            remote(cfg['url'], '/playlists/' + previous['key'], cfg['key'], method='DELETE', plex=True)
        except ValueError:
            warning = 'The new playlist was verified, but the previous playlist could not be removed. Both have been retained.'
    return {'title': title, 'count': plan['count'], 'omitted': plan['omitted'], 'key': key, 'warning': warning, 'fingerprint': plan['fingerprint'], 'updated_at': time.time()}


def upload_playlist_poster(key,poster,cfg):
    import base64
    validated=saved_lists.poster(poster)
    if not str(key).isdigit():raise ValueError('Invalid playlist key.')
    path='/library/metadata/'+str(key)+'/posters'
    before=remote(cfg['url'],path,cfg['key'],plex=True)
    old={r.get('ratingKey') for r in before}
    remote(cfg['url'],path,cfg['key'],payload=base64.b64decode(validated.split(',',1)[1]),method='POST',plex=True)
    after=remote(cfg['url'],path,cfg['key'],plex=True)
    added=[r for r in after if r.get('ratingKey') and r.get('ratingKey') not in old]
    if len(added)!=1:raise ValueError('Plex did not confirm an uploaded poster.')
    if added[0].get('selected')!='1':
        try:
            remote(cfg['url'],path[:-1]+'?'+urllib.parse.urlencode({'url':added[0].get('ratingKey')}),cfg['key'],method='PUT',plex=True)
        except ET.ParseError:pass
    verified=remote(cfg['url'],path,cfg['key'],plex=True)
    if not any(r.get('ratingKey')==added[0].get('ratingKey') and r.get('selected')=='1' for r in verified):
        raise ValueError('Plex did not confirm poster selection.')


def ids_present(item):
    prefix = 'show_' if item['type'] in ('season', 'episode') else ''
    return any(item.get(prefix+p) for p in ('tmdb', 'tvdb', 'imdb'))


def arr_call(settings, service, path, payload=None, method=None):
    cfg = settings.get(service, {})
    return remote(cfg.get('url', ''), '/api/v3/' + path, cfg.get('key', ''), payload, method)


def test_connection(settings, body):
    """Test the current form values without saving them or returning credentials."""
    service = body.get('service')
    if service not in ('plex', 'radarr', 'sonarr', 'tmdb', 'trakt', 'tvdb', 'mdblist', 'prowlarr'):
        raise ValueError('Unknown service')
    candidate = dict(settings)
    saved = settings.get(service, {})
    if service != 'plex' and 'config' in body:
        draft = body['config']
        if not isinstance(draft, dict):
            raise ValueError('Invalid connection settings.')
        candidate[service] = {
            'url': str(draft.get('url', saved.get('url', ''))).strip().rstrip('/'),
            'key': str(draft.get('key') or saved.get('key', '')).strip(),
            'pin': str(draft.get('pin') or saved.get('pin', '')).strip(),
        }
    cfg = candidate.get(service, {})
    if service=='prowlarr':
        if not cfg.get('url') or not cfg.get('key'):raise ValueError('Enter the Prowlarr URL and API key.')
        remote(cfg['url'],'/api/v1/system/status',cfg['key'],timeout=15)
    elif service in ('radarr', 'sonarr'):
        if not cfg.get('url'):
            raise ValueError(f'Enter the {service.capitalize()} server address before testing.')
        if not cfg.get('key'):
            raise ValueError(f'Enter the {service.capitalize()} API key before testing. Find it under Settings → General in {service.capitalize()}.')
        arr_call(candidate, service, 'system/status')
    elif service == 'plex':
        remote(cfg.get('url', ''), '/library/sections', cfg.get('key', ''), plex=True)
    elif service == 'trakt':
        providers.trakt_get('/users/rayrayelite/lists/marvel-universe-timeline-copy', candidate)
    elif service == 'mdblist':
        ratings.request('user',candidate)
    elif service == 'tvdb':
        metadata_sources.tvdb_call('/series/263365/extended', candidate)
    else:
        providers.tmdb('configuration', candidate)
    return {'ok': True}


def request_item(item, settings, profile, root, allowed_episodes=None):
    if item['type'] != 'movie' and not (item.get('show_tvdb') if item['type'] in ('episode', 'season') else item.get('tvdb')):
        item = providers.enrich(item, settings)
    service = 'radarr' if item['type'] == 'movie' else 'sonarr'
    call = lambda path, payload=None, method=None: arr_call(settings, service, path, payload, method)
    # Validate destinations against the live server, rather than trusting form values.
    if int(profile) not in [p['id'] for p in call('qualityprofile')] or root not in [r['path'] for r in call('rootfolder')]:
        raise ValueError('Choose a valid quality profile and root folder.')
    if settings.get(service,{}).get('key'):
        progress=activity.summarize([dict(item,id='request-check')],settings,arr_call,True)['items'].get('request-check',{})
        if progress.get('prevent_duplicate'):
            return progress['label']+'; no duplicate search submitted'
    if service == 'radarr':
        item = dict(item)
        if not item.get('tmdb') and item.get('imdb'):
            matches = call('movie/lookup?term=' + urllib.parse.quote('imdb:' + item['imdb']))
            matches = [m for m in matches if m.get('imdbId') == item['imdb']]
            if len(matches) == 1:
                item['tmdb'] = str(matches[0]['tmdbId'])
        if not item.get('tmdb'):
            raise ValueError('Radarr requests require a TMDB movie ID.')
        existing = next((m for m in call('movie') if str(m.get('tmdbId')) == item['tmdb']), None)
        if existing:
            if existing.get('hasFile'):
                return 'Already has a file in Radarr'
            call('command', {'name': 'MoviesSearch', 'movieIds': [existing['id']]})
            return 'Search submitted for existing movie'
        found = call('movie/lookup/tmdb?tmdbId=' + item['tmdb'])
        found.update(qualityProfileId=int(profile), rootFolderPath=root, monitored=True, addOptions={'searchForMovie': True})
        call('movie', found)
        return 'Movie added and search submitted'
    tvdb = item.get('show_tvdb') if item['type'] in ('episode', 'season') else item.get('tvdb')
    if not tvdb:
        raise ValueError('Sonarr requests require the parent show TVDB ID (show_tvdb for seasons/episodes).')
    series = next((s for s in call('series') if str(s.get('tvdbId')) == tvdb), None)
    if not series:
        found = call('series/lookup?term=tvdb:' + tvdb)
        if len(found) != 1:
            raise ValueError('Sonarr could not uniquely resolve this TVDB ID.')
        series = found[0]
        for season in series.get('seasons', []):
            season['monitored'] = False
        series.update(qualityProfileId=int(profile), rootFolderPath=root, monitored=True, seasonFolder=True, addOptions={'monitor': 'none', 'searchForMissingEpisodes': False})
        series = call('series', series)
    episodes = call(f'episode?seriesId={series["id"]}')
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    targets = [e for e in episodes if not e.get('hasFile') and (allowed_episodes is None or (str(e['seasonNumber']), str(e['episodeNumber'])) in allowed_episodes) and (not e.get('airDateUtc') or e['airDateUtc'][:10] <= today) and (item['type'] == 'show' or e['seasonNumber'] == int(item['season'])) and (item['type'] != 'episode' or e['episodeNumber'] == int(item['episode'])) and (item['type'] != 'show' or e['seasonNumber'] > 0)]
    if not episodes:
        raise ValueError('Series added, but Sonarr has not populated episodes yet. Retry this item shortly.')
    if not targets:
        return 'No missing episodes in the selected scope'
    if settings.get(service,{}).get('key'):
        queued=activity.queue(settings,service,arr_call,True)
        queued_ids={q.get('episodeId') for q in queued if q.get('seriesId')==series['id']}
        targets=[e for e in targets if e['id'] not in queued_ids]
        if not targets:
            return 'Selected missing episodes are already downloading; no duplicate search submitted'
    episode_ids = [e['id'] for e in targets]
    call('episode/monitor', {'episodeIds': episode_ids, 'monitored': True}, 'PUT')
    call('command', {'name': 'EpisodeSearch', 'episodeIds': episode_ids})
    return f'Search submitted for {len(targets)} missing episodes'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Avoid logging credentials or imported content.

    def respond(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get('Host') not in ('127.0.0.1:8765', 'localhost:8765'):
            return self.respond({'error': 'Invalid host'}, 403)
        if self.path == '/api/state':
            state = read_state()
            return self.respond(public_state(state))
        if self.path.startswith('/api/job?'):
            job_id = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('id', [''])[0]
            with JOBS_LOCK:
                job = dict(JOBS.get(job_id, {}))
            return self.respond(job if job else {'error': 'Import job not found. It may have expired or the app restarted.'}, 200 if job else 404)
        if self.path.startswith('/poster-overlays/'):
            path = poster_overlays.asset_path(urllib.parse.unquote(self.path))
            if path is None:
                return self.respond({'error':'Not found'},404)
            self.send_response(200)
            self.send_header('Content-Type','image/png')
            self.send_header('Cache-Control','public, max-age=86400')
            self.end_headers()
            self.wfile.write(path.read_bytes())
            return
        path = {'/': 'index.html', '/app.js': 'app.js', '/trakt.js': 'trakt.js', '/enrichment.js': 'enrichment.js', '/explore.js': 'explore.js', '/style.css': 'style.css', '/workspace.css': 'workspace.css', '/workspace.js': 'workspace.js', '/audit-workflows.js': 'audit-workflows.js', '/discovery-updates.js': 'discovery-updates.js', '/navigation.js': 'navigation.js', '/lists.js':'lists.js', '/requests.js':'requests.js', '/workflow.js':'workflow.js', '/builder.js':'builder.js', '/collection-tools.js':'collection-tools.js', '/taste.js':'taste.js', '/workbench.js':'workbench.js'}.get(self.path)
        if not path:
            return self.respond({'error': 'Not found'}, 404)
        raw = (ROOT / 'web' / path).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html', 'js':'text/javascript', 'css':'text/css'}[path.split('.')[-1]] + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data: https://image.tmdb.org; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.headers.get('Host') not in ('127.0.0.1:8765', 'localhost:8765') or self.headers.get('X-ReelCheck-Token') != SESSION:
            return self.respond({'error': 'Reload the app and try again.'}, 403)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > (31_000_000 if self.path=='/api/explore/official/feed-preview' else 8_000_000):
                raise ValueError('Request too large.')
            body = json.loads(self.rfile.read(length))
            if self.path.startswith('/api/backup/'):
                action=self.path.rsplit('/',1)[-1]
                with LOCK:snapshot=read_state()
                folder=DATA/'backups'
                if action=='export':return self.respond(backups.export(snapshot))
                if action=='list':return self.respond({'files':[p.name for p in sorted(folder.glob('*.json'),reverse=True)] if folder.exists() else []})
                if action not in ('preview','restore'):raise ValueError('Unknown backup action.')
                document=body.get('document')
                if body.get('file'):
                    name=body['file']
                    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.json',name):raise ValueError('Invalid backup file.')
                    path=folder/name
                    if not path.is_file():raise ValueError('That rolling backup is no longer available.')
                    document=json.loads(path.read_text('utf-8'))
                data,summary=backups.validate(document,normalize)
                fingerprint=backups.digest(document)
                if action=='preview':return self.respond({'summary':summary,'fingerprint':fingerprint})
                if body.get('fingerprint')!=fingerprint:raise ValueError('Preview this exact backup before restoring it.')
                with LOCK:
                    current=read_state()
                    backups.rolling(folder,current)
                    restored=backups.restore(current,data,body.get('mode','merge'))
                    save_state(restored,backup=False)
                return self.respond(public_state(restored))
            if self.path=='/api/activity':
                with LOCK:snapshot=read_state()
                entry=next((r for r in snapshot['lists'] if r['id']==body.get('list_id')),None)
                if not entry:raise ValueError('Choose a saved list.')
                ids=body.get('ids',[])
                if not isinstance(ids,list) or len(ids)>100:raise ValueError('Check at most 100 entries at once.')
                rows=[r for r in entry['items'] if r['id'] in ids]
                output={'items':{},'warnings':[],'checked_at':time.time()};groups={}
                for row in rows:
                    saved=next((r for r in snapshot.get('requests',[]) if r['id']==row.get('request_log',{}).get('ledger_id')),None)
                    if saved and saved.get('status')=='awaiting_approval':
                        output['items'][row['id']]={'state':'awaiting_approval','label':'Queued for owner approval'};continue
                    service='radarr' if row['type']=='movie' else 'sonarr';route=saved.get('route','primary') if saved else 'primary'
                    groups.setdefault((service,route),[]).append(row)
                for (service,route),items in groups.items():
                    try:
                        result=activity.summarize(items,manager_routes.routed(snapshot,service,route),arr_call,bool(body.get('refresh')));output['items'].update(result['items']);output['warnings'].extend(result['warnings'])
                    except ValueError as exc:
                        for row in items:output['items'][row['id']]={'state':'unavailable','label':str(exc)}
                return self.respond(output)
            if self.path in ('/api/ratings','/api/ratings/preferences'):
                with LOCK:
                    snapshot=read_state()
                if self.path.endswith('/preferences'):
                    prefs=ratings.preferences(body)
                    with LOCK:
                        state=read_state()
                        state['rating_preferences']=prefs
                        save_state(state)
                    return self.respond(prefs)
                items=body.get('items',[])
                if not isinstance(items,list) or len(items)>20:
                    raise ValueError('Load ratings for at most 20 titles at once.')
                rows=[]
                for item in items:
                    try:
                        rows.append({'key':item.get('key'),**ratings.lookup(item,snapshot['settings'])})
                    except ValueError as exc:
                        rows.append({'key':item.get('key'),'ratings':[],'error':str(exc)})
                return self.respond({'items':rows})
            if self.path.startswith('/api/notifications/'):
                action=self.path.rsplit('/',1)[-1]
                with LOCK:snapshot=read_state()
                if action=='settings':return self.respond(discord_notify.public(snapshot))
                if action=='save':
                    with LOCK:
                        state=read_state();result=discord_notify.configure(state,body);save_state(state)
                    return self.respond(result)
                if action=='test':
                    if not body.get('confirmed'):raise ValueError('Confirm sending a Discord test notification.')
                    cfg=snapshot.get('discord_notifications',{})
                    if not cfg.get('url'):raise ValueError('Save a Discord webhook first.')
                    discord_notify.send(cfg['url'],'ReelCheck notification test. Your Discord connection is working.')
                    return self.respond({'ok':True})
                raise ValueError('Unknown notification action.')
            if self.path.startswith('/api/managers/'):
                action=self.path.rsplit('/',1)[-1]
                with LOCK:snapshot=read_state()
                if action=='list':return self.respond(manager_routes.public(snapshot))
                if action=='test':
                    draft=dict(snapshot);draft['manager_instances']=[dict(r) for r in snapshot.get('manager_instances',[])]
                    cfg=manager_routes.save(draft,body)
                    remote(cfg['url'],'/api/v3/system/status',cfg['key'],timeout=15)
                    return self.respond({'ok':True})
                if action=='save':
                    with LOCK:
                        state=read_state();manager_routes.save(state,body);save_state(state)
                    return self.respond(manager_routes.public(state))
                raise ValueError('Unknown manager action.')
            if self.path=='/api/requests/create':
                with LOCK:snapshot=read_state()
                raw=body.get('item',{})
                if not isinstance(raw,dict):raise ValueError('Choose an exact title.')
                kind=raw.get('type')
                if kind not in ('movie','show','season','episode'):raise ValueError('Choose movie, show, season or episode.')
                identifier=str(raw.get('show_tmdb') if kind in ('season','episode') else raw.get('tmdb',''))
                if not identifier.isdigit() or int(identifier)<1:raise ValueError('Choose an exact TMDB title.')
                item=normalize({**{k:v for k,v in raw.items() if k in ('type','tmdb','show_tmdb','season','episode')},'title':'Title'})
                details=providers.list_details(item,snapshot['settings']);item['title']=details['title']
                if details.get('show_title'):item['show_title']=details['show_title']
                if details.get('release_date'):item['year']=details['release_date'][:4]
                service='radarr' if kind=='movie' else 'sonarr';route=body.get('route') or manager_routes.default(snapshot,service,body.get('tier','standard'))
                cfg=manager_routes.config(snapshot,service,route)
                if body.get('tier') and body['tier']!=cfg['tier']:raise ValueError('Choose a manager route matching the selected library tier.')
                mode=body.get('mode','search')
                if mode not in ('search','monitor') or mode=='monitor' and kind not in ('movie','show'):raise ValueError('Only whole movies/shows support future monitoring.')
                with LOCK:
                    state=read_state();queued=bool(body.get('queue') or state.get('request_policy',{}).get('require_approval'))
                    existing=next((r for r in state.get('requests',[]) if r['id']==request_ledger.routed_fingerprint(item,mode,route)),None)
                    if existing and existing.get('status') in ('cancelled','declined'):existing['status']='pending'
                    request=request_ledger.record(state,item,mode,'awaiting_approval' if queued else 'pending','Queued for owner approval' if queued else 'Awaiting confirmation',route=route,tier=cfg['tier'])
                    save_state(state)
                return self.respond({**request_ledger.public(state),'request_id':request['id']})
            if self.path.startswith('/api/requests/'):
                action=self.path.rsplit('/',1)[-1]
                with LOCK:
                    state=read_state();request_ledger.migrate(state)
                    if action=='list':
                        save_state(state);return self.respond(request_ledger.public(state))
                    if action=='policy':
                        return self.respond(state.get('request_policy',{'require_approval':False}))
                    if action=='policy-save':
                        state['request_policy']={'require_approval':bool(body.get('require_approval'))};save_state(state)
                        return self.respond(state['request_policy'])
                    if action in ('decline','cancel'):
                        request=next((r for r in state.get('requests',[]) if r['id']==body.get('id')),None)
                        if not request or request.get('status') not in ('pending','awaiting_approval'):raise ValueError('Only drafts and queued requests can be declined or cancelled; manager activity is unchanged.')
                        if body.get('expected_updated')!=request.get('updated_at'):raise ValueError('This request changed. Refresh before deciding.')
                        message=str(body.get('reason') or ('Declined by owner' if action=='decline' else 'Draft cancelled'))[:500]
                        request_ledger.record(state,request['item'],request.get('mode','search'),'declined' if action=='decline' else 'cancelled',message,route=request.get('route','primary'),tier=request.get('tier','standard'))
                        save_state(state);return self.respond(request_ledger.public(state))
                    if action=='pending':
                        entry=next((r for r in state['lists'] if r['id']==body.get('list_id')),None)
                        if not entry:raise ValueError('Choose a saved list.')
                        ids=body.get('ids',[])
                        if not isinstance(ids,list) or len(ids)>100:raise ValueError('Review at most 100 requests at once.')
                        for item in entry['items']:
                            if item['id'] in ids and item.get('status') in ('missing','partial'):request_ledger.record(state,item,list_id=entry['id'])
                        save_state(state);return self.respond(request_ledger.public(state))
                    if action=='acknowledge':
                        for notice in state.get('request_notifications',[]):
                            if not body.get('id') or notice['id']==body.get('id'):notice['read']=True
                        save_state(state);return self.respond(request_ledger.public(state))
                    snapshot=state
                if action=='refresh':return self.respond(refresh_request_state(bool(body.get('force'))))
                if action=='retry':
                    if not body.get('confirmed'):raise ValueError('Review and confirm this retry first.')
                    with LOCK:
                        state=read_state();request_ledger.migrate(state)
                        request=next((r for r in state.get('requests',[]) if r['id']==body.get('id')),None)
                        if not request:raise ValueError('Request not found.')
                        if request.get('status')=='awaiting_approval' and not body.get('approved'):raise ValueError('Approve this queued request before submitting it.')
                        if request.get('status') in ('declined','cancelled'):raise ValueError('This request was declined or cancelled. Create a new request to reopen it.')
                        route=request.get('route','primary');cfg=manager_routes.config(state,request['service'],route);settings=manager_routes.routed(state,request['service'],route)
                        option={'profile':body.get('profile'),'root':body.get('root')}
                        item=dict(request['item'])
                        if request.get('status')=='available':raise ValueError('This title is already available in Plex.')
                        try:
                            if settings.get('plex',{}).get('key'):
                                checked=compare([dict(item,id='retry')],settings)[0]
                                if checked.get('status')=='available':raise ValueError('This scope is already available in Plex. Refresh request status.')
                            message=release_watch.monitor(item,settings,option['profile'],option['root'],arr_call) if request.get('mode')=='monitor' else request_item(item,settings,option['profile'],option['root'])
                            request_ledger.record(state,item,request.get('mode','search'),'monitored' if request.get('mode')=='monitor' else 'requested',message,option,request.get('list_id'),route=route,tier=cfg['tier'])
                            remember_request_options(state,request['service'],option['profile'],option['root'],route)
                        except (ValueError,KeyError,TypeError) as exc:
                            request_ledger.record(state,item,request.get('mode','search'),'failed',str(exc),list_id=request.get('list_id'),route=route,tier=cfg['tier'])
                        save_state(state)
                    return self.respond(request_ledger.public(state))
                raise ValueError('Unknown request action.')
            if self.path=='/api/options':
                with LOCK:snapshot=read_state()
                return self.respond({service:request_options(snapshot,service,body.get('routes',{}).get(service) or manager_routes.default(snapshot,service,body.get('tier','standard'))) for service in body.get('services',[]) if service in ('sonarr','radarr')})
            if self.path.startswith('/api/lists/build/'):
                action=self.path.rsplit('/',1)[-1]
                if action=='extract':return self.respond(text_list_builder.fetch_page(body.get('url',''),body.get('default_show',''),all_sheets=body.get('sheet_scope','all')!='selected'))
                if action=='infer':return self.respond({'rows':text_list_builder.infer(body.get('text',''),body.get('default_show',''),body.get('numbering','season'),body.get('dragon_edition','dub'))})
                with LOCK:snapshot=read_state()
                if not snapshot['settings'].get('tmdb',{}).get('key'):raise ValueError('Connect TMDB before matching list entries.')
                if action=='match':return self.respond({'results':text_list_builder.match_batch(body.get('rows'),snapshot['settings'])})
                if action!='save':raise ValueError('Unknown text-list builder action.')
                target=next((row for row in snapshot['lists'] if row['id']==body.get('list_id')),None)
                if body.get('list_id'):
                    if not target:raise ValueError('This saved list was removed. Choose another list.')
                    if body.get('revision')!=saved_lists.revision(target):raise ValueError('This list changed. Reopen Add entries before saving.')
                name=str(body.get('name','')).strip()
                if not target and (not name or len(name)>200):raise ValueError('Enter a list name of up to 200 characters.')
                items=text_list_builder.confirmed_items(body.get('items'),snapshot['settings'],normalize)
                reference=str(body.get('reference',''))[:2000]
                parsed=urllib.parse.urlsplit(reference)
                with LOCK:
                    state=read_state()
                    if target:
                        latest=next((row for row in state['lists'] if row['id']==target['id']),None)
                        if not latest:raise ValueError('This saved list was removed while matching. It was not recreated.')
                        entry,report=saved_lists.update_entries(latest,items,body)
                        state['lists'][state['lists'].index(latest)]=entry
                    else:
                        entry={'id':secrets.token_hex(8),'name':name,'source':None,'items':items,'updated_at':time.time()}
                        report={'added':len(items),'removed':0,'skipped':0,'total':len(items),'mode':'new'}
                        state['lists'].append(entry)
                    if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password:
                        if target:entry['last_update_reference']=reference
                        else:entry['source_reference']=reference
                    save_state(state)
                return self.respond({'entry':entry,'update_report':report})
            if self.path=='/api/lists/delete':
                if body.get('confirmed') is not True:raise ValueError('Confirm deleting this saved list.')
                with LOCK:
                    state=read_state();entry=next((row for row in state['lists'] if row['id']==body.get('list_id')),None)
                    if not entry:raise ValueError('This saved list was already removed.')
                    if body.get('revision')!=saved_lists.revision(entry):raise ValueError('This list changed. Reopen Delete list to review its current version.')
                    state['lists'].remove(entry);save_state(state)
                return self.respond({'deleted_id':entry['id']})
            if self.path.startswith('/api/lists/share/'):
                action=self.path.rsplit('/',1)[-1]
                if action=='export':
                    with LOCK:snapshot=read_state()
                    entry=next((r for r in snapshot['lists'] if r['id']==body.get('list_id')),None)
                    if not entry:raise ValueError('Choose a saved list to share.')
                    return self.respond(list_sharing.export(entry,bool(body.get('include_poster',True))))
                if action not in ('preview','import'):raise ValueError('Unknown list-sharing action.')
                document=body.get('document');entry,summary=list_sharing.validate(document,normalize);fingerprint=list_sharing.digest(document)
                if action=='preview':return self.respond({'summary':summary,'fingerprint':fingerprint})
                if body.get('fingerprint')!=fingerprint:raise ValueError('Preview this exact shared list before importing it.')
                with LOCK:
                    state=read_state();state['lists'].append(entry);save_state(state)
                return self.respond({'entry':entry})
            if self.path in ('/api/lists/edit','/api/lists/search'):
                with LOCK:snapshot=read_state()
                if self.path.endswith('/search'):
                    kind=body.get('type','movie')
                    if kind not in ('movie','show'):raise ValueError('Search movies or TV shows.')
                    if body.get('tmdb_input'):
                        return self.respond({'items':[text_list_builder.lookup_tmdb(body['tmdb_input'],kind,snapshot['settings'])]})
                    query=str(body.get('query','')).strip()[:200]
                    if not query:raise ValueError('Enter a title to search.')
                    results=providers.cached_tmdb('search/'+('tv' if kind=='show' else 'movie')+'?'+urllib.parse.urlencode({'query':query,'include_adult':'false'}),snapshot['settings'])
                    return self.respond({'items':[{'type':kind,'tmdb':str(r['id']),'title':r.get('title') or r.get('name'),'year':(r.get('release_date') or r.get('first_air_date') or '')[:4],'poster':providers.image_url(r.get('poster_path')),'overview':r.get('overview') or '', 'original_language':r.get('original_language')} for r in results.get('results',[])[:20] if not r.get('adult')]})
                with LOCK:
                    state=read_state()
                    entry=next((r for r in state['lists'] if r['id']==body.get('list_id')),None)
                    if body.get('list_id') and not entry:raise ValueError('This list is no longer available.')
                    updated=saved_lists.edit(entry,body,normalize)
                    if entry:state['lists'][state['lists'].index(entry)]=updated
                    else:state['lists'].append(updated)
                    save_state(state)
                return self.respond({'entry':updated,'revision':saved_lists.revision(updated)})
            if self.path=='/api/lists/revision':
                with LOCK:state=read_state()
                entry=next((r for r in state['lists'] if r['id']==body.get('list_id')),None)
                if not entry:raise ValueError('Choose a saved list.')
                return self.respond({'revision':saved_lists.revision(entry),'entry':entry})
            if self.path=='/api/explore/route':
                with LOCK:snapshot=read_state()
                picks=body.get('items')
                if not isinstance(picks,list) or not 1<=len(picks)<=100:raise ValueError('Choose between 1 and 100 discoveries.')
                country=release_watch.region(body.get('region',snapshot.get('release_region','CA')))
                tracked=[];rows=[];seen=set();today=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                for pick in picks:
                    kind=pick.get('type');identifier=str(pick.get('tmdb',''))
                    if kind not in ('movie','show') or not identifier.isdigit() or int(identifier)<1:raise ValueError('Choose exact TMDB movies or shows.')
                    if (kind,identifier) in seen:continue
                    seen.add((kind,identifier))
                    metadata=providers.cached_tmdb(('tv/' if kind=='show' else 'movie/')+identifier,snapshot['settings'])
                    date=metadata.get('first_air_date' if kind=='show' else 'release_date') or ''
                    info=(release_watch.tv_availability if kind=='show' else release_watch.availability)(identifier,country,snapshot['settings'])
                    pending=(kind=='movie' and info['status']!='home' and (info['status']=='theatrical' or not date or date>today)) or (kind=='show' and (not date or date>today))
                    if pending:tracked.append(release_watch.tracked_item(kind,identifier,country,snapshot['settings']))
                    else:rows.append(normalize({'type':kind,'tmdb':identifier,'title':metadata.get('title') or metadata.get('name') or 'Title','year':date[:4]}))
                if rows and snapshot['settings'].get('plex',{}).get('key'):rows=compare(rows,snapshot['settings'])
                entry={'id':secrets.token_hex(8),'name':'Explore picks - '+today,'items':rows,'source':None,'updated_at':time.time()} if rows else None
                with LOCK:
                    state=read_state();watch=state.setdefault('release_watchlist',[]);known={r['id'] for r in watch}
                    watch.extend(r for r in tracked if r['id'] not in known)
                    if entry:state['lists'].append(entry)
                    save_state(state)
                return self.respond({'entry':entry,'tracked':len(tracked),'compared':len(rows),'items':state.get('release_watchlist',[])})
            if self.path.startswith('/api/releases/'):
                action=self.path.rsplit('/',1)[-1]
                with LOCK:
                    snapshot=read_state()
                country=release_watch.region(body.get('region',snapshot.get('release_region','CA')))
                if action=='check':
                    updates=release_watch.check(snapshot.get('release_watchlist',[]),snapshot['settings'])
                    with LOCK:
                        state=read_state()
                        for entry in state.get('release_watchlist',[]):
                            entry.update(updates.get(entry['id'],{}))
                        save_state(state)
                        return self.respond({'items':state.get('release_watchlist',[])})
                if action=='monitor':
                    item=next((r for r in snapshot.get('release_watchlist',[]) if r['id']==body.get('id')),None)
                    if not item:raise ValueError('This tracked title is no longer available.')
                    service='radarr' if item.get('type','movie')=='movie' else 'sonarr';route=body.get('route') or manager_routes.default(snapshot,service);cfg=manager_routes.config(snapshot,service,route);settings=manager_routes.routed(snapshot,service,route)
                    queued=bool(snapshot.get('request_policy',{}).get('require_approval'))
                    try:
                        message='Queued for owner approval' if queued else release_watch.monitor(item,settings,body.get('profile'),body.get('root'),arr_call)
                    except (ValueError,TypeError) as exc:
                        with LOCK:
                            failed=read_state();request_ledger.record(failed,item,mode='monitor',status='failed',message=str(exc),route=route,tier=cfg['tier']);save_state(failed)
                        raise ValueError(str(exc)) from None
                    service='radarr' if item.get('type','movie')=='movie' else 'sonarr'
                    with LOCK:
                        state=read_state()
                        for row in state.get('release_watchlist',[]):
                            if row['id']==item['id'] and not queued:row['manager_monitor']={'service':service,'message':message,'at':time.time(),'route':route,'tier':cfg['tier']}
                        request_ledger.record(state,item,mode='monitor',status='awaiting_approval' if queued else 'monitored',message=message,options={'profile':body['profile'],'root':body['root']},route=route,tier=cfg['tier'])
                        remember_request_options(state,service,body['profile'],body['root'],route)
                        save_state(state)
                    return self.respond({'items':state.get('release_watchlist',[]),'message':message})
                if action=='add':
                    identifier=str(body.get('tmdb',''))
                    if not identifier.isdigit():
                        raise ValueError('Choose an exact movie or TV show.')
                    kind=body.get('type','movie')
                    if kind not in ('movie','show'):
                        raise ValueError('Track a movie or TV show.')
                    item=release_watch.tracked_item(kind,identifier,country,snapshot['settings'])
                with LOCK:
                    state=read_state()
                    entries=state.setdefault('release_watchlist',[])
                    if action=='add':
                        if not any(r['id']==item['id'] for r in entries):
                            entries.append(item)
                    elif action=='remove':
                        state['release_watchlist']=[r for r in entries if r['id']!=body.get('id')]
                    elif action=='acknowledge':
                        for entry in entries:
                            if entry['id']==body.get('id'):
                                entry['acknowledged']=True
                    elif action=='region':
                        state['release_region']=country
                    else:
                        raise ValueError('Unknown release-watchlist action.')
                    save_state(state)
                    return self.respond({'items':state.get('release_watchlist',[]),'region':state.get('release_region','CA')})
            if self.path in ('/api/ignore/add','/api/ignore/remove'):
                item=body.get('item') or {}
                if self.path.endswith('/add') and not item.get('tmdb'):
                    with LOCK:
                        settings=read_state()['settings']
                    if settings.get('tmdb',{}).get('key'):
                        try:
                            item=providers.enrich(item,settings)
                        except ValueError:
                            pass
                with LOCK:
                    state = read_state()
                    if self.path.endswith('/add'):
                        ignored_titles.add(state,item)
                    else:
                        state['ignored_titles']=[r for r in state.get('ignored_titles',[]) if r['id'] != body.get('id')]
                    save_state(state)
                    return self.respond({'ignored_titles':state.get('ignored_titles',[])})
            if self.path == '/api/poster-info':
                with LOCK:
                    settings = read_state()['settings']
                return self.respond(poster_overlays.show_info(body.get('tmdb'), settings))
            if self.path.startswith('/api/explore/'):
                with LOCK:
                    snapshot = read_state()
                if self.path == '/api/explore/preferences':
                    languages=explore.language_preferences(body.get('languages',[]))
                    with LOCK:
                        state=read_state()
                        state['explore_languages']=languages
                        save_state(state)
                    return self.respond({'languages':languages})
                if self.path == '/api/explore/languages':
                    languages=providers.cached_tmdb('configuration/languages',snapshot['settings'])
                    return self.respond({'languages':sorted([{'code':r['iso_639_1'],'name':r.get('english_name') or r.get('name') or r['iso_639_1']} for r in languages if r.get('iso_639_1')],key=lambda r:r['name'])})
                if self.path == '/api/explore/official':
                    return self.respond(official_lists.catalogue())
                if self.path == '/api/explore/official/feed-check':
                    url=catalogue_feed.source_url(snapshot.get('official_feed_url',''))
                    if not url:return self.respond({'configured':False,'count':0})
                    result=catalogue_feed.check_manifest(official_lists.document(),catalogue_feed.download(catalogue_feed.manifest_url(url)))
                    with LOCK:
                        latest=read_state();latest['official_feed_available']={**result,'checked_at':time.time()};save_state(latest)
                    return self.respond(result)
                if self.path == '/api/explore/official/feed-manifest':return self.respond(catalogue_feed.manifest(official_lists.document()))
                if self.path in ('/api/explore/official/feed-source','/api/explore/official/feed-preview','/api/explore/official/feed-install','/api/explore/official/feed-export'):
                    if self.path.endswith('/feed-export'):return self.respond(official_lists.document())
                    if self.path.endswith('/feed-source'):
                        if 'url' in body:
                            url=catalogue_feed.source_url(body['url'])
                            with LOCK:
                                latest=read_state();latest['official_feed_url']=url;save_state(latest)
                        with LOCK:latest=read_state()
                        return self.respond({'url':latest.get('official_feed_url','')})
                    if self.path.endswith('/feed-preview'):
                        url=''
                        if 'document' in body:
                            raw=body['document']
                            if len(json.dumps(raw).encode())>catalogue_feed.MAX_BYTES:raise ValueError('Catalogue files must be smaller than 30 MB.')
                        else:
                            url=catalogue_feed.source_url(body.get('url') or snapshot.get('official_feed_url',''))
                            raw=catalogue_feed.download(url)
                        clean=catalogue_feed.validate(raw,normalize)
                        with LOCK:current=official_lists.document()
                        return self.respond(catalogue_feed.stage(current,clean,url))
                    if body.get('confirmed') is not True:raise ValueError('Preview and confirm the catalogue update before installing.')
                    with LOCK:
                        previous=official_lists.document();review=catalogue_feed.reviewed(body.get('token'),previous)
                        if not review['summary']['added'] and not review['summary']['updated']:raise ValueError('This source has no newer catalogue entries to install.')
                        official_lists.write_document(review['document'])
                        try:
                            latest=read_state();latest['official_feed_checked_at']=time.time();latest.pop('official_feed_available',None);save_state(latest)
                        except Exception:
                            official_lists.write_document(previous,backup=False);raise
                        with catalogue_feed.GUARD:catalogue_feed.PENDING.pop(body.get('token'),None)
                    return self.respond({'summary':review['summary'],'version':review['document']['version']})
                if self.path in ('/api/explore/official/updates','/api/explore/official/update-preview','/api/explore/official/update','/api/explore/official/rollback','/api/explore/official/skip','/api/explore/official/health'):
                    with LOCK:
                        latest=read_state()
                        if self.path.endswith('/updates'):
                            catalogue={row['id']:row for row in official_lists.document()['lists']}
                            copies=[row for row in latest['lists'] if row.get('official_id') in catalogue and not row.get('official_authoring')]
                            return self.respond({'lists':[collection_tools.preview(row,catalogue[row['official_id']]) for row in copies if catalogue[row['official_id']]['version']>row.get('official_version',0) and row.get('official_skip_version')!=catalogue[row['official_id']]['version']], 'recent':[collection_tools.preview(row,catalogue[row['official_id']]) for row in copies if row.get('official_undo') and catalogue[row['official_id']]['version']<=row.get('official_version',0)]})
                        entry=next((row for row in latest['lists'] if row['id']==body.get('list_id')),None)
                        if not entry:raise ValueError('Choose an existing saved list.')
                        if self.path.endswith('/health'):return self.respond(collection_tools.health(entry))
                        official=official_lists.get(entry.get('official_id'))
                        if self.path.endswith('/update-preview'):return self.respond(collection_tools.preview(entry,official))
                        if body.get('revision')!=saved_lists.revision(entry):raise ValueError('This list changed. Review it again before applying changes.')
                        if body.get('version')!=official['version']:raise ValueError('The official catalogue changed. Review the latest version.')
                        if self.path.endswith('/skip'):
                            entry['official_skip_version']=official['version'];save_state(latest)
                            return self.respond({'entry':entry})
                        if body.get('confirmed') is not True:raise ValueError('Review and confirm the collection changes.')
                        result=collection_tools.rollback(entry) if self.path.endswith('/rollback') else collection_tools.apply_update(entry,official,body.get('mode','merge'),normalize)
                        latest['lists'][latest['lists'].index(entry)]=result;save_state(latest)
                    return self.respond({'entry':result})
                if self.path == '/api/explore/official/publish':
                    if os.environ.get('REELCHECK_CURATOR_MODE')!='1':raise ValueError('Official authoring is disabled on this installation. Only publisher workspaces should enable curator mode.')
                    if body.get('confirmed') is not True:raise ValueError('Review and confirm publication to the local official catalogue.')
                    with LOCK:
                        latest=read_state()
                        entry=next((row for row in latest['lists'] if row['id']==body.get('list_id')),None)
                        if not entry:raise ValueError('This list no longer exists.')
                        if body.get('revision')!=saved_lists.revision(entry):raise ValueError('This list changed. Reopen publication and review it again.')
                        previous=official_lists.document()
                        updated,working,report=official_lists.prepare_publish(entry,previous,normalize)
                        official_lists.write_document(updated)
                        latest['lists'][latest['lists'].index(entry)]=working
                        try:save_state(latest)
                        except Exception:
                            official_lists.write_document(previous,backup=False)
                            raise
                    return self.respond({'entry':working,'report':report})
                if self.path == '/api/explore/official/open':
                    identifier=str(body.get('official_id',''))
                    official_lists.get(identifier)
                    with LOCK:
                        latest=read_state()
                        entry=next((row for row in latest['lists'] if row.get('official_id')==identifier),None)
                        if not entry:
                            entry=official_lists.instantiate(identifier,normalize)
                            latest['lists'].append(entry);save_state(latest)
                    return self.respond({'entry':entry})
                if self.path == '/api/explore/extra' or self.path=='/api/explore/home' and body.get('shelf') in ('cult','indexers','downloads_movies','downloads_tv'):
                    return self.respond(explore.extra_shelf(snapshot,body,plex_catalog,remote))
                if self.path == '/api/explore/home':
                    return self.respond(explore.home(snapshot, body, plex_catalog))
                if self.path == '/api/explore/lists':
                    return self.respond(explore.lists(snapshot, body))
                if self.path == '/api/explore/preview':
                    if body.get('official_id'):
                        body['collection_id']=official_lists.collection_id(body['official_id'])
                    if body.get('collection_id'):
                        imported = explore.collection(body['collection_id'], snapshot['settings'])
                    else:
                        imported = providers.import_url(str(body.get('url', '')), settings=snapshot['settings'])
                    rows = [normalize(row) for row in imported['items']]
                    compared = bool(snapshot['settings'].get('plex', {}).get('key'))
                    if compared:
                        rows = compare(rows, snapshot['settings'])
                    return self.respond({'name':imported['name'],'source':imported['source'],'items':rows,'compared':compared, **({'collection_id':imported['collection_id']} if imported.get('collection_id') else {})})
                if self.path == '/api/explore/save':
                    if body.get('official_id'):
                        body['collection_id']=official_lists.collection_id(body['official_id'])
                    if body.get('collection_id'):
                        imported = explore.collection(body['collection_id'], snapshot['settings'])
                        rows = [normalize(row) for row in imported['items']]
                        name = imported['name']
                    else:
                        picks = body.get('items')
                        if not isinstance(picks,list) or not 1 <= len(picks) <= 100:
                            raise ValueError('Choose between 1 and 100 discoveries to save.')
                        rows, seen = [], set()
                        for pick in picks:
                            kind, identifier = pick.get('type'), str(pick.get('tmdb',''))
                            if kind not in ('movie','show') or not identifier.isdigit() or int(identifier)<1:
                                raise ValueError('Choose exact TMDB movies or shows.')
                            if (kind,identifier) in seen:
                                continue
                            seen.add((kind,identifier))
                            row = normalize({'type':kind,'tmdb':identifier,'title':'Title'})
                            details = providers.list_details(row,snapshot['settings'])
                            row['title'] = details['title']
                            if details.get('release_date'):
                                row['year'] = details['release_date'][:4]
                            rows.append(row)
                        name = 'Explore picks · '+datetime.date.today().isoformat()
                    rows = compare(rows,snapshot['settings']) if snapshot['settings'].get('plex',{}).get('key') else rows
                    entry = {'id':secrets.token_hex(8),'name':name,'items':rows,'source':None,'warnings':[],'updated_at':time.time()}
                    with LOCK:
                        latest = read_state()
                        latest['lists'].append(entry)
                        save_state(latest)
                    return self.respond({'entry':entry})
                raise ValueError('Unknown Explore action.')
            if self.path.startswith('/api/companion/'):
                action=self.path.rsplit('/',1)[-1]
                with LOCK:snapshot=read_state()
                if action=='state':
                    for followed in snapshot.get('creator_follows',[]):
                        if not followed.get('profile_path'):
                            try:followed['profile_path']=providers.cached_tmdb('person/'+str(followed['id']),snapshot['settings']).get('profile_path')
                            except ValueError:pass
                    return self.respond({key:snapshot.get(key,default) for key,default in [('discovery_recipes',[]),('creator_follows',[]),('companion_preferences',{})]}|{'manager_routes':{service:[r for r in manager_routes.choices(snapshot,service) if r.get('configured') and r.get('enabled')] for service in ('radarr','sonarr')}})
                if action in ('recipe-save','recipe-delete','preferences','inbox-read','follow','unfollow','impressions','reset-insights','path-save'):
                    verified=None
                    if action=='follow':
                        identifier=str(body.get('person',''))
                        if not identifier.isdigit():raise ValueError('Choose a TMDB person.')
                        person=providers.cached_tmdb('person/'+identifier,snapshot['settings'])
                        role=body.get('role','all')
                        if role not in ('all','cast','crew'):raise ValueError('Choose cast, crew or all credits.')
                        verified={'id':identifier,'name':person['name'],'role':role,'profile_path':person.get('profile_path')}
                    with LOCK:
                        state=read_state()
                        if action=='recipe-save':
                            value=companion.recipe(body);value['id']=str(body.get('id') or secrets.token_hex(8));values=state.setdefault('discovery_recipes',[])
                            found=next((r for r in values if r['id']==value['id']),None)
                            if found:values[values.index(found)]=value
                            elif len(values)<50:values.append(value)
                            else:raise ValueError('Keep up to 50 saved recipes.')
                        if action=='recipe-delete':state['discovery_recipes']=[r for r in state.get('discovery_recipes',[]) if r['id']!=body.get('id')]
                        if action=='preferences':
                            prefs=state.setdefault('companion_preferences',{})
                            for key in ('spoiler_safe','log_recommendations'):
                                if key in body:
                                    if type(body[key]) is not bool:raise ValueError('Choose valid preference toggles.')
                                    prefs[key]=body[key]
                            if 'notification_limit' in body:
                                if type(body['notification_limit']) is not int or body['notification_limit'] not in (5,10,20):raise ValueError('Choose 5, 10 or 20 recent notifications.')
                                prefs['notification_limit']=body['notification_limit']
                            if 'muted_inbox' in body:
                                if not isinstance(body['muted_inbox'],list) or any(r not in ('releases','requests','lists','creators') for r in body['muted_inbox']):raise ValueError('Choose valid inbox categories.')
                                prefs['muted_inbox']=body['muted_inbox']
                        if action=='inbox-read':
                            ids=body.get('ids',[])
                            if not isinstance(ids,list) or len(ids)>200 or any(not isinstance(i,str) or len(i)>300 for i in ids):raise ValueError('Choose valid inbox items.')
                            allowed={r['id'] for r in companion.inbox(state)}
                            state['inbox_seen']=list(dict.fromkeys(state.get('inbox_seen',[])+[i for i in ids if i in allowed]))[-2000:]
                        if action=='follow':
                            rows=state.setdefault('creator_follows',[]);rows[:]=[r for r in rows if r['id']!=verified['id']]
                            if len(rows)>=30:raise ValueError('Follow up to 30 people.')
                            rows.append(verified)
                        if action=='unfollow':state['creator_follows']=[r for r in state.get('creator_follows',[]) if r['id']!=str(body.get('person'))]
                        if action=='impressions' and state.get('companion_preferences',{}).get('log_recommendations'):
                            rows=body.get('items',[])
                            if not isinstance(rows,list) or len(rows)>100:raise ValueError('Log up to 100 recommendations per batch.')
                            log=state.setdefault('discovery_impressions',{})
                            for row in rows:
                                identity=taste.identity(row.get('type'),row.get('tmdb'))
                                log.setdefault(identity,{'type':row['type'],'tmdb':str(row['tmdb']),'title':str(row.get('title',''))[:200],'at':time.time()})
                            state['discovery_impressions']=dict(list(log.items())[-2000:])
                        if action=='reset-insights':
                            if body.get('confirmed') is not True:raise ValueError('Confirm resetting local recommendation history.')
                            state['discovery_impressions']={}
                            if body.get('reset_taste'):state['taste_feedback']={}
                        if action=='path-save':
                            entry=next((r for r in state['lists'] if r['id']==body.get('list_id')),None)
                            if not entry or saved_lists.revision(entry)!=body.get('revision'):raise ValueError('The list changed. Reopen the path editor.')
                            mode=body.get('mode');ids=body.get('ids')
                            if mode not in ('essential','chronological','release','completionist','recommended') or not isinstance(ids,list) or not ids or len(ids)>10000 or len(set(ids))!=len(ids) or any(i not in {r['id'] for r in entry['items']} for i in ids):raise ValueError('Choose a valid ordered set of list entries.')
                            entry.setdefault('watch_paths',{})[mode]=ids
                        save_state(state)
                    return self.respond({'ok':True})
                if action=='person-search':
                    found=providers.cached_tmdb('search/person?'+urllib.parse.urlencode({'query':str(body.get('query',''))[:100],'include_adult':'false'}),snapshot['settings']).get('results',[])
                    people={str(row['id']):row for row in found if str(row.get('id','')).isdigit()}
                    follows={str(row['id']):row['role'] for row in snapshot.get('creator_follows',[])}
                    return self.respond({'items':[dict(row,following=follows.get(str(row['id']))) for row in sorted(people.values(),key=lambda row:-(row.get('popularity') or 0))[:10]]})
                if action=='genres':return self.respond({'items':providers.cached_tmdb('genre/'+('movie' if body.get('type','movie')=='movie' else 'tv')+'/list',snapshot['settings']).get('genres',[])})
                if action=='storage':return self.respond(companion.storage(snapshot,body,arr_call))
                if action=='priorities':return self.respond({'items':companion.priorities(snapshot,body.get('list_id'))})
                if action in ('path','path-editor','path-copy'):
                    entry=next((r for r in snapshot['lists'] if r['id']==body.get('list_id')),None)
                    if not entry:raise ValueError('Choose an existing list.')
                    if action=='path-editor':return self.respond({'entry':entry,'revision':saved_lists.revision(entry)})
                    rows,stale=companion.paths(entry,body)
                    if action=='path-copy':
                        if body.get('revision')!=saved_lists.revision(entry):raise ValueError('The source list changed. Load the path again.')
                        if not rows:raise ValueError('Choose a path with at least one entry.')
                        copied={'id':secrets.token_hex(8),'name':entry['name']+' / '+str(body.get('mode','completionist')).title(),'description':'Personal watch path from '+entry['name'],'poster':entry.get('poster',''),'source':None,'items':[dict(normalize(row),status='unchecked') for row in rows],'updated_at':time.time()}
                        with LOCK:
                            latest=read_state();current=next((r for r in latest['lists'] if r['id']==entry['id']),None)
                            if not current or saved_lists.revision(current)!=body.get('revision'):raise ValueError('The source list changed. Load the path again.')
                            latest['lists'].append(copied);save_state(latest)
                        return self.respond({'entry':copied})
                    return self.respond({'items':rows,'stale':stale,'note':'Release mode uses known years, then show/season/episode order unless a curated path exists. Unknown years sort last. Other paths use the explicitly saved order.'})
                if action=='episode-groups':
                    identifier=str(body.get('tmdb',''))
                    if not identifier.isdigit():raise ValueError('Choose an exact TV show ID.')
                    return self.respond(providers.cached_tmdb('tv/'+identifier+'/episode_groups',snapshot['settings']))
                if action=='episode-group':
                    group=str(body.get('group',''))
                    if not re.fullmatch('[A-Za-z0-9_-]{1,100}',group):raise ValueError('Choose a valid episode group.')
                    return self.respond(providers.cached_tmdb('tv/episode_group/'+group,snapshot['settings']))
                if action in ('episode-map','episode-map-save'):
                    result=companion.episode_map(snapshot['settings'],body)
                    if action=='episode-map-save':
                        if body.get('confirmed') is not True:raise ValueError('Review and confirm the mapped episode entries.')
                        with LOCK:
                            latest=read_state();entry=next((r for r in latest['lists'] if r['id']==body.get('list_id')),None)
                            if not entry:raise ValueError('Choose an existing list.')
                            rows=[dict(normalize(row),status='unchecked') for row in result['items']]
                            updated,report=saved_lists.update_entries(entry,rows,{'revision':body.get('revision'),'mode':'append','skip_duplicates':True,'confirm_detach':body.get('confirm_detach')})
                            latest['lists'][latest['lists'].index(entry)]=updated;save_state(latest)
                        return self.respond({'entry':updated,'report':report})
                    return self.respond(result)
                if action=='inbox':return self.respond({'items':companion.inbox(snapshot)})
                if action in ('recipes','blindspots','tonight','franchises','radar','insights','watched','favorites'):
                    catalog,connected=explore.library(snapshot['settings'],plex_catalog)
                    if action=='favorites':return self.respond(companion.favorites(catalog,body))
                    if action in ('recipes','blindspots'):return self.respond(companion.discover(snapshot,body,catalog,action=='blindspots'))
                    if action=='tonight':return self.respond(companion.tonight([r for r in catalog if not ignored_titles.matches({**r,**r.get('ids',{})},snapshot.get('ignored_titles',[]))],body,plex_leaves,snapshot['settings']))
                    if action=='franchises':return self.respond(companion.franchise(snapshot,catalog))
                    if action=='insights':return self.respond(companion.report(snapshot,catalog))
                    if action=='watched':
                        match=next((r for r in catalog if r['type']==body.get('type') and str(r.get('ids',{}).get('tmdb'))==str(body.get('tmdb'))),None)
                        return self.respond({'watched':bool(match and (match.get('fully_watched') if match['type']=='show' else match.get('watched')))})
                    events,warnings=companion.radar(snapshot,explore.ownership(catalog))
                    with LOCK:
                        latest=read_state();latest['creator_events']=events;save_state(latest)
                    return self.respond({'items':events,'warnings':warnings})
                raise ValueError('Unknown discovery tool.')
            if self.path in ('/api/taste/set','/api/taste/list'):
                with LOCK:snapshot=read_state()
                if self.path.endswith('/list'):return self.respond({'items':snapshot.get('taste_feedback',{})})
                kind=body.get('type');identifier=body.get('tmdb');identity=taste.identity(kind,identifier);value=body.get('value')
                if value not in (*taste.VALUES,'clear'):raise ValueError('Choose valid taste feedback.')
                record=None
                if value!='clear':
                    metadata=providers.cached_tmdb(('movie/' if kind=='movie' else 'tv/')+str(int(identifier))+'?append_to_response=credits',snapshot['settings'])
                    if not metadata.get('title') and not metadata.get('name'):raise ValueError('This title could not be verified. Retry later.')
                    record=taste.record(kind,identifier,value,metadata)
                with LOCK:
                    latest=read_state();feedback=latest.setdefault('taste_feedback',{})
                    if value=='clear':feedback.pop(identity,None)
                    else:
                        if identity not in feedback and len(feedback)>=2000:raise ValueError('Manage existing feedback before adding more than 2,000 titles.')
                        feedback[identity]=record
                    save_state(latest)
                return self.respond({'items':feedback})
            if self.path == '/api/suggestions':
                with LOCK:
                    snapshot = read_state()
                return self.respond(suggestions.discover(body.get('type'), body.get('tmdb'), snapshot['settings']))
            if self.path == '/api/enrichment':
                with LOCK:
                    snapshot = read_state()
                return self.respond(metadata_sources.enrich(body.get('type'), body.get('tmdb'), snapshot['settings']))
            if self.path.startswith('/api/trakt/') or self.path in ('/api/progress', '/api/follow'):
                with LOCK:
                    snapshot = read_state()
                action = self.path
                if action == '/api/trakt/search':
                    return self.respond(trakt_features.search_lists(snapshot['settings'], body.get('query', ''), body.get('mode', 'search'), body.get('page', 1)))
                if action == '/api/trakt/title':
                    return self.respond(trakt_features.title_features(snapshot['settings'], body))
                if action == '/api/trakt/title-lists':
                    return self.respond(trakt_features.title_lists(snapshot['settings'], body))
                if action == '/api/trakt/calendar':
                    return self.respond(release_calendar(snapshot))
                if action == '/api/trakt/preview':
                    url = str(body.get('url', ''))
                    trakt_features.source_base(url)
                    imported = providers.trakt(url, lambda *args: None, snapshot['settings'])
                    rows = [normalize(row) for row in imported['items']]
                    compared = bool(body.get('compare') and snapshot['settings'].get('plex', {}).get('key'))
                    if compared:
                        rows = compare(rows, snapshot['settings'])
                    return self.respond({'name': imported['name'], 'source': imported['source'], 'items': rows, 'compared': compared})
                if action == '/api/trakt/updates':
                    updates = []
                    for entry in snapshot['lists']:
                        source = entry.get('source') or ''
                        if 'trakt.tv/' not in source or not entry.get('followed', True):
                            continue
                        previous_check = entry.get('source_check', {})
                        if not body.get('force') and time.time() - previous_check.get('checked_at', 0) < 21600:
                            updates.append({'id': entry['id'], **previous_check})
                            continue
                        try:
                            checked = trakt_features.check_source(entry, snapshot['settings'])
                        except ValueError as exc:
                            updates.append({'id': entry['id'], 'error': str(exc)})
                            continue
                        with LOCK:
                            latest = read_state()
                            saved = next((r for r in latest['lists'] if r['id'] == entry['id'] and r.get('updated_at') == entry.get('updated_at')), None)
                            if saved:
                                saved['source_check'] = checked
                                if not saved.get('source_version') and not checked['changed']:
                                    saved['source_version'] = checked['source_version']
                                save_state(latest)
                        updates.append({'id': entry['id'], **checked})
                    return self.respond({'updates': updates})
                entry = next((r for r in snapshot['lists'] if r['id'] == body.get('list_id')), None)
                if not entry:
                    raise ValueError('Choose a saved list first.')
                if action == '/api/follow':
                    trakt_features.source_base(entry.get('source') or '')
                    with LOCK:
                        latest = read_state()
                        saved = next(r for r in latest['lists'] if r['id'] == entry['id'])
                        saved['followed'] = bool(body.get('followed'))
                        save_state(latest)
                    return self.respond({'followed': saved['followed']})
                if action == '/api/progress':
                    result = watch_progress(entry, snapshot['settings'])
                    with LOCK:
                        latest = read_state()
                        saved = next((r for r in latest['lists'] if r['id'] == entry['id'] and r.get('updated_at') == entry.get('updated_at')), None)
                        if saved:
                            saved['watch_progress'] = result
                            save_state(latest)
                    return self.respond(result)
                raise ValueError('Unknown Trakt action.')
            if self.path == '/api/title/status':
                with LOCK:snapshot=read_state()
                return self.respond(title_workspace_state(body,snapshot))
            if self.path == '/api/title/scopes':
                identifier=str(body.get('tmdb',''))
                if not identifier.isdigit() or int(identifier)<=0:raise ValueError('Choose a TV show first.')
                with LOCK:settings=read_state()['settings']
                show=providers.cached_tmdb('tv/'+identifier,settings)
                seasons=[{'number':row['season_number'],'name':row.get('name') or 'Season '+str(row['season_number']),'count':row.get('episode_count',0)} for row in show.get('seasons',[]) if isinstance(row.get('season_number'),int)]
                episodes=[]
                if body.get('season') is not None and str(body.get('season'))!='':
                    season=str(body['season'])
                    if not season.isdigit() or not any(row['number']==int(season) for row in seasons):raise ValueError('Choose a season from this show.')
                    data=providers.cached_tmdb('tv/'+identifier+'/season/'+str(int(season)),settings)
                    episodes=[{'number':row['episode_number'],'name':row.get('name') or 'Episode '+str(row['episode_number'])} for row in data.get('episodes',[]) if isinstance(row.get('episode_number'),int)]
                return self.respond({'seasons':seasons,'episodes':episodes})
            if self.path in ('/api/title', '/api/title/save'):
                kind, identifier = body.get('type'), str(body.get('tmdb', ''))
                if kind not in ('movie', 'show', 'episode') or not identifier.isdigit() or int(identifier) <= 0:
                    raise ValueError('Choose a valid TMDB movie, show, or episode.')
                with LOCK:
                    snapshot = read_state()
                if kind == 'episode':
                    season, episode = str(body.get('season', '')), str(body.get('episode', ''))
                    if not season.isdigit() or not episode.isdigit() or int(episode) < 1:
                        raise ValueError('Choose a valid season and episode number.')
                    item = normalize({'type': kind, 'show_tmdb': identifier, 'season': season, 'episode': episode, 'title': 'Episode'})
                else:
                    item = normalize({'type': kind, 'tmdb': identifier, 'title': 'Title'})
                details = providers.title_details(item, snapshot['settings'])
                item['title'] = details['title']
                if kind == 'episode' and details.get('show_title'):
                    item['show_title'] = details['show_title']
                if details.get('release_date'):
                    item['year'] = details['release_date'][:4]
                if self.path == '/api/title':
                    result = {'item': item, 'details': details}
                    if kind == 'show' and not body.get('metadata_only'):
                        result['show'] = show_overview(item, snapshot['settings'])
                    return self.respond(result)
                rows = compare([item], snapshot['settings'])
                entry = {'id': secrets.token_hex(8), 'name': item['title'], 'items': rows, 'source': None, 'warnings': [], 'updated_at': time.time()}
                with LOCK:
                    latest = read_state()
                    latest['lists'].append(entry)
                    save_state(latest)
                return self.respond({'entry': entry})
            if self.path in ('/api/discover', '/api/discover/save'):
                with LOCK:
                    snapshot = read_state()
                result = providers.discovery(body.get('kind'), body.get('identifier'), snapshot['settings'])
                if self.path == '/api/discover':
                    return self.respond(result)
                keys = body.get('keys')
                if not isinstance(keys, list) or not keys:
                    raise ValueError('Select at least one project.')
                rows = [normalize(r) for r in result['items'] if r['key'] in keys]
                if not rows:
                    raise ValueError('No selected projects were found.')
                rows = compare(rows, snapshot['settings'])
                entry = {'id': secrets.token_hex(8), 'name': result['name'], 'items': rows, 'source': None, 'warnings': [result['note']], 'updated_at': time.time()}
                with LOCK:
                    latest = read_state()
                    latest['lists'].append(entry)
                    save_state(latest)
                return self.respond({'entry': entry})
            if self.path == '/api/import/start':
                return self.respond(start_import_job(body))
            if self.path in ('/api/metadata', '/api/details', '/api/show'):
                with LOCK:
                    snapshot = read_state()
                entry = next((x for x in snapshot['lists'] if x['id'] == body.get('list_id')), None)
                if not entry:
                    raise ValueError('Choose a saved list first.')
                if self.path in ('/api/details', '/api/show'):
                    item = next((i for i in entry['items'] if i['id'] == body.get('item_id')), None)
                    if not item:
                        raise ValueError('This title is no longer in the list.')
                    if self.path == '/api/show':
                        return self.respond(show_overview(item, snapshot['settings']))
                    if body.get('parent'):
                        item = providers.parent_show(item, snapshot['settings'])
                    return self.respond(providers.title_details(item, snapshot['settings']))
                ids = body.get('ids', [])
                if not isinstance(ids, list) or len(ids) > 20:
                    raise ValueError('Request metadata for at most 20 titles at once.')
                items = [i for i in entry['items'] if i['id'] in ids]
                def details(item):
                    try:
                        return {'id': item['id'], 'details': providers.list_details(item, snapshot['settings'])}
                    except ValueError as exc:
                        return {'id': item['id'], 'error': str(exc)}
                with ThreadPoolExecutor(max_workers=4) as pool:
                    result = list(pool.map(details, items))
                return self.respond({'items': result})
            with LOCK:
                state = read_state()
                action = self.path
                if action == '/api/plex/start':
                    result = start_plex_login(state)
                    save_state(state)
                    return self.respond(result)
                if action == '/api/plex/status':
                    try:
                        result = check_plex_login(state)
                    finally:
                        save_state(state)
                    return self.respond(result)
                if action == '/api/plex/servers':
                    return self.respond(plex_servers(state))
                if action == '/api/plex/connect':
                    result = connect_plex_server(state, body['server_id'], body.get('url', ''))
                    save_state(state)
                    return self.respond(result)
                if action == '/api/plex/disconnect':
                    client_id = state.get('plex_auth', {}).get('client_id')
                    state['plex_auth'] = {'client_id': client_id} if client_id else {}
                    state['settings'].pop('plex', None)
                    save_state(state)
                    return self.respond({'ok': True})
                if action == '/api/settings':
                    for service in ('sonarr', 'radarr', 'tmdb', 'trakt', 'tvdb', 'mdblist', 'prowlarr'):
                        if service not in body:
                            continue
                        new = body.get(service, {})
                        old = state['settings'].get(service, {})
                        state['settings'][service] = {'url': new.get('url', '').strip().rstrip('/'), 'key': (new.get('key') or old.get('key', '')).strip()}
                        if service == 'tvdb':
                            state['settings'][service]['pin'] = str(new.get('pin') or old.get('pin', '')).strip()
                    save_state(state)
                    return self.respond({'ok': True})
                if action == '/api/test':
                    return self.respond(test_connection(state['settings'], body))
                if action == '/api/import':
                    entry = {'id': secrets.token_hex(8), 'name': body.get('name', '').strip() or 'Untitled list', 'items': import_items(body['content'], body['format'])}
                    state['lists'].append(entry)
                    save_state(state)
                    return self.respond(entry)
                entry = next((x for x in state['lists'] if x['id'] == body.get('list_id')), None)
                if not entry:
                    raise ValueError('Choose a saved list first.')
                if action == '/api/compare':
                    baseline = entry.get('comparison_baseline') or {i['id']: i['status'] for i in entry['items'] if i.get('status') not in (None, 'unchecked')}
                    entry['items'] = compare(entry['items'], state['settings'])
                    entry['availability_report'] = [{'title': i['title'], 'from': baseline[i['id']], 'to': i['status']} for i in entry['items'] if i['id'] in baseline and baseline[i['id']] != i['status']]
                    entry.pop('comparison_baseline', None)
                    entry['compared_at'] = time.time()
                    if entry.get('playlist'):
                        entry['playlist_needs_update'] = playlist_preview(entry)['fingerprint'] != entry['playlist'].get('fingerprint')
                    save_state(state)
                    return self.respond(entry)
                if action == '/api/matches':
                    item = next(i for i in entry['items'] if i['id'] == body['item_id'])
                    query = body.get('query', item.get('show_title') or item['title']).casefold().strip()
                    candidates = [m for m in plex_catalog(state['settings']) if m['type'] == ('movie' if item['type'] == 'movie' else 'show') and query in m['title'].casefold()]
                    return self.respond({'matches': candidates[:50]})
                if action == '/api/identify':
                    item = next(i for i in entry['items'] if i['id'] == body['item_id'])
                    query = str(body.get('query') or item.get('show_title') or item['title']).strip()[:200]
                    kind = 'movie' if item['type'] == 'movie' else 'tv'
                    found = providers.cached_tmdb('search/' + kind + '?' + urllib.parse.urlencode({'query': query, 'include_adult': 'false'}), state['settings'])
                    return self.respond({'results': [{'id': r['id'], 'title': r.get('title') or r.get('name'), 'year': (r.get('release_date') or r.get('first_air_date') or '')[:4]} for r in found.get('results', [])]})
                if action == '/api/correct':
                    item = next(i for i in entry['items'] if i['id'] == body['item_id'])
                    correction = {k: str(v).strip() for k, v in body.get('fields', {}).items() if k in ('title', 'year', 'tmdb', 'tvdb', 'imdb', 'show_tmdb', 'show_tvdb', 'show_imdb', 'show_title', 'season', 'episode')}
                    candidate = dict(item, **correction)
                    if candidate.get('season') not in ('', None) and (candidate['type'] == 'season' or candidate.get('episode') not in ('', None)):
                        candidate.pop('metadata_unresolved', None)
                    validated = normalize(candidate)
                    for field in correction:
                        correction[field] = validated.get(field, '')
                    if body.get('plex_key'):
                        match = next((m for m in plex_catalog(state['settings']) if m['key'] == body['plex_key'] and m['type'] == ('movie' if item['type'] == 'movie' else 'show')), None)
                        if not match:
                            raise ValueError('This Plex match is no longer available.')
                        prefix = 'show_' if item['type'] in ('season', 'episode') else ''
                        correction.update({prefix + provider: ident for provider, ident in match['ids'].items() if provider in ('tmdb', 'tvdb', 'imdb')})
                        correction.update(plex_override=match['key'], plex_server=state['settings']['plex']['url'])
                    item.update(correction, correction=dict(item.get('correction', {}), **correction), status='unchecked', detail='Correction saved. Compare with Plex to apply it.')
                    if not candidate.get('metadata_unresolved'):
                        item.pop('metadata_unresolved', None)
                    item.pop('plex_keys', None)
                    item.pop('plex_key', None)
                    save_state(state)
                    return self.respond(entry)
                if action == '/api/resolve':
                    warnings = []
                    entry.setdefault('comparison_baseline', {i['id']: i['status'] for i in entry['items'] if i.get('status') not in (None, 'unchecked')})
                    for i, row in enumerate(entry['items']):
                        try:
                            enriched = providers.enrich(row, state['settings'])
                            enriched['status'] = 'unchecked'
                            enriched.pop('plex_keys', None)
                            entry['items'][i] = enriched
                            if enriched.get('metadata_unresolved') or not ids_present(enriched):
                                warnings.append(row['title'] + ': exact provider ID or TV scope still needs manual matching.')
                        except ValueError as exc:
                            warnings.append(row['title'] + ': ' + str(exc))
                    save_state(state)
                    return self.respond({'entry': entry, 'warnings': warnings})
                if action == '/api/playlist/preview':
                    order=body.get('watch_order');view=copy.deepcopy(entry) if order else entry
                    if order:view['items']=companion.paths(entry,{'mode':order})[0]
                    return self.respond(dict(playlist_preview(view),watch_order=order))
                if action == '/api/playlist/create':
                    order=body.get('watch_order');view=copy.deepcopy(entry) if order else entry
                    if order:view['items']=companion.paths(entry,{'mode':order})[0]
                    result = create_playlist(view, state['settings'], body.get('title', entry['name']), bool(body.get('replace')))
                    if order:result['watch_order']=order
                    entry['playlist'] = dict(result, server=state['settings']['plex']['url'])
                    entry['playlist_needs_update'] = False
                    save_state(state)
                    return self.respond(result)
                if action == '/api/options':
                    return self.respond({s: request_options(state, s) for s in body['services'] if s in ('sonarr', 'radarr')})
                if action == '/api/show/request':
                    item = next((i for i in entry['items'] if i['id'] == body.get('item_id')), None)
                    if not item or item['type'] == 'movie':
                        raise ValueError('Choose a television entry first.')
                    route=body.get('route') or manager_routes.default(state,'sonarr');cfg=manager_routes.config(state,'sonarr',route);settings=manager_routes.routed(state,'sonarr',route)
                    queued=bool(state.get('request_policy',{}).get('require_approval'))
                    try:
                        result = request_show_scope(item,settings,dict(body,defer=queued))
                    except ValueError as exc:
                        child=item['type'] in ('season','episode');prefix='show_' if child else ''
                        failed_item={'type':'show','title':item.get('show_title') or item['title'],**{key:item.get(prefix+key) for key in ('tmdb','tvdb','imdb') if item.get(prefix+key)}}
                        if body.get('scope')=='season':failed_item.update(type='season',season=str(body.get('season','')),**{'show_'+key:failed_item[key] for key in ('tmdb','tvdb','imdb') if key in failed_item})
                        request_ledger.record(state,failed_item,status='failed',message=str(exc),list_id=entry['id'],route=route,tier=cfg['tier']);save_state(state)
                        raise ValueError(str(exc)) from None
                    if result.get('requested_item'):
                        ledger=request_ledger.record(state,result['requested_item'],status='awaiting_approval' if queued else 'requested',message=result['message'],options={'profile':body['profile'],'root':body['root']},list_id=entry['id'],route=route,tier=cfg['tier'])
                        item['request_log']={'at':time.time(),'service':'sonarr','message':result['message'],'ledger_id':ledger['id']}
                    remember_request_options(state, 'sonarr', body['profile'], body['root'],route)
                    save_state(state)
                    result['entry']=entry
                    return self.respond(result)
                if action == '/api/request':
                    results = []
                    for item in entry['items']:
                        if item['id'] not in body.get('ids', []):
                            continue
                        try:
                            if item.get('status') not in ('missing', 'partial'):
                                raise ValueError('Compare first and select a confirmed missing or partial item.')
                            service = 'radarr' if item['type'] == 'movie' else 'sonarr'
                            option = body['options'][service]
                            route=option.get('route') or manager_routes.default(state,service);cfg=manager_routes.config(state,service,route);settings=manager_routes.routed(state,service,route)
                            queued=bool(state.get('request_policy',{}).get('require_approval'))
                            message='Queued for owner approval' if queued else request_item(item,settings,option['profile'],option['root'])
                            saved_request=request_ledger.record(state,item,status='awaiting_approval' if queued else 'requested',message=message,options=option,list_id=entry['id'],route=route,tier=cfg['tier'])
                            draft=next((r for r in state.get('requests',[]) if r['id']==request_ledger.fingerprint(item) and r.get('status')=='pending' and r['id']!=saved_request['id']),None)
                            if draft:draft.update(status='cancelled',message='Submitted via another manager route',updated_at=time.time())
                            item['request_log']={'at':time.time(),'service':service,'message':message,'ledger_id':saved_request['id']}
                            remember_request_options(state, service, option['profile'], option['root'],route)
                            results.append({'title': item['title'], 'ok': True, 'message': message})
                        except (ValueError, KeyError) as exc:
                            request_ledger.record(state,item,status='failed',message=str(exc),list_id=entry['id'],route=body.get('options',{}).get('radarr' if item['type']=='movie' else 'sonarr',{}).get('route','primary'),tier='standard')
                            results.append({'title': item['title'], 'ok': False, 'message': str(exc)})
                    save_state(state)
                    return self.respond({'results': results,'entry':entry})
                raise ValueError('Unknown action')
        except (ValueError, KeyError, TypeError, ET.ParseError) as exc:
            self.respond({'error': str(exc)}, 400)
        except Exception:
            self.respond({'error': 'Unexpected server response. Check your connection settings and retry.'}, 500)


if __name__ == '__main__':
    start_background_tasks()
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    print('ReelCheck is running at http://127.0.0.1:8765 — Ctrl+C to stop.')
    webbrowser.open('http://127.0.0.1:8765')
    server.serve_forever()
