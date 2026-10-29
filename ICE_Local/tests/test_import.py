"""Import regression coverage, including Windows' non-UTF-8 default locale."""
import io, json, os, sys, tempfile, threading, time, unittest, uuid, zipfile
from pathlib import Path
from unittest.mock import patch
from urllib import request, parse, error

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
TEMP=tempfile.TemporaryDirectory()
os.environ['ICE_DATA_DIR']=TEMP.name
import app
# These HTTP checks run against the loopback-only local app without account login.
from concurrent.futures import ThreadPoolExecutor

def zip_bytes(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return buf.getvalue()

class ImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_data,cls.old_pool=app.DATA,app.POOL
        app.DATA=Path(TEMP.name)
        for sub in ('jobs','uploads','exports'):(app.DATA/sub).mkdir(exist_ok=True)
        app.POOL=ThreadPoolExecutor(max_workers=2)
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        cls.token=cls.call('/api/session')['token']
        with app.engine.fitz.open() as doc:
            doc.new_page().insert_text((50,50),'An article with no arXiv number')
            cls.pdf=doc.tobytes()

    @classmethod
    def call(cls,path,body=None):
        req=request.Request(cls.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-ICE-Token':getattr(cls,'token','')})
        with request.urlopen(req,timeout=30) as r:return json.load(r)

    def import_files(self,files,process=False):
        batch=uuid.uuid4().hex
        for name,data in files.items():
            req=request.Request(self.url+'/api/upload?'+parse.urlencode({'batch':batch,'name':name}),data=data,headers={'X-ICE-Token':self.token})
            with request.urlopen(req) as r:self.assertEqual(r.status,200)
        if process:return self.call('/api/process',{'batch':batch})
        with patch.object(app.POOL,'submit'):
            return self.call('/api/process',{'batch':batch})

    def test_1_nested_uppercase_zip_and_wrapped_supports(self):
        with zipfile.ZipFile(BASE/'samples/toolsamples.zip') as z:
            originals={Path(n).name:z.read(n) for n in z.namelist() if Path(n).name.startswith('2408.09763.') or Path(n).name.startswith('2408.09763_')}
        api=app.engine.etree.fromstring(originals['2408.09763_Api.xml'])
        wrapper=app.engine.etree.Element('OAI-PMH');wrapper.append(api)
        scraping=originals['2408.09763_Scrapping.xml'].replace(b'<ARXIV>',b'<ARXIV xmlns="urn:scraped">')
        inner=zip_bytes({'Package/PDF/paper.PDF':originals['2408.09763.pdf'],
                         'Package/support/metadata.xml':app.engine.etree.tostring(wrapper),
                         'Package/support/web.xml':scraping,
                         'Package/support/page.HTML':originals['2408.09763.html']})
        result=self.import_files({'DELIVERY.ZIP':zip_bytes({'inside/ARTICLE.ZIP':inner})},process=True)
        self.assertEqual(len(result['jobs']),1);self.assertEqual(result['ignored'],[])
        for _ in range(200):
            job=self.call('/api/jobs/'+result['jobs'][0])
            if job['status'] in ('READY','ERROR'):break
            time.sleep(.1)
        self.assertEqual(job['status'],'READY',job['progress'])
        self.assertEqual(job['article_id'],'2408.09763')
        self.assertEqual(set(job['selected']),{'PDF','API','SCRAPPING','HTML'})
        self.assertEqual(len(job['metadata']['references']),45)
        self.assertEqual(len(job['metadata']['authors']),3)
        self.assertEqual(job['metadata']['source_values']['scrapping_version'],2)

    def test_2_generic_folder_names_keep_supports_together(self):
        result=self.import_files({'My article/documents/paper.pdf':self.pdf,'My article/support/source_Api.xml':b'<record><title>Test</title></record>','My article/support/page.html':b'<html><title>Test</title></html>'})
        self.assertEqual(len(result['jobs']),1);self.assertFalse(result['ignored'])
        j=self.call('/api/jobs/'+result['jobs'][0])
        self.assertEqual(set(j['selected']),{'PDF','API','HTML'})

    def test_3_identical_names_in_different_folders_stay_separate(self):
        files={}
        for folder in ('First','Second'):
            files[folder+'/paper.pdf']=self.pdf
            files[folder+'/page.html']=b'<html>Test</html>'
        result=self.import_files(files)
        self.assertEqual(len(result['jobs']),2)
        jobs=[self.call('/api/jobs/'+i) for i in result['jobs']]
        self.assertNotEqual(jobs[0]['article_id'],jobs[1]['article_id'])
        self.assertTrue(all(len(j['files'])==2 for j in jobs))

    def test_4_wrong_article_support_is_reported(self):
        result=self.import_files({'2609.10000.pdf':self.pdf,'2609.20000_Api.xml':b'<record><id>2609.20000</id></record>','notes.docx':b'not a source'})
        self.assertEqual(len(result['jobs']),1)
        self.assertEqual(len(result['ignored']),2)
        skipped=[r for r in result['report'] if r['status']=='SKIPPED']
        self.assertTrue(all(r['reason'] for r in skipped))
        self.assertNotIn('API',self.call('/api/jobs/'+result['jobs'][0])['selected'])

    def test_5_unknown_xml_can_be_manually_assigned(self):
        result=self.import_files({'paper.pdf':self.pdf,'support.xml':b'<custom><title>Test</title></custom>'})
        job=self.call('/api/jobs/'+result['jobs'][0])
        self.assertEqual(job['status'],'NEEDS_SOURCES')
        self.assertIn('PDF',job['selected'])
        other=next(f for f in job['files'] if f['role']=='XML')
        with self.assertRaises(error.HTTPError):self.call('/api/jobs/'+job['id'],{'action':'select','selected':{'API':other['id']}})
        with patch.object(app.POOL,'submit'):
            selected=self.call('/api/jobs/'+job['id'],{'action':'select','selected':{**job['selected'],'API':other['id']}})
        self.assertEqual(selected['status'],'QUEUED')

    def test_6_windows_default_encoding_does_not_hide_articles(self):
        result=self.import_files({'paper.pdf':self.pdf})
        job=app.read_job(result['jobs'][0]);job['metadata']={'title':'Łukasz — α ∑ √','references':[],'authors':[]};app.save_job(job)
        root=app.jobdir(job['id']);app.atomic(root/'extraction.json',{'pages':[{'title':'Łukasz — α'}]})
        (root/'history').mkdir(exist_ok=True);app.atomic(root/'history/revision-00000.json',{'title':'Łukasz'})
        original=Path.read_text
        def windows_read(path,encoding=None,errors=None):return original(path,encoding=encoding or 'cp1252',errors=errors)
        with patch.object(Path,'read_text',windows_read):
            jobs=self.call('/api/jobs')
            self.assertEqual(next(j for j in jobs if j['id']==job['id'])['title'],'Łukasz — α ∑ √')
            self.assertEqual(self.call('/api/jobs/'+job['id']+'/page?number=1')['title'],'Łukasz — α')
            self.assertEqual(self.call('/api/jobs/'+job['id']+'/revision?number=0')['title'],'Łukasz')
            self.assertTrue(self.call('/api/rules'))

    def test_7_javascript_mime_independent_of_windows_registry(self):
        with patch.dict(app.mimetypes.types_map,{'.js':'text/plain'}):
            with request.urlopen(self.url+'/app.js') as r:self.assertIn('application/javascript',r.headers['Content-Type'])

    def test_8_nested_zip_traversal_stays_blocked(self):
        with self.assertRaises(error.HTTPError):self.import_files({'BAD.ZIP':zip_bytes({'../escape.pdf':self.pdf})})

    def test_9_multiple_zip_packages_same_article_id_do_not_merge(self):
        one={'article/2609.12345.pdf':self.pdf,'article/2609.12345_Api.xml':b'<record><id>2609.12345</id></record>'}
        result=self.import_files({'One.zip':zip_bytes(one),'Two.ZIP':zip_bytes(one)})
        self.assertEqual(len(result['jobs']),2)
        self.assertEqual(result['packages'],['One.zip','Two.ZIP'])
        articles=[self.call('/api/jobs/'+id) for id in result['jobs']]
        self.assertEqual({j['article_id'] for j in articles},{'2609.12345'})
        self.assertEqual({j['package_name'] for j in articles},{'One.zip','Two.ZIP'})
        self.assertNotEqual(articles[0]['package_id'],articles[1]['package_id'])
        self.assertTrue(all(len(j['files'])==2 and j['triage']['queue']=='NEEDS_REVIEW' for j in articles))

    def test_10_fifty_zip_packages_remain_distinct(self):
        files={f'Package_{i:02d}.zip':zip_bytes({'2609.12345.pdf':self.pdf}) for i in range(1,51)}
        result=self.import_files(files)
        self.assertEqual(len(result['packages']),50)
        self.assertEqual(len(result['jobs']),50)
        self.assertEqual(len({self.call('/api/jobs/'+jid)['package_id'] for jid in result['jobs']}),50)

    def test_11_unreadable_named_support_xml_keeps_its_role(self):
        self.assertEqual(app.documents.classify('2609.12345_Api.xml',b'<?xml version="1.0"?><!DOCTYPE x><record/>'),'API')
        self.assertEqual(app.documents.classify('2609.12345_Scrapping.xml',b'<?xml version="1.0"?><broken'),'SCRAPPING')
        self.assertEqual(app.documents.classify('notes.xml',b'<?xml version="1.0"?><broken'),'XML')

    def test_12_extra_xml_does_not_hold_a_complete_package(self):
        result=self.import_files({'2609.30000.pdf':self.pdf,'2609.30000_Api.xml':b'<record><id>2609.30000</id></record>',
                                  '2609.30000_Scrapping.xml':b'<arxiv><item id="2609.30000"><version number="1"/></item></arxiv>',
                                  '2609.30000.html':b'<html><head><meta name="citation_arxiv_id" content="2609.30000"></head></html>',
                                  '2609.30000_notes.xml':b'<custom><title>Unrelated</title></custom>'})
        job=self.call('/api/jobs/'+result['jobs'][0])
        self.assertEqual(job['status'],'QUEUED')
        self.assertEqual(set(job['selected']),{'PDF','API','SCRAPPING','HTML'})
        notes=next(r for r in result['report'] if r['name'].endswith('_notes.xml'))
        self.assertTrue(notes['reason'].startswith('Not used'))

    def test_13_damaged_record_does_not_hide_other_articles(self):
        result=self.import_files({'2609.40000.pdf':self.pdf})
        damaged=app.DATA/'jobs'/('d'*32);damaged.mkdir()
        (damaged/'job.json').write_text('{not json',encoding='utf-8')
        try:
            jobs={j['id']:j for j in self.call('/api/jobs')}
            self.assertIn(result['jobs'][0],jobs)
            self.assertEqual(jobs['d'*32]['status'],'ERROR')
            self.assertEqual(self.call('/api/clear',{'job_ids':['d'*32]})['removed'],['d'*32])
        finally:
            if damaged.exists():app.shutil.rmtree(damaged)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();app.POOL.shutdown(wait=True);app.DATA,app.POOL=cls.old_data,cls.old_pool;TEMP.cleanup()

if __name__=='__main__':unittest.main(verbosity=2)
