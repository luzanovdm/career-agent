"""Check actual synthetic PDF/DOCX extraction, without any candidate data or parser scores."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_resume_render as qa


def pdf(path, lines):
    # A real text PDF, generated with the standard library for extraction regression tests.
    stream = 'BT /F1 11 Tf 40 750 Td ' + ' '.join(('0 -16 Td ' if i else '') + '(' + line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ') Tj' for i, line in enumerate(lines)) + ' ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               ('<< /Length '+str(len(stream.encode()))+' >>\nstream\n'+stream+'\nendstream').encode()]
    raw = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1): offsets.append(len(raw)); raw += str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    start = len(raw); raw += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(('%010d 00000 n \n'%n).encode() for n in offsets[1:])
    raw += ('trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start)+'\n%%EOF\n').encode(); path.write_bytes(raw)


class RenderTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('pdftotext'), 'Optional host PDF extractor unavailable')
    def test_actual_pdf_preserves_numbers_contacts_and_order_and_detects_export_losses(self):
        lines = ['Alex Rivers', 'alex@example.com https://portfolio.example/', 'EXPERIENCE',
                 'Northstar Labs - Engineer - Jan 2022 to May 2025',
                 'Team savings USD 48000; personal contribution retry handling.',
                 'Reduced latency from 840 ms to 210 ms.', 'SKILLS', 'Python SQL']
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'reviewed.txt'; target=Path(d)/'export.pdf'; source.write_text('\n'.join(lines))
            pdf(target,lines); result=qa.check(source,target); self.assertTrue(result['extraction_check_passed'])
            pdf(target,[l.replace('48000','').replace('840 ms to 210 ms','210 ms to 840 ms') for l in lines])
            result=qa.check(source,target); self.assertFalse(result['extraction_check_passed']); self.assertIn('48000',result['missing_tokens']); self.assertFalse(result['reading_order_retained'])

    def test_docx_body_and_header_warning_empty_and_columns(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'reviewed.txt'; target=Path(d)/'export.docx';source.write_text('Alex Rivers\nEXPERIENCE\nBuilt retry handling')
            with zipfile.ZipFile(target,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="'+qa.W[1:-1]+'"><w:body><w:p><w:r><w:t>EXPERIENCE</w:t></w:r></w:p><w:p><w:r><w:t>Built retry handling</w:t></w:r></w:p><w:sectPr><w:cols w:num="2"/></w:sectPr></w:body></w:document>')
                z.writestr('word/header1.xml','<w:hdr xmlns:w="'+qa.W[1:-1]+'"><w:p><w:r><w:t>Alex Rivers</w:t></w:r></w:p></w:hdr>')
            r=qa.check(source,target);self.assertFalse(r['extraction_check_passed']);self.assertEqual(len(r['review_notes']),2)
            self.assertFalse(qa.compare('Alex Rivers','')['extraction_check_passed'])

    def test_docx_tabs_and_breaks_separate_titles_dates_and_units(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'resume.docx'
            with zipfile.ZipFile(target,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="'+qa.W[1:-1]+'"><w:body><w:p><w:r><w:t>Engineer</w:t><w:tab/><w:t>Jan 2022</w:t><w:br/><w:t>Latency 840 ms</w:t></w:r></w:p></w:body></w:document>')
            text,_=qa.extract(target)
            self.assertTrue(qa.compare('Engineer Jan 2022 Latency 840 ms',text)['extraction_check_passed'])

    def test_unicode_minus_loss_fails_actual_docx_cli(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'reviewed.txt'; target=Path(d)/'export.docx';source.write_text('Change \u221212%')
            with zipfile.ZipFile(target,'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="'+qa.W[1:-1]+'"><w:body><w:p><w:r><w:t>Change 12%</w:t></w:r></w:p></w:body></w:document>')
            run=subprocess.run([sys.executable,'-B',qa.__file__,str(source),str(target)],capture_output=True,text=True)
            self.assertEqual(run.returncode,3);self.assertIn('"extraction_check_passed": false',run.stdout)
            self.assertTrue(qa.compare('Change \u221212%','Change -12%')['extraction_check_passed'])

    def test_metric_units_qualitative_strength_and_link_text_cannot_silently_disappear(self):
        for old,new in [('Latency 840 ms','Latency 840'),('Built retry handling','Built handling'),('Email alex@example.com','Email'),('https://portfolio.example/','portfolio.example/'),('Change -12%','Change 12%')]:
            self.assertFalse(qa.compare(old,new)['extraction_check_passed'])
        self.assertTrue(qa.compare('# EXPERIENCE\n\nLatency 840 ms','EXPERIENCE\nLatency\n840 ms')['extraction_check_passed'])


if __name__ == '__main__': unittest.main()
