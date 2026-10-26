"""Editable article/text extraction and explicitly reviewed TMDB list building."""
import http.client
import csv
import io
import json
import ipaddress
import re
import socket
import ssl
import urllib.parse
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import providers

MAX_TEXT=200_000
MAX_ROWS=3000

def public_target(url):
    parsed=urllib.parse.urlsplit(str(url).strip())
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Enter a public https:// website URL without credentials or a custom port.')
    addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    ips=list(dict.fromkeys(row[4][0] for row in addresses))
    if not ips or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast for ip in ips):
        raise ValueError('Only public websites can be read; local and private network addresses are not supported.')
    return parsed,ips[0]

def google_sheet_export(url):
    parsed=urllib.parse.urlsplit(str(url).strip())
    if parsed.hostname!='docs.google.com':return None
    match=re.fullmatch(r'/spreadsheets/d/([A-Za-z0-9_-]+)(?:/(?:edit|view|preview|export))?/?',parsed.path)
    if not match:return None
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Use a public https:// Google Sheets link without credentials or a custom port.')
    query=urllib.parse.parse_qs(parsed.query);fragment=urllib.parse.parse_qs(parsed.fragment)
    gid=(query.get('gid') or fragment.get('gid') or ['0'])[0]
    if not re.fullmatch(r'\d+',gid):raise ValueError('The Google Sheets worksheet gid must be a number.')
    return 'https://docs.google.com/spreadsheets/d/'+match[1]+'/export?format=csv&gid='+gid,gid

def extract_sheet(text,gid='0',default_show=''):
    rows=list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    aliases={'show','series','tv show','series name','show name'}
    header_index=None;headers=[]
    for index,row in enumerate(rows[:25]):
        labels=[cell.strip().casefold() for cell in row]
        if any(cell in aliases for cell in labels) and any(cell in ('episode','episode number','season','title','episode title') for cell in labels):
            header_index=index;headers=labels;break
    def column(names):return next((i for i,h in enumerate(headers) if h in names),None)
    show_col=column(aliases);episode_col=column({'episode','episode number','ep'});season_col=column({'season','season number'});title_col=column({'title','episode title','movie title'})
    data=rows[header_index+1:] if header_index is not None else rows
    # The combination of these abbreviations identifies the Chicago crossover format.
    shows={row[show_col].strip().casefold() for row in data if show_col is not None and len(row)>show_col and row[show_col].strip()}
    chicago={'fire','pd','med'}.issubset(shows) or plain(default_show)=='chicago'
    names={'fire':'Chicago Fire','pd':'Chicago P.D.','med':'Chicago Med','justice':'Chicago Justice','svu':'Law & Order: Special Victims Unit','law & order: svu':'Law & Order: Special Victims Unit','fbi':'FBI'}
    lines=[];skipped_log=False
    for row in data:
        if not any(cell.strip() for cell in row):continue
        if headers and row and row[0].strip().casefold()=='legend':break
        def cell(index):return ' '.join(row[index].split()) if index is not None and index<len(row) else ''
        show=cell(show_col);episode=cell(episode_col);season=cell(season_col);title=cell(title_col)
        if headers and not show and not episode and not season and re.match(r'(?i)^change\s*log\b',title):
            skipped_log=True;break
        if headers and not any((show,episode,season,title)):continue
        if chicago:show=names.get(show.casefold(),show)
        show=show or str(default_show).strip()
        if season.isdigit() and episode.isdigit():episode='S'+season.zfill(2)+'E'+episode.zfill(2)
        if show and episode:line=show+' | '+episode+(' | '+title if title else '')
        elif show and season.isdigit():line=show+' Season '+season
        elif headers:line=title or show or episode or season
        else:line=' | '.join(' '.join(value.split()) for value in row if value.strip())
        if line:lines.append(line)
    result='\n'.join(lines)
    if not result:raise ValueError('This worksheet contains no list entries. Check the selected worksheet gid or paste its rows instead.')
    return {'title':'Spreadsheet list','text':result[:MAX_TEXT],'truncated':len(result)>MAX_TEXT,
            'notice':f'Read {len(lines)} rows from worksheet gid {gid}. Only the selected worksheet is included. '+('Expanded Fire / PD / Med to Chicago show names. ' if chicago else '')+('Excluded the trailing Change Log section. ' if skipped_log else '')+'Check the extracted titles and episode numbering before matching.'}

def sheet_tabs(text):
    tabs=[];seen=set()
    for match in re.finditer(r'items\.push\(\{name:\s*("(?:\\.|[^"\\])*"),\s*pageUrl:\s*"(?:\\.|[^"\\])*",\s*gid:\s*"(\d+)"',text):
        name=json.loads(match[1]);gid=match[2]
        if gid not in seen:tabs.append((name,gid));seen.add(gid)
    if not tabs:raise ValueError('Could not discover this workbook\'s tabs. Choose Selected worksheet instead, or paste the rows.')
    if len(tabs)>60:raise ValueError('This workbook has too many tabs. Choose Selected worksheet instead.')
    return tabs

def fetch_workbook(export_url,default_show=''):
    base=export_url.split('/export?',1)[0]
    tabs=sheet_tabs(fetch_page(base+'/htmlview',_raw=True))
    context=default_show
    if not context and any('Fire S' in name and 'PD S' in name for name,gid in tabs):context='Chicago'
    def read(tab):
        name,gid=tab
        try:return name,fetch_page(base+'/edit?gid='+gid,context,all_sheets=False)
        except ValueError as exc:raise ValueError('Could not import worksheet '+name+': '+str(exc)) from None
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(read,tabs))
    text='\n'.join(result['text'] for name,result in results)
    if len(text)>MAX_TEXT or any(result['truncated'] for name,result in results):
        raise ValueError('The workbook exceeds the text limit. Import selected worksheets separately to avoid losing entries.')
    return {'title':'Spreadsheet list','text':text,'truncated':False,'notice':f'Read {len(text.splitlines())} entries from {len(tabs)} worksheets in workbook tab order. Notes and trailing Change Logs are excluded. Review all matches before saving.',
            'worksheets':[{'name':name,'rows':len(result['text'].splitlines())} for name,result in results]}

