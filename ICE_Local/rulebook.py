"""The routing rulebook: which findings send an article to the Irregular queue.

config/rulebook.toml turns each rule on or off and holds its wording and word
lists. The checks live here. A rule name or setting the code does not know is
reported as an error, so a typo never looks like a working rule.
"""
import hashlib
import os
import re
import tomllib
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import engine

DEFAULT_PATH = Path(__file__).resolve().parent / 'config' / 'rulebook.toml'
SOURCES = {'SCRAPPING': 'Scrapping', 'HTML': 'HTML', 'API': 'API'}
RULES = {}
_cache = {}


def rule(key, group, text, needs_layout=False, choices=None, **defaults):
    """Register a check. Its keyword defaults are the settings the rulebook may change."""
    def register(check):
        RULES[key] = {'check': check, 'group': group, 'text': text, 'needs_layout': needs_layout,
                      'choices': choices or {}, 'defaults': defaults}
        return check
    return register


def path():
    return Path(os.environ.get('ICE_RULEBOOK') or DEFAULT_PATH)


def load(file=None):
    """The current rulebook, re-read whenever the file changes."""
    file = Path(file or path())
    try:
        stat = file.stat()
        key = (str(file), stat.st_mtime_ns, stat.st_size)
        if _cache.get('key') == key:
            return _cache['book']
        data = file.read_bytes()
    except OSError as ex:
        return {'path': str(file), 'sha256': '', 'rules': parse('', file)['rules'],
                'errors': [f'The rulebook could not be read: {ex.strerror or ex}']}
    try:
        book = parse(data.decode('utf-8-sig'), file)
    except UnicodeDecodeError:
        book = {'path': str(file), 'rules': parse('', file)['rules'], 'errors': ['The rulebook is not saved as UTF-8 text.']}
    book['sha256'] = hashlib.sha256(data).hexdigest()
    _cache.update(key=key, book=book)
    return book


def parse(text, source='rulebook'):
    """Validate rulebook text. Rules the file leaves out are listed as off."""
    errors, rules = [], []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as ex:
        data, errors = {}, [f'The rulebook is not valid TOML: {ex}']
    for key, entry in data.items():
        spec = RULES.get(key)
        if not spec:
            errors.append(f'Unknown rule [{key}]. Rule names are: {", ".join(RULES)}.')
            continue
        if not isinstance(entry, dict):
            errors.append(f'[{key}] must be a table of settings.')
            continue
        if not isinstance(entry.get('on'), bool):
            errors.append(f'[{key}] needs on = true or on = false.')
        settings = dict(spec['defaults'])
        for name, value in entry.items():
            if name in ('on', 'group', 'text'):
                if name != 'on' and not isinstance(value, str):
                    errors.append(f'[{key}] {name} must be text in quotes.')
                continue
            if name not in settings:
                allowed = ', '.join(['on', 'group', 'text', *settings])
                errors.append(f'[{key}] has no setting "{name}". Settings are: {allowed}.')
                continue
            problem = type_problem(value, settings[name], spec['choices'].get(name))
            if problem:
                errors.append(f'[{key}] {name} must be {problem}.')
                continue
            settings[name] = value
        rules.append({'key': key, 'on': entry.get('on') is True, 'group': str(entry.get('group', spec['group'])),
                      'text': str(entry.get('text', spec['text'])), 'settings': settings})
    for key, spec in RULES.items():
        if key not in data:
            rules.append({'key': key, 'on': False, 'group': spec['group'], 'text': spec['text'],
                          'settings': dict(spec['defaults']), 'missing': True})
    return {'path': str(source), 'rules': rules, 'errors': errors}


def type_problem(value, default, choices):
    if isinstance(default, bool):
        return '' if isinstance(value, bool) else 'true or false'
    if isinstance(default, int):
        return '' if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 'a whole number'
    if isinstance(default, list):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return 'a list of quoted words, like ["one", "two"]'
        if choices and any(v.upper() not in choices for v in value):
            return 'a list of ' + ', '.join(f'"{c}"' for c in choices)
    return ''


