"""ICE Local browser app. Run with Python, then open the printed localhost URL."""
from __future__ import annotations
import argparse, base64, copy, csv, hmac, io, json, mimetypes, os, re, secrets, shutil, socket, threading, time
import functools, traceback, uuid, webbrowser, zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
import engine
import documents
import rulebook
import triage
from lxml import etree

BASE=Path(__file__).resolve().parent
DATA=Path(os.environ.get('ICE_DATA_DIR',BASE/'data')).resolve()
DATA.mkdir(parents=True,exist_ok=True)
for sub in ('jobs','uploads','exports'):(DATA/sub).mkdir(exist_ok=True)
TOKEN=secrets.token_urlsafe(32)
LOCK=threading.RLock()
POOL=ThreadPoolExecutor(max_workers=2)
NETWORK_ATTEMPTS=[]
SETTINGS_DEFAULT={'equivalent_dashes':False,'tesseract_path':'','supplier_id':'4','source_id':'???','order_id':'unknown','parcel_id':'none'}

def atomic(path,data):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def atomic_text(path,data):
    path=Path(path);temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(data,encoding='utf-8');temp.replace(path)

def settings():
    p=DATA/'settings.json'
    return {**SETTINGS_DEFAULT,**(json.loads(p.read_text(encoding='utf-8')) if p.exists() else {})}

def valid_id(value):
    if not re.fullmatch(r'[a-f0-9-]{12,40}',value or ''):raise ValueError('Invalid local record ID')
    return value

def jobdir(jid):return DATA/'jobs'/valid_id(jid)
def read_job(jid):
    job=json.loads((jobdir(jid)/'job.json').read_text(encoding='utf-8'))
    for item in job.get('issues',[]):item['severity']='INFO'
    job.pop('workflow_state',None);job.pop('workflow_note',None)
    return job
def all_jobs():
    """Every saved job. A damaged job.json is listed as an error instead of hiding the others."""
    jobs=[]
    for p in (DATA/'jobs').glob('*/job.json'):
        try:jobs.append(json.loads(p.read_text(encoding='utf-8')))
        except (OSError,ValueError) as ex:
            print(f'Damaged article record {p}: {ex}',flush=True)
            jobs.append({'id':p.parent.name,'status':'ERROR','created':engine.now(),
                         'progress':'The saved record for this article is damaged. Clear it and import the package again.'})
    return jobs
def save_job(job):
    root=jobdir(job['id'])
    atomic(root/'job.json',job)
    if job.get('status')=='READY' and job.get('metadata') is not None:
        atomic(root/'metadata.json',job['metadata'])
        atomic(root/'routing.json',job.get('triage',{}))
        atomic_text(root/'current.xml',job.get('xml',''))
def audit(job,action,details=None):
    job.setdefault('audit',[]).append({'timestamp':engine.now(),'actor':'local-operator','action':action,'details':details or {}})
def summary(j):
    m=j.get('metadata',{})
    t=j.get('triage',{})
    metadata_count=(sum(bool(m.get(k)) for k in ('base_id','version','title','abstract'))+
                    sum(len(m.get(k,[])) for k in ('keywords','authors','affiliations','references'))+
                    sum(bool(a.get('email'))+bool(a.get('orcid')) for a in m.get('authors',[])))
    return {k:j.get(k) for k in ('id','article_id','package_id','package_name','status','progress','created','revision','manual_xml','xml_stale','export_status')}|{'title':m.get('title',''),'metadata_count':metadata_count,'reference_count':len(m.get('references',[])),'author_count':len(m.get('authors',[])),'issues':sum(i['status']=='OPEN' for i in j.get('issues',[])),'queue':t.get('queue','REGULAR'),'automatic_queue':t.get('automatic_queue',t.get('queue','REGULAR')),'queue_override':None,'matched':t.get('matched',0),'total':t.get('total',0),'triage_reasons':t.get('reasons',[])}

def refresh(job):
    dynamic,decisions=engine.verify_metadata(job['metadata'],settings())
    validation=engine.validate_xml(job.get('xml',''),job['metadata'])
    if job.get('manual_xml'):
        dynamic.append(engine.issue('EDIT-008','xml','Review direct XML changes against the sources. Current XML hash: '+engine.digest(job['xml'])[:12]))
    if validation.get('reference_count') is not None and validation['reference_count']!=len(job['metadata']['references']):
        dynamic.append(engine.issue('REF-018','references',f"Direct XML contains {validation['reference_count']} references; metadata contains {len(job['metadata']['references'])}. Reconcile the difference against the PDF."))
    old={i['id']:i for i in job.get('issues',[])}
    new=[]
    for issue in job.get('extraction_issues',[])+dynamic:
        issue=dict(issue);issue['severity']='INFO'
        if issue['id'] in old and old[issue['id']]['status']!='OPEN':issue=old[issue['id']]
        if not any(i['id']==issue['id'] for i in new):new.append(issue)
    job['issues']=new;job['decisions']=decisions
    job['validation']=validation
    route(job)

