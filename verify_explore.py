"""Read-only Explore verification; does not save picks or submit downloads."""
import time
import app
import explore

state=app.read_state()
started=time.time()
result=explore.home(state,{'type':'both'},app.plex_catalog)
print('Library:',result['profile']['count'],'titles;',result['profile']['watched'],'watched',flush=True)
print('Elapsed:',round(time.time()-started,1),'seconds',flush=True)
keys=[]
for row in result['rows']:
    print(row['name'],len(row['items']),'discoveries',flush=True)
    keys.extend(r['key'] for r in row['items'])
assert len(keys)==len(set(keys)),'Duplicate title across shelves'
assert all(explore.qualifies(r,recent=row['id'].startswith('recent-')) for row in result['rows'] if row['id']!='cult' for r in row['items'] if not r.get('upcoming'))
print('Unique, quality-filtered discoveries:',len(keys),flush=True)
for warning in result['warnings']:
    print('Notice:',warning,flush=True)
