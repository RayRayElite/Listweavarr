"""Explainable experimental enjoyable-bad scoring; low scores alone never qualify."""
import copy
import datetime
import hashlib
import math
import re
import threading
import time
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import providers
import ratings

_cache={};_lock=threading.Lock()
ANCHORS=('tt0368226','tt0105643','tt0052077','tt1316037')
STRONG={"so bad it's good",'so bad its good','bad movie night'}
CULT={'cult','cult film','cult classic','cult movie','midnight movie'}
CAMP={'camp','campy','campiness','cheesy','cheesiness','b movie','b-movie','z movie','z-movie','low-budget','low budget','exploitation','trash film'}

def score(data,support=0,extra=None,today=None):
    today=today or datetime.date.today();votes=int(data.get('vote_count') or 0);rating=float(data.get('vote_average') or 0)
    try:age=(today-datetime.date.fromisoformat(data.get('release_date','')[:10])).days/365.25
    except (ValueError,TypeError):return None
    if data.get('adult') or votes<100 or not 2<=rating<=6.3 or age<3:return None
    words={canonical(r.get('name','')) for r in data.get('keywords',{}).get('keywords',[])}
    strong=bool(words&STRONG);cult=bool(words&CULT);camp=len(words&CAMP)
    review_fans=int(data.get('enjoyable_bad_reviews') or 0)
    reasons=[];points=0
    if review_fans:
        points+=min(6,review_fans*3);reasons.append(str(review_fans)+' sampled reviewers explicitly describe enjoyable-bad or unintentionally funny qualities')
    if strong:points+=6;reasons.append('Tagged as enjoyable-bad cinema')
    if cult:points+=2;reasons.append('Cult or midnight-film metadata')
    if camp:points+=min(3,camp);reasons.append('Camp/B-movie themes')
    if support:points+=min(4,support*2);reasons.append('Related to '+str(support)+' established enjoyable-bad favorites')
    values={r['source']:r.get('value') for r in (extra or {}).get('ratings',[]) if r.get('value') is not None}
    gap=values.get('popcorn',0)-values.get('tomatoes',100)
    disagreement=values.get('popcorn',0)>=55 and gap>=25
    if disagreement:points+=3;reasons.append('Audience approval exceeds critics by '+str(round(gap))+' points')
    # Popularity and age support confidence only; they never provide the core fun evidence.
    if age>=10:points+=1;reasons.append('Has an established release history')
    if votes>=500:points+=1
    evidence=strong or review_fans>=2 or (review_fans and (camp or cult or support)) or (camp and support>=2 and disagreement)
    if not evidence or points<7:return None
    return {'score':points,'reasons':reasons,'confidence':'Experimental match - enjoyment is subjective'}

def candidates(settings,refresh=False):
    key=hashlib.sha256((settings.get('tmdb',{}).get('key','')+'\0'+settings.get('mdblist',{}).get('key','')).encode()).hexdigest()
    with _lock:saved=_cache.get(key)
    if saved and not refresh and time.time()-saved[0]<21600:return copy.deepcopy(saved[1]),list(saved[2])
    candidates={};support=defaultdict(set);warnings=[];anchors=set()
    # Anchors generate candidates; they are not a fixed output list and never auto-qualify.
    for imdb in ANCHORS:
        try:
            found=providers.cached_tmdb('find/'+imdb+'?external_source=imdb_id',settings).get('movie_results',[])
            if len(found)!=1:continue
            seed=found[0];anchors.add(str(seed['id']))
            candidates[str(seed['id'])]=seed
            for row in providers.cached_tmdb('movie/'+str(seed['id'])+'/recommendations',settings).get('results',[]):
                candidates[str(row['id'])]=row;support[str(row['id'])].add(imdb)
        except ValueError:warnings.append('Some cult-film candidate sources were unavailable.')
    for term in ("so bad it's good",'cult film','campy','b-movie'):
        try:
            matches=providers.cached_tmdb('search/keyword?'+urllib.parse.urlencode({'query':term}),settings).get('results',[])
            ids=[str(r['id']) for r in matches if canonical(r.get('name','')) in STRONG|CULT|CAMP][:3]
            if not ids:continue
            query={'with_keywords':'|'.join(ids),'vote_average.gte':2,'vote_average.lte':6.3,'vote_count.gte':100,'sort_by':'vote_count.desc','include_adult':'false'}
            for row in providers.cached_tmdb('discover/movie?'+urllib.parse.urlencode(query),settings).get('results',[]):candidates[str(row['id'])]=row
        except ValueError:warnings.append('Some cult-film keyword discovery was unavailable.')
    shortlist=sorted([r for r in candidates.values() if 2<=float(r.get('vote_average') or 0)<=6.3 and int(r.get('vote_count') or 0)>=100],key=lambda r:-(50*(str(r['id']) in anchors)+len(support[str(r['id'])])*10+math.log1p(int(r.get('vote_count') or 0))))[:50]
    review_ids={str(r['id']) for r in shortlist[:24]}
    def evaluate(row):
        try:
            data=providers.cached_tmdb('movie/'+str(row['id'])+'?append_to_response=keywords',settings)
            if str(row['id']) in review_ids:
                try:
                    reviews=providers.cached_tmdb('movie/'+str(row['id'])+'/reviews',settings).get('results',[])
                    data['enjoyable_bad_reviews']=review_evidence(reviews)
                except ValueError:pass
            result=score(data,len(support[str(row['id'])]))
            return (data,result)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=4) as pool:evaluated=[r for r in pool.map(evaluate,shortlist) if r]
    # Optional extra evidence for a bounded set of near misses; no mandatory ratings subscription.
    if settings.get('mdblist',{}).get('key'):
        near=[r for r in evaluated if not r[1]][:8]
        for data,_ in near:
            try:
                extra=ratings.lookup({'type':'movie','tmdb':str(data['id'])},settings)
                result=score(data,len(support[str(data['id'])]),extra)
                if result:evaluated.append((data,result))
            except ValueError:pass
    result=sorted([{'details':data,**scored} for data,scored in evaluated if scored],key=lambda r:(-r['score'],-int(r['details'].get('vote_count') or 0)))
    seen=set();result=[r for r in result if not (r['details']['id'] in seen or seen.add(r['details']['id']))]
    with _lock:_cache[key]=(time.time(),result,list(dict.fromkeys(warnings)))
    return copy.deepcopy(result),list(dict.fromkeys(warnings))


def review_evidence(reviews):
    """Count distinct reviewers explicitly describing enjoyable failure, not generic praise."""
    authors=set()
    for review in reviews[:20]:
        text=canonical(review.get('content',''))
        # Require explicit phrases. Negated statements and generic 'bad movie' do not count.
        positive=re.search(r"so bad.{0,35}?(?:good|fun|hilarious)|hilariously bad|unintentionally (?:funny|hilarious)|delightfully (?:bad|terrible)|enjoyably (?:bad|terrible)",text)
        if not positive:continue
        if re.search(r"(?:not|never|isn't)\s+(?:good|fun|hilarious)",positive.group(0)):continue
        prefix=text[max(0,positive.start()-15):positive.start()]
        if re.search(r"(?:not|isn't|is not|never)\s*$",prefix):continue
        author=review.get('author_details',{}).get('username') or review.get('author') or review.get('id')
        if author:authors.add(author)
    return len(authors)


def canonical(value):
    return str(value).casefold().replace(chr(0x2019),"'").replace(chr(0x2018),"'").strip()
