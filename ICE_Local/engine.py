"""ICE Local. Deterministic source extraction, evidence, checks and ANI builder.

Never reads expected XML fixtures and never performs network requests.
Ambiguous layout, names, affiliations and mathematics stay in human review.
"""
from __future__ import annotations
import csv, hashlib, io, json, os, re, shutil, statistics, subprocess, tempfile, contextvars
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import fitz
from lxml import etree, html

VERSION = '1.3.0'
ANI = 'http://www.elsevier.com/xml/ani/ani'
CE = 'http://www.elsevier.com/xml/ani/common'
XML = 'http://www.w3.org/XML/1998/namespace'
NS = {'a': ANI, 'ce': CE}
ID_RE = re.compile(r'(\d{4}\.\d{4,5})(?:v(\d+))?')
STAMP_RE = re.compile(r'arXiv\s*:\s*(\d{4}\.\d{4,5})(?:v(\d+))?', re.I)
DOC_WORDS = contextvars.ContextVar('document_words', default=frozenset())
EMAIL_RE = re.compile(r'[\w.!#$%&\x27*+/=?^`{|}~-]+@[\w.-]+\.[A-Za-z]{2,}', re.U)
ORCID_RE = re.compile(r'(?<!\d)(\d{4}-\d{4}-\d{4}-[\dX]{4})(?!\d)', re.I)
STOP_HEAD = re.compile(r'^(?:\d+(?:\.\d+)*\s+|[IVX]+\.\s*)?(?:INTRODUCTION|ACKNOWLEDGMENTS?|ACKNOWLEDGEMENTS?|APPENDIX|CONCLUSIONS?|DATA AVAILABILITY|SUPPLEMENT)', re.I)
REF_HEAD = re.compile(r'^(?:\d+\.?\s+)?(?:References|Bibliography|Reference List|List of Cited References|Recommended Reading|Further Reading)\s*$', re.I)
ORG = re.compile(r'\b(?:university|université|universität|universidad|universidade|universit[aàá]|institute|institut|laborator\w*|department|dept\.?|school|college|faculty|centre|center|research|academy|academia|hospital|clinic|observatory|foundation|polytechnic|cnrs|mit|umr|inc\.?|corporation|division|group|unit)\b', re.I)
STATES = {
    'USA': set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split()),
    'AUS': set('ACT NSW NT QLD SA TAS VIC WA'.split()),
    'CAN': set('AB BC MB NB NL NS NT NU ON PE QC SK YT'.split()),
}
STATE_NAMES = {
    'USA': {'Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut','Delaware','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa','Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan','Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire','New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio','Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','South Dakota','Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia','Wisconsin','Wyoming','District of Columbia'},
    'AUS': {'Australian Capital Territory','New South Wales','Northern Territory','Queensland','South Australia','Tasmania','Victoria','Western Australia'},
    'CAN': {'Alberta','British Columbia','Manitoba','New Brunswick','Newfoundland and Labrador','Nova Scotia','Northwest Territories','Nunavut','Ontario','Prince Edward Island','Quebec','Québec','Saskatchewan','Yukon'},
}
STREET = re.compile(r'\b(?:street|st\.?|road|rd\.?|drive|dr\.?|avenue|ave\.?|boulevard|blvd\.?|suite|building|floor|campus|via|bd\.?|lane|ln\.?|highway)\b',re.I)
SPECIAL_ADDRESS = re.compile(r'\b(?:present address|current address|formerly at|former address|now at|correspondence address|corresponding address|work (?:was )?performed at)\b',re.I)
COUNTRIES = {'USA':'USA','U.S.A.':'USA','United States':'USA','United States of America':'USA','UK':'GBR','U.K.':'GBR','United Kingdom':'GBR','England':'GBR','Scotland':'GBR','Wales':'GBR','Northern Ireland':'GBR','Canada':'CAN','Australia':'AUS','France':'FRA','Germany':'DEU','India':'IND','Sri Lanka':'LKA','China':'CHN','P. R. China':'CHN','P.R. China':'CHN','People’s Republic of China':'CHN',"People's Republic of China":'CHN','Japan':'JPN','Italy':'ITA','Spain':'ESP','Morocco':'MAR','Portugal':'PRT','Belgium':'BEL','Finland':'FIN','Poland':'POL','Slovakia':'SVK','Czechia':'CZE','Czech Republic':'CZE','South Africa':'ZAF','Netherlands':'NLD','Switzerland':'CHE','Sweden':'SWE','Norway':'NOR','Denmark':'DNK','Austria':'AUT','New Zealand':'NZL','Brazil':'BRA','Mexico':'MEX','South Korea':'KOR','Republic of Korea':'KOR','Singapore':'SGP','Hong Kong':'HKG','Macau':'MAC','Taiwan':'TWN','Republic of China':'TWN','Israel':'ISR','Palestine':'PSE','Russia':'RUS','Ukraine':'UKR','Greece':'GRC','Turkey':'TUR','Türkiye':'TUR','Ireland':'IRL'}
try:
    COUNTRIES.update(json.loads((Path(__file__).parent/'config'/'country_codes.json').read_text(encoding='utf-8')))
except (OSError, json.JSONDecodeError):
    pass
# Explicit editorial aliases take precedence over generated display names.
COUNTRIES.update({'Scotland':'GBR','Wales':'GBR','Northern Ireland':'GBR','Hong Kong':'HKG','Hong Kong, China':'HKG','Hong Kong SAR':'HKG','Hong Kong SAR China':'HKG','Macao':'MAC','Macau':'MAC','Taiwan':'TWN','Republic of China':'TWN','Türkiye':'TUR','Turkey':'TUR'})
COUNTRY_END = re.compile(r'(?:'+ '|'.join(re.escape(k) for k in sorted(COUNTRIES,key=len,reverse=True)) +r')\.?\s*$',re.I)

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
def digest(v): return hashlib.sha256((v if isinstance(v, bytes) else json.dumps(v, sort_keys=True, ensure_ascii=False).encode())).hexdigest()
def nfc(t): return unicodedata.normalize('NFC', t)
def fold(t): return ''.join(c for c in unicodedata.normalize('NFKD', t).casefold() if not unicodedata.combining(c))
def norm(t): return re.sub(r'\s+', ' ', nfc(t)).strip().casefold()
def country_code_for(value):
    """Resolve a country name or an existing ISO alpha-3 value; preserve unknown input elsewhere."""
    text=str(value or '').strip()
    if re.fullmatch(r'[A-Za-z]{3}',text) and text.upper() in set(COUNTRIES.values()):return text.upper()
    key=norm(text.rstrip('.'))
    for name,code in COUNTRIES.items():
        if norm(name.rstrip('.'))==key:return code
    return ''
def compact(t): return re.sub(r'[^a-z0-9]', '', fold(t))
def arxiv_id(t):
    """The bare arXiv ID in a value such as 'arXiv:2408.09673v2'."""
    m=ID_RE.search(str(t or ''));return m[1] if m else norm(str(t or ''))
def evidence(lines): return [{'page':l['page'], 'bbox':l['bbox'], 'line_id':l['id'], 'text':l['text']} for l in lines]
def issue(rule, field, message, ev=None, severity='INFO'):
    fingerprint=digest([rule, field, message, ev or []])
    return {'id':fingerprint[:18], 'rule_id':rule, 'field':field, 'message':message, 'severity':severity, 'evidence':ev or [], 'status':'OPEN', 'fingerprint':fingerprint}

def join_text(lines):
    s='\n'.join(l['text'] if isinstance(l,dict) else l for l in lines)
    # Only physical line-end hyphens are removed. The raw evidence remains immutable.
    def unwrap(m):
        left,right=m.groups(); joined=left+right; hyphenated=left+'-'+right
        return joined if joined.casefold() in DOC_WORDS.get() and hyphenated.casefold() not in DOC_WORDS.get() else hyphenated
    s=re.sub(r'(\w+)-\s*\n\s*([a-z]\w*)', unwrap, s)
    s=re.sub(r'\s+', ' ', s).strip()
    # PDF accent glyph extraction: P´erez / L¨owen, never broad accent removal.
    accents={'´':'\u0301','`':'\u0300','¨':'\u0308','ˆ':'\u0302','ˇ':'\u030c','˜':'\u0303'}
    for a,c in accents.items(): s=re.sub(re.escape(a)+r'([A-Za-z])', lambda m:nfc(m[1]+c), s)
    return nfc(s)

def secure_xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise ValueError('DTD/entity declarations are not accepted.')
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False))

def xml_source_role(root):
    tag=etree.QName(root).localname.casefold()
    names={etree.QName(n).localname.casefold() for n in root.iter() if isinstance(n.tag,str)}
    if tag in ('units','unit','bibrecord','bibdataset','article-set'):return 'OTHER'
    if 'item' in names and 'version' in names:return 'SCRAPPING'
    if tag in ('record','feed','entry','oai-pmh') or {'keyname','forenames'} & names:return 'API'
    if tag=='arxiv':return 'API' if 'authors' in names or 'abstract' in names else 'SCRAPPING'
    if 'record' in names or 'arxiv' in names:return 'API'
    return 'XML'

def source_data(files, root, feeder=None):
    values={'api_authors':[], 'api_title':'', 'api_abstract':'', 'html_title':'', 'html_id':'', 'html_version':None, 'scrapping_id':'','scrapping_version':None}
    errors=[]
    for role,f in files.items():
        if not f or role=='PDF': continue
        try:
            data=(root/f['path']).read_bytes()
            if feeder is not None:
                feeder[role]={'name':f['name'],'sha256':digest(data),'format':role,
                              'extraction':'structured XML/HTML','text':'','values':{}}
            if role=='API':
                r=secure_xml(data)
                records=r.xpath('.//*[local-name()="record"]')
                entries=r.xpath('.//*[local-name()="entry"]')
                if len(records)>1 or len(entries)>1:raise ValueError('API XML contains multiple articles. Supply one article per support file.')
                if records:r=records[0]
                elif entries:r=entries[0]
                def txt(name):return r.xpath('string(.//*[local-name()="'+name+'"][1])').strip()
                values.update(api_id=txt('id'),api_title=txt('title'),api_abstract=txt('abstract'))
                for a in r.xpath('.//*[local-name()="author"]'):
                    key=a.xpath('string(*[local-name()="keyname"])').strip(); given=a.xpath('string(*[local-name()="forenames"])').strip()
                    suffix=a.xpath('string(*[local-name()="suffix"])').strip()
                    if key:values['api_authors'].append({'surname':key,'given_name':given,**({'suffix':suffix} if suffix else {})})
                if feeder is not None:feeder[role]['text']=' '.join(' '.join(r.itertext()).split())
            elif role=='SCRAPPING':
                r=secure_xml(data)
                values['scrapping_id']=r.xpath('string(.//*[local-name()="item"]/@id)')
                v=r.xpath('string(.//*[local-name()="version"]/@number)'); m=re.search(r'(?:v)?(\d+)',v,re.I)
                values['scrapping_version']=int(m[1]) if m else None
                if feeder is not None:feeder[role]['text']=' '.join(' '.join(r.itertext()).split())
            elif role=='HTML':
                r=html.fromstring(data)
                for name,key in [('citation_title','html_title'),('citation_arxiv_id','html_id')]:
                    vals=r.xpath('//meta[@name="'+name+'"]/@content');values[key]=vals[0] if vals else ''
                if not values['html_title']:
                    vals=r.xpath('//h1[contains(@class,"title")]');values['html_title']=re.sub(r'^Title:\s*','',vals[0].text_content()).strip() if vals else ''
                current=' '.join(r.xpath('//*[contains(@class,"arxividv") or (self::span and @class="arxivid")]/text()'))
                ids=ID_RE.findall(current); versions={int(v) for i,v in ids if v}
                if len(versions)==1:values['html_version']=next(iter(versions))
                if feeder is not None:
                    for node in r.xpath('//script|//style|//noscript'):node.drop_tree()
                    feeder[role]['text']=' '.join(r.text_content().split())
            if feeder is not None:
                feeder[role]['values']={k:v for k,v in values.items() if k.startswith(role.lower()+'_')}
                if len(feeder[role]['text'])>1000000:
                    feeder[role]['text']=feeder[role]['text'][:1000000]
                    feeder[role]['truncated']=True
                    errors.append(issue('PKG-003',role,role+' normalized text was truncated in the feeder; inspect the original source.'))
        except Exception as e:errors.append(issue('PKG-002',role,'Cannot read '+role+': '+str(e)))
    return values,errors