def evaluate(job, book, layout=None):
    """One result per rule that is on. A check that cannot run fires instead of passing."""
    md = job['metadata']
    results = []
    for r in book['rules']:
        if not r['on']:
            continue
        spec = RULES[r['key']]
        ctx = SimpleNamespace(md=md, job=job, layout=layout, s=r['settings'], book=book)
        if spec['needs_layout'] and layout is None:
            found = ('The PDF extraction record is missing. Process the article again.', [])
        else:
            try:
                found = spec['check'](ctx)
            except Exception as ex:
                found = (f'This check could not run ({type(ex).__name__}: {ex}).', [])
        results.append({**r, 'fired': bool(found), 'detail': found[0] if found else '',
                        'evidence': list(found[1])[:6] if found else []})
    return results


def setting(book, key, name):
    """Another rule's setting, so related checks share one word list."""
    for r in book['rules']:
        if r['key'] == key:
            return r['settings'][name]
    return RULES[key]['defaults'][name]


# Helpers ----------------------------------------------------------------

def token_key(word):
    return re.sub(r'[^a-z0-9]', '', engine.fold(word))


def words_pattern(words):
    words = [w for w in words if w.strip()]
    if not words:
        return None
    alternatives = '|'.join(re.escape(w.strip()) for w in sorted(words, key=len, reverse=True))
    return re.compile(r'(?<![^\W_])(?:' + alternatives + r')(?![^\W_])', re.I)


def heading_of(text, phrases):
    """The phrase a line is a heading for: 'Teaser', '2. Teaser' or 'Teaser: ...'."""
    t = engine.norm(re.sub(r'^\s*(?:\d+(?:\.\d+)*\.?|(?:[IVX]+|[A-Z])[.)])\s*', '', text))
    for phrase in phrases:
        p = engine.norm(phrase)
        if p and (t.rstrip(' :.—–-') == p or re.match(re.escape(p) + r'\s*[:.—–-]\s', t)):
            return phrase
    return None


def page_lines(layout, pages=0):
    for page in layout['pages']:
        if pages and page['number'] > pages:
            break
        for line in page['lines']:
            yield page, line


def ev(*lines):
    return engine.evidence(list(lines))


def author_name(a):
    return ' '.join(x for x in (a.get('given_name', ''), a.get('surname', '')) if x).strip()


def listing(items, limit=4):
    items = list(dict.fromkeys(items))
    return '; '.join(items[:limit]) + (f'; and {len(items) - limit} more' if len(items) > limit else '')


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def selected(job, role):
    return role in job.get('selected', {})


# ID and version -------------------------------------------------------------

@rule('id_missing', 'Special cases', 'The PDF is missing its arXiv ID and/or version.')
def id_missing(ctx):
    md=ctx.md
    support_derived=str(md.get('id_capture_source','')).startswith('HTML + SCRAPPING')
    pdf_id=md.get('pdf_base_id') if 'pdf_base_id' in md else '' if support_derived else md.get('base_id')
    pdf_version=md.get('pdf_version') if 'pdf_version' in md else None if support_derived else md.get('version')
    missing=[]
    if not pdf_id:missing.append('arXiv ID')
    if pdf_version is None:missing.append('version')
    if missing:
        return 'The PDF is missing its '+(' and/or '.join(missing))+'.', md.get('field_evidence',{}).get('base_id',[])[:1]


@rule('id_version_mismatch', 'Special cases',
      "The PDF's ID and/or version does not match the HTML and/or Scrapping source.",
      choices={'compare_with': tuple(SOURCES)}, compare_with=['SCRAPPING', 'HTML'])
