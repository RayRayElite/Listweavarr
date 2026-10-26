"""Explicit Radarr/Sonarr destinations. Credentials stay outside public responses/backups."""
import copy
import re
import secrets
import urllib.parse

def validate_url(value):
    value=str(value or '').strip().rstrip('/')
    parsed=urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use a full HTTP/HTTPS manager address without credentials, a query or fragment.')
    return value

def choices(state,service):
    result=[{'id':'primary','service':service,'name':'Primary '+service.capitalize(),'tier':'standard','enabled':True,'configured':bool(state.get('settings',{}).get(service,{}).get('key'))}]
    result.extend({k:row[k] for k in ('id','service','name','tier','enabled')}|{'configured':bool(row.get('key'))} for row in state.get('manager_instances',[]) if row['service']==service)
    return result

def public(state):
    return {'instances':[{**r,'url':state.get('settings',{}).get(service,{}).get('url','') if r['id']=='primary' else next(v['url'] for v in state.get('manager_instances',[]) if v['id']==r['id'])} for service in ('radarr','sonarr') for r in choices(state,service)],'defaults':state.get('manager_route_defaults',{})}

def config(state,service,identifier='primary',allow_disabled=False):
    if service not in ('radarr','sonarr'):raise ValueError('Choose Radarr or Sonarr.')
    if identifier=='primary':return {**state.get('settings',{}).get(service,{}),'tier':'standard','name':'Primary '+service.capitalize()}
    row=next((r for r in state.get('manager_instances',[]) if r['id']==identifier and r['service']==service),None)
    if not row or not allow_disabled and not row.get('enabled'):raise ValueError('This manager route is missing or disabled. Choose another route.')
    return row

def routed(state,service,identifier='primary'):
    cfg=config(state,service,identifier);settings=copy.deepcopy(state['settings']);settings[service]={'url':cfg.get('url',''),'key':cfg.get('key','')}
    settings['_requested_tier']=cfg['tier']
    return settings

def default(state,service,tier='standard'):
    saved=state.get('manager_route_defaults',{}).get(service+':'+tier)
    rows=[r for r in choices(state,service) if r['enabled'] and r['configured'] and r['tier']==tier]
    return next((r['id'] for r in rows if r['id']==saved),rows[0]['id'] if rows else 'primary')

def save(state,body):
    service=body.get('service');tier=body.get('tier','standard');name=str(body.get('name','')).strip()
    if service not in ('radarr','sonarr') or tier not in ('standard','4k'):raise ValueError('Choose a manager and standard/4K route.')
    if not name or len(name)>80:raise ValueError('Enter a route name up to 80 characters.')
    identifier=body.get('id');rows=state.setdefault('manager_instances',[])
    old=next((r for r in rows if r['id']==identifier),None)
    if identifier and not old:raise ValueError('Manager route no longer exists.')
    if old and (old['service']!=service or old['tier']!=tier) and any(r.get('route')==identifier for r in state.get('requests',[])):raise ValueError('This route has request history. Add a new route to change service or library tier.')
    url=validate_url(body.get('url'));key=str(body.get('key') or (old or {}).get('key','')).strip()
    if not key:raise ValueError('Enter the manager API key.')
    other=[state.get('settings',{}).get(service,{})]+[r for r in rows if r['service']==service and r.get('id')!=identifier]
    if any(r.get('url','').rstrip('/')==url for r in other):raise ValueError('That manager address already has a route. Separate copies require separate manager instances.')
    result={'id':identifier or secrets.token_hex(8),'service':service,'tier':tier,'name':name,'url':url,'key':key,'enabled':bool(body.get('enabled',True))}
    if old:rows[rows.index(old)]=result
    else:
        if len(rows)>=20:raise ValueError('At most 20 additional manager instances are supported.')
        rows.append(result)
    if body.get('default') and result['enabled']:state.setdefault('manager_route_defaults',{})[service+':'+tier]=result['id']
    return result
