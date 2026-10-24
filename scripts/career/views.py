"""Derived views consume canonical repository projections; no domain-state writes."""
import csv
import html
import io
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape
from .contracts import CareerError, canonical, digest
from .repository import contained, new_id


def xlsx(sheets):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        names=list(sheets)
        archive.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join('<Override PartName="/xl/worksheets/sheet'+str(i)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(names)+1))+'</Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join('<sheet name="'+escape(name)+'" sheetId="'+str(i)+'" r:id="rId'+str(i)+'"/>' for i,name in enumerate(names,1))+'</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join('<Relationship Id="rId'+str(i)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+str(i)+'.xml"/>' for i in range(1,len(names)+1))+'</Relationships>')
        for i,(name,rows) in enumerate(sheets.items(),1):
            xml='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><sheetData>'
            for row_number,row in enumerate(rows,1):
                xml+='<row r="'+str(row_number)+'">'+''.join('<c t="inlineStr"><is><t xml:space="preserve">'+escape(str(value if value is not None else ''))+'</t></is></c>' for value in row)+'</row>'
            xml+='</sheetData></worksheet>';archive.writestr('xl/worksheets/sheet'+str(i)+'.xml',xml)
    return output.getvalue()


def render(repository,format):
    with repository.open() as snapshot:
        data=snapshot.export_data()
        revision=snapshot.revision
        destination=contained(repository.root,'Views/r'+str(revision)+'-'+new_id('view'))
        destination.mkdir(mode=0o700)
        if format=='profile':
            profile=data['profile'];body='# '+profile['display_name']+'\n\n'+'\n\n'.join('## '+t['name']+'\n\n'+t['positioning'] for t in data['tracks'])+'\n'
            (destination/'Profile.md').write_text(body)
        elif format=='snapshot':
            rows=''.join('<tr><td>'+html.escape(str(row[0]))+'</td><td>'+html.escape(str(row[1]))+'</td><td>'+html.escape(str(row[2]))+'</td><td>'+html.escape(str(row[3]))+'</td></tr>' for row in data['sheets']['Cases'][1:])
            (destination/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Career snapshot</title><h1>Read-only career snapshot</h1><p>Revision '+str(revision)+'. No live synchronization or sending.</p><table><thead><tr><th>Case</th><th>Company</th><th>Title</th><th>Next work</th></tr></thead><tbody>'+rows+'</tbody></table></html>')
        elif format=='xlsx':
            (destination/'Career.xlsx').write_bytes(xlsx(data['sheets']))
        else:
            for name,rows in data['sheets'].items():
                stream=io.StringIO();writer=csv.writer(stream)
                safe_rows=[["'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value for value in row] for row in rows]
                writer.writerows(safe_rows)
                (destination/(name+'.csv')).write_text(stream.getvalue())
        manifest=dict(workspace_id=snapshot.workspace_id,revision=revision,format=format,
                      files={p.name:digest(p.read_bytes()) for p in destination.iterdir() if p.is_file()},selection=data['selections'])
        (destination/'manifest.json').write_text(canonical(manifest))
        result=snapshot.envelope(outcome='satisfied',view_current=True,destination=str(destination),files=list(manifest['files']),external_actions={'performed':0})
    repository.record_view_export(format,revision,str(destination),digest(canonical(manifest).encode()))
    with repository.open() as current:
        result['view_current']=current.revision==revision
        if not result['view_current']:result['outcome']='partial';result['issues']=[dict(code='VIEW_STALE',message='State advanced after rendering; saved view retained')]
    return result
