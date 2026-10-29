"""Local package recognition. Match document evidence and retain import reasons."""
from pathlib import Path
import re
import zipfile
import engine
from lxml import etree

ROLES = ('PDF', 'API', 'SCRAPPING', 'HTML')

def classify(name, data):
    suffix = Path(name).suffix.casefold()
    head = data[:1024].lstrip(b'\xef\xbb\xbf\x00\t\r\n ')
    if b'%PDF-' in data[:1024]:
        return 'PDF'
    if suffix == '.pdf':
        return 'PDF'
    if suffix in ('.html', '.htm', '.xhtml') or head.lower().startswith((b'<!doctype html', b'<html')):
        return 'HTML'
    if suffix == '.xml' or head.startswith(b'<?xml'):
        try:
            role = engine.xml_source_role(engine.secure_xml(data))
        except Exception:
            # Keep the filename role so the parse error is reported when the
            # article is processed, instead of the package waiting for a choice.
            role = 'XML'
        if role != 'XML':
            return role
        stem = Path(name).stem.casefold()
        if re.search(r'(?:^|[_. -])(?:scrap(?:p?ing|ed)?)(?:$|[_. -])', stem):
            return 'SCRAPPING'
        if re.search(r'(?:^|[_. -])api(?:$|[_. -])', stem):
            return 'API'
        return 'XML'
    return 'OTHER'

def content_id(data, role):
    """Inspect identity fields, never search the reference list for an article ID."""
    texts = []
    try:
        if role == 'PDF':
            with engine.fitz.open(stream=data, filetype='pdf') as doc:
                text = doc[0].get_text() if len(doc) else ''
                texts = re.findall(r'arxiv\s*:\s*(\d{4}\.\d{4,5}(?:v\d+)?)', text, re.I)
        elif role == 'HTML':
            root = engine.html.fromstring(data)
            texts = root.xpath('//meta[@name="citation_arxiv_id"]/@content | //meta[@name="citation_pdf_url"]/@content | //link[@rel="canonical"]/@href')
        elif role in ('API', 'SCRAPPING', 'XML'):
            root = engine.secure_xml(data)
            texts = root.xpath('//*[local-name()="id" or local-name()="identifier"]/text() | //*[local-name()="item"]/@id')
        ids = {m[1] for text in texts for m in engine.ID_RE.finditer(text)}
        return next(iter(ids)) if len(ids) == 1 else ''
    except Exception:
        return ''

def filename_id(path, batch):
    parts = path.relative_to(batch).parts
    for name in reversed(parts):
        m = engine.ID_RE.search(name)
        if m:
            return m[1]
    return ''

def stem_key(path):
    stem = re.sub(r'\s*\(\d+\)$', '', path.stem.casefold())
    stem = re.sub(r'(?:[_. -]+)(?:api|scrapping|scraping|scraped|metadata|html|pdf)$', '', stem)
    return re.sub(r'[^\w]', '', stem)

def package_name(path, batch):
    """The outer ZIP is the batch boundary; folder imports keep their folder."""
    parts=path.relative_to(batch).parts
    for i,part in enumerate(parts[:-1]):
        if part.casefold().endswith('.zip.ice-unpacked'):
            return '/'.join((*parts[:i],part[:-len('.ice-unpacked')]))
    return parts[0] if len(parts)>1 else 'Loose files'

def unpack_all(batch):
    """Case-insensitive, recursive ZIP expansion with cumulative safety limits."""
    seen = set()
    count = size = 0
    while True:
        archives = sorted(p for p in batch.rglob('*') if p.is_file() and p.suffix.casefold() == '.zip' and p not in seen)
        if not archives:
            return
        for archive in archives:
            seen.add(archive)
            if len(seen) > 100:
                raise ValueError('Too many nested ZIP files. Split the import into smaller batches.')
            # Unique directory prevents collisions with sibling upload folders.
            dest = archive.parent / (archive.name + '.ice-unpacked')
            dest.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive) as z:
                for member in z.infolist():
                    if member.is_dir():
                        continue
                    name = member.filename.replace('\\', '/')
                    target = (dest / name).resolve()
                    if not target.is_relative_to(dest.resolve()) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Unsafe ZIP path or symbolic link rejected.')
                    if any(part.startswith('.') or part == '__MACOSX' for part in Path(name).parts):
                        continue
                    count += 1
                    size += member.file_size
                    if count > 2500 or size > 512 * 1024 * 1024:
                        raise ValueError('ZIP batch exceeds 2,500 files or 512 MB expanded. Use smaller batches.')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(member))

def inventory(batch):
    unpack_all(batch)
    entries = []
    for path in sorted(batch.rglob('*')):
        if not path.is_file() or path.suffix.casefold() == '.zip':
            continue
        rel = path.relative_to(batch)
        if any(part.startswith('.') or part == '__MACOSX' for part in rel.parts):
            continue
        data = path.read_bytes()
        role = classify(path.name, data)
        key = filename_id(path, batch) or content_id(data, role)
        entries.append({'path': path, 'name': str(rel), 'package': package_name(path,batch), 'role': role, 'key': key, 'reason': '', 'sha256': engine.digest(data)})
    pdfs = [e for e in entries if e['role'] == 'PDF']
    for e in pdfs:
        if not e['key']:
            e['key'] = 'manual-' + re.sub(r'[^a-zA-Z0-9_-]', '_', e['path'].stem)[:35] + '-' + engine.digest(e['name'])[:8]
    for e in entries:
        if e['role'] == 'OTHER':
            e['reason'] = 'Not a supported source document (PDF, HTML or support XML).'
            continue
        if not e['key']:
            # Use the nearest folder with PDFs. Never guess between articles.
            parent = e['path'].parent
            while parent.is_relative_to(batch):
                candidates = [p for p in pdfs if p['package']==e['package'] and p['path'].is_relative_to(parent)]
                keys = {p['key'] for p in candidates}
                if len(keys) > 1:
                    keys = {p['key'] for p in candidates if stem_key(e['path']) == stem_key(p['path'])}
                if len(keys) == 1:
                    e['key'] = next(iter(keys))
                    break
                if candidates or parent == batch:
                    break
                parent = parent.parent
        if not e['key'] or not any(p['package']==e['package'] and p['key'] == e['key'] for p in pdfs):
            e['reason'] = 'No matching PDF. Import together with its PDF in an article folder, or use matching article IDs in filenames.'
    return entries
