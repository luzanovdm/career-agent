#!/usr/bin/env python3
"""Fixed local portal template with paged JSON, file-safe loading and honest packet readiness."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

import career_state as cs
import career_materials as cm
import career_search as search

TEMPLATE_FILES = ('index.html', 'style.css', 'app.js')
CHUNK = 100
LABELS = {'resume': 'Resume', 'cover-letter': 'Cover letter', 'dossier': 'Private dossier', 'form-answers': 'Form answers'}


def data_file(root, key, value):
    cs.require(key == 'manifest' or re.fullmatch(r'index-\d+|(?:detail|document|interview)-[a-f0-9]{64}', key), 'Invalid portal data key')
    raw = json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    (root / 'data' / (key + '.json')).write_text(raw + '\n', encoding='utf-8')
    # Local file fetch is restricted in common browsers; this fixed wrapper contains JSON data only.
    (root / 'data' / (key + '.js')).write_text('window.CareerPortalData.accept(' + json.dumps(key) + ',' + raw + ');\n', encoding='utf-8')


def mark_incomplete(destination):
    """Invalidate only this newly created export; preserve diagnostics and canonical data."""
    root = Path(destination)
    if (root / 'OPEN.html').exists(): (root / 'OPEN.html').rename(root / 'INCOMPLETE.html')
    for name in ('manifest.js', 'manifest.json'):
        path = root / 'data' / name
        if path.exists(): path.rename(path.with_suffix(path.suffix + '.incomplete'))
    diagnostic = root / 'snapshot.json'
    if diagnostic.exists():
        row = json.loads(diagnostic.read_text());row.update(completed=False, valid=False, error='Export did not finish consistently; regenerate from current state')
        diagnostic.write_text(json.dumps(row, indent=2) + '\n')


def write_portal(destination, metadata, records):
    """Stream fixed-size index pages; full packet bodies are separate lazy data resources."""
    destination = Path(destination)
    cs.require(not destination.exists() and not destination.is_symlink(), 'Portal destination must be absent; preserve existing and edited reports')
    try:
        from career_portal_assets import ASSETS
        assets = ASSETS
    except ModuleNotFoundError as error:
        if error.name != 'career_portal_assets': raise
        templates = Path(__file__).resolve().parents[1] / 'templates' / 'portal'
        cs.require(all((templates / name).is_file() and not (templates / name).is_symlink() for name in TEMPLATE_FILES), 'Bundled portal template is unavailable')
        assets = {name: (templates / name).read_text(encoding='utf-8') for name in TEMPLATE_FILES}
    cs.require(set(assets) == set(TEMPLATE_FILES) and all(isinstance(v, str) for v in assets.values()), 'Invalid fixed template assets')
    destination.mkdir(parents=True, mode=0o700)
    for folder in ('assets', 'data', 'documents'): (destination / folder).mkdir(mode=0o700)
    (destination / 'OPEN.html').write_text(assets['index.html'], encoding='utf-8')
    for name in ('style.css', 'app.js'): (destination / 'assets' / name).write_text(assets[name], encoding='utf-8')
    chunk, count, ready, recent, seen, documents = [], 0, 0, [], set(), set()
    try:
        for detail in records:
            detail = {**detail, 'documents': [dict(d) for d in detail['documents']]}
            identifier = detail['id']
            cs.require(re.fullmatch(r'[a-f0-9]{64}', identifier) and identifier not in seen, 'Portal cases require distinct stable exact-opportunity IDs')
            seen.add(identifier)
            row = {key: detail.get(key, '') for key in ('id', 'company', 'role', 'focus', 'person', 'packet_status')}
            chunk.append(row)
            if len(recent) < 10: recent.append(row)
            for document in detail['documents']:
                digest = document['sha256']
                cs.require(re.fullmatch(r'[a-f0-9]{64}', digest) and document['slot'] in LABELS, 'Invalid selected packet material')
                raw = document.pop('_bytes')
                cs.require(hashlib.sha256(raw).hexdigest() == digest, 'Selected artifact bytes changed')
                suffix = Path(document['path']).suffix
                cs.require(suffix in {'.md', '.pdf', '.docx'}, 'Unsupported selected download type')
                document['path'] = 'documents/' + digest + suffix
                if digest not in documents:
                    (destination / document['path']).write_bytes(raw)
                    data_file(destination, 'document-' + digest, {'text': raw.decode('utf-8') if suffix == '.md' else 'Binary approved version: use the original download. No new binary was generated.'})
                    documents.add(digest)
            interview = detail.pop('_interview', {'items': [], 'status': 'Preparation materials are not yet saved'})
            data_file(destination, 'interview-' + identifier, interview)
            detail['interview_key'] = 'interview-' + identifier
            data_file(destination, 'detail-' + identifier, detail)
            count += 1
            ready += detail['packet_status'] in {'ready', 'ready_with_pay_uncertainty'}
            if len(chunk) == CHUNK:
                data_file(destination, 'index-' + str((count - 1) // CHUNK), chunk); chunk = []
        if chunk: data_file(destination, 'index-' + str((count - 1) // CHUNK), chunk)
        manifest = {**metadata, 'format': 1, 'template_version': 1, 'count': count, 'ready': ready, 'incomplete': count-ready,
                    'chunk_size': CHUNK, 'chunks': (count+CHUNK-1)//CHUNK, 'recent': recent}
        data_file(destination, 'manifest', manifest)
        (destination / 'snapshot.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return {'written': True, 'path': str(destination / 'OPEN.html'), 'cases': count, 'ready': ready,
                'max_index_rows': CHUNK, 'browser_page_rows': 50, 'template_version': 1}
    except Exception:
        # A partial export is not a usable/current view; preserve evidence rather than publish OPEN.html.
        mark_incomplete(destination)
        raise


def export_portal(state_path, workspace, batch_id, destination=None):
    root = cs.private_path(workspace).resolve()
    cs.require(root in Path(state_path).resolve().parents, 'State must belong to the selected private workspace')
    state_path = cs.private_path(state_path)
    source_bytes = state_path.read_bytes()
    state = cs.validate(cs.strict_json_loads(source_bytes))
    fingerprint = hashlib.sha256(source_bytes).hexdigest()
    def require_current():
        cs.require(state_path.read_bytes() == source_bytes, 'State changed during portal export; regenerate from the current revision')
    report = search.case_report(state_path, root, batch_id, 1)
    require_current()
    identity_path = cm.inside(root, 'Data/portal-identity.json')
    if identity_path.exists():
        identity = cs.load_json(identity_path)
        cs.require(set(identity) == {'version', 'id'} and identity['version'] == 1 and re.fullmatch(r'[a-f0-9]{32}', identity['id']), 'Invalid portal identity; preserve it for review')
    else:
        identity = {'version': 1, 'id': uuid.uuid4().hex}
        cm.write_new_or_same(identity_path, (json.dumps(identity) + '\n').encode(), mode=0o600)
    relative = destination or ('Reports/Portal-r' + str(state['revision']) + '-' + fingerprint[:12])
    target = cm.inside(root, relative)
    companies = {x['id']: x for x in state['companies']}; roles = {x['id']: x for x in state['opportunities']}
    materials = {x['id']: x for x in state['materials']}; attempts = {x['id']: x for x in state['application_attempts']}
    forms = {x['id']: x for x in state['forms']}; sources = {x['id']: x for x in state['sources']}
    assessed = {x['id']: x for x in report['cases']}
    preparation = {}
    for row in state["interview_prep"]: preparation.setdefault(row["opportunity_id"], []).append(row)
    contacts = {}
    for row in state['referrals']:
        if row['affiliation'] == 'verified_current': contacts.setdefault(row['opportunity_id'], []).append(row)
    def records():
        require_current()
        for case in state.get('search_cases', []):
            if case['batch_id'] != batch_id: continue
            role = roles[case['opportunity_id']]; check = assessed[case['id']]
            status = check['status'] if report['view_current'] else 'incomplete: spreadsheet snapshot not current'
            detail = {'id': hashlib.sha256(case['id'].encode()).hexdigest(), 'opportunity_id': role['id'],
                'company': companies[role['company_id']]['name'], 'role': role['title'], 'kind': role['kind'], 'focus': cs.fit_display(role),
                'person': '', 'fit': cs.fit_display(role), 'packet_status': status,
                'concerns': [*check.get('blockers', []), *check.get('unknowns', []), *([check['error']] if check.get('error') else [])],
                'links': [{'label': 'Posting / observed route', 'url': role['role_url']}], 'sources': [{'label': 'Source', 'url': sources[i]['locator']} for i in role['source_ids'] if sources[i]['kind'] == 'web'],
                'source_date': case['at'], 'documents': [], 'fields': [], 'form_status': 'Not observed'}
            dialogue = []
            for row in preparation.get(role['id'], []):
                if 'interview_prep_ids' in case and row['id'] not in case['interview_prep_ids']: continue
                dialogue.append({'id': row['id'], 'question': row['question'], 'answer': row['outline'],
                    'classification': row['question_status'], 'fact_ids': row['fact_ids'], 'source_ids': row['source_ids'],
                    'terms': row.get('concept_links', []), 'unknowns': row.get('unknowns', []),
                    'pressure_points': row['pressure_points'], 'employer_questions': row['employer_questions'],
                    'review_required': row.get('review_required', False)})
            detail['interview_status'] = 'Saved preparation; not an interactive mock interview' if dialogue else 'Preparation materials are not yet saved'
            detail['interview_key'] = 'interview-' + detail['id']
            detail['_interview'] = {'items': dialogue, 'status': detail['interview_status']}
            people = contacts.get(role['id'], [])
            if people:
                detail['person'] = people[0]['public_name']
                for person in people:
                    detail['links'].extend({'label': person['public_name'] + ' · source checked ' + person['verified_at'], 'url': sources[i]['locator']} for i in person['source_ids'] if sources[i]['kind'] == 'web')
            if role.get('contact_route'): detail['links'].append({'label': 'Observed application/contact route', 'url': role['contact_route']['url']})
            form = forms[case['form_id']]; detail['form_status'] = form['status'] + ': consent pending never authorizes submission'
            detail['fields'] = [{'label': f['label'], 'required': f['required'], 'answer': f.get('answer') if f.get('answer_state') == 'confirmed' and not f.get('is_consent') else 'Unresolved / fresh choice required'} for f in form['fields']]
            for pin in attempts.get(case['attempt_id'], {}).get('materials', []):
                material = materials[pin['material_id']]
                cs.require(pin['sha256'] == material['sha256'], 'Attempt/material version mismatch')
                path = cm.material_file(root, material)
                detail['documents'].append({'slot': pin['slot'], 'label': LABELS[pin['slot']], 'path': path.name,
                                             'sha256': material['sha256'], 'language': material['language'], '_bytes': path.read_bytes()})
            yield detail
        require_current()
    result = write_portal(target, {'campaign_id': identity['id'], 'title': 'Career applications', 'revision': state['revision'],
                                'state_sha256': fingerprint, 'generated_at': cs.utcnow(), 'batch_id': batch_id,
                                'shortfall': report['shortfall'], 'completed': report['completed']}, records())
    try:
        require_current()
    except cs.Invalid:
        mark_incomplete(target)
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state'); parser.add_argument('workspace'); parser.add_argument('batch_id'); parser.add_argument('--destination')
    args = parser.parse_args()
    try:
        print(json.dumps(export_portal(args.state, args.workspace, args.batch_id, args.destination), indent=2)); return 0
    except (cs.Invalid, OSError, ValueError, KeyError) as error:
        print('Error: ' + str(error), file=sys.stderr); return 2


if __name__ == '__main__': sys.exit(cs.run_cli(main))
