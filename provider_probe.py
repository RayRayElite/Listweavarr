"""Fetch public example pages for importer development. No account credentials."""
import urllib.request
from pathlib import Path

PAGES = {
    'letterboxd-sony': 'https://letterboxd.com/ben_vlbd/list/sony-spider-man-multiverse-spumc-ranking/',
    'letterboxd-halloween': 'https://letterboxd.com/mysteriis666/list/halloween/',
    'imdb-mcu': 'https://www.imdb.com/list/ls082926249/',
    'mdblist-mcu': 'https://mdblist.com/lists/rip/marvel-cinematic-universe-mcu-in-universe-chronological-order',
    'chronocanon-pokemon': 'https://chronocanon.com/franchise/pokemon-anime',
}

if __name__ == '__main__':
    folder = Path('data/provider-samples')
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in PAGES.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ReelCheck/0.2; personal list importer)', 'Accept': 'text/html'})
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read()
            (folder / (name + '.html')).write_bytes(raw)
            print(name, len(raw), 'bytes', flush=True)
        except Exception as exc:
            print(name, type(exc).__name__, str(exc), flush=True)
