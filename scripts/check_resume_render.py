#!/usr/bin/env python3
"""Read-only text-retention check for a reviewed resume and its PDF/DOCX export.

This is local extraction evidence, never an ATS score or a claim about an employer parser.
PDF inspection requires the host's optional pdftotext executable; DOCX uses the standard library.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

LIMIT = 8 * 1024 * 1024
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def docx_text(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n == 'word/document.xml' or re.fullmatch(r'word/(?:header|footer)\d+\.xml', n)]
        if sum(archive.getinfo(n).file_size for n in names) > LIMIT:
            raise ValueError('Document XML exceeds the inspection limit')
        roots = {n: ET.fromstring(archive.read(n)) for n in names}
    if 'word/document.xml' not in roots:
        raise ValueError('DOCX has no main document')
    root = roots['word/document.xml']
    text = '\n'.join(''.join((n.text or '') if n.tag == W + 't' else (' ' if n.tag in {W + 'tab', W + 'br', W + 'cr'} else '') for n in p.iter()) for p in root.iter(W + 'p'))
    risks = []
    if list(root.iter(W + 'tbl')): risks.append('Tables need visual and reading-order review')
    if list(root.iter(W + 'txbxContent')): risks.append('Text boxes need reading-order review')
    if any(int(c.get(W + 'num', '1')) > 1 for c in root.iter(W + 'cols')): risks.append('Multiple columns need reading-order review')
    if any(''.join(t.text or '' for t in r.iter(W + 't')).strip() for n, r in roots.items() if n != 'word/document.xml'):
        risks.append('Header/footer text is excluded from body comparison; check that no contact or career facts live there')
    return text, risks


def extract(path):
    if path.stat().st_size > LIMIT: raise ValueError('File exceeds the local inspection limit; this is not an ATS limit')
    if path.suffix.lower() == '.docx': return docx_text(path)
    if path.suffix.lower() == '.pdf':
        binary = shutil.which('pdftotext')
        if not binary: raise ValueError('PDF extraction unavailable: pdftotext is not installed; inspect with another supported host tool')
        run = subprocess.run([binary, '-enc', 'UTF-8', str(path.resolve()), '-'], capture_output=True, timeout=30, check=True)
        return run.stdout.decode('utf-8'), ['PDF layout and actual link targets require separate visual/annotation inspection']
    if path.suffix.lower() in {'.txt', '.md'}: return path.read_text(encoding='utf-8'), []
    raise ValueError('Use reviewed TXT/Markdown/DOCX and a PDF/DOCX export')


def tokens(text):
    # Normalize visual wrapping/ligatures, without deleting numerical values or units.
    text = unicodedata.normalize('NFKC', text).replace('\u00ad', '').replace('\u2212', '-')
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: m[1] if m[1] == m[2] else m[1] + ' ' + m[2], text)
    return re.findall(r'(?<!\w)[+-]?\d+(?:[.,]\d+)*(?!\w)|\w+(?:[.,]\w+)*|[$€£%]', text.casefold())


def compare(reviewed, extracted):
    expected, actual = tokens(reviewed), tokens(extracted)
    if not expected: raise ValueError('Reviewed source has no readable text')
    missing = Counter(expected) - Counter(actual)
    cursor = 0
    ordered = True
    for token in expected:
        try: cursor = actual.index(token, cursor) + 1
        except ValueError: ordered = False; break
    return {'text_retained': not missing, 'reading_order_retained': ordered,
            'missing_tokens': dict(missing), 'readable': bool(actual),
            'extraction_check_passed': bool(actual) and not missing and ordered,
            'scope': 'Local text retention/order only; not semantic approval, ATS compatibility certification or employer acceptance'}


def check(reviewed, rendered):
    reviewed, rendered = Path(reviewed), Path(rendered)
    if rendered.suffix.lower() not in {'.pdf', '.docx'}: raise ValueError('Rendered file must be PDF or DOCX')
    source, _ = extract(reviewed); text, risks = extract(rendered)
    result = compare(source, text)
    result.update(reviewed_sha256=hashlib.sha256(reviewed.read_bytes()).hexdigest(),
                  rendered_sha256=hashlib.sha256(rendered.read_bytes()).hexdigest(),
                  extraction_tool='pdftotext' if rendered.suffix.lower() == '.pdf' else 'DOCX main-body XML',
                  review_notes=risks)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reviewed'); parser.add_argument('rendered'); args = parser.parse_args()
    try:
        result = check(args.reviewed, args.rendered); print(json.dumps(result, indent=2))
        return 0 if result['extraction_check_passed'] else 3
    except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print('Error: ' + str(error), file=sys.stderr); return 2


if __name__ == '__main__': sys.exit(main())
