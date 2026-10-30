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
