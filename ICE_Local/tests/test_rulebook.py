"""Rulebook loading, and each rule against PDFs that do and do not trigger it."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import engine
import rulebook

TITLE = [(40, 'arXiv:2609.12345v1', 9), (80, 'An article title', 16)]
AUTHOR = [(110, 'Ada Lovelace1', 12), (140, '1 University of Example, London, UK', 9)]
ABSTRACT = [(190, 'Abstract', 11), (205, 'This article checks deterministic extraction of the front matter.', 10)]
REFERENCES = [(100, 'References', 12), (125, '[1] Doe J. First sample work. Journal 2021.', 10),
              (140, '[2] Roe K. Second sample work. Journal 2022.', 10), (155, '[3] Poe E. Third sample work. Journal 2023.', 10)]
ADA = [{'given_name': 'Ada', 'surname': 'Lovelace'}]
SUPPORT = {'scrapping_id': '2609.12345', 'scrapping_version': 1, 'html_id': '2609.12345', 'html_version': None,
           'html_title': 'An article title', 'api_id': '2609.12345', 'api_title': 'An article title'}


def check(key, front=None, later=None, authors=ADA, support=None, links=(), **settings):
    """Run one rule over a two-page PDF; returns its detail when it fires, else None."""
    pages = [front if front is not None else TITLE + AUTHOR + ABSTRACT, later if later is not None else REFERENCES]
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
    md, issues = engine.extract_metadata(layout, {'api_authors': list(authors), **SUPPORT, **(support or {})}, {})
    job = {'metadata': md, 'issues': issues, 'selected': {r: r for r in ('PDF', 'API', 'SCRAPPING', 'HTML')}}
    spec = rulebook.RULES[key]
    book = {'rules': [{'key': key, 'on': True, 'group': spec['group'], 'text': spec['text'],
                       'settings': {**spec['defaults'], **settings}}], 'errors': []}
    result = rulebook.evaluate(job, book, layout)[0]
    return result['detail'] if result['fired'] else None


class LoadTest(unittest.TestCase):
    def test_shipped_rulebook_turns_on_every_rule_without_errors(self):
        book = rulebook.load(rulebook.DEFAULT_PATH)
        self.assertEqual(book['errors'], [])
        self.assertEqual({r['key'] for r in book['rules'] if r['on']}, set(rulebook.RULES))
        self.assertFalse(any(r.get('missing') for r in book['rules']))

    def test_mistakes_are_errors_not_silent_rules(self):
        cases = {
            '[titel_mismatch]\non = true': 'Unknown rule [titel_mismatch]',
            '[orcid]\non = true\ncolour = "red"': 'has no setting "colour"',
            '[references_incomplete]\non = true\nmin_length = "twenty"': 'min_length must be a whole number',
            '[orcid]\non = "yes"': 'needs on = true or on = false',
            '[title_mismatch]\non = true\ncompare_with = ["HTLM"]': 'compare_with must be a list of',
            '[orcid]\non = true\ntext = "unclosed': 'not valid TOML',
        }
        for text, message in cases.items():
            errors = rulebook.parse(text)['errors']
            self.assertTrue(any(message in e for e in errors), (text, errors))
        bad_toml = rulebook.parse('[orcid]\non = true\n\n[abstract_missing\non = true')['errors'][0]
        self.assertIn('line 4', bad_toml)

    def test_left_out_rules_are_listed_as_off(self):
        book = rulebook.parse('[orcid]\non = true')
        self.assertEqual(book['errors'], [])
        self.assertEqual([r['key'] for r in book['rules'] if r['on']], ['orcid'])
        self.assertTrue(next(r for r in book['rules'] if r['key'] == 'title_mismatch')['missing'])

    def test_edits_are_picked_up_and_env_var_chooses_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'rules.toml'
            file.write_text('[orcid]\non = true\n', encoding='utf-8')
            with patch.dict(os.environ, {'ICE_RULEBOOK': str(file)}):
                self.assertTrue(next(r for r in rulebook.load()['rules'] if r['key'] == 'orcid')['on'])
                time.sleep(.01)
                file.write_text('[orcid]\non = false\n', encoding='utf-8')
                os.utime(file, ns=(time.time_ns(), time.time_ns() + 10**9))
                self.assertFalse(next(r for r in rulebook.load()['rules'] if r['key'] == 'orcid')['on'])
        missing = rulebook.load(Path(folder) / 'gone.toml')
        self.assertTrue(missing['errors'])
        self.assertFalse(any(r['on'] for r in missing['rules']))


class RuleTest(unittest.TestCase):
    def test_clean_article_passes_every_rule(self):
        for key in rulebook.RULES:
            self.assertIsNone(check(key), key)

    def test_id_and_version(self):
        self.assertTrue(check('id_missing', front=TITLE[1:] + AUTHOR + ABSTRACT,
                              support={'html_id':'','scrapping_id':'','html_title':''}))
        self.assertIn('Scrapping version 2', check('id_version_mismatch', support={'scrapping_version': 2}))
        self.assertIn('HTML ID 2609.99999', check('id_version_mismatch', support={'html_id': '2609.99999'}))
        self.assertIsNone(check('id_version_mismatch', support={'scrapping_id': 'arXiv:2609.12345v1'}))

    def test_title_content(self):
        self.assertIsNone(check('title_mismatch', support={'html_title': 'AN ARTICLE TITLE.'}))
        self.assertIn('Another title', check('title_mismatch', support={'html_title': 'Another title'}))

    def test_abstract(self):
        no_heading = TITLE + AUTHOR + [(205, 'This article checks deterministic extraction of the front matter.', 10)]
        self.assertTrue(check('abstract_missing', front=TITLE + AUTHOR))
        self.assertIsNone(check('abstract_missing', front=no_heading))
        self.assertTrue(check('abstract_missing', front=no_heading, require_heading=True))
        teaser = TITLE + AUTHOR + [(190, 'Teaser', 11), (205, 'A short teaser that sells the article to a general reader.', 10)]
        self.assertIn('"Teaser"', check('abstract_is_pitch', front=teaser))
        both = TITLE + AUTHOR + ABSTRACT + [(260, 'Elevator pitch', 11), (275, 'Why this matters in one line.', 10)]
        self.assertIsNone(check('abstract_is_pitch', front=both))

    def test_author_mismatch(self):
        grace = ADA + [{'given_name': 'Grace', 'surname': 'Hopper'}]
        self.assertIn('Grace Hopper', check('author_mismatch', authors=grace))
        extra = TITLE + [(110, 'Ada Lovelace1, Charles Babbage1', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertIn('Charles Babbage', check('author_mismatch', front=extra))
        initials = TITLE + [(110, 'A. Lovelace1', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertTrue(check('author_mismatch', front=initials))
        self.assertIsNone(check('author_mismatch', front=initials, initials_match_full_names=True))
        honorific = TITLE + [(110, 'Dr. Ada Lovelace1', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertIsNone(check('author_mismatch', front=honorific))

    def test_author_affiliation_links(self):
        two = ADA + [{'given_name': 'Grace', 'surname': 'Hopper'}]
        unmarked = TITLE + [(110, 'Ada Lovelace, Grace Hopper', 12), (140, 'University of Example, London, UK', 9)] + ABSTRACT
        self.assertIn('only because one unmarked affiliation', check('author_affiliation_unlinked', front=unmarked, authors=two))
        single = TITLE + [(110, 'Ada Lovelace', 12), (140, 'University of Example, London, UK', 9)] + ABSTRACT
        self.assertIsNone(check('author_affiliation_unlinked', front=single))
        self.assertTrue(check('author_affiliation_unlinked', front=single, allow_single_author_single_affiliation=False))
        dangling = TITLE + [(110, 'Ada Lovelace1,2', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertIn('indicator 2', check('author_affiliation_unlinked', front=dangling))

    def test_author_name_extras(self):
        self.assertIn('honorific "Dr"', check('author_name_extras', authors=[{'given_name': 'Dr Ada', 'surname': 'Lovelace'}]))
        self.assertIn('suffix "Jr"', check('author_name_extras', authors=[{'given_name': 'Ada', 'surname': 'Lovelace', 'suffix': 'Jr'}]))
        degree = TITLE + [(110, 'Ada Lovelace, PhD1', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertIn('degree "PhD"', check('author_name_extras', front=degree))
        alias = TITLE + [(110, 'Ada (Augusta) Lovelace1', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertIn('alias', check('author_name_extras', front=alias))
        two = TITLE + [(110, 'Ada Lovelace1, Grace Hopper1', 12)] + AUTHOR[1:] + ABSTRACT
        self.assertIsNone(check('author_name_extras', front=two, authors=ADA + [{'given_name': 'Grace', 'surname': 'Hopper'}]))

    def test_references(self):
        bibliography = [(400, 'Bibliography', 12), (425, 'Zoe A. A fourth work. Journal 2020.', 10)]
        self.assertIn('2 separate places', check('references_two_locations', later=REFERENCES + bibliography))
        self.assertTrue(check('references_missing', later=[(100, 'Body text only.', 10)]))
        cut = REFERENCES[:2] + [(140, '[2] Roe K. Second sample work,', 10)] + REFERENCES[3:]
        self.assertIn('reference 2', check('references_incomplete', later=cut))
        gap = REFERENCES[:3] + [(155, '[4] Poe E. Third sample work. Journal 2023.', 10)]
        self.assertIn('gaps', check('references_incomplete', later=gap))
        two_works = REFERENCES[:2] + [(140, '[2] Roe K. Second work. Journal 2022; Smith J. Other work, 2019.', 10)] + REFERENCES[3:]
        self.assertIn('Reference 2', check('references_multiple', later=two_works))

    def test_reference_hyperlinks(self):
        printed = REFERENCES[:2] + [(140, '[2] Roe K. Second work. https://example.org/paper 2022.', 10)] + REFERENCES[3:]
        self.assertIn('https://', check('reference_hyperlinks', later=printed))
        self.assertIsNone(check('reference_hyperlinks', later=printed, include_printed_addresses=False))
        clickable = [(2, (50, 130, 300, 145), 'https://doi.org/10.1000/xyz')]
        self.assertIn('doi.org', check('reference_hyperlinks', links=clickable))

    def test_correspondence_address(self):
        address = TITLE + AUTHOR + ABSTRACT + [(700, '*Correspondence to: Department of Physics, University of Example, UK', 8)]
        self.assertIn('Correspondence to', check('correspondence_address', front=address))
        email = TITLE + AUTHOR + ABSTRACT + [(700, '*Corresponding author: ada@example.org', 8)]
        self.assertIsNone(check('correspondence_address', front=email))
        prose = TITLE + AUTHOR + ABSTRACT + [(400, 'correspondence to the University of Example model is exact', 10)]
        self.assertIsNone(check('correspondence_address', front=prose))

    def test_affiliations(self):
        biography = REFERENCES + [(400, 'Biography', 12), (420, 'Ada Lovelace is at the University of Example.', 10)]
        self.assertIn('"Biography"', check('affiliation_outside_front', later=biography))
        german = TITLE + [(110, 'Ada Lovelace1', 12), (140, '1 Universität Wien, Wien, Austria', 9)] + ABSTRACT
        self.assertIn('Universität', check('affiliation_non_english', front=german))
        self.assertIsNone(check('affiliation_non_english', front=german, words=[]))

    def test_orcid(self):
        self.assertIn('orcid.org', check('orcid', links=[(1, (200, 100, 215, 114), 'https://orcid.org/0000-0002-1825-0097')]))
        printed = TITLE + AUTHOR + ABSTRACT + [(700, 'ORCID: 0000-0002-1825-0097', 8)]
        self.assertTrue(check('orcid', front=printed))


if __name__ == '__main__':
    unittest.main()