def fetch_page(url,default_show='',all_sheets=True,_raw=False):
    sheet=google_sheet_export(url)
    if sheet and all_sheets:return fetch_workbook(sheet[0],default_show)
    if sheet:url=sheet[0]
    # Pin the validated public address for this connection, including redirects.
    for redirect in range(4):
        try:
            parsed,ip=public_target(url)
            connection=http.client.HTTPSConnection(parsed.hostname,timeout=20)
            raw=socket.create_connection((ip,443),timeout=20)
            try:connection.sock=ssl.create_default_context().wrap_socket(raw,server_hostname=parsed.hostname)
            except Exception:raw.close();raise
            try:
                path=urllib.parse.urlunsplit(('', '', parsed.path or '/',parsed.query,''))
                connection.request('GET',path,headers={'User-Agent':'ReelCheck/0.4 personal list builder','Accept':'text/html,text/plain','Accept-Encoding':'identity'})
                response=connection.getresponse()
                if response.status in (301,302,303,307,308):
                    location=response.getheader('Location')
                    if not location:raise ValueError('The website returned an invalid redirect.')
                    url=urllib.parse.urljoin(url,location);continue
                if response.status!=200:raise ValueError('Google Sheets could not export this worksheet. It must be publicly readable; check its sharing settings and worksheet gid, or paste its rows.' if sheet else 'Website returned HTTP '+str(response.status)+'. Copy and paste the list text instead.')
                kind=response.getheader('Content-Type','').lower()
                if not any(t in kind for t in (('text/csv','application/csv','text/plain') if sheet else ('text/html','text/plain','application/xhtml'))):raise ValueError('Google Sheets did not return a public CSV worksheet. Check sharing permissions, or paste its rows.' if sheet else 'This URL is not a text or HTML page. Paste its list text instead.')
                data=response.read(5_000_001)
                if len(data)>5_000_000:raise ValueError('This page is too large. Paste the relevant list section instead.')
                charset=re.search(r'charset=([\w-]+)',kind)
                try:text=data.decode(charset[1] if charset else 'utf-8',errors='replace')
                except LookupError:text=data.decode('utf-8',errors='replace')
                if any(marker in text.lower() for marker in ('cf-chl-','window.awswaf','<title>just a moment','captcha-container')):
                    raise ValueError('This website returned a bot check. Copy and paste the list text instead.')
                if _raw:return text
                if sheet:
                    if text.lstrip().lower().startswith(('<!doctype','<html')):raise ValueError('This spreadsheet requires sign-in. Use a publicly readable sheet or paste its rows.')
                    return extract_sheet(text,sheet[1],default_show)
                return extract_html(text) if 'html' in kind else {'title':'Website list','text':text[:MAX_TEXT],'truncated':len(text)>MAX_TEXT}
            finally:connection.close()
        except (OSError,http.client.HTTPException) as exc:
            raise ValueError('Could not read this public website. Copy and paste the list text instead.') from None
    raise ValueError('Too many website redirects. Paste the list text instead.')

def extract_html(text):
    document=providers.Document(text)
    nodes=list(document.root.walk())
    title=next((n.text().strip() for n in nodes if n.tag=='title'),'Website list')[:200]
    roots=[n for n in nodes if any(word in n.attrs.get('class','').split() for word in ('post-body','entry-content','article-body'))] or [n for n in nodes if n.tag=='article'] or [n for n in nodes if n.tag=='main']
    root=max(roots,key=lambda n:len(n.text())) if roots else document.root
    dragon_guide='dragon ball' in title.casefold() and any(n.has_class('bbWrapper') for n in nodes)
    if dragon_guide:root=next(n for n in nodes if n.has_class('bbWrapper'))
    skip={'script','style','nav','footer','header','aside','noscript','svg','form','iframe','button'}
    blocks={'p','li','h1','h2','h3','h4','h5','h6','div','section','article','main','ul','ol','table','tr'}
    chunks=[]
    def visit(node):
        if isinstance(node,str):chunks.append(node);return
        if node.tag in skip or 'hidden' in node.attrs or node.attrs.get('aria-hidden')=='true':return
        if node.tag=='br':chunks.append('\n');return
        if node.tag in blocks:chunks.append('\n')
        for child in node.children:visit(child)
        if node.tag in ('td','th'):chunks.append(' | ')
        if node.tag in blocks:chunks.append('\n')
    visit(root)
    lines=[' '.join(line.split()).strip(' |') for line in ''.join(chunks).splitlines()]
    result='\n'.join(line for line in lines if line)
    if dragon_guide:
        entries=dragon_ball_lines(result)
        if entries:
            result='\n'.join(line for number,line in entries)
            return {'title':title,'text':result[:MAX_TEXT],'truncated':len(result)>MAX_TEXT,'notice':'Dragon Ball guide: kept watch-order headings from the opening post, excluding descriptions and replies. Choose Original/uncut or edited DUB numbering before review. Movie retelling episode notes are not added as extra TV entries. Check dubbed numbering against your TMDB/Plex episode order.'}
    return {'title':title,'text':result[:MAX_TEXT],'truncated':len(result)>MAX_TEXT}

def dragon_ball_lines(text):
    # Narrow recognition avoids dropping ordinary prose in unrelated text imports.
    if not re.search(r'(?im)^\s*Dragon Ball(?: Z| Super)? Episodes?\s+\d',text) or not re.search(r'(?im)^\s*MOVIE:',text):return None
    entries=[]
    for number,line in enumerate(text.splitlines(),1):
        line=clean_bullet(line.replace('\u200b','')).strip()
        if re.match(r'(?i)^(?:Dragon Ball(?: Z| Super)? Episodes?\s+\d|Dragon Ball:?\s*Daima\s*\(|Dragon Ball GT Complete Series\b|(?:MOVIE|SPECIAL|OPTIONAL):)',line):entries.append((number,line))
    return entries

