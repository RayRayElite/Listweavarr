"""Read-only release audit. Never changes lists, downloads, or Plex playlists."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import datetime
import json
import time
import app
import activity
import providers
import ratings


def main():
    state=app.read_state();settings=state['settings'];report={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ratings':{},'lists':[],'activity':{}}
    if settings.get('mdblist',{}).get('key'):
        for kind,identifier in [('movie','1771'),('show','1403')]:
            result=ratings.lookup({'type':kind,'tmdb':identifier},settings)
            assert all(0<=r['value']<=r['maximum'] for r in result['ratings'])
            report['ratings'][kind]=[r['source'] for r in result['ratings']]
            print(kind,'ratings:',len(result['ratings']),'sources',flush=True)
    for entry in sorted(state['lists'],key=lambda r:len(r['items']),reverse=True)[:2]:
        def check(item):
            try:
                details=providers.list_details(item,settings)
                return {'poster':bool(details.get('poster')),'overview':bool(details.get('overview'))}
            except ValueError as exc:
                return {'error':str(exc)}
        timings=[];results=[]
        for pass_index in range(2):
            start=time.monotonic()
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(check,entry['items']))
            timings.append(round(time.monotonic()-start,2))
            print(entry['name'],len(results),'entries; pass',pass_index+1,'seconds:',timings[-1],flush=True)
        summary={'name':entry['name'],'count':len(results),'seconds':timings,'errors':sum('error' in r for r in results),'missing_poster':sum(not r.get('poster') for r in results),'missing_overview':sum(not r.get('overview') for r in results)}
        report['lists'].append(summary)
        print('  metadata:',summary['errors'],'errors;',summary['missing_poster'],'without artwork;',summary['missing_overview'],'without overview',flush=True)
        start=time.monotonic();progress=activity.summarize(entry['items'],settings,app.arr_call)
        report['activity'][entry['name']]={'counts':dict(Counter(r['state'] for r in progress['items'].values())),'warnings':progress['warnings'],'seconds':round(time.monotonic()-start,2)}
        print('  manager progress:',report['activity'][entry['name']],flush=True)
    folder=Path(__file__).parent/'data'/'audits';folder.mkdir(exist_ok=True)
    (folder/'readiness.json').write_text(json.dumps(report,indent=2),'utf-8')
    print('Aggregate report saved to data/audits/readiness.json. No remote writes performed.',flush=True)

if __name__=='__main__':main()
