"""TV-only poster overlays using local Kometa assets and cached TMDB metadata."""
import datetime
import re
from pathlib import Path
import providers

ASSETS = Path(__file__).resolve().parent / 'Kometa Examples' / 'overlays'

def asset_path(url):
    parts = url.split('/')
    if len(parts) != 4 or parts[1] != 'poster-overlays' or parts[2] not in ('status-top-left', 'network-top-left'):
        return None
    name = parts[3]
    if ':' in name or not name.endswith('.png') or name in ('.', '..') or '/' in name or '\\' in name:
        return None
    path = ASSETS / parts[2] / name
    return path if path.is_file() else None

def show_info(identifier, settings):
    if not str(identifier).isdigit():
        raise ValueError('An exact TV show TMDB ID is required.')
    data = providers.cached_tmdb('tv/'+str(identifier), settings)
    raw = data.get('status', '')
    status = {'Ended':'ended','Canceled':'cancelled','Cancelled':'cancelled','Returning Series':'returning'}.get(raw)
    # Airing means an episode in TMDB's current seven-day broadcast window.
    today = datetime.date.today()
    if status == 'returning':
        for key in ('last_episode_to_air', 'next_episode_to_air'):
            try:
                air = datetime.date.fromisoformat((data.get(key) or {}).get('air_date', ''))
                if today-datetime.timedelta(days=3) <= air <= today+datetime.timedelta(days=3):
                    status = 'airing'
            except (ValueError, TypeError):
                pass
    networks = [n.get('name') for n in data.get('networks', []) if n.get('name')]
    normalize = lambda name: re.sub(r'[^a-z0-9]', '', name.casefold())
    files = {normalize(p.stem):p.name for p in (ASSETS/'network-top-left').glob('*.png')}
    network = next((files[normalize(n)] for n in networks if normalize(n) in files), None)
    return {'status':status, 'status_label':status.capitalize() if status else raw or 'Status unknown',
            'network':networks[0] if networks else None, 'network_asset':network}