@functools.lru_cache(maxsize=8)
def cached_layout(path,stamp):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def route(job):
    """Keep the file in General and record rulebook matches from extraction.json."""
    p=jobdir(job['id'])/'extraction.json'
    try:layout=cached_layout(str(p),p.stat().st_mtime_ns)
    except (OSError,ValueError):layout=None
    job['triage']=triage.assess(job,layout)

def snapshot(job):
    d=jobdir(job['id'])/'history';d.mkdir(exist_ok=True)
    atomic(d/f"revision-{job['revision']:05d}.json",{k:job.get(k) for k in ('metadata','xml','issues','validation','manual_xml','xml_stale','queue_override','revision')})

def process_job(jid):
    try:
        with LOCK:
            j=read_job(jid);j['status']='PROCESSING';save_job(j)
        def progress(text):
            with LOCK:
                j=read_job(jid);j['progress']=text;save_job(j)
        root=jobdir(jid)
        files={role:next((f for f in j['files'] if f['id']==fid),None) for role,fid in j['selected'].items()}
        feeder={}
        support,issues=engine.source_data(files,root,feeder)
        for role in ('API','HTML','SCRAPPING'):
            if not files.get(role):issues.append(engine.issue('PKG-002',role,role+' support document is missing. Dependent verification needs review.'))
        pdf=files.get('PDF')
        if not pdf:raise ValueError('Select a main PDF to start extraction.')
        layout,li=engine.extract_layout(root/pdf['path'],settings(),progress)
        atomic(root/'extraction.json',layout)
        normalized='# PDF normalized text (secondary to the original PDF and extraction.json)\n\n'+'\n\n'.join('## Page '+str(p['number'])+' ('+p['text_origin']+')\n\n'+'\n'.join(l['text'] for l in p['lines']) for p in layout['pages'])
        atomic_text(root/'normalized.md',normalized)
        feeder_record={'version':1,'engine_version':engine.VERSION,'pdf':{'name':pdf['name'],'sha256':layout['pdf_sha256'],
                       'pages':len(layout['pages']),'page_origins':[p['text_origin'] for p in layout['pages']]},
                       'documents':feeder,'parsed_values':support}
        atomic(root/'source_feeder.json',feeder_record)
        atomic_text(root/'source_feeder.md','# Support-document feeder\n\nThe PDF and extraction.json remain authoritative.\n\n'+
                    '\n\n'.join('## '+role+' · '+doc['name']+'\n\nParsed fields: '+
                                 json.dumps(doc['values'],ensure_ascii=False)+'\n\n'+(doc['text'] or '(Fields are in XML attributes or HTML metadata.)')
                                 for role,doc in feeder.items()))
        progress('Applying rules and building XML')
        md,mi=engine.extract_metadata(layout,support,settings())
        md['profile']={k:settings()[k] for k in ('supplier_id','source_id','order_id','parcel_id')}
        if md['base_id'] and md['base_id']!=j['article_id']:issues.append(engine.issue('PKG-001','base_id','PDF content ID differs from the package filename ID.'))
        atomic(root/'candidate_metadata.json',md)
        xml=engine.build_xml(md)
        with LOCK:
            j=read_job(jid);j.update(metadata=md,original_values=triage.original_values(md),extraction_issues=issues+li+mi,xml=xml,manual_xml=False,xml_stale=False,status='READY',progress='XML generated; ready for review',revision=j['revision']+1,pages=len(layout['pages']))
            refresh(j);audit(j,'PROCESSED',{'engine_version':engine.VERSION,'input_hashes':{f['name']:f['sha256'] for f in j['files']},'queue':j['triage']['queue'],'xml_sha256':engine.digest(xml)});snapshot(j);save_job(j)
    except Exception as ex:
        traceback.print_exc()
        try:
            with LOCK:
                j=read_job(jid);j['status']='ERROR';j['progress']=str(ex);audit(j,'PROCESSING_ERROR',{'message':str(ex)});save_job(j)
        except Exception:
            # Without this the job would look like it is still processing.
            print(f'Could not record the processing error for article {jid}:',flush=True);traceback.print_exc()

classify=documents.classify

