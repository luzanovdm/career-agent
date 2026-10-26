"""Actual binary extraction and retention checks. No declared-text substitution."""
import io
import re
import shutil
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from .contracts import CareerError, require

CONTACT_POLICY = 'career-agent.contact-disclosure/5'
CONTACT_CODES = frozenset(('CONTACT_PREFERENCE_UNKNOWN','CONTACT_DISCLOSURE_BLOCKED','CONTACT_MISMATCH','PRIVATE_FLOOR_DISCLOSED'))


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


def calendar_period(text,start,end):
    """Calendar syntax is not a phone; an explicit telephone field takes priority."""
    from datetime import date
    value=text[start:end]
    # Format controls affect presentation, not the field identity or source offsets.
    prefix=''.join(char for char in unicodedata.normalize('NFKC',text[max(0,start-160):start]) if unicodedata.category(char)!='Cf')
    # Field qualifiers and presentation wrappers cannot turn a disclosed phone
    # into a calendar period. Allow decorations only, not intervening prose.
    label=r'(?:\b(?:phone(?:\s+number)?|telephone|tel|mobile(?:\s+number)?|fax|contact|телефон(?:а)?|тел|мобильный|контакт)\.?|☎|📞)'
    pairs={'(':')','[':']','{':'}'}
    quotes={'"':'"',"'":"'",'“':'”','‘':'’','«':'»'}
    decorations=set(':：#()[]{}"\'“”‘’«»*_`')
    def field_tail(value):
        # Every token consumes original prefix characters; the whole input is bounded
        # above. Multiple/nested qualifiers compose without admitting bare prose.
        cursor=0
        while cursor<len(value):
            char=value[cursor]
            if char in pairs:
                stack=[pairs[char]];end=cursor+1
                while end<len(value) and stack:
                    item=value[end]
                    if item in pairs:stack.append(pairs[item])
                    elif item in pairs.values():
                        if item!=stack[-1]:break
                        stack.pop()
                    end+=1
                if not stack:cursor=end;continue
            elif char in quotes:
                end=value.find(quotes[char],cursor+1)
                if end>=0:cursor=end+1;continue
            if char.isspace() or char.isdigit() or char in decorations:cursor+=1;continue
            return False
        return True
    if any(field_tail(prefix[match.end():]) for match in re.finditer(label,prefix,re.IGNORECASE)):return False
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        try:date.fromisoformat(value);return True
        except ValueError:return False
    years=re.fullmatch(r'(\d{4}) *- *(\d{4})',value)
    return bool(years and 1900<=int(years[1])<=int(years[2])<=2099)


def phone_occurrences(documents):
    """Per-slot offsets avoid cross-document matches and never emit private numbers."""
    result=[]
    for document in documents:
        if document['slot'] not in ('resume','message','answers'):continue
        for match in re.finditer(r'(?<!\w)\+?\d[\d ()-]{6,}\d(?!\w)',document['text']):
            if not calendar_period(document['text'],match.start(),match.end()):
                result.append(dict(slot=document['slot'],start=match.start(),end=match.end(),offset_unit='unicode_code_points'))
    return result


def contact_checks(documents,answers):
    from .contracts import issue
    external='\n'.join(d['text'] for d in documents if d['slot'] in ('resume','message','answers'))
    issues=[]
    phones=phone_occurrences(documents)
    if phones and not any(a['meaning']=='contact.phone.preference' and a['disposition']!='pending' for a in answers):
        issues.extend(dict(issue('CONTACT_PREFERENCE_UNKNOWN','External phone has no current explicit application choice'),**phone) for phone in phones)
    for answer in answers:
        value=answer['value']
        if isinstance(value,str):
            import json
            value=json.loads(value)
        if answer['meaning']=='contact.phone.preference':
            disposition=value.get('disposition') if isinstance(value,dict) else answer['disposition']
            selected=value.get('value') if isinstance(value,dict) else value
            if disposition in ('omit','unknown','pending') and phones:
                issues.extend(dict(issue('CONTACT_DISCLOSURE_BLOCKED','Phone appears despite omitted or unresolved current application choice',answer['id']),**phone) for phone in phones)
            if disposition=='use':
                expected=re.sub(r'\D','',str(selected))
                for phone in phones:
                    body=next(d['text'] for d in documents if d['slot']==phone['slot'])
                    if re.sub(r'\D','',body[phone['start']:phone['end']])!=expected:issues.append(dict(issue('CONTACT_MISMATCH','External phone differs from current explicit choice',answer['id']),**phone))
        if answer['meaning']=='compensation.floor' and answer['disposition']=='answered' and str(value) in external:
            issues.append(issue('PRIVATE_FLOOR_DISCLOSED','Private compensation floor appears in external material',answer['id']))
    return issues
