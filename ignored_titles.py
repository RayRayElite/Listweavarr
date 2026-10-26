"""Persistent, reversible exclusions; no media or source-list deletion."""
import re
import uuid

def tokens(row, parent=False):
    kind = 'show' if parent else row.get('type','movie')
    prefix = kind + ':'
    suffix = ':'+str(row.get('season',''))+':'+str(row.get('episode','')) if kind in ('season','episode') else ''
    result=[]
    for provider in ('tmdb','imdb','tvdb'):
        value=row.get(('show_' if parent or kind in ('season','episode') else '')+provider) or (row.get(provider) if not parent and kind not in ('season','episode') else None)
        if value:
            result.append(prefix+provider+':'+str(value)+suffix)
    title=row.get('show_title' if parent else 'title','')
    if title:
        result.append(prefix+'title:'+re.sub(r'[^a-z0-9]','',title.lower())+':'+str(row.get('year',''))+suffix)
    return result

def matches(row, ignored):
    keys=set(tokens(row))
    if row.get('type') in ('episode','season'):
        keys.update(tokens(row,True))
    return any(keys.intersection(entry.get('tokens',[])) for entry in ignored)

def add(state,row):
    if row.get('type') not in ('movie','show','season','episode') or not row.get('title'):
        raise ValueError('Choose a title to ignore.')
    keys=tokens(row)
    if not keys:
        raise ValueError('This title needs an identifier.')
    entries=state.setdefault('ignored_titles',[])
    if not any(set(keys).intersection(e['tokens']) for e in entries):
        entries.append({'id':uuid.uuid4().hex,'title':str(row['title'])[:300], 'type':row['type'],'tokens':keys})
    return entries