def infer_dragon_ball(entries,edition='dub'):
    if edition not in ('dub','original'):raise ValueError('Choose original/uncut or edited DUB numbering.')
    rows=[]
    for number,raw in entries:
        line=raw.replace('\u2013','-').replace('\u2014','-')
        row={'source_line':number,'raw':raw,'year':'','hint':'Dragon Ball watch-order entry. Confirm the proposed identity.'}
        episode=re.match(r'(?i)^(Dragon Ball(?: Z| Super)?) Episodes?\s+(\d+)(?:\s*-\s*(\d+))?',line)
        daima=re.match(r'(?i)^Dragon Ball:?\s*Daima\s*\(DBD Episodes?\s+(\d+)(?:\s*-\s*(\d+))?',line)
        if episode or daima:
            parent=episode[1] if episode else 'Dragon Ball DAIMA'
            first,last=(episode[2],episode[3] or episode[2]) if episode else (daima[1],daima[2] or daima[1])
            dub=re.search(r'(?i)\[\s*(\d+)(?:\s*-\s*(\d+))?\s+DUB\s*\]',line)
            if dub and edition=='dub':first,last=dub[1],dub[2] or dub[1]
            if not 1<=int(first)<=int(last) or int(last)-int(first)>=3000:raise ValueError('Correct the Dragon Ball episode range at line '+str(number)+'.')
            row.update(type='episode',query=parent,season='1',episode=first,episode_end=last,numbering='absolute',hint='Continuous series episode range; verify mapping to TMDB seasons.')
            if dub and edition=='dub':row.update(source_numbering='dub',hint='DUB range selected instead of the original range. This edited dub numbering may differ from TMDB aired order; verify before confirming.')
            elif dub:row.update(source_numbering='original',hint='Original/uncut range selected, also suitable for the 291-episode English dub. Continuous episodes will be mapped across TMDB saga seasons.')
        elif re.match(r'(?i)^Dragon Ball GT Complete',line):row.update(type='show',query='Dragon Ball GT')
        else:
            label,title=line.split(':',1);title=re.sub(r'\s*\([^)]*\)','',title).strip()
            kind='movie' if label.upper()=='MOVIE' else 'show' if label.upper()=='OPTIONAL' else 'auto'
            row.update(type=kind,query=title,hint='Match the Dragon Ball '+label.lower()+' title. Parenthetical retelling/optional notes do not create extra episodes.')
        rows.append(row)
    return rows

def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if not unicodedata.combining(c))

def main_clause(value):
    """Parenthetical prose is evidence/notes, never an episode-number command."""
    out=[];depth=0
    for char in str(value):
        if char=='(':depth+=1;continue
        if char==')' and depth:depth-=1;continue
        if not depth:out.append(char)
    return ' '.join(''.join(out).split()).strip()

def unquote_title(value):
    text=str(value).strip()
    for left,right in (("'","'"),('"','"'),('\u2018','\u2019'),('\u201c','\u201d')):
        if text.startswith(left) and text.endswith(right):return text[1:-1].strip()
    # A quoted title may be followed by a meaningful suffix, e.g. "prequel".
    text=re.sub(r"^['\"\u2018\u201c](.+?)['\"\u2019\u201d](?=\s+(?:prequel|parts?\b))",r'\1',text,flags=re.I)
    return text.strip(" '\"\u2018\u2019\u201c\u201d")

def clean_bullet(value):
    text=re.sub(r'^\s*(?:[-*]\s*)?(?:\[[xX ]\]|[\u2611\u2610\u2713\u2714\u2705])\ufe0f?\s*','',str(value))
    return re.sub(r'^\s*(?:[-*\u2022]|\d+[.)])\s+','',text).strip()

def parent_identity(value):
    text=re.sub(r'(?i)\s*[:,-]?\s*\b(?:the\s+)?original\s+series\s*$','',str(value)).strip()
    return title_identity(text)

def infer_context(text,default_show=''):
    if str(default_show).strip():return str(default_show).strip()[:200]
    text='\n'.join(clean_bullet(line) for line in text.splitlines())
    # Repeated typed prefixes establish list-wide context even before their first occurrence.
    names=re.findall(r'(?im)^\s*(?:\d+[.)]\s*)?([^\n:|]{2,70}?)\s+(?:movies?|films?|special episodes?|mini\s*series)\s*:',text)
    counts=Counter(plain(name).strip() for name in names)
    if counts:
        best,count=counts.most_common(1)[0]
        if sum(1 for value in counts.values() if value==count)==1:
            return next(name.strip() for name in names if plain(name).strip()==best)
    # Revival lists commonly interleave named spin-offs with unlabelled main-series bullets.
    if re.search(r'(?i)\bDoctor Who\b',text) and re.search(r'(?im)^\s*[-*]?\s*series\s+\d',text):return 'Doctor Who'
    explicit=re.findall(r'(?im)^\s*([^\n|]{2,100}?)\s+(?:seasons?|series)\s+\d','\n'.join(main_clause(line) for line in text.splitlines()))
    distinct={plain(name).strip() for name in explicit}
    if len(distinct)==1:return explicit[0].strip()
    return ''