def id_version_mismatch(ctx):
    md, s = ctx.md, ctx.md.get('source_values', {})
    support_derived=str(md.get('id_capture_source','')).startswith('HTML + SCRAPPING')
    pdf_id=md.get('pdf_base_id') if 'pdf_base_id' in md else '' if support_derived else md.get('base_id')
    pdf_version=md.get('pdf_version') if 'pdf_version' in md else None if support_derived else md.get('version')
    problems = []
    for role in dict.fromkeys(v.upper() for v in ctx.s['compare_with']):
        if not selected(ctx.job, role):
            continue  # A missing file is a safety reason of its own.
        name, other_id = SOURCES[role], s.get(role.lower() + '_id')
        if not other_id:
            problems.append(f'the {name} ID could not be read')
        elif engine.arxiv_id(other_id) != engine.arxiv_id(pdf_id):
            problems.append(f'PDF ID {pdf_id or "(none)"} but {name} ID {other_id}')
        if role == 'API':
            continue  # The API record carries no version.
        other_version = s.get(role.lower() + '_version')
        if other_version is None:
            if role == 'SCRAPPING':
                problems.append('the Scrapping version could not be read')
        elif pdf_version != other_version:
            problems.append(f'PDF version {pdf_version if pdf_version is not None else "(none)"} but {name} version {other_version}')
    if problems:
        return 'Mismatch: ' + listing(problems) + '.', md.get('field_evidence', {}).get('base_id', [])[:1]


# Title -----------------------------------------------------------------------

def title_content(text):
    return engine.compact(re.sub(r'<[^>]+>', '', text or ''))


@rule('title_mismatch', 'Title', 'The PDF title does not match the HTML title (content only; case and formatting are ignored).',
      choices={'compare_with': tuple(SOURCES)}, compare_with=['HTML'])
def title_mismatch(ctx):
    md, s = ctx.md, ctx.md.get('source_values', {})
    problems = []
    for role in dict.fromkeys(v.upper() for v in ctx.s['compare_with']):
        if not selected(ctx.job, role):
            continue
        other = s.get(role.lower() + '_title')
        if not other:
            problems.append(f'the {SOURCES[role]} title could not be read')
        elif title_content(md.get('title')) != title_content(other):
            problems.append(f'PDF "{md.get("title") or "(none)"}" but {SOURCES[role]} "{other}"')
    if problems:
        return listing(problems) + '.', md.get('field_evidence', {}).get('title', [])[:1]


# Abstract --------------------------------------------------------------------

@rule('abstract_missing', 'Abstract', 'No clear abstract can be seen in the PDF.', require_heading=False)
def abstract_missing(ctx):
    md = ctx.md
    if not (md.get('abstract') or '').strip():
        return 'No abstract was found in the PDF.', []
    if ctx.s['require_heading'] and not md.get('abstract_heading'):
        return 'The abstract has no printed heading such as "Abstract".', md.get('field_evidence', {}).get('abstract', [])[:1]


@rule('abstract_is_pitch', 'Abstract', 'An elevator pitch or teaser is not the abstract.', needs_layout=True,
      headings=['Elevator pitch', 'Teaser'], pages=2)
def abstract_is_pitch(ctx):
    md = ctx.md
    found = [(heading_of(l['text'], ctx.s['headings']), l) for _, l in page_lines(ctx.layout, ctx.s['pages'])]
    found = [(h, l) for h, l in found if h]
    if not found:
        return None
    name, line = found[0]
    if not md.get('abstract_heading'):
        return f'The PDF prints a "{name}" section and no Abstract heading, so there is no clear abstract.', ev(line)
    abstract_lines = {e.get('line_id') for e in md.get('field_evidence', {}).get('abstract', [])}
    if any(l['id'] in abstract_lines for _, l in found) or heading_of(md.get('abstract', ''), ctx.s['headings']):
        return f'The captured abstract runs into the "{name}" section.', ev(line)


# Authors ---------------------------------------------------------------------

def extra_words(book):
    keys = set()
    for name in ('honorifics', 'suffixes', 'degrees', 'alias_words'):
        keys |= {token_key(w) for w in setting(book, 'author_name_extras', name)}
    return keys


