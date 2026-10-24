"""Actual binary extraction and retention checks. No declared-text substitution."""
import io
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from .contracts import CareerError, require


def extract_docx(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries=archive.infolist()
        require(len(entries)<=2000 and sum(e.file_size for e in entries)<=32*1024*1024,'LIMIT_EXCEEDED','DOCX expanded content too large')
        names=[n for n in archive.namelist() if n.startswith('word/') and n.endswith('.xml')]
        require('word/document.xml' in names,'EXTRACTION_FAILED','DOCX has no document body')
        # Include headers, footers, comments, notes, text boxes and hidden/tracked text:
        # these bytes are disclosed in the attachment even when not in the visual body.
        strings=[]
        for name in sorted(names):
            root=ET.fromstring(archive.read(name))
            strings.extend(node.text or '' for node in root.iter() if node.tag.endswith('}t') or node.tag.endswith('}delText') or node.tag.endswith('}instrText'))
        return '\n'.join(strings),'DOCX XML including header/footer/notes/hidden text'


def extract_binary(path,extension):
    if extension=='docx':return extract_docx(path.read_bytes())
    if extension=='pdf':
        executable=shutil.which('pdftotext')
        require(executable,'EXTRACTION_UNAVAILABLE','Actual PDF extraction requires supported host Poppler; no fake receipt is accepted')
        result=subprocess.run([executable,'-enc','UTF-8',str(path),'-'],capture_output=True,timeout=30)
        require(result.returncode==0,'EXTRACTION_FAILED','Actual PDF bytes could not be extracted')
        return result.stdout.decode('utf-8'),'Host Poppler pdftotext; visual/annotation review remains separate'
    raise CareerError('UNSUPPORTED_BINARY','Only actual DOCX/PDF conversions can attach')


def tokens(text):
    text=unicodedata.normalize('NFKC',text).replace('\u00ad','')
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 \2',text)
    return re.findall(r'\w+(?:[.,]\w+)*|[%$€£+@]',text.casefold())


def check_conversion(source,extracted):
    require(tokens(source)==tokens(extracted),'BINARY_TEXT_MISMATCH','Actual binary text differs from selected content, including extra headers or removed contact fields')


def contact_checks(documents,answers):
    from .contracts import issue
    external='\n'.join(d['text'] for d in documents if d['slot'] in ('resume','message','answers'))
    issues=[]
    phones=re.findall(r'(?<!\w)\+?\d[\d ()-]{6,}\d(?!\w)',external)
    phones=[p for p in phones if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',p)]
    if phones and not any(a['meaning']=='contact.phone.preference' and a['disposition']!='pending' for a in answers):
        issues.append(issue('CONTACT_PREFERENCE_UNKNOWN','External phone has no current explicit application choice'))
    for answer in answers:
        value=answer['value']
        if isinstance(value,str):
            import json
            value=json.loads(value)
        if answer['meaning']=='contact.phone.preference':
            disposition=value.get('disposition') if isinstance(value,dict) else answer['disposition']
            selected=value.get('value') if isinstance(value,dict) else value
            if disposition in ('omit','unknown','pending') and phones:
                issues.append(issue('CONTACT_DISCLOSURE_BLOCKED','Phone appears despite omitted or unresolved current application choice',answer['id']))
            if disposition=='use':
                expected=re.sub(r'\D','',str(selected))
                for phone in phones:
                    if re.sub(r'\D','',phone)!=expected:issues.append(issue('CONTACT_MISMATCH','External phone differs from current explicit choice',answer['id']))
        if answer['meaning']=='compensation.floor' and answer['disposition']=='answered' and str(value) in external:
            issues.append(issue('PRIVATE_FLOOR_DISCLOSED','Private compensation floor appears in external material',answer['id']))
    return issues
