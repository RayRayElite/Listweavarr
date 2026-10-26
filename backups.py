"""Portable, credential-free workspace backups and validated restore previews."""
import copy
import datetime
import hashlib
import json
import re
import secrets
import time
import urllib.parse
import ratings
import explore
import taste
import companion
import catalogue_feed

FIELDS=('official_feed_url','discovery_recipes','creator_follows','companion_preferences','inbox_seen','creator_events','discovery_impressions','taste_feedback','lists','ignored_titles','release_watchlist','release_region','explore_languages','rating_preferences','request_defaults','requests','request_notifications','request_policy')
SENSITIVE={'key','apikey','api_key','token','access_token','refresh_token','secret','client_secret','csrf','pin','password','authorization','plex_auth','settings'}

def sensitive(name):
    name=str(name).lower().replace('-','_')
    return name in SENSITIVE or name.replace('_','').endswith(('token','password','secret'))

def scrub(value):
    if isinstance(value,dict):return {k:scrub(v) for k,v in value.items() if not sensitive(k)}
    if isinstance(value,list):return [scrub(v) for v in value]
    if isinstance(value,str) and value.startswith(('http://','https://')):
        url=urllib.parse.urlsplit(value)
        host=url.netloc.rsplit('@',1)[-1]
        query=urllib.parse.urlencode([(k,v) for k,v in urllib.parse.parse_qsl(url.query) if not sensitive(k)])
        return urllib.parse.urlunsplit((url.scheme,host,url.path,query,''))
    return value

def export(state):
    return {'format':'reelcheck-workspace','version':1,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'data':scrub({k:copy.deepcopy(state[k]) for k in FIELDS if k in state})}

def digest(document):
    return hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate(document,normalize):
    if not isinstance(document,dict) or document.get('format')!='reelcheck-workspace' or document.get('version')!=1 or not isinstance(document.get('data'),dict):
        raise ValueError('Choose a supported ReelCheck workspace backup (version 1).')
    data=scrub({k:v for k,v in document['data'].items() if k in FIELDS})
    if 'official_feed_url' in data:catalogue_feed.source_url(data['official_feed_url'])
    taste.validate(data.get('taste_feedback',{}))
    lists=data.get('lists',[])
    if not isinstance(lists,list) or len(lists)>1000:raise ValueError('Invalid backup lists.')
    count=0;ids=set()
    for entry in lists:
        if not isinstance(entry,dict) or not isinstance(entry.get('items'),list) or not isinstance(entry.get('name'),str):raise ValueError('Each backup list needs a name and items.')
        identifier=entry.get('id')
        if not isinstance(identifier,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',identifier) or identifier in ids:raise ValueError('Backup list IDs must be unique and valid.')
        ids.add(identifier);item_ids=set()
        for row in entry['items']:
            if not isinstance(row,dict):raise ValueError('Invalid backup item.')
            normalize(row)
            if not isinstance(row.get('id'),str) or row['id'] in item_ids:raise ValueError('Each list item needs a unique ID.')
            item_ids.add(row['id']);count+=1
            if count>100000:raise ValueError('This backup exceeds 100,000 entries.')
    companion.validate_state(data)
    for field in ('ignored_titles','release_watchlist','requests','request_notifications'):
        values=data.get(field,[])
        if not isinstance(values,list) or len(values)>10000 or any(not isinstance(r,dict) or not isinstance(r.get('id'),str) for r in values):raise ValueError('Invalid '+field+' entries.')
    for row in data.get('ignored_titles',[]):
        if not isinstance(row.get('tokens'),list) or any(not isinstance(t,str) for t in row['tokens']):raise ValueError('Invalid ignored-title identifiers.')
    for row in data.get('release_watchlist',[]):
        if row.get('type','movie') not in ('movie','show') or not str(row.get('tmdb','')).isdigit() or not re.fullmatch('[A-Z]{2}',str(row.get('region',''))):raise ValueError('Invalid release-watchlist title.')
    for row in data.get('requests',[]):
        if not isinstance(row.get('item'),dict) or row.get('mode') not in ('search','monitor') or row.get('service') not in ('radarr','sonarr'):raise ValueError('Invalid request history.')
        normalize(row['item'])
        if not isinstance(row.get('events',[]),list):raise ValueError('Invalid request events.')
    if 'rating_preferences' in data:ratings.preferences(data['rating_preferences'])
    if 'explore_languages' in data:explore.language_preferences(data['explore_languages'])
    if 'release_region' in data and not re.fullmatch('[A-Z]{2}',str(data['release_region'])):raise ValueError('Invalid release country.')
    if 'request_policy' in data and (not isinstance(data['request_policy'],dict) or not isinstance(data['request_policy'].get('require_approval',False),bool)):raise ValueError('Invalid request approval policy.')
    if 'request_defaults' in data and not isinstance(data['request_defaults'],dict):raise ValueError('Invalid request defaults.')
    return data,{'lists':len(lists),'items':count,'ignored':len(data.get('ignored_titles',[])),'tracked':len(data.get('release_watchlist',[]))}

def restore(state,data,mode):
    if mode not in ('merge','replace'):raise ValueError('Choose Merge or Replace workspace.')
    result=copy.deepcopy(state)
    for key in FIELDS:
        if key not in data:continue
        incoming=copy.deepcopy(data[key])
        if key=='lists':
            for entry in incoming:
                entry.pop('playlist',None)
                for row in entry['items']:
                    for field in ('plex_keys','plex_override','request_log','manager_status'):row.pop(field,None)
                    row['status']='unchecked';row['detail']='Restored - compare with Plex to check availability'
        if mode=='merge' and key in ('lists','ignored_titles','release_watchlist','requests','request_notifications'):
            existing=result.setdefault(key,[]);known={r['id'] for r in existing}
            existing.extend(r for r in incoming if r['id'] not in known)
        elif mode=='replace' or key not in result:
            result[key]=incoming
    if result.get('discord_notifications'):
        result['discord_notifications']['since']=time.time();result['discord_notifications']['collected']={}
        for job in result.get('notification_outbox',[]):
            if job.get('status')=='pending':job['status']='cancelled'
    return result

def rolling(folder,state):
    folder.mkdir(parents=True,exist_ok=True)
    document=export(state)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    file=folder/(stamp+'-'+secrets.token_hex(3)+'.json')
    file.write_text(json.dumps(document,indent=2),'utf-8')
    for old in sorted(folder.glob('*.json'),reverse=True)[10:]:old.unlink()
    return file.name
