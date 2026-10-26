"""Read-only list-summary verification. No library or download mutations."""
from concurrent.futures import ThreadPoolExecutor
import time
import app
import providers

state = app.read_state()
entry = max((l for l in state['lists'] if 'trakt.tv/' in (l.get('source') or '')), key=lambda l: len(l['items']))
started = time.time()
def check(item):
    try:
        data = providers.list_details(item, state['settings'])
        return item['title'], None if data.get('overview') and data.get('poster') else 'Provider synopsis or poster is empty'
    except ValueError as exc:
        return item['title'], str(exc)
failed = []
with ThreadPoolExecutor(max_workers=4) as pool:
    for count, (title, error) in enumerate(pool.map(check, entry['items']), 1):
        if error:
            failed.append((title, error))
        if count % 100 == 0:
            print('Checked', count, '/', len(entry['items']), flush=True)
print('Finished:', len(entry['items']), 'entries in', round(time.time()-started, 1), 'seconds;', len(failed), 'issues', flush=True)
for title, error in failed[:10]:
    print(title, ':', error, flush=True)
