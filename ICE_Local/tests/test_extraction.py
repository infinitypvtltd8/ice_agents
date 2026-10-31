"""Extraction regressions for the ID stamp, reference regions and ORCID links."""
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import engine


def extract(pages, authors=(), support=None, links=()):
    """Build a PDF from (y, text, size) rows per page and run the extractor on it."""
    with tempfile.TemporaryDirectory() as folder:
        pdf = Path(folder) / 'article.pdf'
        with fitz.open() as document:
            for rows in pages:
                page = document.new_page(width=600, height=800)
                for y, text, size in rows:
                    page.insert_text((50, y), text, fontsize=size)
            for number, rect, uri in links:
                document[number - 1].insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(rect), 'uri': uri})
            document.save(pdf)
        layout, _ = engine.extract_layout(pdf, {})
    values = {'api_authors': list(authors), **(support or {})}
    md, issues = engine.extract_metadata(layout, values, {})
    return md, issues, layout


def rules(issues):
    return [i['rule_id'] for i in issues]


FRONT = [(40, 'arXiv:2609.12345v1', 9), (80, 'An article title', 16), (110, 'Ada Lovelace', 12),
         (140, 'University of Example, London, UK', 9), (190, 'Abstract', 11),
         (205, 'This article checks deterministic extraction of the front matter.', 10)]
ADA = [{'given_name': 'Ada', 'surname': 'Lovelace'}]


class StampTest(unittest.TestCase):
    def test_stamp_without_version_is_the_id_and_the_version_is_checked(self):
        rows = [(40, 'arXiv:2609.12345', 9)] + FRONT[1:]
        md, issues, _ = extract([rows], ADA)
        self.assertEqual((md['base_id'], md['version']), ('2609.12345', None))
        self.assertNotIn('ID-004', rules(issues))
        md['source_values'].update(scrapping_id='2609.12345', scrapping_version=1)
        checked = engine.verify_metadata(md, {})[0]
        self.assertTrue(any(i['rule_id'] == 'ID-002' and i['field'] == 'version' for i in checked))


class TextFidelityTest(unittest.TestCase):
    def test_xml_forbidden_pdf_controls_are_replaced_with_review_glyph(self):
        cleaned,count=engine.xml10_text('reference\x12 title')
        self.assertEqual(cleaned,'reference\ufffd title')
        self.assertEqual(count,1)

    def test_unheaded_abstract_acronym_is_not_misread_as_an_affiliation(self):
        rows=[(40,'Effect of a flow on active particles',16),(75,'Ada Lovelace',12),
              (92,'Department of Physics, University of Example, London, UK',9),
              (120,'We simulate active Brownian particles (ABPs) with soft interactions in a flow.',9),
              (132,'The results show that these particles remain mixed in the measured regime.',9),
              (150,'Keywords: active matter, ABPs, flow',8),(180,'1. Introduction',12)]
        md,_,_=extract([rows],ADA)
        self.assertIn('We simulate active Brownian particles (ABPs)',md['abstract'])
        self.assertIn('The results show',md['abstract'])
        self.assertEqual(len(md['affiliations']),1)

    def test_known_accent_glyphs_are_recombined_and_normalized(self):
        self.assertEqual(engine.join_text(['P´erez and École']), 'Pérez and École')

    def test_superscript_is_added_only_when_pdf_span_maps_exactly(self):
        line={'text':'x2','bbox':[0,0,20,10],'size':10,'spans':[
            {'text':'x','bbox':[0,0,8,10],'size':10,'flags':0},
            {'text':'2','bbox':[9,0,13,7],'size':7,'flags':1},
        ]}
        self.assertEqual(engine.inline_markup_from_lines([line],'x2'),'x<sup>2</sup>')
        self.assertEqual(engine.inline_markup_from_lines([line],'x²'),'')

    def test_unicode_and_inline_scripts_survive_generated_xml(self):
        md,_,_=extract([FRONT],ADA)
        md['title']='École x2';md['title_markup']='École x<sup>2</sup>'
        md['abstract']='Résumé naïve x2';md['abstract_markup']='Résumé naïve x<sup>2</sup>'
        root=engine.secure_xml(engine.build_xml(md).encode('utf-8'))
        title=root.xpath('//*[local-name()="titletext"]')[0]
        abstract=root.xpath('//*[local-name()="para"]')[0]
        self.assertEqual(''.join(title.itertext()),'École x2')
        self.assertEqual(''.join(abstract.itertext()),'Résumé naïve x2')
        self.assertEqual(len(abstract.xpath('.//*[local-name()="sup"]')),1)

    def test_formula_placeholder_requires_dense_standalone_equation(self):
        formula='H = ∑ x + ∫ y = ∇z ≤ 2'
        self.assertTrue(engine.is_complex_display_formula(formula))
        prose='We use x = y in this simple example.'
        self.assertFalse(engine.is_complex_display_formula(prose))
        lines=[{'text':formula}]
        self.assertEqual(engine.replace_complex_display_formulas(lines,'Before. '+formula+' After.'),
                         ('Before. (Formula presented) After.',1))

    def test_support_ids_compare_without_prefix_or_version(self):
        md, _, _ = extract([FRONT], ADA)
        md['source_values'].update(scrapping_id='arXiv:2609.12345v1', scrapping_version=1, html_id='2609.12345')
        checked = engine.verify_metadata(md, {})[0]
        self.assertFalse([i for i in checked if i['rule_id'] in ('ID-002', 'ID-003') and i['field'] == 'base_id'])
        md['source_values']['scrapping_id'] = '2609.54321'
        checked = engine.verify_metadata(md, {})[0]
        self.assertTrue(any(i['rule_id'] == 'ID-002' and 'mismatch' in i['message'] for i in checked))


