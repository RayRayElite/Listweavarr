"""Read-only public download charts. No torrent URLs are retained or submitted."""
import copy
import json
import re
import threading
import time
import urllib.request
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
import providers

MOVIES='https://torrentfreak.com/top-10-most-torrented-pirated-movies/'
TV='https://eztvx.to/api/get-torrents'
_cache={}
_lock=threading.Lock()

class ChartParser(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.cells=None;self.cell=None;self.imdb=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.cells=[];self.imdb=None
        if tag in ('td','th') and self.cells is not None:self.cell=[]
        if tag=='a' and self.cells is not None:
            match=re.search(r'imdb\.com/title/(tt\d+)',dict(attrs).get('href',''))
            if match:self.imdb=match[1]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.cells.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.cells is not None:
            if len(self.cells)>=3 and self.cells[0].isdigit() and self.imdb:
                self.rows.append({'rank':int(self.cells[0]),'imdb':self.imdb,'title':self.cells[2]})
            self.cells=None;self.cell=None

def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'ReelCheck/0.4 (+personal media discovery)','Accept':'application/json,text/html'})
    with urllib.request.urlopen(request,timeout=18) as response:
        data=response.read(5_000_001)
    if len(data)>5_000_000:raise ValueError('Source response exceeded the chart size limit.')
    return data.decode('utf-8')

def source_rows(source):
    if source=='downloads_movies':
        parser=ChartParser();parser.feed(fetch(MOVIES))
        rows=sorted(parser.rows,key=lambda r:r['rank'])[:10]
        if not rows:raise ValueError('TorrentFreak chart format was unavailable; try again later.')
        return rows
    grouped={}
    for page in range(1,4):
        data=json.loads(fetch(TV+'?limit=100&page='+str(page)))
        records=data.get('torrents')
        if not isinstance(records,list):raise ValueError('EZTV did not return its release feed; try again later.')
        for row in records:
            imdb=str(row.get('imdb_id') or '').removeprefix('tt')
            if not imdb.isdigit() or int(imdb)==0:continue
            imdb='tt'+imdb.zfill(7)
            try:seeds=max(0,int(row.get('seeds') or 0))
            except (TypeError,ValueError):continue
            if seeds and (imdb not in grouped or seeds>grouped[imdb]['seeders']):grouped[imdb]={'imdb':imdb,'seeders':seeds}
    return sorted(grouped.values(),key=lambda r:(-r['seeders'],r['imdb']))[:40]

def candidates(source,settings,refresh=False):
    if source not in ('downloads_movies','downloads_tv'):raise ValueError('Unknown chart source.')
    # Cache only public chart data; no user configuration or acquisition links.
    with _lock:saved=_cache.get(source)
    notices=[]
    if saved and not refresh and time.time()-saved[0]<1800:rows=copy.deepcopy(saved[1])
    else:
        try:
            rows=source_rows(source)
            with _lock:_cache[source]=(time.time(),copy.deepcopy(rows))
        except Exception:
            if not saved or time.time()-saved[0]>86400:raise ValueError('Could not load '+('TorrentFreak' if source=='downloads_movies' else 'EZTV')+'. The source may be temporarily unavailable or blocking automated access. No chart was substituted.') from None
            rows=copy.deepcopy(saved[1]);notices.append('Source unavailable; showing the last successful chart (less than 24 hours old).')
    media='movie' if source=='downloads_movies' else 'tv'
    def resolve(row):
        try:
            found=providers.cached_tmdb('find/'+row['imdb']+'?external_source=imdb_id',settings).get(media+'_results',[])
            if len(found)!=1:return None
            details=providers.cached_tmdb(media+'/'+str(found[0]['id']),settings)
            return {**row,'details':details}
        except (ValueError,TypeError,KeyError):return None
    with ThreadPoolExecutor(max_workers=4) as pool:items=[item for item in pool.map(resolve,rows) if item]
    if len(items)<len(rows):notices.append(str(len(rows)-len(items))+' titles could not be matched confidently and were omitted.')
    return items,notices