def import_batch(batchid):
    batch=DATA/'uploads'/valid_id(batchid)
    if not batch.is_dir():raise ValueError('Upload batch not found')
    groups=defaultdict(list);ignored=[];report=[]
    for e in documents.inventory(batch):
        report.append({'package':e['package'],'name':e['name'],'role':e['role'],'article_id':e['key'],'status':'SKIPPED' if e['reason'] else 'RECOGNIZED','reason':e['reason']})
        if e['reason']:ignored.append(e['name']);continue
        groups[(e['package'],e['key'])].append((e['path'],e['role']))
    created=[]
    for (package,article),items in groups.items():
        if not any(role=='PDF' for p,role in items):ignored.extend(p.name for p,role in items);continue
        jid=uuid.uuid4().hex;root=jobdir(jid);(root/'sources').mkdir(parents=True)
        files=[];byrole=defaultdict(list);seen=set()
        for n,(p,role) in enumerate(items):
            sha=engine.digest(p.read_bytes())
            if (role,sha) in seen:continue
            seen.add((role,sha));fid=uuid.uuid4().hex[:12]
            safe=re.sub(r'[^\w.()-]','_',p.name)
            dest=root/'sources'/(fid+'_'+safe);shutil.copyfile(p,dest)
            f={'id':fid,'name':p.name,'role':role,'path':str(dest.relative_to(root)),'sha256':sha};files.append(f);byrole[role].append(fid)
        complete=all(len(byrole.get(role,[]))==1 for role in documents.ROLES)
        # An unrecognized XML only needs a decision when it could fill a missing role.
        ambiguous=(bool(byrole.get('XML')) and not complete) or any(len(v)>1 for k,v in byrole.items() if k in documents.ROLES)
        if complete:
            unused={f['name'] for f in files if f['role']=='XML'}
            for r in report:
                if r['package']==package and r['article_id']==article and r['role']=='XML' and Path(r['name']).name in unused:
                    r['reason']='Not used: the package already has its PDF, API, Scrapping and HTML files.'
        selected={role:ids[0] for role,ids in byrole.items() if role in documents.ROLES and len(ids)==1}
        j={'id':jid,'article_id':article,'batch_id':batchid,'package_id':engine.digest([batchid,package])[:16],'package_name':package,'created':engine.now(),'status':'NEEDS_SOURCES' if ambiguous else 'QUEUED','progress':'Select the correct source files' if ambiguous else 'Queued','revision':0,'files':files,'selected':selected,'issues':[],'audit':[],'manual_xml':False,'xml_stale':False,'export_status':'NOT_EXPORTED','triage':{'queue':'REGULAR','automatic_queue':'REGULAR','queue_override':None,'reasons':['Matching and XML generation have not finished.'],'checks':[]}}
        audit(j,'IMPORTED',{'files':len(files),'package':package});save_job(j);created.append(jid)
        if not ambiguous:POOL.submit(process_job,jid)
    return {'jobs':created,'ignored':ignored,'report':report,'packages':list(dict.fromkeys(r['package'] for r in report))}

from collections import defaultdict

class AuthenticationRequired(Exception):
    pass

LOGIN_USERS = {name.casefold(): name for name in ('AP01', 'AP02', 'AP03', 'ST022')}

def authenticate_shared_login(header, shared_password):
    """Accept one of the named shared-workspace logins with the common secret."""
    if not shared_password or not str(header or '').startswith('Basic '):
        return None
    try:
        credentials=base64.b64decode(header[6:],validate=True).decode('utf-8')
        username,provided=credentials.split(':',1)
    except (ValueError,UnicodeError):
        return None
    canonical=LOGIN_USERS.get(username.casefold())
    if canonical and hmac.compare_digest(provided,shared_password):
        return canonical
    return None

