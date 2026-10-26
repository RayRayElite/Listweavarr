"""Read-only, cached Radarr/Sonarr progress with exact television scope."""
import datetime
import hashlib
import threading
import time
import urllib.parse

_cache={}
_lock=threading.RLock()

def cached(settings,service,path,call,force=False):
    cfg=settings.get(service,{})
    identity=hashlib.sha256((cfg.get('url','')+'\0'+cfg.get('key','')+service+path).encode()).hexdigest()
    with _lock:
        saved=_cache.get(identity)
        if saved and not force and time.time()-saved[0]<60:return saved[1]
    value=call(settings,service,path)
    with _lock:_cache[identity]=(time.time(),value)
    return value

def queue(settings,service,call,force=False):
    records=[]
    for page in range(1,21):
        path='queue?'+urllib.parse.urlencode({'page':page,'pageSize':100,'includeMovie':'true','includeSeries':'true','includeEpisode':'true'})
        data=cached(settings,service,path,call,force)
        batch=data.get('records',[]) if isinstance(data,dict) else data
        records.extend(batch)
        if not isinstance(data,dict) or len(records)>=data.get('totalRecords',len(records)):break
    return records

def queue_label(records):
    if any(r.get('trackedDownloadStatus') in ('warning','error') for r in records):return 'import_blocked','Import needs attention'
    if any(str(r.get('status','')).lower()=='completed' or r.get('trackedDownloadState') in ('importPending','importing','importBlocked') for r in records):return 'importing','Waiting for import'
    return 'downloading','Downloading'

def summarize(items,settings,call,force=False):
    outputs={};warnings=[]
    for service,kind,path in [('radarr','movie','movie'),('sonarr','show','series')]:
        selected=[r for r in items if (r['type']=='movie')==(kind=='movie')]
        if not selected:continue
        if not settings.get(service,{}).get('key'):
            for row in selected:outputs[row['id']]={'state':'unavailable','label':service.capitalize()+' not connected'}
            continue
        try:
            catalog=cached(settings,service,path,call,force);queued=queue(settings,service,call,force)
        except ValueError:
            warnings.append(service.capitalize()+' progress is unavailable; availability in Plex is unchanged.')
            for row in selected:outputs[row['id']]={'state':'unavailable','label':'Progress unavailable'}
            continue
        episodes={}
        for row in selected:
            if row.get('status')=='available':
                outputs[row['id']]={'state':'available','label':'Available in Plex','prevent_duplicate':True};continue
            def exact(record):
                if kind=='movie':
                    return bool(row.get('tmdb') and str(record.get('tmdbId'))==str(row['tmdb']) or row.get('imdb') and record.get('imdbId')==row['imdb'])
                identifier=row.get('show_tvdb') if row['type'] in ('episode','season') else row.get('tvdb')
                return bool(identifier and str(record.get('tvdbId'))==str(identifier))
            manager=next((record for record in catalog if exact(record)),None)
            if not manager:
                outputs[row['id']]={'state':'requested' if row.get('request_log') else 'not_managed','label':'Requested; awaiting manager metadata' if row.get('request_log') else 'Not in '+service.capitalize()};continue
            matches=[q for q in queued if q.get('movieId' if kind=='movie' else 'seriesId')==manager['id']]
            full=False
            if kind=='movie':full=bool(manager.get('hasFile'))
            else:
                try:
                    if manager['id'] not in episodes:episodes[manager['id']]=cached(settings,service,'episode?seriesId='+str(manager['id']),call,force)
                    today=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                    scoped=[e for e in episodes[manager['id']] if (row['type']!='show' or e.get('seasonNumber',0)>0) and (row['type']=='show' or str(e.get('seasonNumber'))==str(row.get('season'))) and (row['type']!='episode' or str(e.get('episodeNumber'))==str(row.get('episode'))) and (e.get('airDateUtc') or '9999')[:10]<=today]
                    scoped_ids={e['id'] for e in scoped}
                    matches=[q for q in matches if q.get('episodeId') in scoped_ids or (row['type']=='show' and not q.get('episodeId'))]
                    full=bool(scoped) and all(e.get('hasFile') for e in scoped)
                except ValueError:
                    outputs[row['id']]={'state':'unavailable','label':'Episode progress unavailable'};continue
            if full:
                outputs[row['id']]={'state':'downloaded','label':'Imported in '+service.capitalize()+'; awaiting Plex comparison','prevent_duplicate':True};continue
            if matches:
                state,label=queue_label(matches)
                total=sum(float(q.get('size') or 0) for q in matches);left=sum(float(q.get('sizeleft') or 0) for q in matches)
                prevent=kind=='movie' or row['type']=='episode'
                if kind=='show' and row['type'] in ('show','season'):
                    covered={q.get('episodeId') for q in matches}|{e['id'] for e in scoped if e.get('hasFile')}
                    prevent=bool(scoped) and scoped_ids.issubset(covered)
                outputs[row['id']]={'state':state,'label':label,'percent':round(max(0,min(100,(1-left/total)*100)),1) if total else None,'prevent_duplicate':prevent};continue
            outputs[row['id']]={'state':'requested','label':'Monitored in '+service.capitalize()+'; no active download','prevent_duplicate':False}
    return {'items':outputs,'warnings':warnings,'checked_at':time.time()}
