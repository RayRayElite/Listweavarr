"""Read-only full Trakt chronology import and Plex comparison using saved connections."""
from collections import Counter
import app
import providers

if __name__ == '__main__':
    settings = app.read_state()['settings']
    result = providers.import_url('https://trakt.tv/users/rayrayelite/lists/marvel-universe-timeline-copy', lambda message, *a: print(message, flush=True), settings)
    rows = [app.normalize(row) for row in result['items']]
    print('Complete ranked list:', result['name'], len(rows), dict(Counter(r['type'] for r in rows)), flush=True)
    assert all(r.get('show_tvdb') and r.get('season') is not None and r.get('episode') is not None for r in rows if r['type'] == 'episode')
    compared = app.compare(rows, settings)
    plan = app.playlist_preview({'name': result['name'], 'items': compared})
    print('Plex status:', dict(Counter(r['status'] for r in compared)), '| playable items:', plan['count'], '| omitted entries:', plan['omitted'], flush=True)
    print('No downloads or playlists submitted.', flush=True)