@rule('author_mismatch', 'Authors',
      'The PDF authors do not match the API authors by content (capitalization and formatting are ignored).',
      initials_match_full_names=False)
def author_mismatch(ctx):
    md, api = ctx.md, ctx.md.get('source_values', {}).get('api_authors', [])
    authors = [a for a in md.get('authors', []) if not a.get('pdf_only')]
    problems = []
    if not api:
        problems.append('the API file lists no authors to compare')
    pdf_surnames = [engine.compact(a.get('surname', '')) for a in authors]
    api_surnames = [engine.compact(b.get('surname', '')) for b in api]
    remaining = list(pdf_surnames)
    missing = []
    for b, surname in zip(api, api_surnames):
        if surname in remaining:
            remaining.remove(surname)
        else:
            missing.append(author_name(b))
    if missing:
        problems.append('not found in the PDF: ' + ', '.join(missing))
    elif len(authors) != len(api):
        problems.append(f'the PDF has {len(authors)} authors and the API has {len(api)}')
    elif pdf_surnames != api_surnames:
        problems.append('the author order differs from the API')
    else:
        ignore = extra_words(ctx.book)
        for a, b in zip(authors, api):
            printed = (a.get('pdf_name_parts') or {}).get('before', a.get('given_name', ''))
            tokens = [t for t in re.findall(r'[^\W\d_]+', printed) if token_key(t) not in ignore]
            given = b.get('given_name', '')
            if ctx.s['initials_match_full_names']:
                same = engine.compatible_given_name(given, ' '.join(tokens)) or (not tokens and not given)
            else:
                same = engine.compact(' '.join(tokens)) == engine.compact(given)
            if not same:
                problems.append(f'PDF "{" ".join(tokens)} {a.get("surname", "")}" but API "{author_name(b)}"')
    leftover = [w for w in md.get('author_line_leftover', []) if token_key(w['word']) not in extra_words(ctx.book)]
    if leftover:
        problems.append('names on the PDF author line that the API does not list: ' + ' '.join(w['word'] for w in leftover))
    if problems:
        evidence = md.get('field_evidence', {}).get('authors', [])[:1] + [e for w in leftover[:1] for e in w['evidence']]
        return listing(problems) + '.', evidence


@rule('author_affiliation_unlinked', 'Authors',
      'Authors cannot be reliably linked to affiliations using the printed indicators.',
      allow_single_author_single_affiliation=True)
def author_affiliation_unlinked(ctx):
    md = ctx.md
    authors, affiliations = md.get('authors', []), md.get('affiliations', [])
    ids = {f['id'] for f in affiliations}
    problems, evidence = [], []
    if not affiliations:
        problems.append('no affiliations were found to link the authors to')
    single = ctx.s['allow_single_author_single_affiliation'] and len(authors) == 1 and len(affiliations) == 1
    for a in authors:
        name, before = author_name(a), len(problems)
        links = a.get('affiliation_ids') or []
        if affiliations and not links:
            problems.append(f'{name} has no printed indicator matching an affiliation')
        elif any(i not in ids for i in links):
            problems.append(f'{name} is linked to an affiliation that no longer exists')
        elif a.get('link_method') == 'single_affiliation' and not single:
            problems.append(f'{name} is linked only because one unmarked affiliation is printed near the authors')
        if a.get('unmatched_markers'):
            problems.append(f'{name} has indicator {", ".join(a["unmatched_markers"])} with no matching affiliation')
        if len(problems) > before:
            evidence += a.get('evidence', [])[:1]
    if md.get('unlinked_affiliation_ids'):
        problems.append(f'{len(md["unlinked_affiliation_ids"])} affiliation(s) have no author indicator pointing to them')
    if problems:
        return listing(problems) + '.', evidence


