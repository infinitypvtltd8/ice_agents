"""Match article metadata to its source documents and keep every article in General.

The rulebook and safety checks remain visible as review results; they no longer
route files to a separate Irregular queue.
"""
import engine
import rulebook

# Rules whose card can edit the field they check.
PATHS={'id_missing':'base_id','id_version_mismatch':'base_id','title_mismatch':'title','abstract_missing':'abstract','abstract_is_pitch':'abstract'}

def original_values(md):
    return {
        'base_id':md.get('base_id'),'version':md.get('version'),'title':md.get('title'),
        'title_markup':md.get('title_markup'),'abstract':md.get('abstract'),'abstract_markup':md.get('abstract_markup'),
        'authors':engine.digest([{k:a.get(k) for k in ('given_name','surname','initials','degree','source_text','email','corresponding','affiliation_ids')} for a in md.get('authors',[])]),
        'author_groups':engine.digest(md.get('author_groups')),
        'affiliations':engine.digest([{k:a.get(k) for k in ('marker','organizations','address_parts','city','state','postal_code','country_code','source_text')} for a in md.get('affiliations',[])]),
        'references':engine.digest([{k:r.get(k) for k in ('source_text','full_text','full_text_markup')} for r in md.get('references',[])])
    }

def safety_reasons(job,book):
    """Collect review notes about inputs, XML, manual edits and rulebook state.

    These notes never place a job on hold or block XML generation or export.
    """
    reasons=[role+' file is missing.' for role in ('PDF','SCRAPPING','API','HTML') if role not in job.get('selected',{})]
    reasons+=[i['message'] for i in job.get('extraction_issues',[]) if i['rule_id']=='PKG-002' and i['message'].startswith('Cannot read')]
    if not job.get('validation',{}).get('profile_valid',False):reasons.append('Generated XML has validation errors.')
    if job.get('manual_xml') or job.get('xml_stale'):reasons.append('Manual XML needs source reconciliation.')
    reasons+=['Rulebook error: '+e for e in book['errors']]
    return reasons

def support(key,s):
    if key=='title_mismatch':return [('HTML',s.get('html_title')),('API',s.get('api_title'))]
    if key=='id_version_mismatch':
        return [('Scrapping',f"{s.get('scrapping_id') or 'Missing'} · version {s.get('scrapping_version') or 'missing'}"),
                ('HTML',f"{s.get('html_id') or 'Missing'} · version {s.get('html_version') or 'not shown'}")]
    return []

def assess(job,layout=None,book=None):
    if job.get('status')!='READY':
        status=job.get('status','PROCESSING')
        return {'queue':'REGULAR','automatic_queue':'REGULAR','queue_override':None,
                'reasons':['Matching and XML generation are pending: '+str(job.get('progress') or status)],'checks':[],
                'matched':0,'total':0}
    book=book or rulebook.load()
    md=job['metadata'];s=md.get('source_values',{})
    reasons=safety_reasons(job,book);checks=[]
    for r in rulebook.evaluate(job,book,layout):
        path=PATHS.get(r['key']);message=r['detail'] or 'Nothing found.'
        checks.append({'name':r['key'],'rule':r['key'],'group':r['group'],'label':r['text'],'path':path,
                       'value':md.get(path,'') if path else message,'status':'REVIEW' if r['fired'] else 'VERIFIED','message':message,
                       'support':[{'source':source,'value':value} for source,value in support(r['key'],s)],'evidence':r['evidence']})
        if r['fired']:reasons.append(r['text']+' '+r['detail'])
    reasons=list(dict.fromkeys(reasons))
    return {'queue':'REGULAR','automatic_queue':'REGULAR','queue_override':None,'reasons':reasons,
            'checks':checks,'matched':sum(c['status']=='VERIFIED' for c in checks),'total':len(checks),
            'rulebook':{'path':book['path'],'sha256':book.get('sha256',''),'errors':book['errors']}}