class CorroboratedIdentityTest(unittest.TestCase):
    def test_missing_pdf_stamp_uses_support_identity_only_after_exact_title_match(self):
        support={
            'html_title':'An article title', 'html_id':'arXiv:2609.12345',
            'html_version':None, 'scrapping_id':'2609.12345',
            'scrapping_version':2, 'api_id':'2609.12345',
        }
        md,issues,_=extract([FRONT[1:]],ADA,support)
        self.assertEqual((md['base_id'],md['version']),('2609.12345',2))
        self.assertEqual(md['id_capture_source'],'HTML + SCRAPPING; PDF/HTML title match')
        self.assertNotIn('ID-004',rules(issues))

    def test_missing_stamp_does_not_use_ids_when_pdf_and_html_titles_differ(self):
        support={
            'html_title':'A different article title', 'html_id':'2609.12345',
            'scrapping_id':'2609.12345', 'scrapping_version':1,
        }
        md,issues,_=extract([FRONT[1:]],ADA,support)
        self.assertEqual((md['base_id'],md['version']),('',None))
        self.assertIn('ID-004',rules(issues))

    def test_missing_stamp_does_not_use_conflicting_support_versions(self):
        support={
            'html_title':'An article title', 'html_id':'2609.12345',
            'html_version':2, 'scrapping_id':'2609.12345',
            'scrapping_version':1,
        }
        md,issues,_=extract([FRONT[1:]],ADA,support)
        self.assertEqual((md['base_id'],md['version']),('',None))
        self.assertIn('ID-004',rules(issues))


class ReferenceRegionTest(unittest.TestCase):
    def test_reference_extraction_ignores_glyph_wrapped_page_footer(self):
        rows = [(100, 'References', 12), (125, '[1] Doe J. First sample work. Journal 2021.', 10),
                (145, '[2] Roe K. Second sample work. Journal 2022 [2401.12345].', 10),
                (165, '[3] Poe E. Third sample work. Journal 2023.', 10), (780, '- 38 -', 10)]
        md, _, _ = extract([FRONT, rows], ADA)
        self.assertEqual(len(md['references']), 3)
        self.assertTrue(all('38' not in r['source_text'] for r in md['references']))
        self.assertEqual(md['coverage']['printed_label_inventory'], ['1','2','3'])

    def test_trace_recovers_a_replacement_character_only_when_aligned(self):
        text='It\ufffd, Stratonovich'
        glyphs=[(ord(c),0,None,(0,0,1,1)) for c in 'Itô,Stratonovich']
        trace=[{'font':'Italic','bbox':(0,0,20,10),'chars':glyphs}]
        self.assertEqual(engine.recover_glyph_text(text,(0,0,20,10),'Italic',trace),
                         'Itô, Stratonovich')
        self.assertEqual(engine.recover_glyph_text(text,(0,0,20,10),'Other',trace),text)

    def test_early_numbered_list_does_not_hide_the_bibliography(self):
        body = FRONT + [(300, '[1] first numbered point in the text', 10), (315, '[2] second numbered point', 10),
                        (330, '[3] third numbered point', 10)]
        filler = [(100, 'Body text continues on this page.', 10)]
        bibliography = [(100, 'References', 12), (125, 'Doe J. First sample work. Journal 2021.', 10),
                        (140, 'Roe K. Second sample work. Journal 2022.', 10)]
        md, issues, _ = extract([body, filler, filler, bibliography], ADA)
        self.assertEqual([r['source_text'] for r in md['references']],
                         ['Doe J. First sample work. Journal 2021.', 'Roe K. Second sample work. Journal 2022.'])
        self.assertNotIn('REF-014', rules(issues))
        self.assertNotIn('REF-002', rules(issues))

    def test_empty_reference_list_is_reported(self):
        md, issues, _ = extract([FRONT + [(400, 'References', 12), (430, 'Introduction', 12)]], ADA)
        self.assertEqual(md['references'], [])
        self.assertIn('REF-002', rules(issues))