@rule('author_name_extras', 'Authors',
      'An API or PDF author name has an alternate name or nickname (alias), suffix, degree or honorific.',
      honorifics=['Dr', 'Prof', 'Professor', 'Mr', 'Mrs', 'Ms', 'Miss', 'Sir', 'Dame', 'Rev', 'Revd'],
      suffixes=['Jr', 'Jnr', 'Sr', 'Snr', 'II', 'III', 'IV'],
      degrees=['PhD', 'DPhil', 'MD', 'MSc', 'BSc', 'MBA', 'MPhil', 'DSc', 'MPH', 'FRS', 'FRSE', 'FRCP', 'FACS', 'PharmD'],
      alias_words=['aka', 'a.k.a.', 'née', 'nee', 'also known as'])
def author_name_extras(ctx):
    md, s = ctx.md, ctx.s
    honorifics = {token_key(w) for w in s['honorifics']}
    trailing = {token_key(w): kind for kind, words in (('suffix', s['suffixes']), ('degree', s['degrees'])) for w in words}
    alias = words_pattern(s['alias_words'])
    quotes = re.compile(r'[()"“”«»]')
    name_word = r"[^\W\d_](?:[^\W\d_]|[.'’-])*"  # Stops at digits, so "PhD1" is "PhD" plus marker 1.
    words = lambda text: re.findall(name_word, text or '')
    hits, evidence = [], []

    def check(who, name, before, surname, after, extra=''):
        found = [f'honorific "{w}"' for w in words(before) if token_key(w) in honorifics]
        found += [f'{trailing[token_key(w)]} "{w}"' for w in words(surname + ' ' + extra) if token_key(w) in trailing]
        # Words after the surname count until the next author's name begins.
        for t in re.findall(name_word + r"|\d+|[^\s\w]", after or ''):
            if not t[0].isalpha() or (len(t) == 1 and t.islower()):
                continue
            if token_key(t) not in trailing:
                break
            found.append(f'{trailing[token_key(t)]} "{t}"')
        named = ' '.join((before, surname, (after or '').split(',')[0]))
        if quotes.search(named) or (alias and alias.search(named)):
            found.append('an alias or nickname')
        if found:
            hits.append(f'{who} "{name}": {", ".join(dict.fromkeys(found))}')
        return bool(found)

    for b in md.get('source_values', {}).get('api_authors', []):
        if b.get('suffix'):
            hits.append(f'API "{author_name(b)}": suffix "{b["suffix"]}"')
        else:
            check('API', author_name(b), b.get('given_name', ''), b.get('surname', ''), '')
    for a in md.get('authors', []):
        parts = a.get('pdf_name_parts') or {'before': a.get('given_name', ''), 'surname': a.get('surname', ''), 'after': ''}
        if check('PDF', author_name(a), parts['before'], parts['surname'], parts['after']):
            evidence += a.get('evidence', [])[:1]
    if hits:
        return listing(hits) + '.', evidence


# References ------------------------------------------------------------------

@rule('references_two_locations', 'References', 'References appear in two or more locations.')
def references_two_locations(ctx):
    coverage = ctx.md.get('coverage', {})
    regions = coverage.get('reference_regions')
    if regions is None:  # Articles processed before regions were counted.
        regions = 2 if any(i['rule_id'] == 'REF-014' for i in ctx.job.get('issues', [])) else 1
    if regions > 1:
        return f'References are printed in {regions} separate places in the PDF.', []


@rule('references_missing', 'References', 'There are no references in the PDF.')
def references_missing(ctx):
    if not ctx.md.get('references'):
        return 'No references were captured from the PDF.', []