class Handler(BaseHTTPRequestHandler):
    server_version='ICE-Local/1.0'
    def log_message(self,*args):pass
    def send(self,status,data,kind='application/json',filename=None,headers=None):
        if kind=='application/json':data=json.dumps(data,ensure_ascii=False).encode()
        elif isinstance(data,str):data=data.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if filename:self.send_header('Content-Disposition','attachment; filename="'+re.sub(r'[^\w. -]','_',filename)+'"')
        if kind.startswith('text/html'):
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-src 'self' blob:; object-src 'none'; connect-src 'self'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def route(self):
        raw_host=self.headers.get('Host','')
        host=(urlparse('//'+raw_host).hostname or '').lower().rstrip('.')
        bind_host=self.server.server_address[0]
        local=bind_host in ('127.0.0.1','::1','localhost')
        if local:
            if host not in ('127.0.0.1','localhost','::1'):raise PermissionError('Localhost access only')
            self.authenticated_username=None
        else:
            allowed={x.strip().lower().rstrip('.') for x in (os.environ.get('ICE_ALLOWED_HOSTS','')+','+os.environ.get('REPLIT_DOMAINS','')+','+os.environ.get('REPLIT_DEV_DOMAIN','')).split(',') if x.strip()}
            if host not in allowed and not host.endswith(('.replit.app','.replit.dev','.repl.co')):
                raise PermissionError('This host is not configured for ICE.')
            password=os.environ.get('ICE_ACCESS_PASSWORD','')
            self.authenticated_username=authenticate_shared_login(self.headers.get('Authorization',''),password)
            if not self.authenticated_username:raise AuthenticationRequired()
        u=urlparse(self.path);return u.path,parse_qs(u.query)
    def redirect(self,location):
        self.send_response(302);self.send_header('Location',location);self.send_header('Content-Length','0');self.send_header('Cache-Control','no-store');self.end_headers()
    def do_GET(self):
        try:
            path,q=self.route()
            if path in ('/login.html','/auth/login','/auth/callback'):return self.redirect('/')
            if path=='/api/session':return self.send(200,{'token':TOKEN,'version':engine.VERSION,'settings':settings(),'country_codes':engine.COUNTRIES,'network_guard':'active','blocked_network_attempts':len(NETWORK_ATTEMPTS),'ocr_available':bool(settings().get('tesseract_path') or shutil.which('tesseract')),'user':{'name':getattr(self,'authenticated_username',None) or 'Local operator','role':'editor' if getattr(self,'authenticated_username',None) else 'local'}})
            if path=='/api/jobs':
                with LOCK:jobs=[summary(j) for j in all_jobs()]
                return self.send(200,sorted(jobs,key=lambda j:j['created'],reverse=True))
            if path=='/api/rules':return self.send(200,rulebook.load())
            if path.startswith('/api/jobs/'):
                parts=path.split('/');jid=parts[3]
                with LOCK:j=read_job(jid)
                root=jobdir(jid);op=parts[4] if len(parts)>4 else ''
                if not op:return self.send(200,j)
                if op=='page':
                    pno=int(q.get('number',['1'])[0]);layout=json.loads((root/'extraction.json').read_text(encoding='utf-8'));return self.send(200,layout['pages'][pno-1])
                if op=='search':
                    term=q.get('q',[''])[0].casefold();layout=json.loads((root/'extraction.json').read_text(encoding='utf-8'))
                    return self.send(200,[{'page':l['page'],'bbox':l['bbox'],'text':l['text']} for p in layout['pages'] for l in p['lines'] if term and term in l['text'].casefold()])
                if op=='image':
                    f=next(f for f in j['files'] if f['id']==j['selected'].get('PDF'))
                    with engine.fitz.open(root/f['path']) as doc:
                        pno=int(q.get('page',['1'])[0]);data=doc[pno-1].get_pixmap(matrix=engine.fitz.Matrix(1.7,1.7)).tobytes('png')
                    name=f"{j['article_id']}_page_{pno:03d}.png" if q.get('download')==['1'] else None
                    return self.send(200,data,'image/png',name)
                if op=='source':
                    f=next(f for f in j['files'] if f['id']==q.get('file',[''])[0]);data=(root/f['path']).read_bytes()
                    if q.get('render')==['1'] and f['role']=='HTML':return self.send(200,engine.sanitize_html(data),'text/html; charset=utf-8')
                    kind='application/pdf' if f['role']=='PDF' else 'text/plain; charset=utf-8'
                    return self.send(200,data,kind,f['name'] if q.get('download') else None)
                if op=='audit':return self.send(200,{'events':j['audit'],'issues':j['issues'],'validation':j.get('validation'),'revision':j['revision'],'xml_sha256':engine.digest(j.get('xml',''))})
                if op=='extraction':return self.send(200,(root/'extraction.json').read_bytes(),'application/octet-stream',j['article_id']+'_extraction.json')
                if op=='markdown':return self.send(200,(root/'normalized.md').read_bytes(),'text/markdown',j['article_id']+'.md')
                if op in ('feeder','feeder-markdown','metadata-file','routing-file'):
                    filename={'feeder':'source_feeder.json','feeder-markdown':'source_feeder.md','metadata-file':'metadata.json','routing-file':'routing.json'}[op]
                    kind='text/markdown' if filename.endswith('.md') else 'application/json'
                    content=(root/filename).read_text(encoding='utf-8')
                    return self.send(200,content if filename.endswith('.md') else json.loads(content),kind,j['article_id']+'_'+filename)
                if op=='history':
                    return self.send(200,[{'revision':int(p.stem.split('-')[1])} for p in sorted((root/'history').glob('*.json'),reverse=True)])
                if op=='revision':return self.send(200,json.loads((root/'history'/f"revision-{int(q.get('number',['0'])[0]):05d}.json").read_text(encoding='utf-8')))
            file=BASE/'static'/('index.html' if path=='/' else path.lstrip('/'))
            if file.resolve().is_relative_to((BASE/'static').resolve()) and file.is_file():
                kind={'.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.html':'text/html; charset=utf-8'}.get(file.suffix) or mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                return self.send(200,file.read_bytes(),kind)
            self.send(404,{'error':'Not found'})
        except AuthenticationRequired:self.send(401,{'error':'Sign in with the shared ICE access password.'},headers={'WWW-Authenticate':'Basic realm="ICE shared workspace", charset="UTF-8"'})
        except PermissionError as e:self.send(403,{'error':str(e)})
        except Exception as e:self.send(400,{'error':str(e)})
    def do_POST(self):
        try:
            path,q=self.route()
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise PermissionError('Cross-origin writes are blocked.')
            if self.headers.get('X-ICE-Token')!=TOKEN:raise PermissionError('Missing local session token. Refresh the app.')
            length=int(self.headers.get('Content-Length',0))
            if length>160*1024*1024:raise ValueError('Single upload/request limit is 160 MB. Split the batch.')
            data=self.rfile.read(length)
            if path=='/api/upload':
                batchid=valid_id(q.get('batch',[''])[0]);name=q.get('name',['upload'])[0].replace('\\','/')
                base=DATA/'uploads'/batchid;base.mkdir(exist_ok=True);p=(base/name).resolve()
                if not p.is_relative_to(base.resolve()):raise ValueError('Unsafe upload path')
                if p.exists() and p.read_bytes()!=data:raise ValueError('A different file already uses this upload name.')
                p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return self.send(200,{'saved':name})
            body=json.loads(data or b'{}')
            if path=='/api/parse-affiliation':
                ev=body.get('evidence') or {}
                return self.send(200,engine.parse_affiliation(str(body.get('text',''))[:2000],str(body.get('marker','1'))[:8],[ev],bool(body.get('printed_marker',False))))
            if path=='/api/recheck':
                # Re-match all articles, regenerate generated XML, and retry failed imports.
                book=rulebook.load();checked=changed=regenerated=retrying=manual=0;failures=[]
                with LOCK:
                    for j in all_jobs():
                        before=j.get('triage',{});previous=before.get('queue')
                        j['queue_override']=None
                        if j.get('status')=='ERROR':
                            j['status']='QUEUED';j['progress']='Retrying matching and XML generation';j['revision']+=1
                            route(j);audit(j,'RETRY_AFTER_MATCH_RULE_UPDATE',{'rulebook_sha256':book['sha256']});save_job(j)
                            POOL.submit(process_job,j['id']);retrying+=1;checked+=1;continue
                        if j.get('status')=='READY' and j.get('metadata'):
                            xml_regenerated=False
                            if j.get('manual_xml'):
                                manual+=1
                            else:
                                try:
                                    snapshot(j);j['xml']=engine.build_xml(j['metadata']);j['xml_stale']=False;j['revision']+=1
                                    regenerated+=1;xml_regenerated=True
                                except Exception as ex:
                                    failures.append({'article_id':j.get('article_id'),'error':str(ex)})
                            route(j);checked+=1
                            changed+=previous!='REGULAR'
                            audit(j,'MATCH_RECHECK_AND_XML',{'rulebook_sha256':book['sha256'],'xml_regenerated':xml_regenerated})
                        else:
                            if j.get('status')!='READY':route(j)
                            checked+=1;changed+=previous!='REGULAR'
                        save_job(j)
                return self.send(200,{'checked':checked,'changed':changed,'regenerated':regenerated,'retrying':retrying,'manual_xml_preserved':manual,'failures':failures,'rulebook_errors':book['errors']})
            if path=='/api/clear':
                ids=list(dict.fromkeys(body.get('job_ids',[])))
                if body.get('all'):ids=[p.parent.name for p in (DATA/'jobs').glob('*/job.json')]
                if len(ids)>5000:raise ValueError('Too many records in one clear operation.')
                removed=[];skipped=[];batches=set()
                with LOCK:
                    for jid in ids:
                        root=jobdir(jid)
                        if not (root/'job.json').exists():continue
                        try:job=read_job(jid)
                        except ValueError:job={}  # A damaged record can always be cleared.
                        if job.get('status') in ('QUEUED','PROCESSING'):skipped.append(jid);continue
                        if job.get('batch_id'):batches.add(job['batch_id'])
                        shutil.rmtree(root);removed.append(jid)
                    remaining=all_jobs()
                    for bid in batches:
                        if not any(j.get('batch_id')==bid for j in remaining):
                            upload=DATA/'uploads'/valid_id(bid)
                            if upload.is_dir():shutil.rmtree(upload)
                    if body.get('all') and not remaining:
                        shutil.rmtree(DATA/'uploads');(DATA/'uploads').mkdir()
                return self.send(200,{'removed':removed,'skipped':skipped})
            if path=='/api/export-batch':
                ids=list(dict.fromkeys(body.get('job_ids',[])))
                if not ids or len(ids)>500:raise ValueError('Select 1 to 500 articles for one download.')
                include_sources=bool(body.get('include_sources'))
                buf=io.BytesIO();manifest=[]
                with LOCK,zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
                    for jid in ids:
                        j=read_job(jid)
                        if j['status']!='READY':manifest.append({'id':jid,'status':'SKIPPED_NOT_READY'});continue
                        root=jobdir(jid);package_token=re.sub(r'[^\w.-]','_',j.get('package_name','Package')).strip('._') or 'Package'
                        prefix=package_token+'/'+re.sub(r'[^\w.-]','_',j['article_id'])+'_'+jid[:8]+'/'
                        validation=engine.validate_xml(j.get('xml',''),j['metadata'])
                        valid=validation['profile_valid']
                        state='READY' if valid else 'INVALID_DRAFT'
                        j['export_status']='EXPORTED';j['validation']=validation
                        openissues=[i for i in j.get('issues',[]) if i['status']=='OPEN']
                        audit(j,'EXPORT',{'status':'EXPORTED','revision':j['revision'],'sha256':engine.digest(j.get('xml','')),'unresolved_issues':[i['id'] for i in openissues],'manual_xml':j['manual_xml'],'xml_stale':j['xml_stale'],'batch':True})
                        save_job(j)
                        z.writestr(prefix+j['article_id']+'_'+state+'.xml',j.get('xml',''))
                        z.writestr(prefix+'audit.json',json.dumps({'events':j['audit'],'issues':j['issues'],'validation':validation,'triage':j.get('triage')},ensure_ascii=False,indent=2))
                        if include_sources:
                            for f in j['files']:z.write(root/f['path'],prefix+'sources/'+f['id']+'_'+re.sub(r'[^\w.-]','_',f['name'].split('/')[-1]))
                        manifest.append({'id':jid,'package':j.get('package_name'),'article_id':j['article_id'],'status':state,'references':len(j['metadata']['references']),'authors':len(j['metadata']['authors']),'issues':sum(i['status']=='OPEN' for i in j.get('issues',[]))})
                    z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
                return self.send(200,buf.getvalue(),'application/zip','ICE_selected_articles.zip')
            if path=='/api/process':return self.send(200,import_batch(body['batch']))
            if path=='/api/demo':
                batchid=uuid.uuid4().hex;d=DATA/'uploads'/batchid;d.mkdir()
                for name in ('toolsamples.zip','regular_demo.zip'):shutil.copyfile(BASE/'samples'/name,d/name)
                return self.send(200,import_batch(batchid))
            if path=='/api/settings':
                s=settings()
                for k in SETTINGS_DEFAULT:
                    if k in body:s[k]=bool(body[k]) if k=='equivalent_dashes' else str(body[k])[:400]
                atomic(DATA/'settings.json',s);return self.send(200,s)
            if path.startswith('/api/jobs/'):
                jid=path.split('/')[3];action=body.get('action');root=jobdir(jid)
                with LOCK:
                    j=read_job(jid)
                    if body.get('revision') is not None and body['revision']!=j['revision']:return self.send(409,{'error':'This article changed in another tab. Reload before saving.'})
                    if action=='select':
                        if j['status'] in ('QUEUED','PROCESSING'):raise ValueError('Wait for extraction to finish before changing source files.')
                        if j.get('metadata'):raise ValueError('Import the files as a new article to change source files after editing.')
                        if not body['selected'].get('PDF'):raise ValueError('Choose a main PDF before processing.')
                        used=set()
                        for role,fid in body['selected'].items():
                            allowed={role,'XML'} if role in ('API','SCRAPPING') else {role}
                            if role not in documents.ROLES or (fid and not any(f['id']==fid and f['role'] in allowed for f in j['files'])):raise ValueError('Invalid source selection')
                            if fid in used:raise ValueError('Choose a different document for each source role.')
                            if fid:used.add(fid)
                        j['selected']=body['selected'];j['status']='QUEUED';save_job(j);POOL.submit(process_job,jid);return self.send(200,j)
                    if action=='reextract':
                        if j['status'] in ('QUEUED','PROCESSING'):raise ValueError('This article is already processing.')
                        if not body.get('confirmed'):return self.send(409,{'error':'Re-extraction replaces current metadata and generated XML. Confirm to continue.','needs_confirmation':True})
                        snapshot(j);j['status']='QUEUED';j['progress']='Re-extracting PDF and matching sources';j['revision']+=1
                        audit(j,'REEXTRACTION_REQUESTED',{'engine_version':engine.VERSION,'previous_revision':j['revision']-1});save_job(j)
                        POOL.submit(process_job,jid);return self.send(202,j)
                    if j['status']!='READY':raise ValueError('Wait for extraction to finish.')
                    if action=='metadata':
                        m=body['metadata']
                        for key in ('authors','affiliations','references','keywords'):
                            if not isinstance(m.get(key),list):raise ValueError(key+' must be a list')
                        for affiliation in m['affiliations']:
                            value=str(affiliation.get('country_code') or '').strip()
                            code=engine.country_code_for(value)
                            if code:affiliation['country_code']=code
                        for key in ('source_values','field_evidence','coverage'):m[key]=j['metadata'].get(key)
                        old_candidates={v.get('id'):v for v in j['metadata'].get('affiliation_candidates',[])}
                        old_author_candidates={v.get('id'):v for v in j['metadata'].get('author_candidates',[])}
                        posted_candidates={v.get('id'):v for v in m.get('affiliation_candidates',[])}
                        m['affiliation_candidates']=[]
                        for cid,old in old_candidates.items():
                            posted=posted_candidates.get(cid,{})
                            candidate=copy.deepcopy(old)
                            state=posted.get('status',old.get('status','UNREVIEWED'))
                            candidate['status']=state if state in ('UNREVIEWED','ADDED','DISMISSED') else old.get('status','UNREVIEWED')
                            if candidate['status']=='ADDED' and posted.get('affiliation_id'):candidate['affiliation_id']=posted['affiliation_id']
                            if candidate['status']=='DISMISSED':candidate['review_note']=str(posted.get('review_note','Not an original affiliation'))[:500]
                            m['affiliation_candidates'].append(candidate)
                        posted_author_candidates={v.get('id'):v for v in m.get('author_candidates',[])}
                        m['author_candidates']=[]
                        for cid,old in old_author_candidates.items():
                            candidate=copy.deepcopy(old);posted=posted_author_candidates.get(cid,{})
                            state=posted.get('status',old.get('status','UNREVIEWED'))
                            candidate['status']=state if state in ('UNREVIEWED','ADDED','SAME_AUTHOR') else old.get('status','UNREVIEWED')
                            m['author_candidates'].append(candidate)
                        m['manual_assignments']=j['metadata'].get('manual_assignments',[])+[a for a in m.get('manual_assignments',[]) if a not in j['metadata'].get('manual_assignments',[])]
                        for collection in ('authors','affiliations','references'):
                            originals={v['id']:v for v in j['metadata'][collection]}
                            for val in m[collection]:
                                old=originals.get(val.get('id'),{})
                                candidate=old_author_candidates.get(val.get('candidate_id')) if collection=='authors' else next((old_candidates.get(c.get('id')) for c in m['affiliation_candidates'] if c.get('affiliation_id')==val.get('id')),None)
                                val['evidence']=old.get('evidence',[]) or (candidate or {}).get('evidence',[])
                                if collection=='authors':val['email_evidence']=old.get('email_evidence',[]) if val.get('email')==old.get('email') else []
                        for i,a in enumerate(m['authors'],1):a['global_seq']=i
                        for i,r in enumerate(m['references'],1):r['seq']=i
                        snapshot(j);oldhash=engine.digest(j['metadata']);j['metadata']=m;j['revision']+=1
                        # Any material edit reopens impacted review decisions; never silently reuses an override.
                        for it in j['issues']:
                            if it['status']!='OPEN':it['status']='OPEN';it.pop('override_reason',None)
                        if j['manual_xml']:j['xml_stale']=True
                        else:j['xml']=engine.build_xml(m);j['xml_stale']=False
                        audit(j,'METADATA_EDIT',{'previous_hash':oldhash,'new_hash':engine.digest(m)});refresh(j)
                    elif action=='xml':
                        snapshot(j);j['xml']=str(body['xml']);j['manual_xml']=True;j['xml_stale']=False;j['revision']+=1;audit(j,'DIRECT_XML_EDIT',{'sha256':engine.digest(j['xml'])});refresh(j)
                    elif action=='generate':
                        if j['manual_xml'] and not body.get('confirmed'):return self.send(409,{'error':'Regeneration replaces direct XML edits. Confirm to continue.','needs_confirmation':True})
                        snapshot(j);j['xml']=engine.build_xml(j['metadata']);j['manual_xml']=False;j['xml_stale']=False;j['revision']+=1;audit(j,'REGENERATED');refresh(j)
                    elif action=='validate':
                        return self.send(200,engine.validate_xml(body.get('xml',j['xml']),j['metadata']))
                    elif action=='format':
                        parsed=engine.secure_xml(body.get('xml',j['xml']).encode())
                        return self.send(200,{'xml':etree.tostring(parsed,encoding='UTF-8',xml_declaration=True,pretty_print=True).decode()})
                    elif action=='restore':
                        previous=json.loads((root/'history'/f"revision-{int(body['target_revision']):05d}.json").read_text(encoding='utf-8'));snapshot(j)
                        j['metadata']=previous['metadata'];j['xml']=previous['xml'];j['manual_xml']=previous['manual_xml'];j['xml_stale']=previous.get('xml_stale',False);j['queue_override']=previous.get('queue_override');j['revision']+=1;audit(j,'RESTORED_REVISION',{'target':body['target_revision']});refresh(j)
                    elif action=='export':
                        validation=engine.validate_xml(j['xml'],j['metadata']);openissues=[i for i in j['issues'] if i['status']=='OPEN']
                        draft=body.get('draft',False)
                        status='INVALID_DRAFT_SAVED' if draft else 'EXPORTED'
                        j['export_status']=status;j['validation']=validation
                        audit(j,'EXPORT',{'status':status,'revision':j['revision'],'sha256':engine.digest(j['xml']),'unresolved_issues':[i['id'] for i in openissues],'manual_xml':j['manual_xml'],'xml_stale':j['xml_stale']})
                        save_job(j)
                        name=re.sub(r'[^\w.-]','_',j['metadata'].get('base_id') or j['article_id'])+('_DRAFT' if draft else '')
                        if body.get('format')=='xml':return self.send(200,j['xml'],'application/xml',name+'.xml')
                        buf=io.BytesIO()
                        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
                            z.writestr(name+'.xml',j['xml']);z.writestr(name+'_audit.json',json.dumps({'events':j['audit'],'issues':j['issues'],'validation':validation,'input_files':j['files']},ensure_ascii=False,indent=2))
                            s=io.StringIO();writer=csv.writer(s);writer.writerow(['Rule','Field','Severity','Status','Message'])
                            for it in j['issues']:writer.writerow([it['rule_id'],it['field'],it['severity'],it['status'],it['message']])
                            z.writestr(name+'_issues.csv',s.getvalue())
                        return self.send(200,buf.getvalue(),'application/zip',name+'_XML_AUDIT.zip')
                    else:raise ValueError('Unknown action')
                    save_job(j);return self.send(200,j)
            self.send(404,{'error':'Not found'})
        except AuthenticationRequired:self.send(401,{'error':'Sign in with the shared ICE access password.'},headers={'WWW-Authenticate':'Basic realm="ICE shared workspace", charset="UTF-8"'})
        except PermissionError as e:self.send(403,{'error':str(e)})
        except Exception as e:self.send(400,{'error':str(e)})

