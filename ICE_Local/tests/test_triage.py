"""Rulebook and safety findings remain review notes; they never block XML."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import triage, engine, rulebook

LAYOUT={'pages':[{'number':1,'width':600,'height':800,'lines':[],'links':[]}]}

def book_with(**changes):
    """The shipped rulebook with some rules switched, e.g. book_with(title_mismatch=False)."""
    book=rulebook.load()
    return {**book,'rules':[{**r,'on':changes.get(r['key'],r['on'])} for r in book['rules']]}

class TriageTest(unittest.TestCase):
    def clean_job(self):
        pdf=[{'page':1,'bbox':[10,10,100,20],'text':'Jane Doe'}]
        author={'id':'a','given_name':'Jane','surname':'Doe','email':'jane@example.org',
                'email_evidence':pdf,'corresponding':True,'markers':['1'],'affiliation_ids':['f'],'link_method':'marker','evidence':pdf}
        aff={'id':'f','marker':'1','organizations':['University'],'address_parts':['City'],
             'city':'City','state':'','postal_code':'','country_code':'US',
             'source_text':'University, City','evidence':pdf}
        ref={'id':'r','original_label':'1','source_text':'Doe. A complete sample paper. Journal 2024.','evidence':pdf}
        md={'base_id':'2609.12345','version':1,'title':'Example title','abstract':'A plain abstract.',
            'authors':[author],'affiliations':[aff],'author_groups':[{'author_ids':['a'],'affiliation_id':'f'}],
            'references':[ref],'field_evidence':{'base_id':pdf,'title':pdf,'abstract':pdf,'authors':pdf},
            'source_values':{'scrapping_id':'2609.12345','scrapping_version':1,'api_id':'2609.12345','html_id':'2609.12345',
                             'api_title':'Example title','html_title':'Example title','api_authors':[{'given_name':'Jane','surname':'Doe'}]},
            'coverage':{'method':'numbered-start-inventory','numbered_labels':['1'],'detected_candidates':1,'excluded':[],'reference_regions':1}}
        j={'status':'READY','metadata':md,'files':[],'selected':{x:x.lower() for x in ('PDF','SCRAPPING','API','HTML')},
           'issues':[],'validation':{'profile_valid':True},'manual_xml':False,'xml_stale':False}
        j['original_values']=triage.original_values(md)
        return j

    def assess(self,job,book=None):
        return triage.assess(job,LAYOUT,book)

    def test_clean_job_is_regular_and_every_rule_has_a_card(self):
        result=self.assess(self.clean_job())
        self.assertEqual(result['queue'],'REGULAR',result['reasons'])
        self.assertEqual(result['matched'],result['total'])
        self.assertEqual(result['total'],sum(r['on'] for r in rulebook.load()['rules']))
        self.assertEqual(result['rulebook']['errors'],[])

    def test_title_compares_content_only(self):
        for html in ('EXAMPLE TITLE','Example — title.','<i>Example</i> title'):
            j=self.clean_job();j['metadata']['source_values']['html_title']=html
            self.assertEqual(self.assess(j)['queue'],'REGULAR',html)
        j=self.clean_job();j['metadata']['title']='Different title'
        result=self.assess(j)
        self.assertEqual(result['queue'],'REGULAR')
        self.assertTrue(any(r.startswith('The PDF title does not match') for r in result['reasons']))
        self.assertEqual(next(c for c in result['checks'] if c['rule']=='title_mismatch')['status'],'REVIEW')

    def test_version_mismatch_routes_to_review(self):
        j=self.clean_job();j['metadata']['source_values']['scrapping_version']=2
        result=self.assess(j)
        self.assertEqual(result['queue'],'REGULAR')
        self.assertTrue(any('version 1 but Scrapping version 2' in r for r in result['reasons']))

    def test_safety_checks_always_apply(self):
        j=self.clean_job();j['selected'].pop('HTML')
        self.assertIn('HTML file is missing.',self.assess(j)['reasons'])
        j=self.clean_job();j['manual_xml']=True
        self.assertEqual(self.assess(j)['queue'],'REGULAR')
        j=self.clean_job();j['validation']['profile_valid']=False
        self.assertEqual(self.assess(j)['queue'],'REGULAR')
        j=self.clean_job();j['extraction_issues']=[engine.issue('PKG-002','API','Cannot read API: DTD/entity declarations are not accepted.')]
        self.assertEqual(self.assess(j)['queue'],'REGULAR')
        off=book_with(**{r['key']:False for r in rulebook.load()['rules']})
        j=self.clean_job();j['selected'].pop('API')
        self.assertEqual(self.assess(j,off)['queue'],'REGULAR')

    def test_holds_outside_the_rulebook_do_not_choose_the_queue(self):
        j=self.clean_job()
        j['issues']=[engine.issue('KEY-001','keywords','Visible PDF keywords need review.'),
                     engine.issue('PDF-002','extraction','Page 1 used local OCR.')]
        j['metadata']['affiliations'][0]['component_warnings']=['Postal location was not separated.']
        result=self.assess(j)
        self.assertEqual(result['queue'],'REGULAR',result['reasons'])
        self.assertNotIn('review_holds',result)

    def test_rule_switched_off_does_not_route_and_rulebook_errors_do(self):
        j=self.clean_job();j['metadata']['title']='Different title'
        result=self.assess(j,book_with(title_mismatch=False))
        self.assertEqual(result['queue'],'REGULAR')
        self.assertNotIn('title_mismatch',[c['rule'] for c in result['checks']])
        broken={**rulebook.load(),'errors':['Unknown rule [titel_mismatch].']}
        result=self.assess(self.clean_job(),broken)
        self.assertEqual(result['queue'],'REGULAR')
        self.assertIn('Rulebook error: Unknown rule [titel_mismatch].',result['reasons'])

    def test_missing_extraction_record_never_passes_pdf_rules(self):
        result=triage.assess(self.clean_job(),None)
        self.assertEqual(result['queue'],'REGULAR')
        self.assertTrue(any('extraction record is missing' in r for r in result['reasons']))

    def test_affiliation_candidate_decision_and_manual_queue_transfer(self):
        j=self.clean_job();candidate={'id':'aff-candidate-1','status':'UNREVIEWED','location':'Page 4 footer','source_text':'Lab, Paris, France'}
        j['metadata']['affiliation_candidates']=[candidate]
        self.assertEqual(self.assess(j)['queue'],'REGULAR')
        j['metadata']['affiliation_candidates'][0]['status']='DISMISSED'
        self.assertEqual(self.assess(j)['automatic_queue'],'REGULAR')
        j['metadata']['title']='Different title'
        j['queue_override']={'queue':'REGULAR','note':'Reviewed manually'}
        result=self.assess(j)
        self.assertEqual(result['automatic_queue'],'REGULAR')
        self.assertEqual(result['queue'],'REGULAR')

    def test_not_ready_is_pending(self):
        j=self.clean_job();j['status']='QUEUED'
        self.assertEqual(self.assess(j)['queue'],'REGULAR')

    def test_real_pdf_and_support_files_route_to_regular(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with engine.fitz.open() as doc:
                page=doc.new_page(width=612,height=792)
                rows=[(45,'arXiv:2609.12345v1',9),(80,'Deterministic citation example',17),
                      (112,'Jane Doe1',11),(145,'1 University of Sample, City, United States',10),
                      (190,'Abstract',11),(210,'A straightforward article used to check deterministic citation extraction.',10),
                      (300,'Introduction',11),(320,'This example contains three references.',10),
                      (500,'References',12),(525,'[1] Doe J. First sample work. Journal 2021.',10),
                      (550,'[2] Doe J. Second sample work. Journal 2022.',10),
                      (575,'[3] Doe J. Third sample work. Journal 2023.',10)]
                for y,text,size in rows:page.insert_text((55,y),text,fontsize=size)
                doc.save(root/'paper.pdf')
            supports={'API':'<record><id>2609.12345</id><title>Deterministic citation example</title><author><forenames>Jane</forenames><keyname>Doe</keyname></author></record>',
                      'SCRAPPING':'<catalog><item id="2609.12345"><version number="1"/></item></catalog>',
                      'HTML':'<html><head><meta name="citation_title" content="Deterministic citation example"><meta name="citation_arxiv_id" content="2609.12345"></head><body><span class="arxivid">arXiv:2609.12345v1</span></body></html>'}
            files={}
            for role,data in supports.items():
                path=role.lower()+('.html' if role=='HTML' else '.xml')
                (root/path).write_text(data,encoding='utf-8');files[role]={'path':path}
            values,issues=engine.source_data(files,root)
            layout,layout_issues=engine.extract_layout(root/'paper.pdf',{})
            md,metadata_issues=engine.extract_metadata(layout,values,{})
            all_issues=issues+layout_issues+metadata_issues+engine.verify_metadata(md,{})[0]
            job={'status':'READY','metadata':md,'selected':{role:role for role in ('PDF',*supports)},
                 'issues':all_issues,'extraction_issues':issues+layout_issues+metadata_issues,
                 'validation':engine.validate_xml(engine.build_xml(md),md),'original_values':triage.original_values(md)}
            result=triage.assess(job,layout)
            self.assertEqual(result['queue'],'REGULAR',result['reasons'])
            self.assertEqual(result['matched'],result['total'])
            self.assertEqual(len(md['references']),3)

if __name__=='__main__':unittest.main()