@rule('references_incomplete', 'References', 'The PDF has incomplete references.', min_length=20)
def references_incomplete(ctx):
    refs, coverage = ctx.md.get('references', []), ctx.md.get('coverage', {})
    short, evidence = [], []
    for n, r in enumerate(refs, 1):
        text = (r.get('source_text') or '').strip()
        if (len(text) < ctx.s['min_length'] or re.search(r'(?:[,;:]|\.{3,}|…|\b(?:doi|arXiv):?)$', text, re.I)
                or re.search(r'_{3,}', text)):
            short.append(str(n))
            evidence += r.get('evidence', [])[:1]
    problems = []
    if short:
        problems.append('reference ' + ', '.join(short[:12]) + (' and more' if len(short) > 12 else '') + ' look incomplete')
    labels = [int(x) for x in coverage.get('numbered_labels', []) if str(x).isdigit()]
    if labels and labels != list(range(labels[0], labels[0] + len(labels))):
        problems.append('the printed reference numbers have gaps')
    inventory = coverage.get('printed_label_inventory')
    if labels and inventory is not None and len(inventory) > len(labels):
        problems.append(f'the PDF prints {len(inventory)} reference numbers but {len(labels)} entries were captured')
    if problems:
        return listing(problems) + '.', evidence


@rule('references_multiple', 'References', 'A reference entry holds multiple references.')
def references_multiple(ctx):
    found = [(n, r) for n, r in enumerate(ctx.md.get('references', []), 1) if engine.multiple_works(r.get('source_text') or '')]
    if found:
        return ('Reference ' + ', '.join(str(n) for n, _ in found[:12]) + ' may contain more than one work.',
                [e for _, r in found[:3] for e in r.get('evidence', [])[:1]])


@rule('reference_hyperlinks', 'References', 'A reference has hyperlinks.', needs_layout=True, include_printed_addresses=True)
def reference_hyperlinks(ctx):
    links = {p['number']: p.get('links', []) for p in ctx.layout['pages']}
    printed = re.compile(r'https?://|\bwww\.|\bdoi\.org/|\bdoi:\s*10\.', re.I)
    found = []
    for n, r in enumerate(ctx.md.get('references', []), 1):
        hit = next((link['uri'] for e in r.get('evidence', []) for link in links.get(e.get('page'), [])
                    if overlaps(link['bbox'], e['bbox'])), None)
        if not hit and ctx.s['include_printed_addresses']:
            m = printed.search(r.get('source_text') or '')
            hit = m and m[0]
        if hit:
            found.append((n, r, hit))
    if found:
        n, _, uri = found[0]
        return (f'{len(found)} reference(s) contain links, for example reference {n}: {uri}',
                [e for _, r, _ in found[:3] for e in r.get('evidence', [])[:1]])


# Correspondence --------------------------------------------------------------

COUNTRY_WORDS = re.compile(r'\b(?:' + '|'.join(re.escape(c) for c in sorted(engine.COUNTRIES, key=len, reverse=True)) + r')\b')


@rule('correspondence_address', 'Correspondence', 'The PDF prints a separate correspondence address.', needs_layout=True,
      phrases=['Address correspondence to', 'Correspondence address', 'Corresponding address', 'Correspondence to',
               'Corresponding author', 'Reprint requests to', 'All correspondence to', 'Contact address'],
      pages=2)
def correspondence_address(ctx):
    start = words_pattern(ctx.s['phrases'])
    if not start:
        return None
    for page, line in page_lines(ctx.layout, ctx.s['pages']):
        text = re.sub(r'^[\s\d*∗†‡✉★§¶#a-z]{0,3}(?=[A-Z])', '', line['text'])
        m = text[:1].isupper() and start.match(text)
        if not m:
            continue  # Lowercase starts are running prose, e.g. "correspondence to the Hamiltonian".
        following = [l for l in page['lines'] if 0 <= l['bbox'][1] - line['bbox'][3] < 15 and abs(l['bbox'][0] - line['bbox'][0]) < 40]
        block = engine.EMAIL_RE.sub(' ', ' '.join([text[m.end():]] + [l['text'] for l in following[:1]]))
        if engine.ORG.search(block) or engine.STREET.search(block) or COUNTRY_WORDS.search(block) or re.search(r'\b\d{4,6}\b', block):
            return f'Page {page["number"]}: "{line["text"].strip()[:120]}"', ev(line, *following[:1])