def install_network_guard():
    original=socket.socket.connect
    def guarded(sock,address):
        if isinstance(address,tuple) and address[0] not in ('127.0.0.1','localhost','::1'):
            NETWORK_ATTEMPTS.append({'time':engine.now(),'destination':str(address[0])});raise PermissionError('ICE processing blocks external network connections.')
        return original(sock,address)
    socket.socket.connect=guarded

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default=os.environ.get('ICE_HOST','127.0.0.1'));parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765')));parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    if args.host not in ('127.0.0.1','localhost','::1'):
        password=os.environ.get('ICE_ACCESS_PASSWORD','')
        if len(password)<24:raise SystemExit('Public hosting requires ICE_ACCESS_PASSWORD with at least 24 characters. Set it as a server-side deployment secret; never put it in source control.')
    install_network_guard()
    # Restore interrupted queue jobs on a clean restart.
    for j in all_jobs():
        if j['status'] in ('QUEUED','PROCESSING'):POOL.submit(process_job,j['id'])
    try:server=ThreadingHTTPServer((args.host,args.port),Handler)
    except OSError:
        print('Port is already in use. Close the other ICE window or run app.py --port 8766.');raise
    url=f'http://127.0.0.1:{args.port}' if args.host in ('127.0.0.1','localhost','::1') else f'Listening on {args.host}:{args.port}'
    print(f'ICE Local {engine.VERSION}\n{url}\nKeep this process running. Workspace data is stored in {DATA}\nPress Ctrl+C to stop.',flush=True)
    book=rulebook.load()
    print(f"Rulebook: {book['path']} ({sum(r['on'] for r in book['rules'])} of {len(book['rules'])} rules on)",flush=True)
    for e in book['errors']:print('Rulebook error: '+e+' Every article goes to Irregular until this is fixed.',flush=True)
    print('Public workspace password protection is active.' if args.host not in ('127.0.0.1','localhost','::1') else 'Local workspace opens directly without sign-in.',flush=True)
    if not args.no_browser and args.host in ('127.0.0.1','localhost','::1'):threading.Timer(.8,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:print('\nStopping ICE Local. Saved articles will be available next time.')
    finally:server.server_close();POOL.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__':main()