def infer(text,default_show='',default_numbering='season',dragon_edition='dub'):
    if default_numbering not in ('season','absolute'):raise ValueError('Choose season or absolute episode numbering.')
    if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT:raise ValueError('Paste between 1 and 200,000 characters of list text.')
    dragon_entries=dragon_ball_lines(text)
    if dragon_entries:return infer_dragon_ball(dragon_entries,dragon_edition)
    result=[];context=infer_context(text,default_show);franchise=context;parts={};current_season=None
    parent_years={}
    parent_year=re.search(r'\((\d{4})\)',context)
    if parent_year:
        context=re.sub(r'\s*\(\d{4}\)','',context).strip();franchise=context;parent_years[plain(context)]=parent_year[1]
    if plain(franchise)=='doctor who' and plain(franchise) not in parent_years and re.search(r'\b2005\b',text):parent_years[plain(franchise)]='2005'
    pokemon=plain(franchise).strip()=='pokemon'
    for number,raw in enumerate(text.splitlines(),1):
        raw=raw.strip()
        if not raw:continue
        line=clean_bullet(raw)
        line=line.replace('\u2013','-').replace('\u2014','-').replace('\u2212','-')
        source_main=main_clause(line)
        # Preserve compact range parentheses, but discard narrative placement references.
        numeric_line=source_main
        compact=re.search(r'(?i)\(\s*(?:(?:seasons?|series)\s+\d{1,3}(?:\s*(?:-|to|through)\s*\d{1,3})?(?:\s*,?\s*(?:episodes?|eps?\.?)\s*\d{1,4}(?:\s*(?:-|to|through)\s*\d{1,4})?)?|(?:episodes?|eps?\.?)\s*(?:from\s+)?\d{1,4}(?:\s*(?:-|to|through)\s*\d{1,4})?)\s*\)',line)
        if compact:numeric_line+=' '+compact[0][1:-1]
        # In a structured row the next delimiter starts the title, not an episode range.
        # E.g. Chicago PD - S01E12 - 8:30 PM must remain episode 12.
        columns=re.match(r'(?i)^(.*?)\s+[-|]\s+((?:S\d{1,3}E\d{1,4}(?:-E?\d{1,4})?|\d{1,3}x\d{1,4}))\s+[-|]\s+(.+)$',numeric_line)
        scope_line=columns[2] if columns else numeric_line
        crossing=re.search(r'(?i)S(\d+)E\d+\s*-\s*S(\d+)E\d+',scope_line)
        if crossing and crossing[1]!=crossing[2]:raise ValueError('Split the cross-season episode range at line '+str(number)+' into separate seasons.')
        scope=re.search(r'(?i)\bS(\d{1,3})\s*E(\d{1,4})(?:\s*(?:-|to|through)\s*(?:S\d+\s*)?E?(\d{1,4})(?![\d:]))?\b|\b(\d{1,3})x(\d{1,4})\b',scope_line)
        words=re.search(r'(?i)\b(?:seasons?|series)\s+(\d{1,3})(?:\s*(?:-|to|through)\s*(\d{1,3}))?\b',numeric_line)
        ep=re.search(r'(?i)\b(?:episodes?|eps?\.?)\s*(?:from\s+)?(\d{1,4})(?:\s*(?:-|to|through)\s*(?:episodes?|eps?\.?)?\s*(\d{1,4}))?\b',numeric_line)
        typed=re.match(r'(?i)^(.+?)\s+(movies?|films?|special episodes?|mini\s*series)\s*:\s*(.*)',line)
        year=re.search(r'\((18\d{2}|19\d{2}|20\d{2})\)',line)
        hint='Check the title and media type.';kind='auto';season=None;start=None;end=None;numbering='';extra_queries=[];named_title='';parent_alternatives=[];episode_aliases=[];episode_parts=[];last_season=None
        named_pair=re.match(r"^['\"\u2018\u201c](.+?)['\"\u2019\u201d]\s+(?:pilot\s+)?['\"\u2018\u201c](.+?)['\"\u2019\u201d]$",source_main,flags=re.I)
        if not named_pair:
            named_pair=re.match(r"^(.+?)\s+pilot\s+['\"\u2018\u201c](.+?)['\"\u2019\u201d]$",source_main,flags=re.I)
        quoted_colon=source_main.startswith(("'",'\"','\u2018','\u201c')) and source_main.endswith(("'",'\"','\u2019','\u201d')) and ':' in source_main
        if typed:
            family,label,title=typed.groups();family=family.strip();title=title.strip();label=plain(label)
            # Movie/special/miniseries names never replace the ongoing parent-series context.
            if not franchise:franchise=family;context=family;pokemon=plain(family)=='pokemon'
            if label.startswith(('movie','film')):
                kind='movie'
                if pokemon:
                    title=re.sub(r'(?i)\bheros\b','Heroes',title)
                    title=re.sub(r'(?i)\bspell of the unknown\b','Spell of the Unown',title)
                variants=[part.strip() for part in re.split(r'\s*/\s*',title) if part.strip()]
                extra_queries=[family+' '+part for part in variants]
                title=extra_queries[0] if extra_queries else family+' '+title
                if len(variants)>1 and not (pokemon and re.search(r'(?i)\bwhite\b',variants[0]) and re.search(r'(?i)\bblack\b',variants[-1])):
                    extra_queries=extra_queries[1:]
                else:
                    extra_queries=[]
                    if len(variants)>1:
                        for variant in variants[:-1]:
                            result.append({'source_line':number,'raw':raw,'query':(family+' '+variant)[:200],'type':'movie','year':'','hint':'Separate movie version named in the source; confirm its identity.'})
                        title=family+' '+variants[-1]
                hint='Movie label removed for matching; check the proposed title against the original wording.'
            elif label.startswith('mini'):
                title=re.split(r'(?i)\s*\(\s*(?:ep|\d+\s+episodes)',title)[0].strip()
                title=family+' '+title;kind='show'
                if ep:
                    kind='episode';season=1;start=int(ep[1]);end=int(ep[2] or start)
                    hint='Miniseries inferred as season 1. Check whether TMDB lists it separately or as specials of the parent show.'
                else:hint='Check whether this miniseries has a separate TV entry.'
            else:
                title=family+' '+title;kind='auto'
                hint='Special: search movie and TV records. If catalogued as a parent-show special, choose Episode and season 0 manually.'
        elif scope:
            season=int(scope[1] or scope[4]);start=int(scope[2] or scope[5]);end=int(scope[3] or start)
            title=(columns[1] if columns else numeric_line[:scope.start()]).strip(' |:-()') or context;kind='episode'
            if title:context=re.sub(r'^\d+\s*\|\s*','',title)
            hint='Check the parent show and episode ordering (TMDB aired order).'
        elif words:
            season=int(words[1]);prefix=numeric_line[:words.start()].strip(' |:-()')
            subtitle=numeric_line[words.end():].strip()
            explicit_parent=unquote_title(re.sub(r'^\d+\s*\|\s*','',prefix))
            if explicit_parent and not context:context=explicit_parent;franchise=explicit_parent
            if not explicit_parent:current_season=season
            # These source seasons use absolute numbering for the separate Horizons series.
            if pokemon and re.search(r'(?i)\bhorizons\b',subtitle):context=franchise+' Horizons';numbering='absolute'
            elif pokemon and 'horizons' in plain(context):numbering='absolute'
            title=explicit_parent or context
            kind='episode' if ep else 'season'
            if ep:start=int(ep[1]);end=int(ep[2] or start)
            if words[2]:
                last_season=int(words[2])
                if last_season<season or last_season-season>=100:raise ValueError('Correct the season range at line '+str(number)+'. Use up to 100 seasons per range.')
                if ep and last_season!=season:raise ValueError('Episode ranges must use a single season. Split the line into separate season blocks.')
            hint='Parent inferred from list context: '+context+'. Check the source season/episode numbering.' if context else 'No parent show inferred. Set Default parent show or enter its name before matching.'
            part=re.search(r'(?i)\bpart\s+(\d+)\b',subtitle)
            if part and start is not None:
                key=(plain(context),season);prior=parts.get(key)
                if prior and int(part[1])==prior[0]+1 and start==1:
                    start+=prior[1];end+=prior[1];hint+=' Part numbering restarted at 1; proposed continuation adds '+str(prior[1])+' episodes.'
                parts[key]=(int(part[1]),end)
        elif named_pair:
            title=unquote_title(named_pair[1]);named_title=unquote_title(named_pair[2]);kind='episode'
            hint='Named pilot/episode: match within this explicitly named parent show, including specials. Confirm the catalogue scope.'
        elif context and not quoted_colon and (source_main.startswith(("'",'"','\u2018','\u201c')) or ':' in source_main or re.search(r'(?i)\b(?:special|mini-episode)\b',line) or plain(context)=='doctor who'):
            title=context;kind='episode';named_title=source_main
            if ':' in source_main:
                prefix,tail=source_main.split(':',1)
                title=prefix.strip();named_title=tail.strip()
                if plain(title)!=plain(context):parent_alternatives=[context]
                if 'night and the doctor' in plain(title):episode_aliases=[source_main]
            named_title=unquote_title(named_title)
            aliases=re.findall(r"(?i)a\.?k\.?a\.?\s*['\"\u2018\u201c]([^'\"\u2019\u201d]+)",line)
            if aliases:episode_aliases.append(named_title);named_title=aliases[0]
            parts_match=re.search(r'(?i)\s+parts?\s+(?:one|1)\s+and\s+(?:two|2)\s*$',named_title)
            if parts_match:named_title=unquote_title(named_title[:parts_match.start()]);episode_parts=[1,2]
            count_match=re.search(r'(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+mini[- ]episodes',line)
            if count_match and not episode_parts:
                count_word=count_match[1].lower();count={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}.get(count_word,int(count_word) if count_word.isdigit() else 0)
                if 1<count<=50:episode_parts=list(range(1,count+1))
            if '/' in named_title and re.search(r'(?i)mini-episodes',line):
                episode_aliases=[unquote_title(part) for part in named_title.split('/')];episode_parts=['split']
            hint='Named episode/special: match within the parent show, including season 0. Source notes remain visible; placement instructions are not automatically expanded.'
        else:
            title=re.sub(r'\s*\((?:18|19|20)\d{2}\)\s*',' ',line).strip()
            title=unquote_title(re.sub(r'(?i)\s*[-(]\s*(?:movie|film|tv series|tv show)\)?\s*$','',title).strip())
            if re.search(r'(?i)\b(tv series|tv show)\b',line):kind='show'
            if re.search(r'(?i)\b(movie|film)\)?$',line):kind='movie'
        if kind=='auto' and typed:
            title=re.sub(r'\s*\([^)]*\)\s*',' ',title).strip()
        if start is not None:
            if start<1:raise ValueError('Episode numbers must start at 1 at line '+str(number)+'. Use season 0 for specials.')
            if end<start:raise ValueError('The episode range ends before it starts at line '+str(number)+'. Check its first and last episode numbers.')
            if end-start>=3000:raise ValueError('The episode range at line '+str(number)+' exceeds 3,000 episodes. Split it into smaller ranges.')
        title=unquote_title(re.sub(r'^\d+\s*\|\s*','',title).strip(' |'))
        if not title:title=franchise or line
        seasons=[season]
        for sn in seasons:
            row={'source_line':number,'raw':raw,'query':title[:200],'type':kind,'year':year[1] if year else parent_years.get(plain(title),''), 'hint':hint}
            if named_title:
                row['episode_title']=named_title
                row['season_hint']=str(current_season) if current_season is not None else ''
                if parent_alternatives:
                    row['parent_alternatives']=parent_alternatives;row['parent_year']=parent_years.get(plain(context),'')
                if episode_aliases:row['episode_aliases']=episode_aliases
                if episode_parts:row['episode_parts']=episode_parts
            if '(' in line and not compact:row['source_note']='Parenthetical notes kept for review; extra mini-episodes or scene-level placement instructions are not expanded automatically.'
            if extra_queries:row['alternatives']=extra_queries[:3]
            if sn is not None:row['season']=str(sn)
            if kind=='season':row['season_end']=str(last_season if last_season is not None else sn)
            if start is not None:row.update(episode=str(start),episode_end=str(end))
            if kind in ('season','episode'):row['numbering']=numbering or default_numbering
            result.append(row)
            if len(result)>MAX_ROWS:raise ValueError('Build at most 3,000 review entries at a time. Split the source into sections.')
    if not result:raise ValueError('No candidate lines found. Paste the list entries as text.')
    return result