# Affiliations ----------------------------------------------------------------

@rule('affiliation_outside_front', 'Affiliations', 'Affiliations are found in the middle of the paper or in a biography.',
      needs_layout=True,
      biography_headings=['Biography', 'Biographies', 'About the author', 'About the authors', 'Author biographies',
                          'Author biography'])
def affiliation_outside_front(ctx):
    problems, evidence = [], []
    for c in ctx.md.get('affiliation_candidates', []):
        location = c.get('location', '')
        if c.get('status') == 'DISMISSED' or location in ('Page 1', 'Page 1 footer'):
            continue
        problems.append(f'{location}: {(c.get("source_text") or c.get("text") or "")[:80]}')
        evidence += c.get('evidence', [])[:1]
    for page, line in page_lines(ctx.layout):
        name = heading_of(line['text'], ctx.s['biography_headings'])
        if name:
            problems.append(f'page {page["number"]} has a "{name}" section')
            evidence += ev(line)
            break
    if problems:
        return listing(problems) + '.', evidence


def non_latin(text):
    return any(ch.isalpha() and 'LATIN' not in unicodedata.name(ch, '') for ch in text)


@rule('affiliation_non_english', 'Affiliations', 'An affiliation is not in English.', non_latin_script=True,
      words=['Universität', 'Universitat', 'Université', 'Universite', 'Universidad', 'Universidade', 'Università',
             'Universita', 'Universiteit', 'Universitet', 'Uniwersytet', 'Univerzita', 'Egyetem', 'Instituto', 'Istituto',
             'Institut', 'Dipartimento', 'Departamento', 'Département', 'Departement', 'Facultad', 'Faculdade', 'Facoltà',
             'Fakultät', 'Fakulta', 'Hochschule', 'Fachhochschule', 'École', 'Ecole', 'Laboratoire', 'Laboratorio',
             'Laboratório', 'Centro de', 'Centre de', 'Escuela', 'Escola', 'Politecnico', 'Politécnica', 'Politecnica',
             'Technische', 'Deutschland', 'España', 'Brasil', 'México', 'Italia', 'Polska', 'Nederland', 'Schweiz',
             'Suisse', 'Svizzera', 'Österreich', 'Sverige', 'Norge', 'Danmark', 'Suomi', 'Česká republika', 'Slovensko',
             'Magyarország', 'România'])
def affiliation_non_english(ctx):
    pattern = words_pattern(ctx.s['words'])
    found, evidence = [], []
    for f in ctx.md.get('affiliations', []):
        text = f.get('source_text') or ' '.join(f.get('organizations', []))
        m = pattern and pattern.search(text)
        if m or (ctx.s['non_latin_script'] and non_latin(text)):
            found.append(f'"{text[:90]}"' + (f' ({m[0]})' if m else ' (non-Latin script)'))
            evidence += f.get('evidence', [])[:1]
    if found:
        return listing(found, 3) + '.', evidence


# ORCID -----------------------------------------------------------------------

@rule('orcid', 'ORCID', 'The article has an ORCID logo, link or number.', needs_layout=True)
def orcid(ctx):
    for page in ctx.layout['pages']:
        for link in page.get('links', []):
            if 'orcid.org' in link['uri'].casefold():
                return f'Page {page["number"]} links to {link["uri"]}.', [{'page': page['number'], 'bbox': link['bbox'], 'text': link['uri']}]
    printed = re.compile(r'\borcid\b|\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b', re.I)
    for page, line in page_lines(ctx.layout):
        if printed.search(line['text']):
            return f'Page {page["number"]}: "{line["text"].strip()[:120]}"', ev(line)
    named = [author_name(a) for a in ctx.md.get('authors', []) if a.get('orcid')]
    if named:
        return 'ORCID recorded for ' + ', '.join(named) + '.', []
