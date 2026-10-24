"""Offline import SQL owner, excluded from all installed runtime archives."""
import json
from career.repository import Repository
from career.contracts import canonical,digest,require

def import_legacy_records(repository,state,objects,artifact_by_path):
    """Maintenance-only SQL boundary. No legacy reader exists in normal operations."""
    mappings={};quarantine=[];normalized=[];archived=[];retained_rows={};db=repository.connect()
    def map_id(kind,old):
        key=kind+':'+str(old)
        mappings.setdefault(key,kind+'_'+digest(key)[:24]);return mappings[key]
    def retain(group,row):
        return db.execute('INSERT INTO record_history(kind,record_id,version,body,revision) VALUES (?,?,?,?,0)',('legacy:'+group,str(row.get('id','unidentified')),1,canonical(row))).lastrowid
    try:
        db.execute('BEGIN IMMEDIATE')
        require(db.execute('SELECT revision FROM workspace').fetchone()[0]==0,'DESTINATION_CHANGED','Import destination is no longer empty')
        for obj in objects:db.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?,?,?)',tuple(obj[k] for k in ('id','sha256','extension','size','media_type')))
        for group,value in state.items():
            rows=value if isinstance(value,list) else [dict(id=group,value=value)]
            for index,row in enumerate(rows):
                if not isinstance(row,dict):row=dict(id='value-'+digest(row)[:16],value=row)
                retained_rows[(group,index)]=retain(group,row)
        for row in state.get('sources',[]):
            rid=map_id('source',row['id']);observations=row.get('observations',[])
            excerpt='\n'.join(o['evidence'] for o in observations if isinstance(o.get('evidence'),str) and o['evidence'].strip())
            at=next((o.get('at') for o in observations if o.get('at')),'unknown')
            db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?)',(rid,1,str(row.get('locator','Legacy source')),excerpt,at,int(bool(excerpt)),canonical(dict(legacy=row))))
        for row in state.get('facts',[]):
            rid=map_id('claim',row['id']);statement=row.get('statement','')
            confirmation='confirmed' if row.get('status')=='confirmed' and row.get('confirmation') else 'unconfirmed'
            disclosure=row.get('disclosure','unknown');disclosure=disclosure if disclosure in ('allowed','private','unknown','withdrawn') else 'unknown'
            db.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?)',(rid,1,statement,statement,confirmation,disclosure,int(bool(row.get('contradiction_ids'))),canonical(dict(kind='achievement',legacy=row))))
            for source_id in row.get('source_ids',[]):
                if 'source:'+str(source_id) in mappings:db.execute('INSERT INTO claim_sources VALUES (?,?)',(rid,map_id('source',source_id)))
        # Move original assertions and structured meanings into the current claim bank.
        # This retains supplied statuses; it never approves a new tailored packet.
        for row in state.get('achievement_evidence',[]):
            claim_id=mappings.get('claim:'+str(row.get('fact_id')));source_id=mappings.get('source:'+str(row.get('source_id')))
            if not claim_id or not source_id or not isinstance(row.get('original_text'),str) or not row['original_text'].strip():
                quarantine.append(dict(group='achievement_evidence',id=row.get('id'),reason='ACHIEVEMENT_REFERENCE_MISSING',retained=True));continue
            claim=db.execute('SELECT assertion,detail FROM claims WHERE id=?',(claim_id,)).fetchone();detail=json.loads(claim['detail'])
            detail.update(original_text=row['original_text'],numeric_anchors=row.get('numeric_anchors',[]),metrics=row.get('metrics',[]),source_evidence_id=row['id'])
            db.execute('UPDATE claims SET assertion=?,detail=? WHERE id=?',(row['original_text'],canonical(detail),claim_id))
            db.execute('INSERT OR IGNORE INTO claim_sources VALUES (?,?)',(claim_id,source_id));mappings['achievement:'+str(row['id'])]=claim_id
            normalized.append(dict(group='achievement_evidence',id=row['id'],target_kind='claim',target_id=claim_id,status='mapped_original_assertion_and_metrics'))
        for row in state.get('achievement_interpretations',[]):
            claim_id=mappings.get('achievement:'+str(row.get('achievement_id')))
            fields=row.get('fields',{})
            if not claim_id or not isinstance(fields,dict) or any(not isinstance(value,dict) or value.get('status') not in ('supported','unknown','hypothesis','confidential') or any('claim:'+str(fid) not in mappings for fid in value.get('fact_ids',[])) for value in fields.values()):
                quarantine.append(dict(group='achievement_interpretations',id=row.get('id'),reason='INTERPRETATION_REFERENCE_UNRESOLVED',retained=True));continue
            detail=json.loads(db.execute('SELECT detail FROM claims WHERE id=?',(claim_id,)).fetchone()['detail'])
            transformed={name:dict(value,fact_ids=[mappings['claim:'+str(fid)] for fid in value.get('fact_ids',[])]) for name,value in fields.items()}
            previous=detail.get('interpretation')
            if not previous or row.get('version',0)>=previous.get('version',0):detail['interpretation']=dict(version=row.get('version',1),at=row.get('at'),fields=transformed,source_id=row['id'])
            db.execute('UPDATE claims SET detail=? WHERE id=?',(canonical(detail),claim_id))
            normalized.append(dict(group='achievement_interpretations',id=row['id'],target_kind='claim',target_id=claim_id,status='mapped_structured_meaning_without_new_confirmation'))
        for row in state.get('companies',[]):
            rid=map_id('company',row['id'])
            db.execute('INSERT INTO companies VALUES (?,?,?,?,?)',(rid,1,row.get('name','Legacy company'),None,canonical(dict(legacy=row))))
        default_track=map_id('track','legacy-review')
        db.execute('INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)',(default_track,1,'Imported track awaiting scope review','Legacy choices retained in import report; no inferred policies.',0,'unknown','{}','{}'))
        for row in state.get('opportunities',[]):
            rid=map_id('case',row['id']);company_id=mappings.get('company:'+str(row.get('company_id')))
            if not company_id:
                quarantine.append(dict(group='opportunities',id=row['id'],reason='COMPANY_REFERENCE_MISSING'));continue
            opportunity=map_id('opportunity',row['id']);kind=row.get('kind','speculative');kind=kind if kind in ('vacancy','project','speculative') else 'speculative'
            # Preserve old identity verbatim in retained record. Do not deduplicate ambiguous old keys.
            db.execute('INSERT INTO opportunities VALUES (?,?,?,?,?,?)',(opportunity,company_id,kind,row.get('title','Imported opportunity'),str(row['identity']) if row.get('identity') else None,row.get('role_url') if str(row.get('role_url','')).startswith(('http://','https://')) else None))
            source_ids=[mappings['source:'+str(s)] for s in row.get('source_ids',[]) if 'source:'+str(s) in mappings]
            db.execute('INSERT INTO cases(id,version,company_id,opportunity_id,title,kind,route,detail) VALUES (?,?,?,?,?,?,?,?)',(rid,1,company_id,opportunity,row.get('title','Imported opportunity'),kind,'unknown',canonical(dict(source_ids=source_ids,legacy=row))))
            db.execute('INSERT INTO case_tracks VALUES (?,?,?)',(rid,default_track,'Imported association requires explicit track review'))
        # Preserve supplied track labels without inventing scope-specific policies.
        for index,label in enumerate(state.get('profile',{}).get('selected_directions',[])):
            if not isinstance(label,str):
                quarantine.append(dict(group='profile.selected_directions',id=str(index),reason='TRACK_SHAPE_UNKNOWN',retained=True));continue
            track_id=map_id('track',str(index)+':'+label)
            db.execute('INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)',(track_id,1,label,label,1,'unknown','{}',canonical(dict(legacy_label=label))))
        material_rows={}
        for row in state.get('materials',[]):
            artifact=artifact_by_path.get(row.get('path',''))
            if not artifact or artifact['sha256']!=row.get('sha256'):
                quarantine.append(dict(group='materials',id=row.get('id'),reason='MATERIAL_PIN_UNRESOLVED',retained=True));continue
            mappings['material:'+str(row['id'])]=artifact['id'];material_rows[row['id']]=(row,artifact)
        for row in state.get('answers',[]):
            # Legal consent remains an exact permission observation, never an ordinary reusable answer.
            if not row.get('confirmed') or not row.get('confirmation_evidence'):
                quarantine.append(dict(group='answers',id=row.get('id'),reason='ANSWER_CONFIRMATION_UNKNOWN',retained=True));continue
            if row.get('is_consent'):
                rid=map_id('permission',row['id'])
                db.execute('INSERT INTO permissions VALUES (?,?,?,?,?,?,?)',(rid,row['meaning'],canonical(dict(row['scope'],legacy=True)),
                    'active',row['confirmation_evidence'],row.get('valid_until'),1))
                continue
            rid=map_id('answer',row['id']);disposition=row.get('disposition','answered')
            if disposition not in ('answered','unknown','confidential','declined','no_preference','omit'):disposition='unknown'
            db.execute('INSERT INTO answers VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,1,row['meaning'],canonical(row.get('scope',{})),canonical(row.get('units',{})),
                disposition,canonical(row.get('value')),row['confirmation_evidence'],row.get('valid_from'),row.get('valid_until')))
        packet_pins={}
        for row in state.get('application_attempts',[]):
            case_id=mappings.get('case:'+str(row.get('opportunity_id')))
            if not case_id:
                quarantine.append(dict(group='application_attempts',id=row.get('id'),reason='CASE_REFERENCE_MISSING',retained=True));continue
            pinned=[];failed=False
            for slot in row.get('materials',[]):
                pair=material_rows.get(slot.get('material_id'))
                if not pair or pair[1]['sha256']!=slot.get('sha256') or pair[0].get('version')!=slot.get('version'):
                    quarantine.append(dict(group='application_attempts',id=row.get('id'),slot=slot.get('slot'),reason='HISTORICAL_PIN_UNRESOLVED',retained=True));failed=True;continue
                name={'cover-letter':'message','cover':'message','form-answers':'answers','private-dossier':'dossier','interview-prep':'interview'}.get(slot['slot'],slot['slot'])
                if name not in ('resume','message','dossier','answers','interview','notes'):
                    quarantine.append(dict(group='application_attempts',id=row.get('id'),slot=name,reason='SLOT_REUSE_REVIEW_REQUIRED',retained=True))
                pinned.append((name,pair[1]['id']))
            if not pinned:
                quarantine.append(dict(group='application_attempts',id=row.get('id'),reason='NO_READABLE_HISTORICAL_PINS',retained=True));continue
            packet_id=map_id('packet',row['id']);version_id=map_id('version',row['id'])
            db.execute('INSERT INTO packets VALUES (?,?,?,?,?,NULL)',(packet_id,1,case_id,None,'application'))
            db.execute('INSERT INTO packet_versions VALUES (?,?,?,?,?,?,NULL)',(version_id,packet_id,1,row.get('at','unknown'),'[]','[]'))
            for name,artifact in pinned:db.execute('INSERT INTO slots VALUES (?,?,?)',(version_id,name,artifact))
            db.execute('UPDATE packets SET selected_version_id=? WHERE id=?',(version_id,packet_id))
            packet_pins[row['id']]=(packet_id,version_id)
        # Select only an explicit legacy current-attempt pointer; never latest/order/filename.
        selections={}
        for row in state.get('search_cases',[]):
            case_id=mappings.get('case:'+str(row.get('opportunity_id')));pin=packet_pins.get(row.get('attempt_id'))
            if case_id and pin:selections.setdefault(case_id,set()).add(pin[0])
            elif row.get('attempt_id'):quarantine.append(dict(group='search_cases',id=row.get('id'),reason='SELECTED_ATTEMPT_UNRESOLVED',retained=True))
        for case_id,choices in selections.items():
            if len(choices)==1:db.execute('INSERT INTO case_selections VALUES (?,?)',(case_id,next(iter(choices))))
            else:quarantine.append(dict(group='search_cases',id=case_id,reason='SELECTION_AMBIGUOUS',retained=True))
        attempts={row['id']:row for row in state.get('attempts',[])}
        for row in state.get('attempts',[]):
            case_id=mappings.get('case:'+str(row.get('opportunity_id')))
            if not case_id:
                quarantine.append(dict(group='attempts',id=row.get('id'),reason='CASE_REFERENCE_MISSING',retained=True));continue
            rid=map_id('activity',row['id']);pin=packet_pins.get(row.get('application_attempt_id'))
            if not pin and row.get('outcome') in ('sent','uncertain'):quarantine.append(dict(group='attempts',id=row['id'],reason='HISTORICAL_SELECTION_UNKNOWN',retained=True))
            resolution=row.get('resolves_attempt_id');old=attempts.get(resolution,{})
            occurred=row.get('occurred_at') or old.get('occurred_at') or old.get('at') or row.get('at','unknown')
            db.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,case_id,row.get('outcome','uncertain'),occurred,row.get('recorded_at') or row.get('at','unknown'),
                row.get('evidence','Historical observation; original retained.'),pin[0] if pin else None,pin[1] if pin else None,None,canonical(dict(legacy=row))))
        for row in state.get('attempts',[]):
            if row.get('resolves_attempt_id') and 'activity:'+str(row['id']) in mappings and 'activity:'+str(row['resolves_attempt_id']) in mappings:
                db.execute('UPDATE activities SET resolves_activity_id=? WHERE id=?',(mappings['activity:'+str(row['resolves_attempt_id'])],mappings['activity:'+str(row['id'])]))
        response_kinds={'auto_receipt':'receipt','human_reply':'human_reply','interview':'interview','offer':'offer','rejection':'rejection','bounce':'bounce','withdrawal':'withdrawal','rejected_before_application':'rejection_before_application'}
        for row in state.get('responses',[]):
            case_id=mappings.get('case:'+str(row.get('opportunity_id')))
            if not case_id or row.get('type') not in response_kinds:
                quarantine.append(dict(group='responses',id=row.get('id'),reason='RESPONSE_MAPPING_UNKNOWN',retained=True));continue
            db.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',(map_id('activity',row['id']),case_id,response_kinds[row['type']],row.get('at','unknown'),row.get('recorded_at') or row.get('at','unknown'),row.get('evidence','Original observation retained.'),None,None,None,canonical(dict(legacy=row,attempt_id=row.get('attempt_id')))))
        for row in state.get('coverage',[]):
            case_id=mappings.get('case:'+str(row.get('opportunity_id')))
            if not case_id:
                quarantine.append(dict(group='coverage',id=row.get('id'),reason='CASE_REFERENCE_MISSING',retained=True));continue
            db.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',(map_id('activity',row['id']),case_id,'coverage',row.get('through','unknown'),row.get('checked_at','unknown'),
                'Imported coverage observation; original channels, status and cutoffs retained.',None,None,None,canonical(dict(coverage=row))))
        profile=state.get('profile',{})
        if isinstance(profile,dict) and isinstance(profile.get('name'),str) and 0<len(profile['name'])<=200:db.execute('UPDATE workspace SET display_name=?',(profile['name'],))
        handled={'achievement_evidence','achievement_interpretations','sources','facts','companies','opportunities','schema_version','revision','materials','application_attempts','attempts','responses','coverage','answers','search_cases'}
        for group,value in state.items():
            if group in handled:continue
            if group=='change_history':
                for index,row in enumerate(value):
                    retained=db.execute('SELECT id,body FROM record_history WHERE id=?',(retained_rows[(group,index)],)).fetchone()
                    expected=row if isinstance(row,dict) else dict(id='value-'+digest(row)[:16],value=row)
                    require(retained and retained['body']==canonical(expected),'IMPORT_HISTORY_MISMATCH','Retained audit history differs from original')
                    archived.append(dict(group=group,id=row.get('id') if isinstance(row,dict) else None,record_history_id=retained['id'],sha256=digest(canonical(row).encode()),status='read_only_audit_history'))
                continue
            if isinstance(value,list):
                for row in value:
                    quarantine.append(dict(group=group,id=row.get('id') if isinstance(row,dict) else None,reason='HISTORICAL_SCOPE_UNRESOLVED' if group=='history_imports' else 'CURRENT_PACKET_MAPPING_REQUIRED' if group in ('packet_rebuilds','priority_preparation_batches','private_drafts','private_correspondence') else 'FORM_RESPONSE_MAPPING_REQUIRED' if group=='forms' else 'SEMANTIC_MAPPING_REQUIRED',retained=True))
            elif value not in (None,{},[],False,0,''):
                quarantine.append(dict(group=group,id=group,reason='SCOPED_DECISION_MAPPING_REQUIRED',retained=True))
        db.execute('UPDATE workspace SET revision=1')
        db.execute('INSERT INTO change_log VALUES (1,1,?,?,?)',(canonical(['import']),canonical(list(mappings.values())),canonical(['context','cases','contacts','selection'])))
        db.commit()
        return dict(mappings=mappings,quarantined_records=quarantine,normalized_records=normalized,archived_records=archived,revision=1)
    finally:db.rollback();db.close()


class ImportRepository(Repository):
    @classmethod
    def assert_runtime(cls,root):
        from pathlib import Path
        root=Path(root)
        require(not (root/'.career-agent/active.json').exists(),'IMPORT_DESTINATION_ACTIVE','Offline importer requires an unactivated isolated destination')

    import_legacy_records=import_legacy_records