def lookup_tmdb(value,kind,settings):
    """IDs are explicit lookups, never an interpretation of numeric film titles."""
    value=str(value).strip();scope={}
    if value.startswith('https://'):
        parsed=urllib.parse.urlsplit(value)
        if parsed.hostname not in ('themoviedb.org','www.themoviedb.org') or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('Use an official https://www.themoviedb.org movie or TV URL, or a numeric TMDB ID.')
        match=re.fullmatch(r'/(movie|tv)/(\d{1,12})(?:-[^/]+)?(?:/season/(\d{1,3})(?:/episode/(\d{1,4}))?)?/?',parsed.path)
        if not match or match[1]=='movie' and match[3]:raise ValueError('Use a TMDB movie, TV show, season or episode URL.')
        identifier=match[2];media='movie' if match[1]=='movie' else 'show'
        target=kind if media=='show' and kind in ('season','episode') else media
        if match[3] is not None:
            target='episode' if match[4] is not None else 'season';scope['season']=match[3];scope['season_end']=match[3]
            if match[4] is not None:scope.update(episode=match[4],episode_end=match[4])
            scope['episode_title']=''
    else:
        identifier=value
        if kind not in ('movie','show','season','episode'):raise ValueError('For a numeric TMDB ID, choose Movie, TV show, Season or Episode first; movie and TV IDs use separate catalogues.')
        media='movie' if kind=='movie' else 'show';target=kind
    if not re.fullmatch(r'\d{1,12}',identifier) or int(identifier)<1:raise ValueError('Enter a positive numeric TMDB ID, or an official TMDB title URL.')
    identifier=str(int(identifier))
    details=providers.cached_tmdb(('movie/' if media=='movie' else 'tv/')+identifier,settings)
    title=details.get('title') if media=='movie' else details.get('name')
    if not title or str(details.get('id'))!=identifier:raise ValueError('No title exists for that TMDB ID and media type.')
    if details.get('adult'):raise ValueError('Adult titles are not supported by this list builder.')
    scope['type']=target
    if scope.get('season') is not None:
        path='tv/'+identifier+'/season/'+str(int(scope['season']))
        if target=='episode':
            if int(scope['episode'])<1:raise ValueError('Episode numbers must start at 1. Use season 0 for specials.')
            path+='/episode/'+str(int(scope['episode']))
        metadata=providers.cached_tmdb(path,settings)
        if not metadata.get('id'):raise ValueError('That TMDB season or episode could not be verified.')
    if media=='movie':scope['episode_title']=''
    return {'type':media,'tmdb':identifier,'title':title,'year':(details.get('release_date') or details.get('first_air_date') or '')[:4],'poster':providers.image_url(details.get('poster_path')),'direct_scope':scope}

