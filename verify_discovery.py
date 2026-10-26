"""Read-only check of discovery using saved TMDB settings; never submits requests."""
import app
import providers

settings = app.read_state()['settings']
pilot = providers.title_details({'type': 'episode', 'title': 'Episode', 'show_tmdb': '1403', 'season': '1', 'episode': '1'}, settings)
assert pilot['title'] == 'Pilot' and pilot['overview'] and pilot['cast']
print('Individual episode:', pilot['show_title'], '/', pilot['title'], '| cast:', len(pilot['cast']))
shield = providers.title_details({'type': 'show', 'title': 'Agents of S.H.I.E.L.D.', 'tmdb': '1403'}, settings)
shield_names = {person['name'] for person in shield['cast']}
assert {'Iain De Caestecker', 'Brett Dalton', 'Adrianne Palicki', 'Nick Blood'} <= shield_names
assert len(shield['cast']) > 24
print('Agents of S.H.I.E.L.D.:', len(shield['cast']), 'cast members across all seasons; earlier regulars verified.')
details = providers.title_details({'type': 'movie', 'title': 'Iron Man', 'tmdb': '1726'}, settings)
assert details['cast'][0]['id']
assert details['cast'][0]['photo']
assert details['studios'] and details['producer_people'] and details['director_people']
studio = providers.discovery('company', details['studios'][0]['id'], settings)
assert studio['items'] and all(r['type'] in ('movie', 'show') for r in studio['items'])
person = providers.discovery('person', details['cast'][0]['id'], settings)
assert person['profile']['photo'] and person['profile']['biography']
assert any(r['tmdb'] == '1726' and r['type'] == 'movie' for r in person['items'])
related = providers.discovery('movie', '1726', settings)
collection = [r for r in related['items'] if not r['group'].startswith('Recommendations')]
assert {'10138', '68721'} <= {r['tmdb'] for r in collection}
print('Person:', person['name'], '| unique movie/TV projects:', len(person['items']))
print('Iron Man collection companions:', len(collection), '| recommendations:', len(related['items']) - len(collection))
print('Studio:', studio['name'], '| movie/TV projects on first pages:', len(studio['items']))
print('Read-only verification passed. No lists, playlists, or downloads created.')