def ocr_page(page, page_num, executable):
    if not executable: raise RuntimeError('Local Tesseract OCR is not installed. Set its path in Settings or edit this article manually.')
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'page.png';scale=2.5;page.get_pixmap(matrix=fitz.Matrix(scale,scale)).save(p)
        cp=subprocess.run([executable,str(p),'stdout','-l','eng','tsv'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180,check=True)
        groups=defaultdict(list)
        for row in csv.DictReader(io.StringIO(cp.stdout),delimiter='\t'):
            if row.get('text','').strip() and row.get('level')=='5':groups[(row['block_num'],row['par_num'],row['line_num'])].append(row)
        lines=[]
        for n,words in enumerate(groups.values()):
            boxes=[[float(w['left'])/scale,float(w['top'])/scale,(float(w['left'])+float(w['width']))/scale,(float(w['top'])+float(w['height']))/scale] for w in words]
            bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
            lines.append({'id':f'p{page_num}-ocr{n}','page':page_num,'block':int(words[0]['block_num']),'text':' '.join(w['text'] for w in words),'bbox':bbox,'size':bbox[3]-bbox[1],'bold':False,'direction':[1,0],'spans':[],'origin':'OCR','ocr_confidence':statistics.mean(float(w['conf']) for w in words),
                          'words':[{'text':w['text'],'bbox':b,'confidence':float(w['conf'])} for w,b in zip(words,boxes)]})
        return lines

def extract_layout(pdf, settings, progress=lambda x:None):
    doc=fitz.open(pdf);pages=[];issues=[]
    tess=settings.get('tesseract_path') or shutil.which('tesseract')
    if not tess and os.name=='nt':
        candidate=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Tesseract-OCR/tesseract.exe'
        if candidate.exists():tess=str(candidate)
    for pi,page in enumerate(doc):
        progress(f'Reading page {pi+1} of {len(doc)}')
        lines=[]
        for bi,b in enumerate(page.get_text('dict')['blocks']):
            for li,l in enumerate(b.get('lines',[])):
                spans=l.get('spans',[]);text=''.join(s['text'] for s in spans)
                if not text.strip():continue
                lines.append({'id':f'p{pi+1}-b{bi}-l{li}','page':pi+1,'block':bi,'text':text,'bbox':list(l['bbox']),'size':max(s['size'] for s in spans),'bold':sum(len(s['text']) for s in spans if s['flags']&16)>len(text)*.5,'direction':list(l['dir']),'spans':[{'text':s['text'],'bbox':list(s['bbox']),'size':s['size'],'flags':s['flags'],'font':s['font']} for s in spans],'origin':'NATIVE'})
        native_chars=sum(len(l['text']) for l in lines if l['direction'][0]>.8)
        replacement=sum(l['text'].count('\ufffd') for l in lines)
        unreliable=native_chars<30 or (replacement>5 and replacement/max(native_chars,1)>.02)
        if unreliable:
            try:
                ol=ocr_page(page,pi+1,tess)
                if not ol:raise RuntimeError('Local OCR returned no readable text.')
                lines=ol
                issues.append(issue('PDF-002','extraction',f'Page {pi+1} used local OCR. Check its text and layout.',evidence(ol[:1])))
                if statistics.mean(l['ocr_confidence'] for l in ol)<75:
                    issues.append(issue('PDF-003','extraction',f'Page {pi+1} OCR confidence is below 75; inspect its image and correct metadata.',evidence(ol[:1])))
            except Exception as e:issues.append(issue('PDF-002','extraction',f'Page {pi+1}: {e}'))
        links=[{'bbox':list(l['from']),'uri':l.get('uri','')} for l in page.get_links() if l.get('uri')]
        native_words=[{'text':str(w[4]),'bbox':list(w[:4]),'block':w[5],'line':w[6]} for w in page.get_text('words')]
        pages.append({'number':pi+1,'width':page.rect.width,'height':page.rect.height,'rotation':page.rotation,
                      'text_origin':'OCR' if lines and lines[0]['origin']=='OCR' else 'NATIVE',
                      'lines':lines,'words':[w for l in lines for w in l['words']] if lines and lines[0]['origin']=='OCR' else native_words,'links':links})
    return {'version':1,'engine_version':VERSION,'pdf_sha256':digest(Path(pdf).read_bytes()),'pages':pages},issues

def initials(given):
    parts=re.findall(r'[^\W\d_]+(?:-[^\W\d_]+)*',given,re.U)
    return ''.join('-'.join(x[0].upper()+'.' for x in part.split('-')) for part in parts)

def name_tokens(value):
    return re.findall(r'[^\W\d_]+',fold(str(value or '')),re.U)

def compatible_given_name(api_given,pdf_given):
    api=name_tokens(api_given);pdf=name_tokens(pdf_given)
    return bool(api and pdf and all(a[0]==p[0] for a,p in zip(api,pdf)))

def parse_affiliation(text, marker, ev, printed_marker=True):
    result={'id':'aff-'+str(marker),'marker':str(marker),'printed_marker':printed_marker,'organizations':[],'address_parts':[],'city':'','state':'','postal_code':'','country_text':'','country_code':'','source_text':text,'evidence':ev,'component_warnings':[]}
    chunks=[x.strip().strip('.') for x in text.split(',') if x.strip()]
    if len(chunks)>=2 and norm(chunks[-1])=='china' and norm(chunks[-2]) in ('hong kong','hong kong sar','hong kong special administrative region'):
        result['country_code']='HKG';result['country_text']=', '.join(chunks[-2:]);chunks=chunks[:-2]
    if chunks and not result['country_code']:
        for country,code in sorted(COUNTRIES.items(),key=lambda item:len(item[0]),reverse=True):
            if norm(chunks[-1])==norm(country.rstrip('.')):
                result['country_code']=code;result['country_text']=chunks.pop();break
    if not result['country_code']:result['component_warnings'].append('Country is not explicitly recognized at the end of this PDF affiliation.')
    consumed=set();state_codes=STATES.get(result['country_code'],set());state_aliases=sorted(state_codes|STATE_NAMES.get(result['country_code'],set()),key=len,reverse=True)
    def state_suffix(value):
        for alias in state_aliases:
            match=re.search(r'(?<!\w)'+re.escape(alias)+r'\s*$',value,re.I)
            if match:return value[match.start():].strip(),value[:match.start()].strip(' ,')
        return '',value.strip()
    postal_pattern=r'(?:\d{4,6}|[A-Z]\d[A-Z]\s*\d[A-Z]\d)'
    for i in range(len(chunks)-1,-1,-1):
        c=chunks[i]
        postal_match=re.fullmatch(r'(.+?)\s+('+postal_pattern+r')',c,re.I)
        if postal_match:
            state,city=state_suffix(postal_match[1])
            if state and not ORG.search(city):
                result['state'],result['postal_code']=state,postal_match[2];consumed.add(i)
                if city:result['city']=city
                elif i and i-1 not in consumed and not STREET.search(chunks[i-1]) and not ORG.search(chunks[i-1]):result['city']=chunks[i-1];consumed.add(i-1)
                continue
        state,city=state_suffix(c)
        if state and not ORG.search(c):
            result['state']=state;consumed.add(i)
            if city:result['city']=city
            if i+1<len(chunks) and re.fullmatch(postal_pattern,chunks[i+1],re.I):result['postal_code']=chunks[i+1];consumed.add(i+1)
            if i and i-1 not in consumed and not STREET.search(chunks[i-1]) and not ORG.search(chunks[i-1]):result['city']=chunks[i-1];consumed.add(i-1)
            elif i+1<len(chunks) and i+1 not in consumed and not ORG.search(chunks[i+1]):result['city']=chunks[i+1];consumed.add(i+1)
            continue
    # Parse explicit postal and state syntax before attempting an unlabelled city.
    # This prevents a street number such as "4750 Walnut Street" from becoming a city.
    for i in range(len(chunks)-1,-1,-1):
        if i in consumed:continue
        c=chunks[i]
        if not result['postal_code'] and state_codes:
            m=re.fullmatch(r'(?:(.+?)\s+)?([A-Z]{2,3})\s+(\d{4,6}|[A-Z]\d[A-Z]\s*\d[A-Z]\d)',c)
            if m and m[2] in state_codes:
                result['state'],result['postal_code']=m[2],m[3]
                if m[1] and not STREET.search(m[1]):result['city']=m[1].strip()
                elif i and not STREET.search(chunks[i-1]) and (not ORG.search(chunks[i-1]) or re.fullmatch(r'College Park',chunks[i-1],re.I)):
                    result['city']=chunks[i-1];consumed.add(i-1)
                consumed.add(i);continue
        if result['postal_code']:continue
        m=re.fullmatch(r'((?:[A-Z]{2}-)?\d{4,6})\s+(.+)',c)
        if m and not STREET.search(m[2]) and not ORG.search(m[2]):
            result['postal_code'],result['city']=m[1],m[2].strip();consumed.add(i);continue
        m=re.fullmatch(r'(.+?)\s+((?:[A-Z]{2}-)?\d{4,6})',c)
        if m and not STREET.search(m[1]) and not ORG.search(m[1]):
            result['city'],result['postal_code']=m[1].strip(),m[2];consumed.add(i);continue
    if not result['city'] and chunks:
        i=next((i for i in range(len(chunks)-1,-1,-1) if i not in consumed and not STREET.search(chunks[i]) and not ORG.search(chunks[i]) and not re.fullmatch(r'[A-Z]{2,3}\s+\d{4,6}',chunks[i])),None)
        if i is not None:result['city']=chunks[i];consumed.add(i)
    if not result['postal_code'] and result['city'] and chunks:
        i=next((i for i,c in enumerate(chunks) if i in consumed and c==result['city']),len(chunks)-1)
        if i and i-1 not in consumed and re.fullmatch(r'\d{4,6}',chunks[i-1]):
            result['postal_code']=chunks[i-1];consumed.add(i-1)
    organization_indices=[i for i,c in enumerate(chunks) if i not in consumed and (ORG.search(c) or c in ('MIT','CNRS'))]
    first_org=min(organization_indices,default=-1);last_org=max(organization_indices,default=-1)
    for i,c in enumerate(chunks):
        if i in consumed:continue
        if ORG.search(c) or c in ('MIT','CNRS'):
            result['organizations'].append(c)
        elif first_org>=0 and first_org<i<last_org and result['organizations'] and not STREET.search(c):
            # Keep department/subunit wording such as "Telematics and Communications"
            # with the preceding organization when it sits between two recognized
            # institution chunks, instead of misclassifying it as a street address.
            result['organizations'][-1]+=', '+c
        else:
            result['address_parts'].append(c)
            if re.search(r'\d{4,6}',c) and not STREET.search(c):
                result['component_warnings'].append('Postal or locality wording was not safely separated: '+c)
    if not result['organizations']:result['component_warnings'].append('No organization component was safely identified.')
    return result

SUPERSCRIPT_DIGITS = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠ', '0123456789abcdef')
FRONT_HEADING = re.compile(r'^\s*(?:(?:\d+(?:\.\d+)*|[IVX]+)[.\s]+)?(?:abstract|synopsis|summary|key\s*words|keywords|index terms|introduction|accepted|received|submitted)\b', re.I)

def front_marker(text, allow_letters=False):
    """Return a printed affiliation label, preserving the unmodified PDF line as evidence."""
    normalized=text.translate(SUPERSCRIPT_DIGITS)
    label=r'\d{1,2}|[★*∗†‡✉]'
    if allow_letters:label+=r'|[a-fA-F]'
    match=re.match(r'^\s*('+label+r')\s*[.)]?(?:\s+|(?=[A-ZÀ-Ž])|$)(.*)$',normalized)
    return (match[1].lower(),match[2].strip()) if match else (None,text.strip())

def author_markers(suffix):
    """Read only the indicator immediately following an author surname."""
    suffix=re.sub(r'^\s*(?:(?:ORCID|ID)\s*[:#]?\s*)+', '', suffix.lstrip(' ,'), flags=re.I)
    if re.match(r'^(?:and\b|&\s)',suffix,re.I):return []
    token=r'(?:\d{1,2}|[⁰¹²³⁴⁵⁶⁷⁸⁹]+|[ᵃᵇᶜᵈᵉᶠ]+|[a-f](?![A-Za-z])|[★*∗†‡✉])'
    match=re.match(r'^('+token+r'(?:[\s,;]*'+token+r')*)',suffix,re.I)
    if not match:return []
    raw=match[1].translate(SUPERSCRIPT_DIGITS)
    return re.findall(r'\d{1,2}|[a-f]|[★*∗†‡✉]',raw.lower())

def front_affiliations(horizontal, author_end, height, author_markers_seen):
    """Locate compact front-matter address lines using labels, organizations and geometry."""
    allow_letters=any(re.fullmatch(r'[a-f]',m,re.I) for m in author_markers_seen)
    known_markers={str(m).casefold() for m in author_markers_seen}
    # Some publishers place author affiliation footnotes at the bottom of page one,
    # after the abstract and opening paragraph. Keep those in scope, but only accept
    # deep-page starts when their printed marker is attached to a known author.
    top_limit=min(height*.67,max(height*.45,author_end+190))
    limit=height*.97
    candidates=sorted((l for l in horizontal if author_end-3<=l['bbox'][1]<limit),key=lambda l:(l['bbox'][1],l['bbox'][0]))
    affiliations=[];used=[];current=None;previous=None
    def flush():
        nonlocal current
        if current:
            source=join_text(current['texts'])
            marker=current['marker'] or str(len(affiliations)+1)
            parsed=parse_affiliation(source,marker,evidence(current['lines']),bool(current['marker']))
            # Some PDFs repeat the same affiliation before each author's contact row.
            # Keep every source occurrence as evidence, but emit one affiliation record.
            duplicate=next((a for a in affiliations if a['marker']==parsed['marker'] and norm(a['source_text'])==norm(parsed['source_text'])),None)
            if duplicate:
                existing={e['line_id'] for e in duplicate['evidence']}
                duplicate['evidence'].extend(e for e in parsed['evidence'] if e['line_id'] not in existing)
            else:affiliations.append(parsed)
            current=None
    for index,l in enumerate(candidates):
        raw=l['text'].strip()
        if re.search(r'arXiv\s*:',raw,re.I):continue
        # Contact rows can interrupt repeated affiliations; they are not address text.
        if EMAIL_RE.search(raw) or ORCID_RE.search(raw):
            if current:flush()
            previous=None
            continue
        if SPECIAL_ADDRESS.search(raw):
            if current:flush()
            continue
        if current and abs(l['bbox'][0]-current['lines'][0]['bbox'][0])>65:
            first=current['lines'][0]
            same_centered_block=(l['block']==first['block'] and
                                 l['bbox'][0]<=first['bbox'][2]+12 and
                                 l['bbox'][2]>=first['bbox'][0]-12)
            if not same_centered_block:continue
        if FRONT_HEADING.match(raw):
            if current:flush()
            if used:break
            continue
        marker,body=front_marker(raw,allow_letters)
        # A label alone is insufficient: it must introduce an organization, possibly on the next line.
        next_text=candidates[index+1]['text'] if index+1<len(candidates) and candidates[index+1]['bbox'][1]-l['bbox'][3]<18 else ''
        marked_start=bool(marker and (ORG.search(body) or ORG.search(next_text)))
        deep_marked_start=bool(marked_start and marker.casefold() in known_markers)
        if l['bbox'][1]>top_limit and not deep_marked_start and not current:
            continue
        unmarked_start=bool(ORG.search(raw[:95]) and len(raw)<220 and not EMAIL_RE.search(raw))
        if not current:
            if l['bbox'][1]>author_end+105 and not used and not deep_marked_start:continue
            if not (marked_start or unmarked_start):continue
            current={'marker':marker if marked_start else None,'texts':[body if marked_start else raw],'lines':[l]}
            used.append(l);previous=l;continue
        gap=l['bbox'][1]-previous['bbox'][3]
        if COUNTRY_END.search(current['texts'][-1]) and not (marked_start or unmarked_start):flush();break
        if gap>max(16,previous['size']*1.7) and not (marked_start or unmarked_start):flush();break
        if marked_start or (unmarked_start and not marker and
                            (COUNTRY_END.search(current['texts'][-1]) or gap>max(5,previous['size']*.7))):
            flush();current={'marker':marker if marked_start else None,'texts':[body if marked_start else raw],'lines':[l]}
        elif gap<max(20,previous['size']*2) and not EMAIL_RE.search(raw) and len(raw)<230:
            current['texts'].append(raw);current['lines'].append(l)
        else:flush();break
        used.append(l);previous=l
    flush()
    # A single unmarked address may be linked to every author; several remain reviewable.
    return affiliations,used

def named_affiliation_statements(layout, authors):
    """Extract explicit 'Author is/are with Institution' statements on page one."""
    if not layout.get('pages') or not authors:return [],{}
    lines=layout['pages'][0]['lines'];pieces=[];spans=[];offset=0
    for line in lines:
        if line.get('direction',[1,0])[0]<.8:continue
        value=line.get('text','').strip()
        if not value:continue
        if pieces:offset+=1
        start=offset;pieces.append(value);offset+=len(value);spans.append((start,offset,line))
    text=' '.join(pieces)
    verbs=list(re.finditer(r'\b(?:is|are)\s+(?:with|at|from)\s+',text,re.I))
    statements=[];affiliations=[];links={}
    name_token=re.compile(r"[A-ZÀ-ÖØ-Þ][\w'’.-]*(?:\s+[A-ZÀ-ÖØ-Þ][\w'’.-]*){0,5}",re.U)
    for verb in verbs:
        prefix_start=max(0,verb.start()-180);prefix=text[prefix_start:verb.start()]
        matched=[]
        for author in authors:
            given=str(author.get('given_name','')).strip();surname=str(author.get('surname','')).strip()
            if not surname:continue
            full=(given+' '+surname).strip()
            pattern=re.compile(r'(?<![\w])'+r'\s+'.join(re.escape(t) for t in full.split())+r'(?![\w])',re.I)
            occurrences=list(pattern.finditer(prefix))
            for occurrence in reversed(occurrences):
                suffix=prefix[occurrence.end():].strip()
                if suffix and not re.fullmatch(r'(?:,|and|&)\s*'+name_token.pattern+r'(?:\s*(?:,|and|&)\s*'+name_token.pattern+r')*',suffix,re.U):continue
                matched.append((prefix_start+occurrence.start(),author['id']));break
        if not matched:continue
        statement_start=min(position for position,_ in matched)
        statements.append((statement_start,verb.end(),[aid for _,aid in matched]))
    for index,(statement_start,aff_start,author_ids) in enumerate(statements):
        aff_end=statements[index+1][0] if index+1<len(statements) else len(text)
        if index+1==len(statements):
            corresponding=re.search(r'\bCorresponding author\s*:',text[aff_start:aff_end],re.I)
            if corresponding:aff_end=aff_start+corresponding.start()
        source=text[aff_start:aff_end].strip(' ,;:.\t\n')
        source=re.sub(r'\s+',' ',source)
        if len(source)<12 or not ORG.search(source):continue
        evidence_lines=[line for start,end,line in spans if end>statement_start and start<aff_end]
        marker='named-'+str(len(affiliations)+1)
        affiliation=parse_affiliation(source,marker,evidence(evidence_lines),False)
        affiliation['id']='aff-named-'+str(len(affiliations)+1)
        found_id=affiliation['id']
        if any(norm(affiliation['source_text'])==norm(existing['source_text']) for existing in affiliations):continue
        affiliations.append(affiliation)
        for aid in author_ids:links.setdefault(aid,[]).append(found_id)
    return affiliations,links

def endmatter_author_affiliations(layout, authors):
    """Capture an affiliation printed beside named authors after the references."""
    if not layout.get('pages') or not authors:return [],{}
    lines=layout['pages'][-1]['lines'];start=max(0,len(lines)-30);tail=lines[start:];found=[];links={}
    for index,line in enumerate(tail):
        if not ORG.search(line.get('text','')):continue
        context=' '.join(x.get('text','') for x in tail[max(0,index-4):index])
        folded=compact(context)
        author_ids=[a['id'] for a in authors if compact(str(a.get('given_name',''))+' '+str(a.get('surname',''))) in folded]
        if not author_ids:continue
        block=[line]
        for following in tail[index+1:index+4]:
            value=following.get('text','').strip()
            if EMAIL_RE.search(value) or ORCID_RE.search(value) or REF_HEAD.match(value):break
            if following['page']!=line['page'] or following['bbox'][1]-block[-1]['bbox'][3]>18:break
            if any(compact(str(a.get('given_name',''))+' '+str(a.get('surname',''))) in compact(value) for a in authors):break
            block.append(following)
            if COUNTRY_END.search(join_text(block)):break
        source=join_text(block)
        source=re.sub(r"People[’']s\s+Re-\s*public", 'People’s Republic', source, flags=re.I)
        source=re.sub(r'(?<=\w)-\s+(?=[a-z])','',source)
        if not COUNTRY_END.search(source) and not re.search(r'\b\d{4,6}\b',source):continue
        marker='endmatter-'+str(len(found)+1)
        affiliation=parse_affiliation(source,marker,evidence(block),False)
        affiliation['id']='aff-endmatter-'+str(len(found)+1)
        if any(norm(source)==norm(existing['source_text']) for existing in found):continue
        found.append(affiliation)
        for aid in author_ids:links.setdefault(aid,[]).append(affiliation['id'])
    return found,links

def trailing_affiliation_candidates(layout):
    """Find explicit affiliation-like blocks printed after the bibliography.

    These blocks are candidates only: their author links are intentionally left
    for the operator to verify. Keeping the detector anchored after the last
    numbered reference avoids treating ordinary publisher names in references
    as affiliations.
    """
    lines=[l for p in layout['pages'] for l in p['lines'] if l['direction'][0]>.8]
    headings=[i for i,l in enumerate(lines) if REF_HEAD.match(l['text'].strip())]
    if not headings:return []
    last_heading=headings[-1]
    labels=[i for i,l in enumerate(lines) if i>last_heading and re.match(r'^\s*\[\d{1,4}\]\s*',l['text'])]
    if len(labels)<3:return []
    tail=lines[labels[-1]+1:]
    found=[];used=set()
    for i,line in enumerate(tail):
        if line['id'] in used or SPECIAL_ADDRESS.search(line['text']):continue
        for size in range(1,4):
            block=tail[i:i+size]
            if not block or any(b['page']!=line['page'] for b in block):break
            if size>1 and len(block)>1 and block[-1]['bbox'][1]-block[-2]['bbox'][3]>max(22,block[-2]['size']*2):break
            text=join_text(block)
            has_location=bool(COUNTRY_END.search(text) or re.search(r'\b\d{4,6}\b',text))
            if not ORG.search(text) or not has_location or len(text)<18 or len(text)>320:continue
            # Affiliation lines are address-like, not prose or another reference.
            if re.match(r'^\s*\[\d+\]',text) or text.count('.')>5:continue
            context=[]
            if i and tail[i-1]['page']==line['page'] and line['bbox'][1]-tail[i-1]['bbox'][3]<24 and (EMAIL_RE.search(tail[i-1]['text']) or re.match(r'^[A-Z][\w .\-]{2,50}$',tail[i-1]['text'].strip())):
                context=[tail[i-1]]
            source=join_text(block)
            parsed=parse_affiliation(source,'candidate-'+str(len(found)+1),evidence(block),False)
            parsed['id']='aff-candidate-'+str(len(found)+1)
            parsed['status']='UNREVIEWED'
            parsed['location']='After references'
            parsed['contact_text']=join_text(context) if context else ''
            parsed['contact_evidence']=evidence(context)
            found.append(parsed);used.update(b['id'] for b in block)
            break
    return found

def page_footer_affiliation_candidates(layout, known_line_ids=()):
    """Retain strong address-like blocks printed in page footers outside the front block."""
    known=set(known_line_ids);found=[]
    # Footnotes are set smaller than the body text; body-size lines near a page foot are prose.
    sizes=Counter()
    for page in layout['pages']:
        for l in page['lines']:sizes[round(l['size'],1)]+=len(l['text'])
    body=sizes.most_common(1)[0][0] if sizes else 0
    for page in layout['pages']:
        rows=sorted((l for l in page['lines'] if l['direction'][0]>.8 and l['id'] not in known and l['size']<body-.4),key=lambda l:(l['bbox'][1],l['bbox'][0]))
        for i,line in enumerate(rows):
            if line['bbox'][1]<page['height']*.70 or SPECIAL_ADDRESS.search(line['text']):continue
            for size in range(1,4):
                block=rows[i:i+size]
                if not block or any(b['page']!=page['number'] for b in block):break
                if size>1 and len(block)>1 and block[-1]['bbox'][1]-block[-2]['bbox'][3]>max(22,block[-2]['size']*2):break
                text=join_text(block)
                if not ORG.search(text) or not (COUNTRY_END.search(text) or re.search(r'\b\d{4,6}\b',text)) or len(text)<18 or len(text)>320:continue
                parsed=parse_affiliation(text,'candidate-'+str(len(found)+1),evidence(block),False)
                parsed.update(id='aff-candidate-footer-'+str(len(found)+1),status='UNREVIEWED',location=f'Page {page["number"]} footer')
                found.append(parsed);known.update(b['id'] for b in block);break
    return found

def apply_correspondence_rules(md, layout):
    """Apply the supplied single-/multi-author correspondence rules to PDF evidence.

    A lone author with a captured affiliation or email is the correspondence
    author under the current guide. For multi-author papers, an author-side
    asterisk/envelope is a signal unless its matching note assigns it another
    meaning (for example, equal contribution or fellowship). An email-side or
    affiliation-side symbol alone never assigns correspondence to an author.
    """
    authors=md.get('authors',[])
    if not authors:return
    lines=[line for page in layout.get('pages',[]) for line in page.get('lines',[])]
    by_id={line.get('id'):line for line in lines}
    symbols={'*','∗','✉','✉️'}
    if len(authors)==1:
        author=authors[0]
        if author.get('email') or author.get('affiliation_ids'):
            author['corresponding']=True
            author['correspondence_basis']='single-author-with-email-or-affiliation'
            author['correspondence_evidence']=author.get('email_evidence') or author.get('evidence',[])
        return
    for line in lines:
        text=line.get('text','')
        if not re.search(r'\b(?:corresponding\s+author|reprint\s+request|all\s+correspondence|contact\s+address)\b',text,re.I):continue
        folded=compact(text)
        for author in authors:
            full=compact(str(author.get('given_name',''))+' '+str(author.get('surname','')))
            surname=compact(author.get('surname',''))
            if (full and full in folded) or (len(surname)>=3 and surname in folded):
                author['corresponding']=True
                author['correspondence_basis']='author-named-in-correspondence-statement'
                author['correspondence_evidence']=evidence([line])
    for author in authors:
        marks=set(author.get('markers',[])) & symbols
        evidence=author.get('evidence',[])
        source_lines=[by_id[e.get('line_id')] for e in evidence if e.get('line_id') in by_id]
        if not source_lines:continue
        # Recover symbols that the author parser left in its source line but
        # missed while splitting adjacent superscript name/affiliation markers.
        surname=fold(author.get('surname',''))
        for item in evidence:
            text=item.get('text',''); visible=fold(text)
            pos=visible.find(surname) if surname else -1
            if pos>=0:
                marks.update(set(author_markers(text[pos+len(surname):])) & symbols)
        # Some PDFs place raised symbols in a separate text span/line at the
        # right edge of the name. Treat a tightly adjacent same-baseline mark
        # as part of that author's name, with the PDF coordinates as evidence.
        for src in source_lines:
            sb=src.get('bbox',[0,0,0,0])
            for line in lines:
                if line.get('page')!=src.get('page') or line is src:continue
                lb=line.get('bbox',[0,0,0,0]);candidate=line.get('text','').strip()
                if not candidate or not any(candidate.startswith(m) for m in symbols):continue
                vertical_gap=max(0,sb[1]-lb[3],lb[1]-sb[3])
                horizontal_gap=lb[0]-sb[2]
                if vertical_gap<=4 and -3<=horizontal_gap<=35:
                    marks.update(set(author_markers(candidate)) & symbols)
        if not marks:continue
        marker=next((m for m in ('✉️','✉','∗','*') if m in marks),None)
        if not marker:continue
        # Only a matching symbol note can override the author-side marker.
        # Keep this restricted to footnote-style lines to avoid stars in body math.
        notes=[]
        for line in lines:
            text=line.get('text','').strip()
            if not text.startswith(marker):continue
            if not any(line.get('page')==src.get('page') and
                       line.get('bbox',[0,0,0,0])[1] >= src.get('bbox',[0,0,0,0])[1]
                       for src in source_lines):continue
            notes.append(text[len(marker):].strip())
        other_meaning=any(re.search(r'\b(?:equal(?:ly)?\s+(?:contribut\w*|author\w*)|contribut\w*\s+equally|fellow|present\s+address|current\s+address|formerly\s+at|formerly\s+affiliated|now\s+at|work\s+(?:was\s+)?performed\s+at)\b',note,re.I) for note in notes)
        if other_meaning:continue
        explicit=any(re.search(r'\b(?:corresponding\s+author|reprint\s+request|contact\s+address|all\s+correspondence)\b',note,re.I) for note in notes)
        author['corresponding']=True
        author['correspondence_basis']='explicit-correspondence-marker-note' if explicit else 'author-side-asterisk-or-envelope'
        author['correspondence_evidence']=evidence

def extract_metadata(layout, support, settings):
    issues=[];pages=layout['pages'];lines=[l for p in pages for l in p['lines']];first=pages[0]['lines']
    DOC_WORDS.set(frozenset(w.casefold() for l in lines for w in re.findall(r'[^\W\d_]+(?:-[^\W\d_]+)*',l['text'])))
    horizontal=[l for l in first if l['direction'][0]>.8]
    md={'base_id':'','version':None,'title':'','abstract':'','keywords':[],'authors':[],'affiliations':[],'references':[],'field_evidence':{},'source_values':support,'profile':{'supplier_id':'4','order_id':'unknown','parcel_id':'none','source_id':'???'}}
    def stamp(candidates,need_version):
        return next(((m,l) for l in candidates for m in [STAMP_RE.search(l['text'])] if m and (m[2] or not need_version)),None)
    # A first-page stamp without a version is still the ID; the version check then flags it.
    found=stamp(first,True) or stamp(first,False)
    if not found:
        found=stamp(lines,True)
        issues.append(issue('ID-004','base_id','ID/version is missing from the expected first-page arXiv stamp. Check the PDF.'))
    if found:
        m,l=found;md['base_id'],md['version']=m[1],int(m[2]) if m[2] else None;md['field_evidence']['base_id']=evidence([l])
    top=[l for l in horizontal if l['bbox'][1]<pages[0]['height']*.25 and not re.search(r'MNRAS|Preprint|Compiled using|Accepted|Received',l['text'])]
    if top:
        maxsize=max(l['size'] for l in top)
        titlelines=[l for l in top if l['size']>=maxsize*.94]
        # Font size is primary; support title is only verification, never the source value.
        if titlelines:
            first_title=titlelines[0];titlelines=[l for l in titlelines if abs(l['bbox'][1]-first_title['bbox'][1])<maxsize*4]
            md['title']=join_text(titlelines);md['field_evidence']['title']=evidence(titlelines)
            if any(any((s['flags']&1) or (s['size']<l['size']*.82 and re.search(r'[\w\d]',s['text']))
                       for s in l.get('spans',[])) for l in titlelines):
                issues.append(issue('PDF-008','title','Title contains raised/lowered or mathematical typography. Check and tag the printed title before delivery.',evidence(titlelines)))
    title_end=max((e['bbox'][3] for e in md['field_evidence'].get('title',[])),default=0)
    api_authors=support['api_authors'];authorlines=[];found=[];used_occurrences=set();author_candidates=[]
    for a in api_authors:
        pattern=r'(?<![^\W\d_])'+re.escape(fold(a['surname']))+r'(?![^\W\d_])'
        choices=[]
        for idx,l in enumerate(horizontal):
            if not (title_end<=l['bbox'][1]<pages[0]['height']*.45):continue
            visible=fold(l['text'])
            for m in re.finditer(pattern,visible):
                if (idx,m.start()) in used_occurrences:continue
                if any(mail.start()<=m.start()<mail.end() for mail in EMAIL_RE.finditer(visible)):continue
                prefix=visible[max(0,m.start()-70):m.start()]
                nearest=re.split(r',|\band\b|&',prefix,flags=re.I)[-1]
                given_matches=compatible_given_name(a.get('given_name',''),nearest)
                choices.append((given_matches,idx,m.start(),m.end(),l))
        matches=[c for c in choices if c[0]]
        if len(matches)==1:chosen=matches[0]
        elif len(choices)==1:chosen=choices[0]
        else:
            issues.append(issue('AUTHOR-002','authors','API author '+a['surname']+' could not be unambiguously located in the PDF author area.'))
            continue
        matched_given,idx,pos,end,l=chosen
        used_occurrences.add((idx,pos));found.append((idx,pos,a,l,end))
        if l not in authorlines:authorlines.append(l)
    found.sort(key=lambda x:(x[0],x[1]))
    consumed=defaultdict(list)
    for seq,(idx,pos,a,l,end) in enumerate(found,1):
        following=next((next_pos for next_idx,next_pos,*_ in found if next_idx==idx and next_pos>pos),len(l['text']))
        suffix=l['text'][end:following]
        visible=fold(l['text']);prefix=visible[max(0,pos-70):pos];nearest=re.split(r',|\band\b|&',prefix,flags=re.I)[-1]
        rawprefix=l['text'][max(0,pos-70):pos];rawsegment=re.split(r',|\band\b|&',rawprefix,flags=re.I)[-1];rawnearest=rawsegment.strip()
        consumed[idx].append((pos-len(rawsegment),end))
        pdf_tokens=re.findall(r'[^\W\d_]+\.?(?!\w)',rawnearest,re.U)
        api_tokens=name_tokens(a.get('given_name',''));pdf_name=' '.join(pdf_tokens[-max(1,len(name_tokens(nearest))):])
        api_initials=bool(api_tokens) and all(len(t)==1 for t in api_tokens)
        distinct_extra=api_initials and len(name_tokens(nearest))>len(api_tokens)
        name_conflict=not compatible_given_name(a.get('given_name',''),nearest)
        candidate_index=None
        if distinct_extra or name_conflict:
            author_candidates.append({'id':'author-candidate-'+str(len(author_candidates)+1),'api_given_name':a['given_name'],'given_name':pdf_name,'surname':a['surname'],'source_text':(rawnearest+' '+l['text'][pos:end]).strip(),'status':'UNREVIEWED','location':f'Page {l["page"]}','pdf_order':(idx,pos),'evidence':evidence([l]),'reason':'PDF and API name forms need an identity decision.' if name_conflict else 'PDF shows additional name components while API has initials; confirm whether these are distinct people.'})
            candidate_index=len(author_candidates)-1
        elif compatible_given_name(a.get('given_name',''),nearest) and pdf_name and len(api_tokens)==len(name_tokens(nearest)) and any(len(t)==1 for t in api_tokens) and any(len(t)>1 for t in pdf_tokens):
            a={**a,'given_name':pdf_name}
        au={'id':f'author-{seq}','global_seq':seq,'given_name':a['given_name'],'surname':a['surname'],'initials':initials(a['given_name']),'displayed_name':a['given_name']+' '+a['surname'],'source_text':(rawnearest+' '+l['text'][pos:end]).strip(),'pdf_name_match':compatible_given_name(a.get('given_name',''),nearest),'pdf_name_parts':{'before':rawnearest,'surname':l['text'][pos:end],'after':suffix},'markers':author_markers(suffix),'affiliation_ids':[],'email':'','orcid':'','corresponding':False,'evidence':evidence([l])}
        md['authors'].append(au)
        if candidate_index is not None:author_candidates[candidate_index]['api_author_id']=au['id']
    md['author_candidates']=author_candidates
    # Name-like words on an author line that no API author accounts for may be a PDF-only author.
    leftover=[]
    for idx,spans in consumed.items():
        text=list(horizontal[idx]['text'])
        for start,stop in spans:text[start:stop]=' '*(stop-start)
        rest=EMAIL_RE.sub(' ',''.join(text))
        for word in re.findall(r"[^\W\d_][\w'’.-]*",rest):
            if len(word.rstrip('.'))>1 and word[0].isupper():
                leftover.append({'word':word,'evidence':evidence([horizontal[idx]])})
    md['author_line_leftover']=leftover
    if author_candidates:issues.append(issue('AUTHOR-002','authors',str(len(author_candidates))+' possible PDF/API author identity difference(s). Decide whether to use the more complete name or capture a separate author, then check the sequence.',[e for c in author_candidates for e in c['evidence']]))
    if not api_authors:
        issues.append(issue('AUTHOR-007','authors','API name components unavailable. Add or verify authors manually from the PDF.'))
        # Retain a visibly author-like block as a candidate, not a fabricated surname split.
        candidates=[l for l in horizontal if l['bbox'][1]>=title_end and l['bbox'][1]<title_end+65 and len(l['text'].split())>2 and not re.search(r'\b20\d\d\b',l['text'])]
        md['author_candidate_text']=join_text(candidates[:2]);md['field_evidence']['authors']=evidence(candidates[:2])
    else:md['field_evidence']['authors']=evidence(authorlines)
    author_end=max((l['bbox'][3] for l in authorlines),default=title_end+25)
    md['affiliations'],afflines=front_affiliations(horizontal,author_end,pages[0]['height'],[m for a in md['authors'] for m in a['markers']])
    named_affiliations,named_links=named_affiliation_statements(layout,md['authors'])
    endmatter_affiliations,endmatter_links=endmatter_author_affiliations(layout,md['authors'])
    md['affiliations'].extend(named_affiliations+endmatter_affiliations)
    for author_id,affiliation_ids in endmatter_links.items():named_links.setdefault(author_id,[]).extend(affiliation_ids)
    printed={f['marker'] for f in md['affiliations'] if f['printed_marker']}
    for a in md['authors']:
        marker_ids=[f['id'] for f in md['affiliations'] if f['printed_marker'] and f['marker'] in a['markers']]
        a['affiliation_ids']=list(dict.fromkeys(marker_ids+named_links.get(a['id'],[])))
        a['link_method']='marker' if marker_ids else 'named_statement' if a['affiliation_ids'] else None
        if not a['affiliation_ids'] and len(md['affiliations'])==1 and not md['affiliations'][0]['printed_marker']:
            # Linked by position only: nothing printed ties this author to the address.
            a['affiliation_ids']=[md['affiliations'][0]['id']];a['link_method']='single_affiliation'
        a['unmatched_markers']=[m for m in a['markers'] if re.fullmatch(r'\d{1,2}|[a-f]',m) and m not in printed]
        if not a['affiliation_ids']:issues.append(issue('AFF-003','authors','No unambiguous affiliation mapping for '+a['surname'],a['evidence']))
    md['author_groups']=[{'author_ids':[a['id'] for a in md['authors'] if f['id'] in a['affiliation_ids']],'affiliation_id':f['id']} for f in md['affiliations']]
    md['unlinked_affiliation_ids']=[g['affiliation_id'] for g in md['author_groups'] if not g['author_ids']]
    md['author_groups']=[g for g in md['author_groups'] if g['author_ids']]
    if not md['affiliations']:issues.append(issue('AFF-017','affiliations','No original affiliation block found. Review the PDF and add affiliations; no location data has been invented.'))
    else:
        issues.append(issue('AFF-007','affiliations','Review the automatically separated organizations and address components against the PDF.',evidence(afflines[:1])))
        if len(md['affiliations'])>1 and any(not f['printed_marker'] for f in md['affiliations']):
            issues.append(issue('AFF-003','affiliations','Multiple affiliations include unmarked address blocks. Review their boundaries and author links.'))
        for f in md['affiliations']:
            for warning in f['component_warnings']:
                issues.append(issue('AFF-007','affiliations',f['id']+': '+warning,f['evidence']))
    for l in horizontal:
        if l['bbox'][1]<min(pages[0]['height']*.48,author_end+240) and SPECIAL_ADDRESS.search(l['text']):
            issues.append(issue('AFF-004','affiliations','A current/former or correspondence-only address is visible. Verify it was not substituted for an original affiliation.',evidence([l])))
    used_aff_ids={l['id'] for l in afflines}
    visible_markers={m for a in md['authors'] for m in a['markers'] if re.fullmatch(r'\d{1,2}|[a-f]',m)}
    candidates=[]
    for p in pages:
        for l in p['lines']:
            if l['id'] in used_aff_ids or l['direction'][0]<.8 or SPECIAL_ADDRESS.search(l['text']):continue
            marker,body=front_marker(l['text'],bool(visible_markers & set('abcdef')))
            if marker in visible_markers and ORG.search(body) and len(body)<230:
                candidate=parse_affiliation(body,marker,evidence([l]),True)
                candidate.update(id='aff-candidate-'+str(len(candidates)+1),text=l['text'],status='UNREVIEWED',location=f'Page {p["number"]}')
                candidates.append(candidate)
    md['affiliation_candidates']=candidates
    if candidates:issues.append(issue('AFF-017','affiliations',str(len(candidates))+' additional marked affiliation candidate(s) outside the extracted original block. Check their location and add only original affiliations.',[e for c in candidates for e in c['evidence']]))
    # Abstract: explicit heading, otherwise first prose block after affiliations.
    start=None;absls=[];start_bold=False;last=None;md['abstract_heading']=None
    for i,l in enumerate(horizontal):
        m=re.match(r'^(Abstract|Synopsis|Summary)(?:\s*[:.—-]|\s*$)',l['text'],re.I)
        if m:start=i;md['abstract_heading']=m[1];break
    if start is None and afflines:
        lastblock=max(l['block'] for l in afflines)
        blocks_after=defaultdict(list)
        for i,l in enumerate(horizontal):
            if l['block']>lastblock:blocks_after[l['block']].append((i,l))
        for block_lines in blocks_after.values():
            block_text=join_text([l for _,l in block_lines])
            first_text=block_lines[0][1]['text'].strip()
            if (EMAIL_RE.search(block_text) or
                re.match(r'^[★*∗†‡✉]|^(?:corresponding\s+authors?|e-?mail)\b',first_text,re.I) or
                STOP_HEAD.match(first_text)):
                continue
            if len(block_text)>=60 and any(len(l['text'].strip())>=45 for _,l in block_lines):
                start=block_lines[0][0];break
    if start is not None:
        for l in horizontal[start:]:
            text=l['text'].strip()
            if re.match(r'^(Abstract|Synopsis|Summary)\s*$',text,re.I):continue
            if STOP_HEAD.match(text) or re.match(r'^(Key\s*words|Index Terms|Words and Phrases)\s*:',text,re.I):break
            if not absls:
                start_bold=l['bold']
            elif last:
                rightedge=max(a['bbox'][2] for a in absls)
                same_column=l['bbox'][0]>=absls[0]['bbox'][0]-15 and l['bbox'][2]<=rightedge+20
                if not same_column or (l['bbox'][1]-last['bbox'][3]>max(13,last['size']*1.35)) or (start_bold and not l['bold'] and len(text)>45 and l['block']!=last['block']):break
            copy=dict(l);copy['text']=re.sub(r'^(Abstract|Synopsis|Summary)\s*[:.—-]\s*','',text,flags=re.I)
            absls.append(copy);last=l
        md['abstract']=join_text(absls);md['field_evidence']['abstract']=evidence(absls)
    if not md['abstract']:issues.append(issue('ABS-002','abstract','Abstract boundary could not be determined. Select/read the PDF and enter the abstract.'))
    if any(any(s['flags']&1 for s in l['spans']) for l in absls) or re.search(r'[√𝑀𝑞]',md['abstract']):issues.append(issue('PDF-008','abstract','Abstract contains scripts or mathematical layout. Plain-text extraction needs visual review before delivery.',evidence(absls[:1])))
    keyword_label=None
    for l in horizontal:
        if re.match(r'^(?:Key\s*words|Index Terms|Words and Phrases|Additional Keywords and Phrases)\b',l['text'],re.I):keyword_label=l
        m=re.match(r'^(?:Key\s*words|Index Terms|Words and Phrases|Additional Keywords and Phrases)\s*[:—-]\s*(.+)',l['text'],re.I)
        if m:md['keywords']=[t.strip() for t in re.split(r'\s+[–—]\s+|;|,',m[1]) if t.strip()];md['field_evidence']['keywords']=evidence([l]);break
        if keyword_label is l and re.fullmatch(r'(?:Key\s*words|Index Terms|Words and Phrases|Additional Keywords and Phrases)\s*[:—-]?\s*',l['text'],re.I):
            nearby=sorted((x for x in horizontal if x is not l and -2<=x['bbox'][1]-l['bbox'][3]<=25 and
                           abs(x['bbox'][0]-l['bbox'][0])<40),key=lambda x:x['bbox'][1])
            if nearby:
                candidate=nearby[0]['text'].strip()
                if len(candidate)<180 and len(candidate.split())<=12 and not candidate.endswith('.') and not STOP_HEAD.match(candidate) and not EMAIL_RE.search(candidate):
                    md['keywords']=[t.strip() for t in re.split(r'\s+[–—]\s+|;|,',candidate) if t.strip()]
                    md['field_evidence']['keywords']=evidence([l,nearby[0]]);break
    if keyword_label and not md['keywords']:
        issues.append(issue('KEY-001','keywords','A PDF keyword label is visible, but its keyword list was not separated. Review and enter the printed keywords.',evidence([keyword_label])))
    # Contact details may be printed in rows below affiliation blocks without
    # repeating an author marker. Use PDF name evidence, then the adjacent
    # affiliation marker and row order when multiple authors share that marker.
    email_rows=[]
    for l in horizontal:
        mails=EMAIL_RE.findall(l['text'])
        visible_orcids=[m.upper() for m in ORCID_RE.findall(l['text'])]
        row_links=[link for p in pages if p['number']==l['page'] for link in p['links']
                   if ORCID_RE.search(link['uri']) and link['bbox'][1]<=l['bbox'][3] and link['bbox'][3]>=l['bbox'][1]]
        linked_orcids=[ORCID_RE.search(link['uri'])[1].upper() for link in row_links]
        orcids=list(dict.fromkeys(visible_orcids+linked_orcids))
        if not mails and not orcids:continue
        marks=re.findall(r'[★*∗†‡✉]',l['text'].split(mails[0])[0] if mails else l['text'])
        marker=next((m for m in reversed(marks) if any(m in a['markers'] for a in md['authors'])),None)
        if marker is None:
            preceding=[]
            for f in md['affiliations']:
                for ev in f.get('evidence',[]):
                    if ev['page']==l['page'] and 0<=l['bbox'][1]-ev['bbox'][3]<=22:
                        preceding.append((l['bbox'][1]-ev['bbox'][3],f['marker']))
            if preceding:marker=min(preceding)[1]
        email_rows.append({'line':l,'emails':mails,'orcids':orcids,'links':row_links,'marker':marker,'author_id':None})

    def email_author_matches(mail):
        local=compact(mail.split('@',1)[0])
        return [a for a in md['authors'] if len(compact(a.get('surname','')))>=3 and compact(a['surname']) in local]

    # Surname matches resolve repeated asterisk groups; a single marked author
    # can be assigned directly when their email local part is not name-based.
    for row in email_rows:
        for mail in row['emails']:
            matches=email_author_matches(mail)
            if len(matches)==1:row['author_id']=matches[0]['id'];break
        if row['author_id'] is None and row['marker']:
            matches=[a for a in md['authors'] if row['marker'] in a['markers']]
            if len(matches)==1:row['author_id']=matches[0]['id']

    for marker in dict.fromkeys(row['marker'] for row in email_rows if row['marker']):
        rows=[r for r in email_rows if r['marker']==marker and r['author_id'] is None]
        authors=[a for a in md['authors'] if marker in a['markers'] and not any(r['author_id']==a['id'] for r in email_rows)]
        if len(rows)==len(authors):
            for row,a in zip(sorted(rows,key=lambda r:r['line']['bbox'][1]),authors):row['author_id']=a['id']

    assigned_emails=[]
    for row in email_rows:
        author=next((a for a in md['authors'] if a['id']==row['author_id']),None)
        if not author:continue
        if len(row['emails'])==1:
            author['email']=row['emails'][0];author['email_evidence']=evidence([row['line']]);assigned_emails.extend(row['emails'])
        elif len(row['emails'])>1:
            issues.append(issue('EMAIL-001','authors','Multiple email candidates for '+author['surname']+'. Select one.',evidence([row['line']])))
        if len(row['orcids'])==1:
            author['orcid']=row['orcids'][0];author['orcid_evidence']=evidence([row['line']])
        elif len(row['orcids'])>1:
            issues.append(issue('ORCID-001','authors','Multiple ORCID candidates for '+author['surname']+'. Select one.',evidence([row['line']])))
        if re.search(r'correspond(?:ing)?\s+author',row['line']['text'],re.I):author['corresponding']=True

    all_emails=[(mail,l) for l in horizontal for mail in EMAIL_RE.findall(l['text'])]
    if all_emails and any(mail not in assigned_emails for mail,l in all_emails):
        unmatched=[l for mail,l in all_emails if mail not in assigned_emails]
        issues.append(issue('EMAIL-001','authors','Some PDF email addresses were not unambiguously linked to an author. Check contact fields.',evidence(unmatched)))

    apply_correspondence_rules(md,layout)

    # Also support ORCID links printed on a name line rather than a contact row.
    for p in pages:
        for link in p['links']:
            m=re.search(r'orcid\.org/(\d{4}-\d{4}-\d{4}-[\dX]{4})',link['uri'],re.I)
            if not m:continue
            orcid=m[1].upper()
            row=next((r for r in email_rows if r['line']['page']==p['number'] and any(link is x for x in r['links'])),None)
            if row and row['author_id']:continue
            near=[a for a in md['authors'] if any(e['page']==p['number'] and abs(e['bbox'][1]-link['bbox'][1])<16 for e in a['evidence'])]
            if len(near)==1:
                near[0]['orcid']=orcid;near[0]['orcid_evidence']=[{'page':p['number'],'bbox':link['bbox'],'text':link['uri']}]
            else:issues.append(issue('ORCID-001','authors','ORCID '+orcid+' found in PDF; assign it to the correct author.',[{'page':p['number'],'bbox':link['bbox'],'text':link['uri']}]))
    md['references'],md['coverage'],refissues=extract_references(layout)
    issues.extend(refissues)
    extra=trailing_affiliation_candidates(layout)
    ref_line_ids={e['line_id'] for r in md['references'] for e in r.get('evidence',[]) if e.get('line_id')}
    candidate_line_ids={e['line_id'] for c in md['affiliation_candidates'] for e in c.get('evidence',[]) if e.get('line_id')}
    footer=page_footer_affiliation_candidates(layout,ref_line_ids|candidate_line_ids|{l['id'] for l in afflines})
    if footer:
        md['affiliation_candidates'].extend(footer)
        issues.append(issue('AFF-017','affiliations',str(len(footer))+' address-like affiliation candidate(s) found in page footers or lower-page notes. Verify whether each is an original affiliation.',[e for c in footer for e in c['evidence']]))
    if extra:
        known={tuple(e.get('text','') for e in c.get('evidence',[])) for c in md['affiliation_candidates']}
        md['affiliation_candidates'].extend(c for c in extra if tuple(e.get('text','') for e in c.get('evidence',[])) not in known)
        issues.append(issue('AFF-017','affiliations',str(len(extra))+' additional affiliation candidate(s) found outside the author block, including after the references. Verify each candidate and link it to an author or mark it as not an original affiliation.',[e for c in extra for e in c['evidence']]))
    return md,issues

def multiple_works(text):
    """A second dated work after ';' or a cf./see pointer inside one reference entry."""
    return bool(re.search(r';\s*[A-Z].{0,80}\b(?:19|20)\d{2}\b',text) or
                re.search(r'\b(?:cf\.|see\s+(?:also\s+|his\s+|her\s+|my\s+)?)[A-Z][^.;]{0,120}\b(?:19|20)\d{2}\b',text,re.I))

def footnote_references(layout):
    '''Numbered bottom-of-page notes, each with its PDF lines.'''
    footnotes=[]
    for page in layout['pages']:
        bottom=sorted((l for l in page['lines'] if l['direction'][0]>.8 and l['bbox'][1]>=page['height']*.76 and l['size']<=10.5),key=lambda l:(l['bbox'][1],l['bbox'][0]))
        current=None
        for line in bottom:
            m=re.match(r'^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.)])\s+(.+)',line['text'])
            if m:
                if current:footnotes.append(current)
                current={'label':m[1] or m[2],'text':m[3],'evidence':[line],'region':f'footnote-page-{page["number"]}'}
            elif current and line['bbox'][0]>=current['evidence'][0]['bbox'][0]-5 and line['bbox'][1]-current['evidence'][-1]['bbox'][3]<18:
                current['text']+='\n'+line['text'];current['evidence'].append(line)
        if current:footnotes.append(current)
    return footnotes

def extract_references(layout):
    issues=[];lines=[]
    trailing_candidates=trailing_affiliation_candidates(layout)
    trailing_ids={e['line_id'] for c in trailing_candidates for e in c['evidence']}
    trailing_context_ids={e['line_id'] for c in trailing_candidates for e in c.get('contact_evidence',[])}
    for p in layout['pages']:
        for l in p['lines']:
            if l['direction'][0]<.8:continue
            if re.match(r'^\s*\d+\s*$',l['text']) and (l['bbox'][1]<45 or l['bbox'][3]>p['height']-65):continue
            if re.search(r'^MNRAS\s+\d|^This paper has been typeset|^©',l['text']):continue
            lines.append(l)
    headings=[i for i,l in enumerate(lines) if REF_HEAD.match(l['text'].strip())]
    labels=[]
    for i,l in enumerate(lines):
        m=re.match(r'^\s*\[(\d{1,4})\]\s*(.*)',l['text'])
        if m:labels.append((i,int(m[1]),m[2]))
    # Choose longest ordered run, not a first-N limit; separate runs are retained for review.
    runs=[]
    for item in labels:
        if not runs or item[1]<=runs[-1][-1][1]:runs.append([])
        runs[-1].append(item)
    # A run must be in a bibliography region or late paper with multiple labels.
    runs=[run for run in runs if len(run)>=3 and
          (any(h<=run[0][0] for h in headings) or lines[run[0][0]]['page']>=max(1,len(layout['pages'])*.35))]
    keyed_labels=[]
    if headings:
        keyed_labels=[(i,m.group(1)) for i,l in enumerate(lines)
                      if i>headings[-1] and
                      (m:=re.match(r'^\s*\[([A-Za-z0-9][A-Za-z0-9+.-]{1,19})\]\s*',l['text']))]
    refs=[];candidates=[]
    if runs:
        if len(runs)>1:issues.append(issue('REF-014','references','Multiple numbered reference regions found. Review all regions.'))
        for runno,run in enumerate(runs):
            for ri,(start,label,firsttext) in enumerate(run):
                end=run[ri+1][0] if ri+1<len(run) else len(lines)
                use=[]
                for l in lines[start:end]:
                    if l['id'] in trailing_ids or l['id'] in trailing_context_ids:break
                    if l!=lines[start] and (STOP_HEAD.match(l['text']) or REF_HEAD.match(l['text'])):break
                    # Do not consume a later independent numbered region.
                    if l!=lines[start] and re.match(r'^\[\d+\]',l['text']):break
                    use.append(l)
                clean=[firsttext]+[l['text'] for l in use[1:]]
                candidates.append({'label':str(label),'text':join_text(clean),'evidence':evidence(use),'region':runno+1})
            numbers=[n for _,n,_ in run]
            if numbers!=list(range(numbers[0],numbers[-1]+1)):issues.append(issue('REF-018','references','Source numbering contains gaps. Inspect the reference coverage.'))
        if not headings:issues.append(issue('REF-003','references','A numbered bibliography was found without a References heading. Review its beginning and end.',candidates[0]['evidence'][:1] if candidates else []))
    elif headings and len(keyed_labels)>=3:
        # Author-year bibliographies often print keys such as [AJL09] instead
        # of numeric labels. Use those explicit printed starts as boundaries;
        # hanging-indent coordinates alone split continuation spans and can
        # absorb appendix prose after the final entry.
        for ri,(start,label) in enumerate(keyed_labels):
            end=keyed_labels[ri+1][0] if ri+1<len(keyed_labels) else len(lines)
            use=[]
            for l in lines[start:end]:
                if l['id'] in trailing_ids or l['id'] in trailing_context_ids:break
                if ri+1==len(keyed_labels) and l['id'].rsplit('-l',1)[0]!=lines[start]['id'].rsplit('-l',1)[0]:break
                if l!=lines[start] and (STOP_HEAD.match(l['text']) or REF_HEAD.match(l['text'].strip())):break
                use.append(l)
            candidates.append({'label':label,'text':join_text([l['text'] for l in use]),
                               'evidence':evidence(use),'region':1})
        issues.append(issue('REF-006','references','Unnumbered references were separated by their printed bracketed citation keys. Review their boundaries.',candidates[0]['evidence'][:1] if candidates else []))
    elif headings:
        start=headings[-1]+1;use=[]
        for l in lines[start:]:
            if STOP_HEAD.match(l['text']):break
            use.append(l)
        # Group using actual start-margin clusters within each page/column.
        widths={p['number']:p['width'] for p in layout['pages']}
        groups=defaultdict(list)
        for l in use:groups[(l['page'],0 if l['bbox'][0]<widths[l['page']]*.48 else 1)].append(l)
        margin={k:min(l['bbox'][0] for l in ls) for k,ls in groups.items()}
        current=None
        for l in use:
            key=(l['page'],0 if l['bbox'][0]<widths[l['page']]*.48 else 1)
            is_start=abs(l['bbox'][0]-margin[key])<2 and re.match(r'^[A-ZÀ-Ž]',l['text'])
            if is_start:
                if current:candidates.append(current)
                current={'label':None,'text':l['text'],'evidence':evidence([l]),'region':1}
            elif current:
                current['text']+='\n'+l['text'];current['evidence']+=evidence([l])
        if current:candidates.append(current)
        for c in candidates:c['text']=join_text([c['text']])
        issues.append(issue('REF-006','references','Unnumbered references were separated by hanging indentation. Review their boundaries.',candidates[0]['evidence'][:1] if candidates else []))
    else:
        footnotes=footnote_references(layout)
        if footnotes:
            candidates=footnotes
            issues.append(issue('REF-006','references','No main bibliography found; captured numbered bottom-of-page footnote references for review.',evidence(candidates[0]['evidence'])))
        else:issues.append(issue('REF-002','references','No reliable main bibliography region found. Add references manually or inspect footnote/supplementary lists.'))
    excluded=[]
    for i,c in enumerate(candidates,1):
        if re.fullmatch(r'(ibid|supra|op\.?\s*cit|loc\.?\s*cit)[.\s]*',c['text'],re.I):excluded.append({'candidate':i,'rule':'REF-009','text':c['text']});continue
        alpha=[x for x in c['text'] if x.isalpha()]
        if alpha and not any('LATIN' in unicodedata.name(x,'') for x in alpha):excluded.append({'candidate':i,'rule':'REF-010','text':c['text']});continue
        r={'id':f'ref-{i}','seq':len(refs)+1,'candidate_id':f'candidate-{i}','original_label':c['label'],'source_text':c['text'],'full_text':c['text'],'evidence':c['evidence'],'split_from':None,'region':c['region']};refs.append(r)
        if re.search(r'_{3,}',c['text']):issues.append(issue('REF-015','references','Underscore placeholder in reference '+str(r['seq']),r['evidence'][:1]))
        if multiple_works(c['text']):issues.append(issue('REF-013','references','Possible multiple or stealth works in reference '+str(r['seq'])+'. Separate each evidenced work with Split and preserve the printed text.',r['evidence'][:1]))
    if not refs and not any(i['rule_id']=='REF-002' for i in issues):
        issues.append(issue('REF-002','references','No references were extracted from the PDF. Add references manually or inspect the reference region.'))
    duplicates=[t for t,n in Counter(compact(r['source_text']) for r in refs).items() if n>1]
    if duplicates:issues.append(issue('REF-019','references','Potential duplicate reference entries retained. Review before removal.'))
    # Independently retain every printed numeric start found in the PDF, including
    # candidates later rejected by segmentation. A smaller emitted list cannot pass.
    inventory=[str(n) for index,n,_ in labels if not headings or any(h<index for h in headings)]
    method='numbered-start-inventory' if runs else 'keyed-label-start-inventory' if headings and len(keyed_labels)>=3 else 'footnote-candidates' if candidates and all(str(c.get('region','')).startswith('footnote-page-') for c in candidates) else 'hanging-indent-start-inventory'
    # Separate places the PDF prints references: numbered runs or headed lists, plus
    # footnote citations (numbered notes with a year) alongside a main list.
    headed=[h for h in headings if h+1<len(lines) and not (STOP_HEAD.match(lines[h+1]['text']) or REF_HEAD.match(lines[h+1]['text'].strip()))]
    regions=max(len(runs),len(headed))
    ref_lines={e.get('line_id',e.get('id')) for r in refs for e in r['evidence']}
    first_ref_page=min((e['page'] for r in refs for e in r['evidence']),default=0)
    if regions and any(re.search(r'\b(?:19|20)\d{2}\b',f['text']) and f['evidence'][0]['page']<first_ref_page and
                       not any(l['id'] in ref_lines for l in f['evidence']) for f in footnote_references(layout)):regions+=1
    coverage={'reference_regions':regions,'detected_candidates':len(candidates),'included_candidates':len(refs),'excluded':excluded,'unresolved_candidates':0 if candidates else None,'generated_references':len(refs),'extra_split_parts':0,'numbered_labels':[c['label'] for c in candidates if c['label']], 'printed_label_inventory':[label for _,label in keyed_labels] if headings and len(keyed_labels)>=3 else inventory,'method':method,'reviewed':False}
    issues.append(issue('REF-018','references','Confirm the reference list is complete against the PDF. Counts are reconciled, but automatic region detection alone cannot certify completeness.'))
    return refs,coverage,issues

def verify_metadata(md, settings):
    issues=[];s=md.get('source_values',{});decisions=[]
    def check(rule,field,actual,other,label,normalizer=lambda x:x):
        if actual in ('',None,[]) or other in ('',None,[]):
            issues.append(issue(rule,field,label+' verification could not run because evidence is missing.'));state='NOT_RUN'
        elif normalizer(actual)!=normalizer(other):
            issues.append(issue(rule,field,label+' mismatch. PDF/accepted value: '+str(actual)+'; support: '+str(other)));state='MISMATCH'
        else:state='MATCH' if actual==other else 'NORMALIZED_MATCH'
        decisions.append({'rule_id':rule,'field':field,'status':state,'source':label,'actual':actual,'other':other})
    check('ID-002','base_id',md.get('base_id'),s.get('scrapping_id'),'Scrapping ID',arxiv_id)
    check('ID-002','version',md.get('version'),s.get('scrapping_version'),'Scrapping version')
    check('ID-003','base_id',md.get('base_id'),s.get('html_id'),'HTML ID',arxiv_id)
    check('ID-003','version',md.get('version'),s.get('html_version'),'HTML version')
    def nt(t):
        t=norm(t)
        if settings.get('equivalent_dashes'):t=re.sub(r'\s*(?:—|–|--)\s*',' — ',t)
        return t
    check('TITLE-001','title',md.get('title'),s.get('html_title'),'HTML title',nt)
    check('AUTHOR-003','authors',[compact(a['surname']) for a in md['authors']],[compact(a['surname']) for a in s.get('api_authors',[])],'API author order')
    ids={a['id'] for a in md['affiliations']}
    for a in md['authors']:
        if any(i not in ids for i in a.get('affiliation_ids',[])):issues.append(issue('AFF-003','authors','Invalid affiliation link for '+a['surname']))
        if a.get('orcid') and not re.fullmatch(r'\d{4}-\d{4}-\d{4}-[0-9X]{4}',a['orcid']):issues.append(issue('ORCID-002','authors','Invalid ORCID format for '+a['surname']))
        if a.get('email') and not EMAIL_RE.fullmatch(a['email']):issues.append(issue('EMAIL-001','authors','Invalid email for '+a['surname']))
    if not md['authors']:issues.append(issue('AUTHOR-001','authors','No accepted author identities. Add authors from the PDF.'))
    if not md.get('abstract'):issues.append(issue('ABS-002','abstract','Abstract is empty.'))
    if any(v in ('???','unknown','none','') for k,v in md.get('profile',{}).items() if k!='supplier_id'):issues.append(issue('XML-005','profile','Sample delivery placeholders are in use. Set delivery values or explicitly accept these values for this export.'))
    return issues,decisions

def build_xml(md, timestamp=None):
    root=etree.Element('{'+ANI+'}units',nsmap={None:ANI,'ce':CE})
    def xml10_text(value):
        text=str(value)
        return ''.join(char for char in text if (ord(char) in (0x9,0xA,0xD) or
                       0x20<=ord(char)<=0xD7FF or 0xE000<=ord(char)<=0xFFFD or
                       0x10000<=ord(char)<=0x10FFFF))
    def e(parent,tag,text=None,**attrs):
        if tag.startswith('ce:'):tag='{'+CE+'}'+tag[3:]
        else:tag='{'+ANI+'}'+tag
        el=etree.SubElement(parent,tag,**{k:xml10_text(v) for k,v in attrs.items()})
        if text is not None:el.text=xml10_text(text)
        return el
    def inline(parent,plain,markup):
        plain=xml10_text(plain or '')
        if not markup:parent.text=plain;return
        markup=xml10_text(markup)
        try:fragment=secure_xml(('<root>'+markup+'</root>').encode('utf-8'))
        except Exception:
            parent.text=plain;return
        if xml10_text(''.join(fragment.itertext()))!=plain:
            parent.text=plain;return
        parent.text=xml10_text(fragment.text or '')
        for child in fragment:
            if child.tag not in ('sup','inf') or child.attrib or len(child):
                parent.text=plain
                for added in list(parent):parent.remove(added)
                return
            tagged=e(parent,child.tag,child.text or '');tagged.tail=xml10_text(child.tail or '')
    unit=e(root,'unit',type='ARTICLE');ui=e(unit,'unit-info');p=md.get('profile',{})
    for k,v in [('unit-id','1'),('order-id',p.get('order_id','unknown')),('parcel-id',p.get('parcel_id','none')),('supplier-id',p.get('supplier_id','4')),('timestamp',timestamp or now())]:e(ui,k,v)
    bib=e(e(unit,'unit-content'),'bibrecord');item=e(bib,'item-info');e(item,'status',state='new')
    itemlist=e(item,'itemidlist')
    if md.get('base_id'):e(itemlist,'itemid',md['base_id']+('v'+str(md['version']) if md.get('version') else ''),idtype='ARXIV')
    head=e(bib,'head');ci=e(head,'citation-info');e(ci,'citation-type',code='ar')
    for k in ('citation-language','abstract-language'):e(ci,k).set('{'+XML+'}lang','ENG')
    if md.get('keywords'):
        kws=e(ci,'author-keywords')
        for kw in md['keywords']:e(kws,'author-keyword',kw)
    title=e(e(head,'citation-title'),'titletext',original='y');inline(title,md.get('title',''),md.get('title_markup'));title.set('{'+XML+'}lang','ENG')
    def person(parent,a,tag='author'):
        el=e(parent,tag)
        if tag=='author':
            el.set('seq',str(a['global_seq']))
            if a.get('orcid'):el.set('orcid',a['orcid'])
        e(el,'ce:initials',a.get('initials',''));e(el,'ce:surname',a.get('surname',''))
        if a.get('given_name'):e(el,'ce:given-name',a['given_name'])
        if tag=='author' and a.get('degree'):e(el,'ce:degrees',a['degree'])
        if tag=='author' and a.get('email'):e(el,'ce:e-address',a['email'])
        return el
    def affiliation(parent,a):
        el=e(parent,'affiliation')
        for org in a.get('organizations',[]):e(el,'organization',org)
        # The receiving REDCAR validator does not permit address-part inside
        # affiliation. The complete printed affiliation remains in source-text.
        for key,tag in [('city','city'),('state','state'),('postal_code','postal-code')]:
            if a.get(key):e(el,tag,a[key])
        if a.get('country_code'):e(el,'country',**{'iso-code':a['country_code']})
        e(el,'ce:source-text',a.get('source_text',''))
    linked=set();emitted_affiliations=set();authors_by_id={a['id']:a for a in md['authors']};affs_by_id={f['id']:f for f in md['affiliations']}
    groups=md.get('author_groups')
    if groups is None:
        groups=[{'author_ids':[a['id'] for a in md['authors'] if aff['id'] in a.get('affiliation_ids',[])],'affiliation_id':aff['id']} for aff in md['affiliations']]
        groups=[g for g in groups if g['author_ids']]
    for index,group in enumerate(groups,1):
        members=[authors_by_id[aid] for aid in group.get('author_ids',[]) if aid in authors_by_id]
        if not members:continue
        g=e(head,'author-group',seq=index)
        for a in sorted(members,key=lambda a:a['global_seq']):person(g,a);linked.add(a['id'])
        aff=affs_by_id.get(group.get('affiliation_id'))
        if aff:affiliation(g,aff);emitted_affiliations.add(aff['id'])
    unlinked=[a for a in md['authors'] if a['id'] not in linked]
    if unlinked:
        g=e(head,'author-group',seq=len([g for g in head if g.tag=='{'+ANI+'}author-group'])+1)
        for a in unlinked:person(g,a)
    next_group_seq=len(head.findall('{'+ANI+'}author-group'))+1
    for aff in md['affiliations']:
        if aff['id'] in emitted_affiliations:continue
        group=e(head,'author-group',seq=next_group_seq);next_group_seq+=1
        affiliation(group,aff);emitted_affiliations.add(aff['id'])
    for a in md['authors']:
        if a.get('corresponding'):
            c=e(head,'correspondence');person(c,a,'person')
            affs=[f for f in md['affiliations'] if f['id'] in a.get('affiliation_ids',[]) ]
            if affs:affiliation(c,affs[0]);emitted_affiliations.add(affs[0]['id'])
            if a.get('email'):e(c,'ce:e-address',a['email'])
    abstracts=e(head,'abstracts');ab=e(abstracts,'abstract',original='y');ab.set('{'+XML+'}lang','ENG');inline(e(ab,'ce:para'),md.get('abstract',''),md.get('abstract_markup'))
    e(head,'source',srcid=p.get('source_id','???'));bibliography=e(e(bib,'tail'),'bibliography',refcount=len(md['references']))
    for seq,r in enumerate(md['references'],1):
        ref=e(bibliography,'reference',seq=seq);e(ref,'ref-info');inline(e(ref,'ref-fulltext'),r.get('full_text',r['source_text']),r.get('full_text_markup'));e(ref,'ce:source-text',r['source_text'])
    return etree.tostring(root,xml_declaration=True,encoding='UTF-8',pretty_print=True).decode()

def validate_xml(text, md=None):
    errors=[];warnings=[]
    try:r=secure_xml(text.encode('utf-8'))
    except Exception as ex:
        pos=getattr(ex,'position',(1,1));return {'well_formed':False,'profile_valid':False,'xsd':'NOT_RUN','errors':[{'message':str(ex),'line':pos[0],'column':pos[1]}],'warnings':[]}
    def error(message,node=None):errors.append({'message':message,'line':getattr(node,'sourceline',1) or 1,'column':1})
    if r.tag!='{'+ANI+'}units':error('Root must be units in the supplied ANI namespace.',r)
    for path in ['./a:unit','./a:unit/a:unit-info','./a:unit/a:unit-content/a:bibrecord','./a:unit/a:unit-content/a:bibrecord/a:head','./a:unit/a:unit-content/a:bibrecord/a:tail/a:bibliography']:
        if not r.xpath(path,namespaces=NS):error('Missing required sample-profile path '+path,r)
    refs=r.xpath('.//a:bibliography/a:reference',namespaces=NS)
    for bib in r.xpath('.//a:bibliography',namespaces=NS):
        own=bib.findall('a:reference',NS)
        if bib.get('refcount')!=str(len(own)):error('refcount does not equal the actual number of reference elements.',bib)
        if [x.get('seq') for x in own]!=[str(i) for i in range(1,len(own)+1)]:error('Reference sequence must be contiguous from 1.',bib)
        for ref in own:
            if not ref.xpath('string(ce:source-text)',namespaces=NS).strip():error('Reference source text is empty.',ref)
    authors=r.xpath('.//a:author-group/a:author',namespaces=NS);identity={}
    for a in authors:
        seq=a.get('seq');name=a.xpath('string(ce:surname)',namespaces=NS)+'|'+a.xpath('string(ce:given-name)',namespaces=NS)
        if seq in identity and identity[seq]!=name:error('Repeated global author seq has inconsistent names.',a)
        identity[seq]=name
    if not authors:error('No author identity is present.',r)
    if not r.xpath('string(.//a:titletext)',namespaces=NS).strip():error('Title is empty.',r)
    if md:
        inline_fields=[('title',md.get('title',''),md.get('title_markup','')),('abstract',md.get('abstract',''),md.get('abstract_markup',''))]
        inline_fields.extend((f'reference {ref.get("seq",i+1)}',ref.get('full_text',ref.get('source_text','')),ref.get('full_text_markup','')) for i,ref in enumerate(md.get('references',[])))
        for label,plain,markup in inline_fields:
            if not markup:continue
            try:fragment=secure_xml(('<root>'+str(markup)+'</root>').encode('utf-8'))
            except Exception:
                warnings.append(f'{label} inline markup could not be read; plain text was written to XML.')
                continue
            valid_text=''.join(fragment.itertext())==str(plain or '')
            valid_tags=all(child.tag in ('sup','inf') and not child.attrib and len(child)==0 for child in fragment)
            if not valid_text or not valid_tags:warnings.append(f'{label} inline markup was not applied; plain text was written to XML.')
    if md and len(refs)!=len(md.get('references',[])):warnings.append('Manual XML reference count differs from current metadata. Verify the selected revision.')
    for group in r.xpath('.//a:author-group',namespaces=NS):
        if not group.xpath('./a:author',namespaces=NS):warnings.append('An unlinked affiliation was preserved in an author-group without an author.')
    known=set('units unit unit-info unit-id order-id parcel-id supplier-id timestamp unit-content bibrecord item-info status itemidlist itemid head citation-info citation-type citation-language abstract-language author-keywords author-keyword citation-title titletext author-group author affiliation organization address-part city state postal-code country correspondence person abstracts abstract source tail bibliography reference ref-info ref-fulltext sup inf'.split())
    for el in r.iter():
        if not isinstance(el.tag,str):continue
        q=etree.QName(el)
        if (q.namespace==ANI and q.localname not in known) or q.namespace not in (ANI,CE):warnings.append('Unmapped element '+q.localname+' at line '+str(el.sourceline))
    return {'well_formed':True,'profile_valid':not errors,'xsd':'NOT_RUN','errors':errors,'warnings':warnings,'reference_count':len(refs),'author_count':len(identity)}

def sanitize_html(data):
    doc=html.fromstring(data)
    for e in doc.xpath('//script|//iframe|//object|//embed|//link|//base|//meta|//form'):e.drop_tree()
    for e in doc.iter():
        for k in list(e.attrib):
            if k.lower().startswith('on') or k.lower() in ('src','srcset','href','action','style'):del e.attrib[k]
    return '<meta charset="utf-8"><style>body{font:16px system-ui;line-height:1.65;padding:24px;color:#17273d;max-width:850px;margin:auto}pre{white-space:pre-wrap}</style>'+html.tostring(doc,encoding='unicode')