def search(query,kind,year,settings):
    query=str(query).strip()[:200]
    if not query:return []
    if kind not in ('auto','movie','show','season','episode'):raise ValueError('Choose a supported media type.')
    media='movie' if kind=='movie' else 'multi' if kind=='auto' else 'tv'
    params={'query':query,'include_adult':'false'}
    if str(year).isdigit() and media!='multi':params['year' if media=='movie' else 'first_air_date_year']=str(year)
    found=providers.cached_tmdb('search/'+media+'?'+urllib.parse.urlencode(params),settings)
    matches=[]
    results=list(found.get('results',[]))
    if media=='tv':
        original=bool(re.search(r'(?i)\boriginal\s+series\s*$',query))
        results.sort(key=lambda row:(parent_identity(row.get('name',''))!=parent_identity(query),(row.get('first_air_date') or '9999') if original else ''))
    for row in results:
        actual=row.get('media_type',media)
        if actual not in ('movie','tv') or row.get('adult'):continue
        matches.append({'tmdb':str(row['id']),'type':'show' if actual=='tv' else 'movie','title':row.get('title') or row.get('name'),'year':(row.get('release_date') or row.get('first_air_date') or '')[:4], 'poster':providers.image_url(row.get('poster_path'))})
        if len(matches)>=8:break
    return matches

def scope_proposal(row,match,settings):
    if row.get('type') not in ('season','episode') or match['type']!='show':return {}
    season=str(row.get('season',''));episode=str(row.get('episode',''));end=str(row.get('episode_end') or episode)
    if not season.isdigit() or row.get('type')=='episode' and (not episode.isdigit() or not end.isdigit() or int(episode)<1 or int(end)<int(episode)):
        return {'scope_error':'Enter a valid season and episode range.'}
    details=providers.cached_tmdb('tv/'+match['tmdb'],settings)
    seasons=[value for value in details.get('seasons',[]) if int(value.get('season_number',0))>0]
    if row.get('source_numbering')=='dub' and row.get('numbering')=='absolute' and plain(row.get('query',''))=='dragon ball z' and sum(int(value.get('episode_count') or 0) for value in seasons)!=276:
        return {'scope_error':'This guide uses the edited 276-episode DUB numbering, which differs from this TMDB record. Map the range to verified TMDB seasons/episodes, then choose Per season. The original range has not been substituted.'}
    target=int(season);note=''
    if row.get('type')=='season':
        last=str(row.get('season_end') or season)
        if not last.isdigit() or not target<=int(last)<=999 or int(last)-target>=100:return {'scope_error':'Choose a valid first/last season, up to 100 seasons per range.'}
        available={int(value.get('season_number',-1)) for value in details.get('seasons',[])}
        missing=next((number for number in range(target,int(last)+1) if number not in available),None)
        if missing is not None:return {'scope_error':'TMDB has no season '+str(missing)+' in this range. Correct the scope; no seasons will be silently dropped.'}
        return {'scope':{'season':str(target),'season_end':last},'scope_note':('Seasons '+str(target)+'-'+last+' will be added in order when saved.') if target!=int(last) else ''}
    if row.get('numbering')=='absolute' and len(seasons)!=1:
        ordered=sorted(seasons,key=lambda value:int(value['season_number']))
        if not ordered or [int(value['season_number']) for value in ordered]!=list(range(1,len(ordered)+1)) or any(int(value.get('episode_count') or 0)<1 for value in ordered):
            return {'scope_error':'Continuous numbering needs complete consecutive TMDB seasons with known episode counts. Correct the scope manually.'}
        offset=0;segments=[]
        for value in ordered:
            count=int(value['episode_count']);first=max(int(episode),offset+1);last=min(int(end),offset+count)
            if first<=last:segments.append({'season':str(value['season_number']),'episode':str(first-offset),'episode_end':str(last-offset)})
            offset+=count
        if int(end)>offset:return {'scope_error':'Continuous range ends at '+end+' but TMDB lists only '+str(offset)+' regular episodes. No episodes were dropped.'}
        label=', '.join('S'+part['season'].zfill(2)+'E'+part['episode'].zfill(2)+'-'+part['episode_end'].zfill(2) for part in segments)
        return {'scope_segments':segments,'scope_note':'Continuous episodes '+episode+'-'+end+' map to '+label+'. Specials excluded; each episode will be verified when saved.'}
    if row.get('numbering')=='absolute' and len(seasons)==1:
        target=int(seasons[0]['season_number'])
        note='Source uses absolute episode numbers. TMDB has one continuous season; proposed season '+str(target)+', episodes '+episode+'-'+end+'.'
    selected=next((value for value in details.get('seasons',[]) if int(value.get('season_number',-1))==target),None)
    if not selected:return {'scope_error':'TMDB has no season '+str(target)+'. Check the source numbering or choose another show.'}
    count=int(selected.get('episode_count') or 0)
    if int(end)>count:
        return {'scope_error':'TMDB season '+str(target)+' contains '+str(count)+' episodes, but this source range ends at '+end+'. Correct the numbering; no episodes will be silently dropped.'}
    return {'scope':{'season':str(target),'episode':episode,'episode_end':end},'scope_note':note}

