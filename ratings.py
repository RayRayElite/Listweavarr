"""Optional MDBList ratings. Exact IDs, daily caching, no title searches."""
import hashlib
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import providers

SOURCES={
 'tmdb':('TMDB',10), 'imdb':('IMDb',10), 'tomatoes':('Rotten Tomatoes critics',100),
 'popcorn':('Rotten Tomatoes audience',100), 'metacritic':('Metacritic critics',100),
 'metacriticuser':('Metacritic users',10), 'trakt':('Trakt',10), 'letterboxd':('Letterboxd',5),
 'myanimelist':('MyAnimeList',10), 'rogerebert':('Roger Ebert',4), 'mdblist':('MDBList aggregate',100)}
_lock=threading.RLock()
_cooldown={}

def preferences(value):
    value=value if isinstance(value,dict) else {}
    main=value.get('main','tmdb')
    display=value.get('display','all')
    if main not in SOURCES or (display!='all' and (not isinstance(display,list) or not display or any(s not in SOURCES for s in display))):
        raise ValueError('Choose a main rating and at least one displayed source, or All ratings.')
    result={'main':main,'display':display}
    if 'order' in value:
        order=value['order']
        if not isinstance(order,list) or any(s not in SOURCES for s in order) or len(order)!=len(set(order)):
            raise ValueError('Choose a unique display order using known rating sources.')
        result['order']=order+[s for s in SOURCES if s not in order]
    return result

def number(value):
    if isinstance(value,bool):return None
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):
        return None

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('MDBList redirected unexpectedly; credentials were not forwarded.')

def request(path,settings):
    key=settings.get('mdblist',{}).get('key','').strip()
    if not key:
        raise ValueError('Add your MDBList API key under Connections to load additional ratings.')
    if not re.fullmatch(r'(user|(?:tmdb|imdb)/(?:movie|show)/(?:[0-9]+|tt[0-9]+))',path):
        raise ValueError('Invalid ratings lookup.')
    identity=hashlib.sha256(key.encode()).hexdigest()
    if _cooldown.get(identity,0)>time.time():
        raise ValueError('MDBList ratings are paused after an access or rate-limit error. Check your key or retry later.')
    url='https://api.mdblist.com/'+path+'?'+urllib.parse.urlencode({'apikey':key})
    try:
        req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'ReelCheck/0.4'})
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as response:
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise ValueError('MDBList response too large.')
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get('error') or data.get('response') is False:
            raise ValueError('MDBList could not provide ratings for this title.')
        return data
    except urllib.error.HTTPError as exc:
        code=exc.code
        exc.close()
        if code in (401,403,429):
            _cooldown[identity]=time.time()+300
        if code==404:
            return {}
        raise ValueError('MDBList rejected the key or reached its request limit.' if code in (401,403,429) else 'MDBList ratings are temporarily unavailable.') from None
    except (urllib.error.URLError,TimeoutError,json.JSONDecodeError):
        raise ValueError('Could not load MDBList ratings. TMDB remains available.') from None

def parse(data):
    result={}
    for row in data.get('ratings',[]):
        if not isinstance(row,dict):continue
        source={'tomatoesaudience':'popcorn','audience':'popcorn'}.get(row.get('source'),row.get('source'))
        if source not in SOURCES:continue
        value=number(row.get('value'))
        # The single-item API reports TMDB and Trakt on a 100-point scale.
        if source in ('tmdb','trakt') and value is not None:value/=10
        maximum=SOURCES[source][1]
        if value is None or not 0<=value<=maximum:continue
        if value==0 and source in ('imdb','tmdb','trakt','letterboxd','myanimelist'):continue
        url=row.get('url')
        if not isinstance(url,str) or not url.startswith('https://'):url=None
        result[source]={'source':source,'label':SOURCES[source][0],'value':value,'maximum':maximum,'score':value*10/maximum,'votes':number(row.get('votes')),'url':url,'via':'MDBList'}
    aggregate=number(data.get('score'))
    if aggregate is not None and 0<=aggregate<=100:
        result['mdblist']={'source':'mdblist','label':SOURCES['mdblist'][0],'value':aggregate,'maximum':100,'score':aggregate/10,'votes':None,'url':None,'via':'MDBList'}
    return list(result.values())

def lookup(item,settings):
    if item.get('type') not in ('movie','show'):
        return {'ratings':[],'note':'Additional series ratings are not substituted for episode or season ratings.'}
    kind=item['type']
    if str(item.get('tmdb','')).isdigit():path='tmdb/'+kind+'/'+str(item['tmdb'])
    elif re.fullmatch(r'tt[0-9]+',str(item.get('imdb',''))):path='imdb/'+kind+'/'+item['imdb']
    else:return {'ratings':[],'note':'An exact TMDB or IMDb ID is needed.'}
    key=settings.get('mdblist',{}).get('key','')
    if not key:return {'ratings':[],'note':'Connect MDBList for additional rating sources.'}
    file=providers.CACHE/'ratings'/(hashlib.sha256((hashlib.sha256(key.encode()).hexdigest()+path).encode()).hexdigest()+'.json')
    with _lock:
        if file.exists() and time.time()-file.stat().st_mtime<86400:
            try:return json.loads(file.read_text('utf-8'))
            except (ValueError,OSError):pass
        data=request(path,settings)
        returned_type=data.get('mediatype') or data.get('type')
        if returned_type and returned_type not in (kind,'tv' if kind=='show' else 'movie'):
            raise ValueError('MDBList returned a different media type; ratings were not used.')
        returned=(data.get('ids') or {}).get('tmdb') or data.get('tmdbid') or data.get('tmdb_id')
        if path.startswith('tmdb/') and returned is not None and str(returned)!=str(item['tmdb']):
            raise ValueError('MDBList returned a different title; ratings were not used.')
        result={'ratings':parse(data),'checked_at':time.time(),'note':'Scores via MDBList. Coverage and freshness vary by source.'}
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(json.dumps(result),'utf-8')
        return result
