"""Rebuild the transparent synthetic General-queue example (development only)."""
from pathlib import Path
import io
import zipfile
import fitz

HERE=Path(__file__).resolve().parent
ID='2609.12345'
TITLE='Deterministic citation example'
ABSTRACT='A straightforward article used to check deterministic citation extraction.'

def build():
    doc=fitz.open();page=doc.new_page(width=612,height=792)
    for y,text,size in [
        (45,'arXiv:2609.12345v1',9),(80,TITLE,17),(112,'Jane Doe1',11),
        (145,'1 University of Sample, City, United States',10),
        (190,'Abstract',11),(210,ABSTRACT,10),
        (300,'Introduction',11),(320,'This example contains three references.',10),
        (500,'References',12),
        (525,'[1] Doe J. First sample work. Journal 2021.',10),
        (550,'[2] Doe J. Second sample work. Journal 2022.',10),
        (575,'[3] Doe J. Third sample work. Journal 2023.',10),
    ]:page.insert_text((55,y),text,fontsize=size)
    pdf=doc.tobytes();doc.close()
    api=f'<record><id>{ID}</id><title>{TITLE}</title><author><forenames>Jane</forenames><keyname>Doe</keyname></author></record>'.encode()
    scraping=f'<catalog><item id="{ID}"><version number="1"/></item></catalog>'.encode()
    html=f'<html><head><meta name="citation_title" content="{TITLE}"><meta name="citation_arxiv_id" content="{ID}"></head><body><span class="arxivid">arXiv:{ID}v1</span></body></html>'.encode()
    with zipfile.ZipFile(HERE/'regular_demo.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name,data in [(ID+'.pdf',pdf),(ID+'_Api.xml',api),(ID+'_Scrapping.xml',scraping),(ID+'.html',html)]:
            z.writestr('synthetic_regular_example/'+name,data)

if __name__=='__main__':build()
