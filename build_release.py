"""Build a credential-free runtime archive. Never include the data directory."""
from pathlib import Path
import hashlib
import zipfile

ROOT=Path(__file__).resolve().parent
MODULES=['app.py','providers.py','explore.py','ratings.py','metadata_sources.py','title_relationships.py','suggestions.py','trakt_features.py','ignored_titles.py','poster_overlays.py','release_watch.py','backups.py','activity.py','official_lists.py','collection_tools.py','taste.py','companion.py','catalogue_feed.py','saved_lists.py','indexer_discovery.py','popular_downloads.py','cult_discovery.py','request_ledger.py','manager_routes.py','discord_notify.py','list_sharing.py','text_list_builder.py']

def main():
    version=(ROOT/'VERSION').read_text().strip()
    folder=ROOT/'releases';folder.mkdir(exist_ok=True)
    target=folder/('ReelCheck-'+version+'.zip')
    files=[ROOT/name for name in MODULES+['README.md','RELEASE_NOTES.md','FEATURE_ROADMAP.md','VERSION','Start ReelCheck.cmd']]
    files.extend((ROOT/'catalogue').glob('*.json'))
    files.extend(p for p in (ROOT/'web').iterdir() if p.suffix in ('.js','.css','.html'))
    for name in ('status-top-left','network-top-left'):
        files.extend((ROOT/'Kometa Examples'/'overlays'/name).glob('*.png'))
    for file in files:
        if file.suffix=='.py':compile(file.read_text('utf-8-sig'),str(file),'exec')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):archive.write(file,file.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert all(not name.startswith(('data/','releases/')) for name in archive.namelist())
        assert all(name in archive.namelist() for name in MODULES)
    checksum=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(checksum+'  '+target.name+'\n')
    print(target.name,len(files),'files;',target.stat().st_size,'bytes; archive verified.')

if __name__=='__main__':main()
