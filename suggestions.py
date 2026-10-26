"""Explainable movie/TV discovery from exact TMDB metadata and people credits."""
import math
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import providers


def discover(kind, identifier, settings):
    if kind not in ('movie', 'show') or not str(identifier).isdigit() or int(identifier) < 1:
        raise ValueError('Choose an exact movie or parent-show TMDB ID.')
    media = 'movie' if kind == 'movie' else 'tv'
    title = providers.cached_tmdb(media + '/' + str(identifier) + '?append_to_response=credits,keywords', settings)
    genres = {int(g['id']): g['name'] for g in title.get('genres', [])}
    keywords = (title.get('keywords') or {}).get('keywords' if kind == 'movie' else 'results', [])
    keywords = {int(k['id']): k['name'] for k in keywords if str(k.get('id', '')).isdigit()}
    credits = title.get('credits') or {}
    actors = list({str(p['id']): p for p in credits.get('cast', []) if str(p.get('id', '')).isdigit()}.values())[:3]
    directors = list({str(p['id']): p for p in credits.get('crew', []) if p.get('job') == 'Director' and str(p.get('id', '')).isdigit()}.values())[:2]
    creators = [p for p in title.get('created_by', []) if str(p.get('id', '')).isdigit()][:2] if not directors else []
    jobs = []
    if genres:
        params = {'with_genres': '|'.join(map(str, genres)), 'sort_by': 'vote_average.desc', 'vote_count.gte': 150, 'include_adult': 'false', 'page': 1}
        jobs.append(('genres', media, None, 'discover/' + media + '?' + urllib.parse.urlencode(params)))
        params['sort_by'] = 'popularity.desc'
        jobs.append(('genres', media, None, 'discover/' + media + '?' + urllib.parse.urlencode(params)))
    if keywords:
        for candidate_media in ('movie', 'tv'):
            params = {'with_keywords': '|'.join(map(str, list(keywords)[:8])), 'sort_by': 'popularity.desc', 'vote_count.gte': 50, 'include_adult': 'false', 'page': 1}
            jobs.append(('keywords', candidate_media, None, 'discover/' + candidate_media + '?' + urllib.parse.urlencode(params)))
    for role, people in [('actor', actors), ('director', directors), ('creator', creators)]:
        for person in people:
            jobs.append((role, None, person, 'person/' + str(person['id']) + '/combined_credits'))
    warnings = []
    def fetch(job):
        try:
            return job, providers.cached_tmdb(job[3], settings)
        except ValueError:
            return job, None
    candidates = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, jobs))
    for (signal, candidate_media, person, _), data in results:
        if data is None:
            warnings.append('Some suggestion sources could not be checked.')
            continue
        if signal == 'actor':
            rows = data.get('cast', [])
        elif signal in ('director', 'creator'):
            rows = [r for r in data.get('crew', []) if r.get('job') in (('Director',) if signal == 'director' else ('Creator',))]
        else:
            rows = data.get('results', [])
        for row in rows:
            row_media = candidate_media or row.get('media_type')
            if row_media not in ('movie', 'tv') or not str(row.get('id', '')).isdigit() or row.get('adult'):
                continue
            # Interview appearances and making-of footage otherwise dominate shared-cast
            # matches. Keep them when exploring that kind of title deliberately.
            if set(row.get('genre_ids', [])) & ({99, 10763, 10764, 10767} - set(genres)):
                continue
            if signal == 'actor' and str(row.get('character') or '').strip().lower() in ('self', 'himself', 'herself', 'themselves'):
                continue
            key = row_media + ':' + str(row['id'])
            if key == media + ':' + str(identifier):
                continue
            if not row.get('title') and not row.get('name'):
                continue
            candidate = candidates.setdefault(key, {'row': row, 'media': row_media, 'signals': {}})
            if person:
                label = ('With ' if signal == 'actor' else 'Directed by ' if signal == 'director' else 'Created by ') + person['name']
                candidate['signals'][signal + ':' + str(person['id'])] = (7 if signal != 'actor' else 4, label)
            elif signal == 'keywords':
                # The OR query proves at least one keyword matches, not which one.
                candidate['signals']['keywords'] = (4, 'Shared story themes / keywords')
            if row_media == media:
                shared = [name for genre_id, name in genres.items() if genre_id in row.get('genre_ids', [])]
                if shared:
                    candidate['signals']['genres'] = (min(len(shared), 3) * 2, 'Similar genres: ' + ', '.join(shared[:3]))
    ranked = []
    for key, candidate in candidates.items():
        row = candidate['row']
        signals = candidate['signals']
        if not signals:
            continue
        votes = max(0, int(row.get('vote_count') or 0))
        rating = float(row.get('vote_average') or 0)
        quality = (votes * rating + 100 * 6.5) / (votes + 100)
        score = sum(weight for weight, _ in signals.values()) + quality * .45 + min(math.log1p(max(0, float(row.get('popularity') or 0))), 5) * .2
        reasons = [label for _, label in sorted(signals.values(), key=lambda pair: -pair[0])]
        date = row.get('release_date') or row.get('first_air_date') or ''
        ranked.append({'key': key, 'type': 'movie' if candidate['media'] == 'movie' else 'show', 'tmdb': str(row['id']),
                       'title': row.get('title') or row['name'], 'year': date[:4], 'poster': providers.image_url(row.get('poster_path')),
                       'original_language':row.get('original_language'), 'genre_ids':row.get('genre_ids',[]), 'people_ids':[value.split(':',1)[1] for value in signals if value.startswith(('actor:','director:','creator:'))], 'rating': rating if votes else None, 'vote_count': votes, 'release_date': date, 'reasons': reasons[:3], 'score': round(score, 3), 'provider': 'TMDB'})
    ranked.sort(key=lambda row: (-row['score'], row['title'], row['key']))
    # Keep a useful mix instead of allowing one actor's filmography to fill the row.
    selected, remaining, reason_counts = [], [], {}
    for row in ranked:
        primary = row['reasons'][0]
        if reason_counts.get(primary, 0) >= 12:
            remaining.append(row)
            continue
        selected.append(row)
        reason_counts[primary] = reason_counts.get(primary, 0) + 1
    return {'items': (selected + remaining)[:100], 'warnings': list(dict.fromkeys(warnings)),
            'note': 'Ranked using shared cast, directors or creators, genres, and story keywords, with rating confidence. Connections are suggestions, not confirmed franchise membership.'}
