"""Affiliation extraction from real coordinate-aware PDF text."""
import sys
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import fitz

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import engine


class AffiliationTest(unittest.TestCase):
    def pdf_metadata(self, items, authors):
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'article.pdf'
            document = fitz.open()
            page = document.new_page(width=600, height=800)
            for y, line, size in items:
                page.insert_text((50, y), line, fontsize=size)
            document.save(pdf)
            document.close()
            layout, _ = engine.extract_layout(pdf, {})
        return engine.extract_metadata(layout, {'api_authors': authors}, {})[0]

    def test_endmatter_emails_link_each_affiliation_to_one_author(self):
        authors=[
            {'id':'author-1','given_name':'Shilei','surname':'Fan','email':''},
            {'id':'author-2','given_name':'Bochen','surname':'Liu','email':''},
        ]
        texts=[
            'SHILEI FAN AND BOCHEN LIU',
            'School of Mathematics and Statistics, Central China Normal University, Wuhan 430079, China',
            'Email address: slfan@ccnu.edu.cn',
            'Department of Mathematics, Southern University of Science and Technology, Shenzhen 518055, China',
            'Email address: Bochen.Liu1989@gmail.com',
        ]
        lines=[{'page':2,'bbox':[10,20+i*12,500,30+i*12],'id':f'p2-l{i}','text':text} for i,text in enumerate(texts)]
        affiliations,links=engine.endmatter_author_affiliations({'pages':[{'lines':[]},{'lines':lines}]},authors)
        self.assertEqual(links['author-1'],['aff-endmatter-1'])
        self.assertEqual(links['author-2'],['aff-endmatter-2'])
        self.assertEqual([author['email'] for author in authors],['slfan@ccnu.edu.cn','Bochen.Liu1989@gmail.com'])

    def test_detached_superscripts_and_orcid_links_use_surname_geometry(self):
        authors=[
            {'id':'author-1','surname':'Chan','evidence':[{'line_id':'p1-b1-l0'}]},
            {'id':'author-2','surname':'Chashkina','evidence':[{'line_id':'p1-b1-l1'}]},
            {'id':'author-3','surname':'Bromberg','evidence':[{'line_id':'p1-b1-l1'}]},
        ]
        lines=[
            {'id':'p1-b1-l0','page':1,'block':1,'text':'Ho-Sang Chan','bbox':[0,20,50,32],
             'spans':[{'text':'1','bbox':[53,17,57,26],'flags':1}]},
            {'id':'p1-b1-l1','page':1,'block':1,'text':'Anna Chashkina Omer Bromberg','bbox':[60,20,180,32],
             'spans':[{'text':'2','bbox':[120,17,124,26],'flags':1},{'text':'3','bbox':[183,17,187,26],'flags':1}]},
        ]
        words=[
            {'text':'Chan','bbox':[25,20,50,32],'block':1,'line':0},
            {'text':'Chashkina','bbox':[90,20,120,32],'block':1,'line':1},
            {'text':'Bromberg','bbox':[150,20,180,32],'block':1,'line':1},
        ]
        links=[{'bbox':[51,19,59,33],'uri':'https://orcid.org/0000-0001-2345-6789'}]
        layout={'pages':[{'number':1,'lines':lines,'words':words,'links':links}]}
        boxes=engine.apply_geometric_author_markers(layout,authors,['1','2','3'])
        self.assertEqual([author['markers'] for author in authors],[['1'],['2'],['3']])
        self.assertEqual(engine.nearest_author_by_pdf_box(authors,boxes,1,links[0]['bbox'])['id'],'author-1')

    def test_uc_berkeley_affiliations_are_individual_and_split(self):
        md=self.pdf_metadata([
            (75,'Efficient Mass Matrix Estimation with Gaussian Cooling',16),
            (105,'Jake Hofgard1, Michael Lindsey2',12),
            (135,'1 UC Berkeley, hofgard@berkeley.edu',9),
            (150,'2 UC Berkeley and Lawrence Berkeley National Laboratory, lindsey@math.berkeley.edu',9),
            (200,'Abstract',11),(215,'A sufficiently long paragraph begins the paper and explains the method.',10),
        ],[{'given_name':'Jake','surname':'Hofgard'},{'given_name':'Michael','surname':'Lindsey'}])
        self.assertEqual([a['markers'] for a in md['authors']],[['1'],['2']])
        self.assertEqual([a['affiliation_ids'] for a in md['authors']],[['aff-1'],['aff-2']])
        self.assertEqual([f['organizations'] for f in md['affiliations']],[['UC Berkeley'],['UC Berkeley','Lawrence Berkeley National Laboratory']])

    def test_alpha_labels_create_groups_with_pdf_evidence(self):
        md = self.pdf_metadata([
            (75, 'An article title', 16),
            (102, 'Ada Lovelace a, Grace Hopper b', 12),
            (145, 'a Department of Mathematics, Example University, Paris, France', 9),
            (160, 'b Institute of Computing, Example City, UK', 9),
            (225, 'Abstract', 11),
            (240, 'This paper explores a deterministic extraction example.', 10),
        ], [{'given_name': 'Ada', 'surname': 'Lovelace'},
            {'given_name': 'Grace', 'surname': 'Hopper'}])
        self.assertEqual([a['marker'] for a in md['affiliations']], ['a', 'b'])
        self.assertEqual([a['affiliation_ids'] for a in md['authors']], [['aff-a'], ['aff-b']])
        self.assertEqual([g['author_ids'] for g in md['author_groups']], [['author-1'], ['author-2']])
        self.assertEqual(md['affiliations'][0]['evidence'][0]['page'], 1)

    def test_mexican_address_keeps_street_city_region_postal_and_country_distinct(self):
        source=('Universidad Nacional Autónoma de México, Instituto de Radioastronomía y Astrofísica., '
                'Antigua Carretera a Pátzcuaro 8701, Ex-Hda. San José de la Huerta, '
                '58089, Morelia, Michoacán, México')
        aff=engine.parse_affiliation(source,'1',[])
        self.assertEqual(aff['organizations'],[
            'Universidad Nacional Autónoma de México',
            'Instituto de Radioastronomía y Astrofísica'])
        self.assertEqual(aff['city'],'Morelia')
        self.assertEqual(aff['postal_code'],'58089')
        self.assertEqual(aff['country_code'],'MEX')
        self.assertEqual(aff['state'],'')
        self.assertIn('Antigua Carretera a Pátzcuaro 8701',aff['address_parts'])
        self.assertIn('Ex-Hda. San José de la Huerta',aff['address_parts'])
        self.assertIn('Michoacán',aff['address_parts'])

    def test_full_us_state_names_serialize_as_two_letter_codes(self):
        aff=engine.parse_affiliation(
            'Example University, Boulder, Colorado 80301, USA','1',[])
        self.assertEqual((aff['city'],aff['state'],aff['postal_code']),
                         ('Boulder','CO','80301'))

    def test_jila_coordinated_institutions_and_us_zip_plus_four_follow_source_order(self):
        source=('JILA, University of Colorado and National Institute of Standards and Technology, '
                '440 UCB, Boulder, CO 80309-0440, USA')
        aff=engine.parse_affiliation(source,'1',[])
        self.assertEqual(aff['organizations'],[
            'JILA','University of Colorado','National Institute of Standards and Technology'])
        self.assertEqual(aff['address_parts'],['440 UCB'])
        self.assertEqual((aff['city'],aff['state'],aff['postal_code'],aff['country_code']),
                         ('Boulder','CO','80309-0440','USA'))
        self.assertEqual(aff['source_text'],source)

    def test_university_name_is_not_country_and_macau_sar_uses_autonomous_code(self):
        aff=engine.parse_affiliation(
            'SKL-IOTSC, Department of CIS, University of Macau, Macau SAR, China',
            '1',[])
        self.assertEqual(aff['country_code'],'MAC')
        self.assertEqual(aff['city'],'Macau')
        self.assertIn('University of Macau',aff['organizations'])
        self.assertIsNone(engine.COUNTRY_END.search('University of Macau'))
        university_only=engine.parse_affiliation('University of Macau','1',[])
        self.assertEqual(university_only['country_code'],'')

    def test_affiliation_and_email_in_author_footnote_are_both_captured(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace*',12),
            (225,'Abstract',11),(240,'A sufficiently long abstract paragraph for the example.',10),
            (690,'*Department of Computer Science and Engineering, UC San Diego. ada@example.org',9),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertEqual(len(md['affiliations']),1)
        self.assertIn('Department of Computer Science and Engineering',md['affiliations'][0]['source_text'])
        self.assertIn('UC San Diego',md['affiliations'][0]['organizations'])
        self.assertEqual(md['authors'][0]['email'],'ada@example.org')
        self.assertEqual(md['authors'][0]['affiliation_ids'],[md['affiliations'][0]['id']])

    def test_explicit_abstract_keeps_formula_glyph_lines_until_real_section_heading(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace',12),(180,'Abstract',11),
            (195,'We study the model and define a Hamiltonian H = 1',10),
            (196,'SUM_i J_ij Z_i Z_j',9),
            (210,'The algorithm then achieves the stated guarantee.',10),
            (245,'1 Introduction',11),
            (260,'This is the body of the introduction, not the abstract.',10),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertIn('SUM_i J_ij Z_i Z_j',md['abstract'])
        self.assertIn('stated guarantee',md['abstract'])
        self.assertNotIn('body of the introduction',md['abstract'])

    def test_complex_hamiltonian_in_abstract_uses_supplied_formula_placeholder(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace',12),(180,'Abstract',11),
            (200,'We study the model defined by the Hamiltonian H = 1/2 sum_i,j J_ij Z_i Z_j + sum_i h_i Z_i where J is symmetric.',10),
            (245,'1 Introduction',11),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertIn('Hamiltonian (Formula presented) where J is',md['abstract'])

    def test_two_column_abstract_skips_publisher_notice_and_reads_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'article.pdf';doc=fitz.open();page=doc.new_page(width=600,height=800)
            for x,y,text,size in [
                (50,75,'An article title',16),(50,102,'Ada Lovelace',12),
                (50,150,'Abstract',11),(50,170,'The first column explains the problem and the approach.',10),
                (50,190,'The final left-column words end with relative transitions',10),
                (50,740,'Permission to make digital or hard copies of this work.',7),
                (320,170,'contain less city-specific information and improve transfer.',10),
                (320,190,'These findings complete the abstract.',10),(320,220,'CCS Concepts',10),
                (320,240,'Keywords',10),(50,280,'1 Introduction',11),
                (50,300,'This paragraph belongs to the article body.',10)]:
                page.insert_text((x,y),text,fontsize=size)
            doc.save(pdf);doc.close();layout,_=engine.extract_layout(pdf,{})
            md,_=engine.extract_metadata(layout,{'api_authors':[{'given_name':'Ada','surname':'Lovelace'}]}, {})
        self.assertIn('relative transitions',md['abstract'])
        self.assertIn('contain less city-specific information',md['abstract'])
        self.assertNotIn('Permission to make',md['abstract'])
        self.assertNotIn('CCS Concepts',md['abstract'])
        self.assertNotIn('article body',md['abstract'])

    def test_title_rules_choose_complete_form_and_html_when_content_is_different(self):
        pdf='The main ingredient - clean water, air.'
        summary='The main $_ingredient_$ - - clean water, air.'
        self.assertEqual(engine.choose_title(pdf,summary),
                         ('The main ingredient - - clean water, air.','HTML'))
        self.assertEqual(engine.choose_title('Preprint: Same scientific title*','Same scientific title'),
                         ('Same scientific title','PDF'))
        self.assertEqual(engine.choose_title('A study about quantum systems','Completely unrelated title'),
                         ('Completely unrelated title','HTML'))

    def test_reference_cleanup_removes_only_linked_internal_page_locators(self):
        line={'text':'[4] A. Author, A reference title, 2024. 2, 3',
              'internal_linked_words':['2','3']}
        self.assertEqual(engine.reference_line_text(line),
                         '[4] A. Author, A reference title, 2024.')
        citation={'text':'A. Author. A title. (cit. on pp. 4, 20, 23, 25).',
                  'internal_linked_words':['4','20','23','25']}
        self.assertEqual(engine.reference_line_text(citation),'A. Author. A title.')
        punctuated={'text':'A. Author. A title. (cit. on p. 5).',
                    'internal_linked_words':['5']}
        self.assertEqual(engine.reference_line_text(punctuated),'A. Author. A title.')
        wrapped_tail={'text':'p. 2).','internal_linked_words':['2']}
        self.assertEqual(engine.reference_line_text(wrapped_tail),'p. 2).')
        wrapped=engine.join_text(['A. Author. A title. URL: https://example.org/paper (cit. on',
                                  engine.reference_line_text(wrapped_tail)])
        self.assertEqual(engine.strip_internal_citation_locators(wrapped,['2']),
                         'A. Author. A title. URL: https://example.org/paper')
        ranged='A. Author. https://example.org/paper (cit. on pp. 32, 37, 40–42, 46). A Outline'
        self.assertEqual(engine.strip_internal_citation_locators(ranged,
                         ['32','37','40','41','42','46']),
                         'A. Author. https://example.org/paper A Outline')
        external={'text':'[4] A. Author, https://example.org/paper, 2024. 2'}
        self.assertEqual(engine.reference_line_text(external),external['text'])

    def test_alias_and_api_suffix_are_preserved_as_author_tags(self):
        given,alias=engine.split_author_alias('Christopher (Xiang)')
        self.assertEqual((given,alias),('Christopher','Xiang'))
        md={'base_id':'2408.00001','version':1,'title':'Sample','abstract':'Text',
            'authors':[{'id':'a1','global_seq':1,'given_name':given,'surname':'Lee',
                        'initials':'C.','alias':alias,'suffix':'Jr.'}],
            'affiliations':[],'references':[],'profile':{}}
        root=engine.secure_xml(engine.build_xml(md).encode())
        author=root.xpath('.//*[local-name()="author"]')[0]
        self.assertEqual(author.xpath('string(*[local-name()="alias"])'),'Xiang')
        self.assertEqual(author.xpath('string(*[local-name()="suffix"])'),'Jr.')

    def test_surname_attached_superscript_markers_do_not_hide_pdf_author(self):
        match=engine.author_surname_pattern('Mu').search('Tianwei Mua,b,c')
        self.assertIsNotNone(match)
        self.assertEqual(engine.author_markers('a,b,c'),['a','b','c'])

    def test_adjacent_affiliation_and_correspondence_markers_do_not_hide_author(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Courtney L. Crawford1★',12),
            (145,'1 Department of Astronomy, Example University, Sydney, Australia',9),
            (225,'Abstract',11),(240,'A sufficiently long abstract sentence for a marker test.',10),
        ],[{'given_name':'Courtney L.','surname':'Crawford'}])
        self.assertEqual(len(md['authors']),1)
        self.assertEqual(md['authors'][0]['markers'],['1','*'])

    def test_single_star_correspondence_does_not_promote_double_star_email_marker(self):
        lines=[
            {'id':'author-1','page':1,'text':'Ioannis Iatrakis 1,*','bbox':[50,100,260,112]},
            {'id':'author-2','page':1,'text':'Frank de Groot 3,**','bbox':[50,120,250,132]},
            {'id':'email-1','page':1,'text':'* ioannis.iatrakis@example.org','bbox':[50,700,300,710]},
            {'id':'email-2','page':1,'text':'** frank.degroot@example.org','bbox':[50,720,300,730]},
        ]
        authors=[
            {'id':'author-1','global_seq':1,'given_name':'Ioannis','surname':'Iatrakis',
             'initials':'I.','markers':['1','*'],'email':'ioannis.iatrakis@example.org',
             'affiliation_ids':[],'corresponding':False,
             'evidence':[{'line_id':'author-1','text':lines[0]['text']}]},
            {'id':'author-2','global_seq':2,'given_name':'Frank','surname':'de Groot',
             'initials':'F.','markers':['3','*','*'],'email':'frank.degroot@example.org',
             'affiliation_ids':[],'corresponding':False,
             'evidence':[{'line_id':'author-2','text':lines[1]['text']}]},
        ]
        engine.apply_correspondence_rules({'authors':authors},{'pages':[{'lines':lines}]})
        self.assertTrue(authors[0]['corresponding'])
        self.assertFalse(authors[1]['corresponding'])
        self.assertEqual(engine.author_markers('3,**'),['3','*','*'])

        metadata={'base_id':'2610.04797','version':1,'title':'Sample article title',
                  'abstract':'Sample abstract text','authors':authors,
                  'affiliations':[],'author_groups':[],'keywords':[],'references':[],
                  'profile':{}}
        root=engine.secure_xml(engine.build_xml(metadata).encode('utf-8'))
        self.assertEqual(len(root.xpath('.//*[local-name()="titletext"]')),1)
        self.assertEqual(len(root.xpath('.//*[local-name()="title"]')),0)
        correspondences=root.xpath('.//*[local-name()="correspondence"]')
        self.assertEqual(len(correspondences),1)
        self.assertEqual(correspondences[0].xpath('string(.//*[local-name()="surname"])'),'Iatrakis')

    def test_collective_pdf_author_is_preserved_when_api_lists_people(self):
        md=self.pdf_metadata([
            (75,'UniWAM: Unified World-Action Model',16),(102,'UniWAM Team',12),
            (135,'Abstract',11),(150,'A sufficiently long abstract paragraph is included for this test.',10),
        ],[{'given_name':'Wenxuan','surname':'Song'}])
        self.assertEqual(len(md['authors']),1)
        self.assertEqual(md['authors'][0]['surname'],'UniWAM Team')
        self.assertTrue(md['authors'][0]['collective_author'])
        self.assertTrue(md['author_candidates'])

    def test_affiliation_after_last_reference_is_a_candidate_not_part_of_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'article.pdf';doc=fitz.open()
            first=doc.new_page(width=600,height=800)
            for y,text,size in [(75,'An article title',16),(102,'Ada Lovelace1',12),
                                (145,'1 Department of Mathematics, Paris, France',9),
                                (225,'Abstract',11),(240,'This is a sufficiently long abstract for a citation processing example.',10),
                                (500,'References',11)]:first.insert_text((50,y),text,fontsize=size)
            last=doc.new_page(width=600,height=800)
            for y,text,size in [(120,'[1] Doe A. First sample reference. Journal 2020.',9),
                                (150,'[2] Doe A. Second sample reference. Journal 2021.',9),
                                (180,'[3] Doe A. Third sample reference. Journal 2022.',9),
                                (210,'Bohao Ji, bhji24@fudan.edu.cn',9),
                                (228,'School of Mathematical Sciences, Fudan University, Shanghai, 200433, P.R. China',9)]:last.insert_text((50,y),text,fontsize=size)
            doc.save(pdf);doc.close();layout,_=engine.extract_layout(pdf,{})
            md,issues=engine.extract_metadata(layout,{'api_authors':[{'given_name':'Ada','surname':'Lovelace'}]}, {})
        self.assertEqual(len(md['references']),3)
        self.assertNotIn('Fudan University',md['references'][-1]['source_text'])
        self.assertEqual(len(md['affiliation_candidates']),1)
        candidate=md['affiliation_candidates'][0]
        self.assertEqual(candidate['location'],'After references')
        self.assertEqual(candidate['country_code'],'CHN')
        self.assertEqual(candidate['evidence'][0]['page'],2)
        self.assertIn('AFF-017',[i['rule_id'] for i in issues])

    def test_api_initials_match_expanded_pdf_name_without_merging_middle_mismatch(self):
        self.assertTrue(engine.compatible_given_name('W','William'))
        self.assertTrue(engine.compatible_given_name('Nigel Hamil','N H'))
        self.assertTrue(engine.compatible_given_name('Alan Davis','Alan D'))
        self.assertFalse(engine.compatible_given_name('Alan Davis','Alan P'))

    def test_more_complete_pdf_name_and_conflicting_middle_name_candidate(self):
        expanded=self.pdf_metadata([(75,'Article title',16),(105,'William Price1',12),
            (145,'1 Department of Mathematics, Paris, France',9),(225,'Abstract',11),
            (240,'A sufficiently long abstract sentence for testing the name.',10)],
            [{'given_name':'W','surname':'Price'}])
        self.assertEqual(expanded['authors'][0]['given_name'],'William')
        self.assertFalse(expanded['author_candidates'])
        conflict=self.pdf_metadata([(75,'Article title',16),(105,'Alan P Parker1',12),
            (145,'1 Department of Mathematics, Paris, France',9),(225,'Abstract',11),
            (240,'A sufficiently long abstract sentence for testing the name.',10)],
            [{'given_name':'Alan Davis','surname':'Parker'}])
        self.assertEqual(conflict['author_candidates'][0]['given_name'],'Alan P')
        self.assertEqual(conflict['author_candidates'][0]['api_given_name'],'Alan Davis')

    def test_unmarked_single_original_affiliation(self):
        md = self.pdf_metadata([
            (75, 'An article title', 16), (102, 'Ada Lovelace', 12),
            (145, 'Department of Mathematics, Example University, Paris, France', 9),
            (225, 'Abstract', 11), (240, 'The study includes a university example.', 10),
        ], [{'given_name': 'Ada', 'surname': 'Lovelace'}])
        self.assertEqual(len(md['affiliations']), 1)
        self.assertEqual(md['authors'][0]['affiliation_ids'], [md['affiliations'][0]['id']])
        self.assertEqual(md['author_groups'][0]['author_ids'], ['author-1'])

    def test_city_only_affiliation_is_captured_and_shared_by_authors(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Fangqi Dong and Alex Lombardi',12),
            (140,'Princeton',9),(225,'Abstract',11),
            (240,'A sufficiently long abstract paragraph for the city-only affiliation test.',10),
        ],[{'given_name':'Fangqi','surname':'Dong'},
           {'given_name':'Alex','surname':'Lombardi'}])
        self.assertEqual(len(md['affiliations']),1)
        self.assertEqual(md['affiliations'][0]['city'],'Princeton')
        self.assertEqual([a['affiliation_ids'] for a in md['authors']],
                         [[md['affiliations'][0]['id']],[md['affiliations'][0]['id']]])

    def test_repeated_surname_uses_given_name_and_skips_email(self):
        md = self.pdf_metadata([
            (75, 'An article title', 16),
            (102, 'Tomas Samuely3, Peter Samuely4', 12),
            (145, '3 Institute of Physics, Bratislava, Slovakia', 9),
            (160, '4 Department of Physics, Trento, Italy', 9),
            (185, 'Peter.Samuely@example.org', 8),
            (225, 'Abstract', 11),
            (240, 'This study includes two authors with the same surname.', 10),
        ], [{'given_name':'Tomas','surname':'Samuely'},
            {'given_name':'Peter','surname':'Samuely'}])
        self.assertEqual([a['given_name'] for a in md['authors']], ['Tomas','Peter'])
        self.assertEqual([a['markers'] for a in md['authors']], [['3'],['4']])
        self.assertEqual([a['affiliation_ids'] for a in md['authors']], [['aff-3'],['aff-4']])

    def test_orcid_id_labels_keep_numeric_author_markers_and_morocco_country(self):
        md=self.pdf_metadata([
            (75,'Do EEG Foundation Models Transfer to Speech?',16),
            (105,'Owais Mujtaba Khanday ID 1,2, Mohamed Baha Ben Ticha ID 1,2, Sanae Belfrouh ID 3, Marc Ouellet ID 4, Jose A. Gonzalez-Lopez ID 1,2',9),
            (140,'1 Dept. Signal Theory, Telematics and Communications, University of Granada, Spain',9),
            (155,'2 Research Centre for Information and Communication Technologies (CITIC-UGR), Spain',9),
            (170,'3 Laboratory of Information Technologies, University of Chouaib Doukkali, Morocco',9),
            (185,'4 Brain, Mind, and Behavior Research Center (CIMCYC), University of Granada, Spain',9),
            (225,'Abstract',11),(240,'A sufficiently long abstract paragraph for checking text conversion and metadata capture.',10),
        ],[
            {'given_name':'Owais Mujtaba','surname':'Khanday'},
            {'given_name':'Mohamed Baha Ben','surname':'Ticha'},
            {'given_name':'Sanae','surname':'Belfrouh'},
            {'given_name':'Marc','surname':'Ouellet'},
            {'given_name':'Jose A.','surname':'Gonzalez-Lopez'},
        ])
        self.assertEqual([a['markers'] for a in md['authors']],[['1','2'],['1','2'],['3'],['4'],['1','2']])
        self.assertEqual([a['affiliation_ids'] for a in md['authors']],[['aff-1','aff-2'],['aff-1','aff-2'],['aff-3'],['aff-4'],['aff-1','aff-2']])
        self.assertEqual([a['country_code'] for a in md['affiliations']],['ESP','ESP','MAR','ESP'])
        self.assertIn('Telematics and Communications',md['affiliations'][0]['organizations'][0])
        self.assertEqual([g['author_ids'] for g in md['author_groups']],[['author-1','author-2','author-5'],['author-1','author-2','author-5'],['author-3'],['author-4']])
        generated=engine.secure_xml(engine.build_xml(md).encode('utf-8'))
        groups=generated.xpath('.//*[local-name()="author-group"]')
        self.assertEqual(len(groups),4)
        self.assertEqual([len(g.xpath('./*[local-name()="author"]')) for g in groups],[3,3,1,1])
        self.assertEqual(len(generated.xpath('.//*[local-name()="affiliation"]')),4)

    def test_centered_address_continuation_stays_in_same_pdf_block(self):
        def line(n,x0,x1,y,text):
            return {'id':str(n),'page':1,'block':2,'text':text,'bbox':[x0,y,x1,y+9],
                    'size':9,'direction':[1,0],'spans':[]}
        lines=[line(1,100,510,145,'3 Centre of Low Temperature Physics, Slovak Academy of Sciences,'),
               line(2,250,360,157,'SK-04001 Košice, Slovakia'),
               line(3,100,510,170,'4 Department of Physics, University of Trento, Italy')]
        affiliations,used=engine.front_affiliations(lines,126,792,['3','4'])
        self.assertEqual(len(affiliations),2)
        self.assertEqual(affiliations[0]['country_code'],'SVK')
        self.assertTrue(affiliations[0]['source_text'].endswith('Košice, Slovakia'))
        self.assertEqual(len(used),3)

    def test_keyword_heading_without_list_is_flagged(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'article.pdf'
            doc=fitz.open();page=doc.new_page(width=600,height=800)
            for y,line,size in [(75,'An article title',16),(102,'Ada Lovelace1',12),
                                (145,'1 Department of Mathematics, Paris, France',9),
                                (225,'Abstract',11),(240,'This article has a visible keyword heading.',10),
                                (300,'Keywords',10)]:
                page.insert_text((50,y),line,fontsize=size)
            doc.save(pdf);doc.close()
            layout,_=engine.extract_layout(pdf,{})
            _,issues=engine.extract_metadata(layout,{'api_authors':[{'given_name':'Ada','surname':'Lovelace'}]}, {})
        self.assertIn('KEY-001',[i['rule_id'] for i in issues])

    def test_keyword_and_phrases_is_a_label_not_a_keyword(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace1',12),
            (145,'1 Department of Mathematics, Paris, France',9),
            (180,'Abstract',11),(195,'This article has a sufficiently long abstract paragraph for testing the full keyword label.',10),
            (235,'Key words and phrases: oscillatory integral; Fourier frame',9),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertEqual(md['keywords'],['oscillatory integral','Fourier frame'])

    def test_dutch_postcodes_and_weg_street_addresses_parse_separately(self):
        examples=[
            ('Materials and Structural Analysis Division, Thermo Fisher Scientific, Achtseweg Noord 5, 5651 GG, Eindhoven, The Netherlands',
             ['Materials and Structural Analysis Division','Thermo Fisher Scientific'],['Achtseweg Noord 5'],'Eindhoven','5651 GG'),
            ('MESA+ Institute, Faculty of Science and Technology, University of Twente, 7500 AE Enschede, The Netherlands',
             ['MESA+ Institute','Faculty of Science and Technology','University of Twente'],[],'Enschede','7500 AE'),
            ('Debye Institute for Nanomaterials Science, Utrecht University, Universiteitsweg 99, 3584 CG, Utrecht, The Netherlands',
             ['Debye Institute for Nanomaterials Science','Utrecht University'],['Universiteitsweg 99'],'Utrecht','3584 CG'),
        ]
        for source,organizations,address,city,postal in examples:
            with self.subTest(source=source):
                parsed=engine.parse_affiliation(source,'1',[],False)
                self.assertEqual(parsed['organizations'],organizations)
                self.assertEqual(parsed['address_parts'],address)
                self.assertEqual(parsed['city'],city)
                self.assertEqual(parsed['postal_code'],postal)
                self.assertEqual(parsed['country_code'],'NLD')

    def test_trailing_duplicate_affiliation_fragment_merges_only_with_complete_match(self):
        complete=engine.parse_affiliation('School of Mathematics, Central China Normal University, Wuhan 430079, China','1',[{'line_id':'full'}],True)
        fragment=engine.parse_affiliation('mal University, Wuhan 430079, China','2',[{'line_id':'fragment'}],True)
        separate=engine.parse_affiliation('Department of Mathematics, Southern University, Shenzhen 518055, China','3',[{'line_id':'other'}],True)
        merged,fragments,id_map=engine.merge_affiliation_fragments([complete,fragment,separate])
        self.assertEqual(len(merged),2)
        self.assertEqual(merged[0]['source_text'],complete['source_text'])
        self.assertEqual({e['line_id'] for e in merged[0]['evidence']},{'full','fragment'})
        self.assertEqual(id_map[fragment['id']],complete['id'])
        self.assertEqual(len(fragments),1)

    def test_keyword_list_on_next_pdf_line_is_captured(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'article.pdf'
            doc=fitz.open();page=doc.new_page(width=600,height=800)
            for y,line,size in [(75,'An article title',16),(102,'Ada Lovelace1',12),
                                (145,'1 Department of Mathematics, Paris, France',9),
                                (225,'Abstract',11),(240,'This article has a visible keyword heading.',10),
                                (300,'Keywords',10),(315,'Physics; mathematics',10)]:
                page.insert_text((50,y),line,fontsize=size)
            doc.save(pdf);doc.close()
            layout,_=engine.extract_layout(pdf,{})
            md,issues=engine.extract_metadata(layout,{'api_authors':[{'given_name':'Ada','surname':'Lovelace'}]}, {})
        self.assertEqual(md['keywords'],['Physics','mathematics'])
        self.assertEqual(len(md['field_evidence']['keywords']),2)
        self.assertNotIn('KEY-001',[i['rule_id'] for i in issues])

    def test_author_keywords_after_abstract_win_and_index_terms_are_ignored(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace1',12),
            (145,'1 Department of Mathematics, Paris, France',9),
            (180,'Keywords: older, list',9),(210,'Abstract',11),
            (225,'This article has a sufficiently long abstract paragraph for testing keywords.',10),
            (270,'Index Terms: ignored, list',9),
            (300,'Keywords: physics; mathematics. systems,',9),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertEqual(md['keywords'],['physics','mathematics','systems'])

    def test_author_footnotes_are_not_unheaded_abstract(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace1,*',12),
            (145,'1 Department of Mathematics, Paris, France',9),
            (185,'*These authors contributed equally to this work',9),
            (200,'Corresponding authors: ada@example.org',9),
            (245,'We investigate a substantive research problem with a reproducible method and measured results.',10),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertTrue(md['abstract'].startswith('We investigate'),md['abstract'])

    def test_sample_two_column_address_does_not_include_abstract(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with zipfile.ZipFile(BASE / 'samples' / 'toolsamples.zip') as archive:
                names = [n for n in archive.namelist() if '2408.09673n/' in n and
                         n.endswith(('.pdf', '_Api.xml'))]
                for name in names:
                    (root / Path(name).name).write_bytes(archive.read(name))
            layout, _ = engine.extract_layout(root / '2408.09673.pdf', {})
            support, _ = engine.source_data({'API': {'path': '2408.09673_Api.xml'}}, root)
            md, _ = engine.extract_metadata(layout, support, {})
        self.assertEqual(len(md['affiliations']), 3)
        self.assertEqual(len(md['author_groups']), 3)
        self.assertTrue(all(a['source_text'].endswith('USA') for a in md['affiliations']))
        self.assertEqual([a['global_seq'] for a in md['authors']], [1, 2, 3, 4, 5])
        self.assertIn('author-1', md['author_groups'][0]['author_ids'])
        self.assertIn('author-1', md['author_groups'][1]['author_ids'])

    def test_sample_australian_and_us_addresses_keep_printed_components(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with zipfile.ZipFile(BASE/'samples'/'toolsamples.zip') as z:
                for n in z.namelist():
                    if '2408.09700' in n and n.endswith(('.pdf','_Api.xml')):
                        (root/Path(n).name).write_bytes(z.read(n))
            layout,_=engine.extract_layout(root/'2408.09700.pdf',{})
            support,_=engine.source_data({'API':{'path':'2408.09700_Api.xml'}},root)
            md,_=engine.extract_metadata(layout,support,{})
        self.assertEqual(len(md['affiliations']),5)
        nsw,_,colorado,_,act=md['affiliations']
        self.assertEqual((nsw['state'],nsw['postal_code'],nsw['city']),('NSW','2006',''))
        self.assertEqual((colorado['city'],colorado['state'],colorado['postal_code']),('Boulder','CO','80301'))
        self.assertIn('4750 Walnut Street',colorado['address_parts'])
        self.assertIn('Suite 205',colorado['address_parts'])
        self.assertEqual((act['city'],act['state'],act['postal_code']),('Weston Creek','ACT','2611'))
        self.assertFalse(any(a['component_warnings'] for a in md['affiliations']))

    def test_marked_single_affiliation_with_unrelated_author_marker_is_not_linked(self):
        md=self.pdf_metadata([
            (75,'An article title',16),(102,'Ada Lovelace2',12),
            (145,'1 Department of Mathematics, Paris, France',9),
            (225,'Abstract',11),(240,'A fully printed abstract for the example article.',10),
        ],[{'given_name':'Ada','surname':'Lovelace'}])
        self.assertEqual(len(md['affiliations']),1)
        self.assertEqual(md['authors'][0]['affiliation_ids'],[])
        self.assertEqual(md['author_groups'],[])

    def test_numbered_author_prefixes_and_comma_delimiters_link_in_pdf_order(self):
        md=self.pdf_metadata([
            (75,'An article title',16),
            (102,'1- Ada Lovelace, 2- Grace Hopper',12),
            (145,'1, PhD Student, Department of Mathematics, Example University, Norfolk, VA, USA',9),
            (165,'2, Associated professor, Institute of Computing, Example University, Tehran, Iran',9),
            (225,'Abstract',11),(240,'A sufficiently long abstract for the author marker regression.',10),
        ],[{'given_name':'Ada','surname':'Lovelace'},
           {'given_name':'Grace','surname':'Hopper'}])
        self.assertEqual([a['markers'] for a in md['authors']],[['1'],['2']])
        self.assertEqual([a['affiliation_ids'] for a in md['authors']],[['aff-1'],['aff-2']])
        self.assertEqual([g['author_ids'] for g in md['author_groups']],[['author-1'],['author-2']])
        self.assertEqual([f['city'] for f in md['affiliations']],['Norfolk','Tehran'])

    def test_named_acronym_organization_street_uk_postcode_and_xml_tags(self):
        curl=engine.parse_affiliation(
            'Cosmology, Universe and Relativity at Louvain (CURL), Institute of Mathematics and Physics, '
            'University of Louvain, 2 Chemin du Cyclotron, 1348 Louvain-la-Neuve, Belgium','b',[])
        lancaster=engine.parse_affiliation(
            'Consortium for Fundamental Physics, Physics Department, Lancaster University, '
            'Lancaster LA1 4YB, United Kingdom','a',[])
        self.assertEqual(curl['organizations'],[
            'Cosmology, Universe and Relativity at Louvain (CURL)',
            'Institute of Mathematics and Physics','University of Louvain'])
        self.assertEqual(curl['address_parts'],['2 Chemin du Cyclotron'])
        self.assertEqual((curl['city'],curl['postal_code'],curl['country_code']),
                         ('Louvain-la-Neuve','1348','BEL'))
        self.assertEqual((lancaster['city'],lancaster['postal_code'],lancaster['country_code']),
                         ('Lancaster','LA1 4YB','GBR'))
        metadata={'base_id':'2507.15522','version':1,'title':'Sample','abstract':'Text',
                  'authors':[{'id':'author-1','global_seq':1,'given_name':'Eemeli','surname':'Tomberg',
                              'initials':'E.','affiliation_ids':['aff-b']}],
                  'affiliations':[curl],'author_groups':[{'author_ids':['author-1'],'affiliation_id':'aff-b'}],
                  'keywords':[],'references':[],'profile':{}}
        root=engine.secure_xml(engine.build_xml(metadata).encode('utf-8'))
        affiliation=root.xpath('.//*[local-name()="affiliation"]')[0]
        self.assertEqual(affiliation.xpath('./*[local-name()="address-part"]/text()'),['2 Chemin du Cyclotron'])
        self.assertEqual(affiliation.xpath('./*[local-name()="city"]/text()'),['Louvain-la-Neuve'])

    @unittest.skipUnless(shutil.which('tesseract'),'Local Tesseract is optional')
    def test_image_only_pdf_uses_coordinate_aware_local_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf=Path(folder)/'scan.pdf';image=Path(folder)/'page.png'
            doc=fitz.open();page=doc.new_page(width=612,height=792)
            page.insert_text((40,70),'Scanned example with a clear text line',fontsize=16)
            page.get_pixmap(matrix=fitz.Matrix(2,2)).save(image);doc.close()
            doc=fitz.open();page=doc.new_page(width=612,height=792)
            page.insert_image(page.rect,filename=str(image));doc.save(pdf);doc.close()
            layout,issues=engine.extract_layout(pdf,{})
        self.assertEqual(layout['pages'][0]['text_origin'],'OCR')
        self.assertTrue(layout['pages'][0]['words'])
        self.assertTrue(all(len(w['bbox'])==4 for w in layout['pages'][0]['words']))
        self.assertIn('PDF-002',[i['rule_id'] for i in issues])


if __name__ == '__main__':
    unittest.main()