def title_identity(value):
    text=plain(unquote_title(value)).strip()
    text=re.sub(r'\((?!\d+\))[^)]*\)','',text).strip()
    # Keep prequels distinct from their full episodes despite different word order.
    prequel=re.match(r'^prequel\s+(?:to\s+)?(.+)',text)
    if prequel:text=prequel[1]+' prequel'
    return re.sub(r'[^a-z0-9]+','',text)

def title_part(value):
    text=str(value).strip()
    part=re.search(r'(?i)\s*(?:[:,-]?\s*\bpart\s+(one|two|\d+)|\((\d+)\))\s*$',text)
    if not part:return title_identity(text),None
    number=part[1] or part[2];number={'one':'1','two':'2'}.get(number.lower(),number)
    return title_identity(text[:part.start()]),int(number)

def named_scopes(row,parent,settings):
    """Propose exact episode/arc identities from the parent catalogue, never made-up numbers."""
    identifier=parent['tmdb'];requested=str(row.get('episode_title','')).strip()
    if not requested:return []
    details=providers.cached_tmdb('tv/'+identifier,settings)
    aliases=[requested]+[str(value) for value in row.get('episode_aliases',[])[:5]]
    keys={title_identity(value) for value in aliases}
    keys.update(title_identity(value.rsplit(':',1)[-1]) for value in aliases if ':' in value)
    choices=[]
    for season in details.get('seasons',[]):
        if int(season.get('season_number',0))>0 and title_identity(season.get('name','')) in keys:
            choices.append(dict(parent,scope={'type':'season','season':str(season['season_number'])},scope_label='Season '+str(season['season_number'])+' / '+str(season.get('name','')),scope_note='The named story is catalogued by TMDB as a whole season. Confirm this scope.'))
    if choices:return choices
    # Specials first, then the current main-series season. Do not scan every season of a long show.
    numbers=[0]
    if str(row.get('season_hint','')).isdigit() and int(row['season_hint'])>0:numbers.append(int(row['season_hint']))
    regular=[int(value['season_number']) for value in details.get('seasons',[]) if int(value.get('season_number',0))>0]
    if len(regular)<=3:numbers=list(dict.fromkeys(numbers+regular))
    episode_rows=[]
    for season in numbers:
        if not any(int(value.get('season_number',-1))==season for value in details.get('seasons',[])):continue
        try:metadata=providers.cached_tmdb('tv/'+identifier+'/season/'+str(season),settings)
        except ValueError:continue
        for episode in metadata.get('episodes',[]):
            if not episode.get('id') or not str(episode.get('episode_number','')).isdigit():continue
            episode_rows.append((season,episode))
    parts=row.get('episode_parts',[])
    def choice(season,first,last,name):
        return dict(parent,scope={'type':'episode','season':str(season),'episode':str(first),'episode_end':str(last)},scope_label='S'+str(season)+' E'+str(first)+('-'+str(last) if last!=first else '')+' / '+name,scope_note='Named entry matched to TMDB '+('specials' if season==0 else 'season '+str(season))+'. Confirm this episode scope against the source.')
    if parts:
        matches=[]
        if parts==['split']:
            for alias in row.get('episode_aliases',[]):
                matches.append([(sn,ep) for sn,ep in episode_rows if title_part(ep.get('name',''))[0]==title_identity(alias)])
        else:
            for part in parts:
                matches.append([(sn,ep) for sn,ep in episode_rows if title_part(ep.get('name',''))==(title_identity(requested),int(part))])
        if matches and all(len(values)==1 for values in matches):
            selected=[values[0] for values in matches];seasons={value[0] for value in selected};nums=[int(value[1]['episode_number']) for value in selected]
            if len(seasons)==1 and nums==list(range(nums[0],nums[0]+len(nums))):return [choice(selected[0][0],nums[0],nums[-1],requested)]
        return []
    seen=set()
    for season,episode in episode_rows:
        name=episode.get('name','');candidate_keys={title_identity(name)}
        if ':' in name:
            candidate_keys.add(title_identity(name.rsplit(':',1)[-1]));candidate_keys.add(title_identity(name.split(':',1)[0]))
        if keys.intersection(candidate_keys) and (season,episode['episode_number']) not in seen:
            seen.add((season,episode['episode_number']));choices.append(choice(season,int(episode['episode_number']),int(episode['episode_number']),name))
    return choices

