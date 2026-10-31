"""Real local HTTP upload, extraction and editing/export regression test."""
import base64, io, json, os, sys, tempfile, threading, time, unittest, urllib.request, urllib.error, uuid, zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
TEMP=tempfile.TemporaryDirectory()
os.environ['ICE_DATA_DIR']=TEMP.name
import app
# These HTTP checks run against the loopback-only local app without account login.

class SharedLoginTest(unittest.TestCase):
    def header(self, username, password):
        value=base64.b64encode(f'{username}:{password}'.encode()).decode()
        return 'Basic '+value
    def test_four_named_logins_share_the_configured_password(self):
        for username in ('AP01','AP02','AP03','ST022'):
            with self.subTest(username=username):
                self.assertEqual(app.authenticate_shared_login(self.header(username,'shared-secret'),'shared-secret'),username)
    def test_unknown_users_and_wrong_password_are_rejected(self):
        self.assertIsNone(app.authenticate_shared_login(self.header('AP04','shared-secret'),'shared-secret'))
        self.assertIsNone(app.authenticate_shared_login(self.header('AP01','wrong-secret'),'shared-secret'))
        self.assertIsNone(app.authenticate_shared_login('Basic not-base64','shared-secret'))

class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
        cls.token=cls.call('/api/session')['token']
        batch=uuid.uuid4().hex
        data=(BASE/'samples/toolsamples.zip').read_bytes()
        req=urllib.request.Request(cls.base+'/api/upload?batch='+batch+'&name=toolsamples.zip',data=data,headers={'X-ICE-Token':cls.token})
        urllib.request.urlopen(req).read()
        ids=cls.call('/api/process',{'batch':batch})['jobs']
        for _ in range(180):
            cls.jobs=[cls.call('/api/jobs/'+i) for i in ids]
            if all(j['status'] in ('READY','ERROR') for j in cls.jobs):break
            time.sleep(.1)
    @classmethod
    def call(cls,path,body=None,raw=False):
        req=urllib.request.Request(cls.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-ICE-Token':getattr(cls,'token','')})
        with urllib.request.urlopen(req,timeout=20) as r:return r.read() if raw else json.load(r)
    def test_1_sample_counts_names_and_xml(self):
        expected={'2408.09673':(58,5),'2408.09700':(89,6),'2408.09763':(45,3)}
        summaries={j['id']:j for j in self.call('/api/jobs')}
        for j in self.jobs:
            self.assertEqual(j['status'],'READY',j.get('progress'))
            self.assertEqual((len(j['metadata']['references']),len(j['metadata']['authors'])),expected[j['article_id']])
            self.assertTrue(j['validation']['profile_valid'],j['validation'])
            self.assertEqual(j['status'],'READY')
            self.assertIn('<bibliography',j['xml'])
            self.assertGreater(len(j['metadata']['abstract']),800)
            self.assertGreaterEqual(summaries[j['id']]['metadata_count'],len(j['metadata']['references'])+len(j['metadata']['authors'])+4)
    def test_1b_samples_route_by_the_rulebook_and_recheck_applies_edits(self):
        # Checked against each PDF: initials vs full API names, DOI/web links in
        # references, and a French affiliation ("Sorbonne Université").
        expected={'2408.09673':{'author_mismatch','reference_hyperlinks'},
                  '2408.09700':{'reference_hyperlinks','affiliation_non_english'},
                  '2408.09763':{'reference_hyperlinks'}}
        for j in self.jobs:
            fired={c['rule'] for c in j['triage']['checks'] if c['status']=='REVIEW'}
            self.assertEqual(fired,expected[j['article_id']],j['triage']['reasons'])
            self.assertEqual(j['triage']['queue'],'REGULAR')
        text=app.rulebook.DEFAULT_PATH.read_text(encoding='utf-8')
        for key in ('author_mismatch','reference_hyperlinks','affiliation_non_english'):
            text=text.replace(f'[{key}]\non = true',f'[{key}]\non = false')
        with tempfile.TemporaryDirectory() as folder:
            edited=Path(folder)/'rulebook.toml';edited.write_text(text,encoding='utf-8')
            try:
                os.environ['ICE_RULEBOOK']=str(edited)
                result=self.call('/api/recheck',{})
                self.assertEqual((result['checked'],result['changed'],result['failures']),(3,0,[]))
                self.assertEqual(result['rulebook_errors'],[])
                for j in self.jobs:
                    after=self.call('/api/jobs/'+j['id'])
                    self.assertEqual(after['triage']['queue'],'REGULAR',after['triage']['reasons'])
                    self.assertEqual(after['audit'][-1]['action'],'MATCH_RECHECK_AND_XML')
            finally:
                del os.environ['ICE_RULEBOOK']
                self.call('/api/recheck',{})
        self.assertEqual(self.call('/api/rules')['errors'],[])
    def test_2_viewers(self):
        j=self.jobs[0];prefix='/api/jobs/'+j['id']
        self.assertIn('lines',self.call(prefix+'/page?number=1'))
        self.assertTrue(self.call(prefix+'/image?page=1',raw=True).startswith(b'\x89PNG'))
        with urllib.request.urlopen(self.base+prefix+'/image?page=1&download=1') as response:
            self.assertEqual(response.headers['Content-Type'],'image/png')
            self.assertIn('_page_001.png',response.headers['Content-Disposition'])
            self.assertTrue(response.read(8).startswith(b'\x89PNG'))
        self.assertGreater(len(self.call(prefix+'/search?q=the')),0)
        for f in j['files']:
            self.assertGreater(len(self.call(prefix+'/source?file='+f['id'],raw=True)),10)
        feeder=self.call(prefix+'/feeder')
        self.assertEqual(set(feeder['documents']),{'API','SCRAPPING','HTML'})
        self.assertEqual(feeder['pdf']['sha256'],self.call(prefix+'/extraction')['pdf_sha256'])
        self.assertEqual(self.call(prefix+'/metadata-file')['base_id'],j['metadata']['base_id'])
        self.assertEqual(self.call(prefix+'/routing-file')['queue'],j['triage']['queue'])
        self.assertIn(b'Support-document feeder',self.call(prefix+'/feeder-markdown',raw=True))
    def test_3_manual_edit_preserved_and_export(self):
        j=self.call('/api/jobs/'+self.jobs[0]['id']);path='/api/jobs/'+j['id'];manual=j['xml'].replace('srcid="???"','srcid="TEST"')
        j=self.call(path,{'action':'xml','xml':manual,'revision':j['revision']})
        m=j['metadata'];m['title']+=' Test correction'
        j=self.call(path,{'action':'metadata','metadata':m,'revision':j['revision']})
        self.assertEqual(j['xml'],manual);self.assertTrue(j['xml_stale'])
        data=self.call(path,{'action':'export','format':'zip'},raw=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertTrue(any(n.endswith('_audit.json') for n in z.namelist()))
            xml_name=next(n for n in z.namelist() if n.endswith('.xml'))
            self.assertIn('srcid="TEST"',z.read(xml_name).decode('utf-8'))
        with self.assertRaises(urllib.error.HTTPError):self.call(path,{'action':'generate'})
        restored=self.call(path,{'action':'generate','confirmed':True})
        self.assertIn('Test correction',restored['xml'])
    def test_4_invalid_xml_and_draft(self):
        path='/api/jobs/'+self.jobs[1]['id']
        result=self.call(path,{'action':'validate','xml':'<units><bad></units>'})
        self.assertFalse(result['well_formed']);self.assertGreater(result['errors'][0]['column'],0)
        self.call(path,{'action':'xml','xml':'<broken'})
        self.assertEqual(self.call(path,{'action':'export','format':'xml','draft':True},raw=True),b'<broken')
    def test_5_synthetic_82_references(self):
        lines=[{'id':str(i),'page':1,'text':f'[{i}] Author A. Sample work {i}. Journal 2024.','bbox':[30,50+i,400,60+i],'direction':[1,0],'block':i,'size':10,'bold':False,'spans':[]} for i in range(1,83)]
        refs,coverage,issues=app.engine.extract_references({'pages':[{'number':1,'width':600,'height':900,'lines':lines}]})
        self.assertEqual(len(refs),82);self.assertEqual(coverage['detected_candidates'],82)
    def test_5b_bottom_page_footnote_references_are_captured_without_main_bibliography(self):
        lines=[{'id':'foot-1','page':1,'text':'[1] Smith A. A complete footnote citation. Journal 2020.',
                'bbox':[30,700,410,710],'direction':[1,0],'block':1,'size':8,'bold':False,'spans':[]},
               {'id':'foot-2','page':1,'text':'[2] ibid.','bbox':[30,720,150,730],'direction':[1,0],'block':2,'size':8,'bold':False,'spans':[]}]
        refs,coverage,issues=app.engine.extract_references({'pages':[{'number':1,'width':600,'height':800,'lines':lines}]})
        self.assertEqual(len(refs),1)
        self.assertEqual(refs[0]['source_text'],'Smith A. A complete footnote citation. Journal 2020.')
        self.assertEqual(coverage['method'],'footnote-candidates')
        self.assertEqual(coverage['excluded'][0]['rule'],'REF-009')
        self.assertIn('REF-006',[i['rule_id'] for i in issues])
    def test_6_groups_markup_batch_export_and_clear(self):
        j=self.call('/api/jobs/'+self.jobs[2]['id']);path='/api/jobs/'+j['id'];md=j['metadata']
        title=md['title'];md['title_markup']='<sup>'+title[:1]+'</sup>'+title[1:]
        ref=md['references'][0];ref['full_text']=ref['source_text'];ref['full_text_markup']='<inf>'+ref['full_text'][:1]+'</inf>'+ref['full_text'][1:]
        md['author_groups']=[{'author_ids':[a['id'] for a in md['authors'][:2]],'affiliation_id':md['affiliations'][0]['id']},
                             {'author_ids':[md['authors'][0]['id']],'affiliation_id':md['affiliations'][0]['id']}]
        updated=self.call(path,{'action':'metadata','metadata':md,'revision':j['revision']})
        self.assertTrue(updated['validation']['profile_valid'])
        parsed=app.engine.secure_xml(updated['xml'].encode())
        author=parsed.xpath('//*[local-name()="author" and @seq="1"]')
        self.assertEqual(len(author),2)
        self.assertEqual(len(parsed.xpath('//*[local-name()="titletext"]/*[local-name()="sup"]')),1)
        self.assertEqual(len(parsed.xpath('//*[local-name()="ref-fulltext"]/*[local-name()="inf"]')),1)
        self.assertEqual(updated['triage']['queue'],'REGULAR')
        data=self.call('/api/export-batch',{'job_ids':[j['id']],'include_sources':True},raw=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIsNone(z.testzip());self.assertTrue(any(n.endswith('.xml') for n in z.namelist()))
            self.assertTrue(any('/sources/' in n for n in z.namelist()))
        cleared=self.call('/api/clear',{'job_ids':[j['id']]})
        self.assertEqual(cleared['removed'],[j['id']]);self.assertNotIn(j['id'],[v['id'] for v in self.call('/api/jobs')])
    def test_7_review_findings_never_block_or_move_xml_out_of_general(self):
        j=self.call('/api/jobs/'+self.jobs[0]['id'])
        self.assertEqual(j['triage']['queue'],'REGULAR')
        self.assertTrue(j['triage']['reasons'])
        self.assertEqual(j['validation']['profile_valid'],True)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();app.POOL.shutdown(wait=True);TEMP.cleanup()

if __name__=='__main__':unittest.main(verbosity=2)