class OrcidTest(unittest.TestCase):
    def test_orcid_link_is_assigned_only_on_the_authors_page(self):
        # Place the clickable ORCID icon just after the printed author name;
        # far-away links must remain unassigned rather than being guessed.
        same_page = [(1, (126, 100, 140, 114), 'https://orcid.org/0000-0002-1825-009x')]
        md, issues, _ = extract([FRONT], ADA, links=same_page)
        self.assertEqual(md['authors'][0]['orcid'], '0000-0002-1825-009X')
        other_page = [(2, (200, 100, 215, 114), 'https://orcid.org/0000-0002-1825-0097')]
        md, issues, _ = extract([FRONT, [(300, 'Second page', 10)]], ADA, links=other_page)
        self.assertEqual(md['authors'][0]['orcid'], '')
        self.assertIn('ORCID-001', rules(issues))


class RulebookFactsTest(unittest.TestCase):
    def test_abstract_heading_is_recorded(self):
        md, _, _ = extract([FRONT], ADA)
        self.assertEqual(md['abstract_heading'], 'Abstract')

    def test_link_method_and_unmatched_markers(self):
        two = [{'given_name': 'Ada', 'surname': 'Lovelace'}, {'given_name': 'Grace', 'surname': 'Hopper'}]
        rows = FRONT[:2] + [(110, 'Ada Lovelace, Grace Hopper', 12)] + FRONT[3:]
        md, _, _ = extract([rows], two)
        self.assertEqual([a['link_method'] for a in md['authors']], ['single_affiliation'] * 2)
        rows = FRONT[:2] + [(110, 'Ada Lovelace1,2', 12), (140, '1 University of Example, London, UK', 9)] + FRONT[4:]
        md, _, _ = extract([rows], ADA)
        self.assertEqual(md['authors'][0]['link_method'], 'marker')
        self.assertEqual(md['authors'][0]['unmatched_markers'], ['2'])

    def test_printed_name_parts_and_leftover_author_words(self):
        rows = FRONT[:2] + [(110, 'Dr. Ada Lovelace, Charles Babbage', 12)] + FRONT[3:]
        md, _, _ = extract([rows], ADA)
        self.assertEqual(md['authors'][0]['pdf_name_parts']['before'], 'Dr. Ada')
        self.assertEqual([w['word'] for w in md['author_line_leftover']], ['Charles', 'Babbage'])
        md, _, _ = extract([FRONT], ADA)
        self.assertEqual(md['author_line_leftover'], [])

    def test_api_name_suffix_is_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'api.xml').write_text('<record><author><keyname>King</keyname><forenames>Martin</forenames>'
                                                 '<suffix>Jr</suffix></author></record>', encoding='utf-8')
            values, _ = engine.source_data({'API': {'path': 'api.xml', 'name': 'api.xml'}}, Path(folder))
        self.assertEqual(values['api_authors'], [{'surname': 'King', 'given_name': 'Martin', 'suffix': 'Jr'}])

    def test_reference_regions_and_footer_candidates(self):
        refs = [(100, 'References', 12), (125, 'Doe J. First sample work. Journal 2021.', 10),
                (140, 'Roe K. Second sample work. Journal 2022.', 10)]
        md, _, _ = extract([FRONT, refs], ADA)
        self.assertEqual(md['coverage']['reference_regions'], 1)
        md, _, _ = extract([FRONT, refs, [(100, 'Bibliography', 12), (125, 'Poe E. Third sample work. Journal 2023.', 10)]], ADA)
        self.assertEqual(md['coverage']['reference_regions'], 2)
        footer = [(100, 'Body text of the second page of the article.', 10), (120, 'More body text in the main font.', 10),
                  (700, 'Department of Physics, University of Example, Paris, France', 7)]
        prose = [(100, 'Body text of the third page.', 10),
                 (700, 'Research at the University of Example, Paris, France', 10)]
        md, _, _ = extract([FRONT, footer, prose, refs], ADA)
        self.assertEqual([c['location'] for c in md['affiliation_candidates']], ['Page 2 footer'])


if __name__ == '__main__':
    unittest.main()