def match_batch(rows,settings):
    if not isinstance(rows,list) or not 1<=len(rows)<=20:raise ValueError('Match between 1 and 20 lines at a time.')
    if any(not isinstance(row,dict) for row in rows):raise ValueError('Invalid matching row.')
    def match(row):
        try:
            direct=bool(str(row.get('tmdb_input','')).strip());direct_scope={}
            if direct:
                choice=lookup_tmdb(row['tmdb_input'],row.get('type','auto'),settings);direct_scope=choice.pop('direct_scope');row=dict(row,**direct_scope);choices=[choice]
            else:choices=search(row.get('query',''),row.get('type','auto'),row.get('year',''),settings)
            alternatives=row.get('alternatives',[])
            if not isinstance(alternatives,list):alternatives=[]
            if not choices:
                for query in alternatives[:3]:
                    choices=search(str(query),row.get('type','auto'),row.get('year',''),settings)
                    if choices:break
            if row.get('episode_title') and row.get('type') in ('season','episode'):
                parents=list(choices)
                fallback=[] if direct else row.get('parent_alternatives',[])
                if not isinstance(fallback,list):fallback=[]
                if isinstance(fallback,list):
                    for query in fallback[:2]:parents.extend(search(str(query),'show',row.get('year') or row.get('parent_year',''),settings))
                named=[];seen=set()
                # Exact parent-name suggestions are preferred over similarly named documentaries.
                parent_keys={parent_identity(row.get('query',''))}|{parent_identity(value) for value in fallback if isinstance(value,str)}
                if direct:parent_keys.update(parent_identity(value['title']) for value in choices)
                for parent in parents:
                    if parent['type']!='show' or parent['tmdb'] in seen or parent_identity(parent['title']) not in parent_keys:continue
                    seen.add(parent['tmdb'])
                    try:named.extend(named_scopes(row,parent,settings))
                    except ValueError:pass
                if named:return {'matches':named}
                return {'matches':[dict(parent,scope_error='No exact episode or story-arc match was found in this parent show. Edit Named episode / story, or clear that field and enter a verified season/episode scope.') for parent in parents if parent['type']=='show'][:8]}
            for choice in choices:
                if row.get('type') in ('season','episode'):
                    try:choice.update(scope_proposal(row,choice,settings))
                    except ValueError:choice['scope_error']='Could not verify the TV numbering. Retry matching before confirming.'
            if direct:
                for choice in choices:choice['scope']={**direct_scope,**choice.get('scope',{})}
            return {'matches':choices}
        except ValueError as error:return {'matches':[],'error':str(error) if row.get('tmdb_input') else 'Matching unavailable. Edit this query and retry.'}
    with ThreadPoolExecutor(max_workers=4) as pool:return list(pool.map(match,rows))

def confirmed_items(rows,settings,normalize):
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_ROWS:raise ValueError('Confirm between 1 and 3,000 entries.')
    expanded=[]
    for row in rows:
        if isinstance(row,dict) and row.get('confirmed') is True and row.get('type')=='episode' and row.get('numbering')=='absolute':
            identifier=str(row.get('tmdb',''))
            if not identifier.isdigit() or int(identifier)<1:raise ValueError('Choose an exact parent-show match.')
            proposal=scope_proposal(row,{'type':'show','tmdb':identifier},settings)
            if proposal.get('scope_error'):raise ValueError(proposal['scope_error'])
            scopes=proposal.get('scope_segments') or [proposal.get('scope',{})]
            expanded.extend(dict(row,**scope,numbering='season') for scope in scopes)
        else:expanded.append(row)
    rows=expanded
    result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('confirmed') is not True:raise ValueError('Confirm every included entry before saving.')
        kind=row.get('type');identifier=str(row.get('tmdb',''))
        if kind not in ('movie','show','season','episode') or not identifier.isdigit() or int(identifier)<1:raise ValueError('Choose a matched movie or show for every entry.')
        base=('movie/' if kind=='movie' else 'tv/')+identifier
        details=providers.cached_tmdb(base,settings)
        title=details.get('title') or details.get('name')
        if not title:raise ValueError('A confirmed title is no longer available. Match it again.')
        item={'type':kind,'title':title,'year':(details.get('release_date') or details.get('first_air_date') or '')[:4]}
        if kind in ('season','episode'):
            season=str(row.get('season',''));episode=str(row.get('episode',''));end=str(row.get('episode_end') or episode)
            if not season.isdigit() or int(season)>999 or kind=='episode' and (not episode.isdigit() or not end.isdigit() or not 1<=int(episode)<=int(end)<=9999 or int(end)-int(episode)>=3000):raise ValueError('Choose valid season and episode numbers (up to 3,000 episodes per range).')
            path=base+'/season/'+str(int(season))
            if kind=='season':
                last=str(row.get('season_end') or season)
                if not last.isdigit() or not int(season)<=int(last)<=999 or int(last)-int(season)>=100:raise ValueError('Choose a valid first/last season, up to 100 seasons per range.')
                if int(last)>int(season):
                    if len(result)+int(last)-int(season)+1>10000:raise ValueError('Expanded lists support up to 10,000 entries.')
                    for number in range(int(season),int(last)+1):
                        metadata=providers.cached_tmdb(base+'/season/'+str(number),settings)
                        if not metadata.get('id'):raise ValueError(title+' season '+str(number)+' could not be verified. Correct the season range before saving.')
                        value=dict(item,show_tmdb=identifier,show_title=title,season=str(number),title=metadata.get('name') or title)
                        result.append(dict(normalize(value),status='unchecked'))
                    continue
            if kind=='episode' and int(end)>int(episode):
                count=int(end)-int(episode)+1
                if len(result)+count>10000:raise ValueError('Expanded lists support up to 10,000 entries. Split this watch order.')
                metadata=providers.cached_tmdb(path,settings)
                episodes={int(value['episode_number']):value for value in metadata.get('episodes',[]) if value.get('id') and str(value.get('episode_number','')).isdigit()}
                missing=[number for number in range(int(episode),int(end)+1) if number not in episodes]
                if missing:raise ValueError(title+' season '+season+' has no verified episode '+str(missing[0])+'. Correct the source-to-TMDB numbering before saving.')
                for number in range(int(episode),int(end)+1):
                    value=dict(item,show_tmdb=identifier,show_title=title,season=season,episode=str(number),title=episodes[number].get('name') or title)
                    result.append(dict(normalize(value),status='unchecked'))
                continue
            if kind=='episode':path+='/episode/'+str(int(episode))
            scope=providers.cached_tmdb(path,settings)
            if not scope.get('id'):raise ValueError('That season or episode could not be verified. Correct its scope.')
            item.update(show_tmdb=identifier,show_title=title,season=season,title=scope.get('name') or title)
            if kind=='episode':item['episode']=episode
        else:item['tmdb']=identifier
        if len(result)>=10000:raise ValueError('Expanded lists support up to 10,000 entries.')
        result.append(dict(normalize(item),status='unchecked'))
    return result
