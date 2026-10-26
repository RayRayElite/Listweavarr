"""Versioned, portable official catalogue; personal state is never bundled."""
import copy
import json
from pathlib import Path
import time

def prepare_publish(entry,previous,normalize):
    import list_sharing
    data=list_sharing.export(entry)['list']
    list_sharing.validate({'format':'reelcheck-list','version':1,'list':data},normalize)
    identifier=entry.get('official_id') or 'curated-'+entry['id']
    before=next((row for row in previous.get('lists',[]) if row['id']==identifier),None)
    same=before is not None and all(before.get(key)==data.get(key) for key in ('name','description','poster','playlist_poster','items','paths'))
    result=copy.deepcopy(previous)
    if same:published=copy.deepcopy(before)
    else:
        published=dict(data,id=identifier,version=(before or {}).get('version',0)+1,updated_at=time.time())
        if before:result['lists'][result['lists'].index(before)]=published
        else:result.setdefault('lists',[]).append(published)
        result['version']=result.get('version',0)+1
        result['format']='reelcheck-official-catalogue'
    working=copy.deepcopy(entry)
    working.update(official_id=identifier,official_version=published['version'],official_authoring=True)
    return result,working,{'name':published['name'],'version':published['version'],'changed':not same,'new':before is None,'count':len(published['items'])}

def write_document(data,backup=True):
    ROOT.mkdir(exist_ok=True)
    target=ROOT/'official-lists.json'
    if backup and target.exists():(ROOT/'official-lists.json.bak').write_bytes(target.read_bytes())
    temporary=ROOT/'official-lists.tmp'
    temporary.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temporary.replace(target)
    import catalogue_feed
    manifest_target=ROOT/'official-lists.manifest.json'
    manifest_temp=ROOT/'official-lists.manifest.tmp'
    manifest_temp.write_text(json.dumps(catalogue_feed.manifest(data),ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    manifest_temp.replace(manifest_target)

ROOT=Path(__file__).resolve().parent/'catalogue'

def document():
    path=ROOT/'official-lists.json'
    return json.loads(path.read_text('utf-8')) if path.exists() else {'version':1,'lists':[]}

def catalogue():
    data=document()
    return {'version':data['version'],'lists':[{k:v for k,v in row.items() if k!='items'}|{'count':len(row['items']),'kind':'curated','provider':'ReelCheck'} for row in data['lists']],
            'sources':[],'note':'Bundled official watch orders. Open a list to create your own editable copy. Personal edits are kept separate from catalogue updates.'}

def get(identifier):
    row=next((r for r in document()['lists'] if r['id']==identifier),None)
    if not row:raise ValueError('Choose an available official list.')
    return copy.deepcopy(row)

def instantiate(identifier,normalize):
    import list_sharing
    import collection_tools
    row=get(identifier)
    entry,_=list_sharing.validate({'format':'reelcheck-list','version':1,'list':row},normalize)
    entry.update(official_id=row['id'],official_version=row['version'],official_base=collection_tools.snapshot(row))
    return entry

def collection_id(identifier):
    raise ValueError('The starter collections have been replaced by curated official lists.')
