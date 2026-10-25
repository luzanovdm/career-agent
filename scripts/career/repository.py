"""Only owner of SQL, snapshots, atomic mutations, backups and object paths."""
from contextlib import contextmanager
from datetime import datetime, timezone
import base64
import json
import errno
import shutil
import os
from pathlib import Path
import re
import sqlite3
import uuid
from .contracts import FORMAT, CareerError, canonical, digest, require


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def new_id(prefix):
    return prefix + '_' + uuid.uuid4().hex


def contained(root, relative):
    root = Path(root).absolute()
    relative = Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts, 'UNSAFE_PATH', 'Relative contained path required')
    current = root
    require(not root.is_symlink(), 'UNSAFE_PATH', 'Workspace cannot be a symlink')
    for part in relative.parts:
        current = current / part
        require(not current.is_symlink(), 'UNSAFE_PATH', 'Symlink component is not supported')
    require(current.resolve().is_relative_to(root.resolve()), 'UNSAFE_PATH', 'Path escapes workspace')
    return current


class Snapshot:
    def __init__(self, repository, connection):
        self.repository, self._db = repository, connection
        self.root = repository.root
        self._verified_objects={};self._object_rows={};self.material_status={};self.integrity_changed=False
        self._entity_rows={};self._entity_bytes=0
        row = self.one('SELECT * FROM workspace')
        require(row and row['format'] == FORMAT, 'UNSUPPORTED_FORMAT', 'Explicit import is required')
        self.workspace_id, self.revision = row['id'], row['revision']

    def one(self, sql, args=()):
        row = self._db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def rows(self, sql, args=()):
        return [dict(row) for row in self._db.execute(sql, args)]

    def get(self, kind, record_id):
        require(kind in TABLES, 'INVALID_INPUT', 'Unknown record kind')
        key=(kind,record_id)
        cached=self._entity_rows.get(key)
        if cached:return dict(cached[0])
        row = self.one('SELECT * FROM ' + TABLES[kind] + ' WHERE id=?', (record_id,))
        require(row, 'NOT_FOUND', kind + ' not found', 404)
        # Snapshot-local raw metadata only. All canonical writes precede projection reads.
        # Copies prevent callers from mutating cached rows; no permission decision is cached.
        if kind in ('company','source','claim','track'):
            weight=sum(4*len(value) if isinstance(value,str) else 32 for value in row.values())
            if weight<=8*1024*1024:
                while self._entity_rows and (len(self._entity_rows)>=512 or self._entity_bytes+weight>8*1024*1024):
                    first=next(iter(self._entity_rows));_,size=self._entity_rows.pop(first);self._entity_bytes-=size
                self._entity_rows[key]=(dict(row),weight);self._entity_bytes+=weight
        return row

    def envelope(self, **payload):
        return dict(workspace_id=self.workspace_id, revision=self.revision, **payload)

    def object(self,artifact_id):
        if artifact_id in self._verified_objects:
            value=self._verified_objects[artifact_id]
            if isinstance(value,CareerError):raise value
            return value
        row=self._object_rows.get(artifact_id) or self.get('object',artifact_id)
        self._object_rows[artifact_id]=row
        path=contained(self.root,'Objects/'+row['sha256']+'.'+row['extension'])
        valid=False
        if path.is_file() and path.stat().st_size==row['size']:
            import hashlib
            actual=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):actual.update(chunk)
            valid=actual.hexdigest()==row['sha256']
        self.material_status[artifact_id]=valid
        if not valid:
            error=CareerError('MATERIAL_CHANGED','Immutable selected object is missing or changed',issues=[dict(code='MATERIAL_CHANGED',message='Restore exact saved bytes or prepare a new version; historical pins are retained',record_id=artifact_id)])
            self._verified_objects[artifact_id]=error;raise error
        self._verified_objects[artifact_id]=(row,path);return row,path

    def verify_projection_materials(self,items):
        versions=[row['selected_version_id'] for row in items if row.get('selected_version_id')]
        if not versions:return
        for row in self.rows('SELECT DISTINCT o.* FROM objects o JOIN slots s ON s.artifact_id=o.id WHERE s.version_id IN(SELECT value FROM json_each(?))',(canonical(versions),)):
            self._object_rows[row['id']]=row
            try:self.object(row['id'])
            except CareerError as error:
                if error.code!='MATERIAL_CHANGED':raise

    def changes(self, after):
        require(type(after) is int and after >= 0, 'INVALID_INPUT', 'Invalid change cursor')
        first = self.one('SELECT MIN(cursor) AS n FROM change_log')['n']
        gap = after > self.revision or (first is not None and after < first - 1)
        rows = self.rows('SELECT * FROM change_log WHERE cursor>? ORDER BY cursor LIMIT 1000', (after,))
        gap=gap or (bool(rows) and rows[-1]['cursor']<self.revision)
        signal=self.one('SELECT sha256,path FROM view_exports WHERE kind="integrity_signal"')
        known_fault=bool(self.one('SELECT 1 FROM view_exports WHERE kind LIKE "material_status:%" LIMIT 1'))
        refresh=known_fault or bool(signal and json.loads(signal['path']).get('refresh_until','')>now())
        return self.envelope(changes=[dict(cursor=r['cursor'], revision=r['revision'],
                             kinds=json.loads(r['kinds']), ids=json.loads(r['ids']),
                             projection_keys=json.loads(r['projection_keys'])) for r in rows],resync_required=gap or refresh,replay_gap=gap,integrity_token=signal['sha256'] if signal else None)

    def export_data(self):
        cases=self.rows('SELECT * FROM cases ORDER BY id')
        summaries=[self.case_summary(case) for case in cases]
        people=[self.contact(row['id']) for row in self.rows('SELECT id FROM persons ORDER BY id')]
        tracks=[dict(row,policies=json.loads(row['policies']),selected=bool(row['selected'])) for row in self.rows('SELECT id,version,name,positioning,language,policies,selected FROM tracks ORDER BY id')]
        selections=[]
        for row in summaries:
            if row['selected_version_id']:
                projection=self.selection(row['selected_packet_id'])
                selections.append(dict(packet_id=projection['packet_id'],version_id=projection['version_id'],
                         artifacts=[dict(id=s['artifact_id'],sha256=s['sha256'],slot=s['name']) for s in projection['slots']]))
        sheets={
            'Contacts':[['Person ID','Name','Company ID','Qualified','Affiliation','Route','Issues']]+[[p['id'],p['name'],p['company_id'],p['qualified'],p['affiliation'],p['route']['value'] if p['route'] else '',canonical(p['issues'])] for p in people],
            'Cases':[['Case ID','Company','Title','Next work','Selected packet','Selected version','Blockers']]+[[r['id'],r['company'],r['title'],r['column'],r['selected_packet_id'],r['selected_version_id'],canonical(r['blockers'])] for r in summaries],
            'Tracks':[['Track ID','Name','Positioning','Language','Policy']]+[[t['id'],t['name'],t['positioning'],t['language'],canonical(t['policies'])] for t in tracks],
            'Metadata':[['Workspace ID','Revision','Format'],[self.workspace_id,self.revision,FORMAT]]}
        return dict(profile=self.context()['profile'],tracks=tracks,sheets=sheets,selections=selections)

    def applicable_answers(self, case_id):
        if not hasattr(self,'_contact_answers'):
            self._contact_answers=self.rows('SELECT * FROM answers WHERE meaning LIKE "contact.%" OR meaning="compensation.floor"')
        if not self._contact_answers:return []
        case=self.get('case',case_id)
        tracks={r['track_id'] for r in self.rows('SELECT track_id FROM case_tracks WHERE case_id=?',(case_id,))}
        matches=[]
        for answer in self._contact_answers:
            scope=json.loads(answer['scope'])
            from .policy import answer_scope_matches
            if not answer_scope_matches(scope,tracks,case):continue
            if answer['valid_from'] and answer['valid_from']>now():continue
            if answer['valid_until'] and answer['valid_until']<=now():continue
            matches.append(answer)
        return matches

    def preferences(self):
        row=self.one('SELECT * FROM app_preferences')
        return dict(theme=row['theme'],ui_locale=row.get('ui_locale','en'),introduction_shown=bool(row.get('introduction_shown',0)))

    def builtin_catalog(self,locale):
        from .localization import validate_catalog
        active=contained(self.root,'.career-agent/active.json')
        if active.exists():
            locator=json.loads(active.read_text());base=contained(self.root,locator['release_dir'])/'ui/locales'
        else:
            base=Path(__file__).resolve().parents[2]/'ui/public/locales'
            if not base.exists():base=Path(__file__).resolve().parents[2]/'ui/locales'
        path=contained(base,locale+'.json')
        require(path.is_file(),'CATALOG_UNAVAILABLE','Builtin catalog unavailable')
        return validate_catalog(json.loads(path.read_text()))

    def localization(self,locale=None):
        from .localization import validate_catalog,locale_tag
        locale=locale_tag(locale or self.preferences()['ui_locale'])
        english=self.builtin_catalog('en');catalog=english;issues=[]
        if locale in ('en','ru'):
            catalog=validate_catalog(self.builtin_catalog(locale),english)
        else:
            row=self.one('SELECT artifact_id FROM locale_catalogs WHERE locale=?',(locale,))
            if row:
                _,path=self.object(row['artifact_id']);custom=validate_catalog(json.loads(path.read_text()))
                # An update may add UI keys. Preserve validated custom strings and use
                # English for new keys without rewriting the user's immutable catalog.
                shared={key:value for key,value in custom['messages'].items() if key in english['messages']}
                if shared:validate_catalog(dict(custom,messages=shared),dict(english,messages={key:english['messages'][key] for key in shared}))
                fallback={key:value if isinstance(value,str) else {category:value.get(category,value['other']) for category in custom['plural_categories']} for key,value in english['messages'].items()}
                missing=sorted(set(fallback)-set(shared))
                catalog=validate_catalog(dict(custom,messages=dict(fallback,**shared)),english)
                if missing:issues=[dict(code='LOCALE_FALLBACK',message='New interface keys use English until the workspace catalog is updated',missing_keys=missing)]
            else:
                issues=[dict(code='LOCALE_FALLBACK',message='Requested catalog unavailable; English fallback is active')]
        return self.envelope(locale=locale,fallback_locale='en',catalog=catalog['messages'],plural_categories=catalog['plural_categories'],issues=issues)

    def agent_intent(self,intent,case_id=None,track_id=None,packet_id=None,version_id=None):
        require(intent in ('agent.research','agent.prepare','agent.review'),'INVALID_INTENT','Unknown agent intent')
        cases=[];packets=[];versions=[];tracks=[]
        if case_id:
            case=self.get('case',case_id);cases=[case_id]
            tracks=[r['track_id'] for r in self.rows('SELECT track_id FROM case_tracks WHERE case_id=?',(case_id,))]
            packet=self.one('SELECT p.* FROM packets p JOIN case_selections s ON s.packet_id=p.id WHERE s.case_id=?',(case_id,))
            if packet:
                packets=[packet['id']]
                if packet['selected_version_id']:versions=[packet['selected_version_id']]
        else:tracks=[r['id'] for r in self.rows('SELECT id FROM tracks WHERE selected=1 LIMIT 100')]
        if packet_id:
            packet=self.get('packet',packet_id)
            require(case_id==packet['case_id'],'SCOPE_CONFLICT','Packet does not belong to requested case',409)
            packets=[packet_id];versions=[packet['selected_version_id']] if packet['selected_version_id'] else []
        if track_id:
            track=self.get('track',track_id)
            require(track['selected'],'SCOPE_NOT_ACTIVE','Requested research track is not selected',409)
            require(not case_id or track_id in tracks,'SCOPE_CONFLICT','Track does not belong to this case',409)
            tracks=[track_id]
        descriptor=dict(workspace_id=self.workspace_id,revision=self.revision,intent=intent,
            scope=dict(case_ids=cases,packet_ids=packets,version_ids=versions,track_ids=tracks),status='not_executed')
        if packet_id:descriptor['selection_mode']='packet'
        if version_id:
            require(packet_id and intent=='agent.review','INVALID_INTENT','Historical materials support explicit read/review only')
            version=self.get('version',version_id);require(version['packet_id']==packet_id,'SCOPE_CONFLICT','Version belongs to another packet',409)
            descriptor['scope']['version_ids']=[version_id];descriptor['selection_mode']='version'
        descriptor['id']='intent_'+digest(descriptor)[:32]
        prompt='Use the installed Career Agent workspace already associated with workspace ID '+self.workspace_id+'. Resolve this bounded intent with the installed CLI before working: '+canonical(descriptor)+'. '+{
            'agent.research':'Find useful evidenced people/opportunities within the selected tracks. Reuse actual existing scoped research permission; copying this prompt did not grant permission. Ask only if a material scope/start choice is missing.',
            'agent.prepare':'Prepare or revise the exact selected case packet from supported evidence, including fact/tone review and saved immutable documents. Do not send or accept agreements.',
            'agent.review':'Review the exact selected saved content against its evidence, disclosure/contact choices and tone; report concrete findings and save through the installed task facade. A copied prompt is not proof that review happened.'}[intent]
        try:
            catalog=self.localization()['catalog']
            action=catalog.get('agentPrompt.'+{'agent.research':'researchInstruction','agent.prepare':'prepareInstruction','agent.review':'reviewInstruction'}[intent])
            template=catalog.get('agentPrompt.boundPrompt')
            if isinstance(action,str) and isinstance(template,str):
                prompt=template.replace('{workspace_id}',self.workspace_id).replace('{descriptor}',canonical(descriptor)).replace('{action}',action)
        except (CareerError,OSError,ValueError):pass
        return self.envelope(descriptor=descriptor,prompt=prompt,executed=False,external_actions={'performed':0})

    def resolve_intent(self,value):
        require(isinstance(value,dict) and set(value) in ({'id','workspace_id','revision','intent','scope','status'},{'id','workspace_id','revision','intent','scope','status','selection_mode'}),'INVALID_INTENT','Invalid bounded intent descriptor')
        require(value['workspace_id']==self.workspace_id,'WORKSPACE_CONFLICT','Intent belongs to another workspace',409)
        require(value['intent'] in ('agent.research','agent.prepare','agent.review') and value['status']=='not_executed','INVALID_INTENT','Unknown or executed intent')
        original={key:entry for key,entry in value.items() if key!='id'}
        require(value['id']=='intent_'+digest(original)[:32],'INVALID_INTENT','Intent binding changed')
        scope=value['scope']
        require(isinstance(scope,dict) and set(scope)=={'case_ids','packet_ids','version_ids','track_ids'},'INVALID_INTENT','Invalid intent scope')
        for key in scope:require(isinstance(scope[key],list) and len(scope[key])<=100,'LIMIT_EXCEEDED','Intent scope exceeds bounds')
        require(value.get('selection_mode') in (None,'packet','version'),'INVALID_INTENT','Unknown selection binding')
        current_packets=[];current_versions=[]
        for case_id in scope['case_ids']:
            self.get('case',case_id)
            packet=self.one('SELECT p.* FROM packets p JOIN case_selections s ON s.packet_id=p.id WHERE s.case_id=?',(case_id,))
            if packet:
                current_packets.append(packet['id'])
                if packet['selected_version_id']:current_versions.append(packet['selected_version_id'])
        if value.get('selection_mode') in ('packet','version'):
            require(len(scope['case_ids'])==1 and len(scope['packet_ids'])==1,'INVALID_INTENT','One explicit case packet required')
            packet=self.get('packet',scope['packet_ids'][0])
            require(packet['case_id']==scope['case_ids'][0],'SCOPE_CONFLICT','Packet case changed',409)
            current_packets=[packet['id']];current_versions=[packet['selected_version_id']] if packet['selected_version_id'] else []
            if value.get('selection_mode')=='version':
                require(value['intent']=='agent.review' and len(scope['version_ids'])==1,'INVALID_INTENT','One historical review version required')
                version=self.get('version',scope['version_ids'][0]);require(version['packet_id']==packet['id'],'SCOPE_CONFLICT','Version packet changed',409);current_versions=[version['id']]
        require(set(current_packets)==set(scope['packet_ids']) and set(current_versions)==set(scope['version_ids']),
                'SELECTION_CONFLICT','Selected target/materials changed; inspect the current selection',409)
        for track_id in scope['track_ids']:
            track=self.get('track',track_id)
            if value['intent']=='agent.research':require(track['selected'],'SCOPE_CONFLICT','Requested track is no longer selected',409)
            if scope['case_ids']:
                require(any(self.one('SELECT 1 FROM case_tracks WHERE case_id=? AND track_id=?',(case_id,track_id)) for case_id in scope['case_ids']),'SCOPE_CONFLICT','Case track association changed',409)
        research=self.research_check()
        if value['intent']=='agent.research':
            require(research['allowed'] and set(scope['track_ids'])<=set(research['scope'].get('track_ids',[])),
                    'RESEARCH_NOT_AUTHORIZED','Research is paused, revoked, expired or outside current scope',403)
        return self.envelope(descriptor=value,viewed_selection=self.selection(scope['packet_ids'][0],version_id=scope['version_ids'][0] if value.get('selection_mode')=='version' else None) if value.get('selection_mode') else None,context=self.context(task='contacts' if value['intent']=='agent.research' else 'packets',case_id=next(iter(scope['case_ids']),None),_track_ids=scope['track_ids']),research=research,context_refreshed=value['revision']!=self.revision,
                             executed=False,external_actions={'performed':0})

    def refresh_case_projection(self, case_id):
        case=self.get('case',case_id)
        summary=self.case_summary(case)
        boundaries=[]
        if summary['contact']:
            person=self.get('person',summary['contact']['id']);expiry=json.loads(person['detail']).get('valid_until')
            if expiry and timestamp(expiry)>datetime.now(timezone.utc):boundaries.append(expiry)
        for answer in self.applicable_answers(case_id):
            if answer['valid_until'] and timestamp(answer['valid_until'])>datetime.now(timezone.utc):boundaries.append(answer['valid_until'])
        self._db.execute('INSERT INTO case_projection_cache VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET column_key=excluded.column_key,closed=excluded.closed,search_text=excluded.search_text,person_id=excluded.person_id,qualified=excluded.qualified,body=excluded.body,expires_at=excluded.expires_at',
            (case_id,summary['column'],case['closed'],(case['title']+' '+summary['company']).casefold(),summary['contact']['id'] if summary['contact'] else None,int(bool(summary['contact'] and summary['contact']['qualified'])),canonical(summary),min(boundaries) if boundaries else None))

    def command_hash(self, request_id):
        return self.one('SELECT command_hash FROM commands WHERE request_id=?',(request_id,))['command_hash']

    def public_claim(self,row):
        value=dict(row);value['detail']=json.loads(value['detail'])
        value['source_ids']=[r['source_id'] for r in self.rows('SELECT source_id FROM claim_sources WHERE claim_id=? ORDER BY source_id',(row['id'],))]
        return value

    def public_answer(self,row,track_ids=(),case=None):
        from .policy import answer_scope_matches
        value=dict(row)
        for key in ('scope','units','value'):value[key]=json.loads(value[key])
        current=(not row['valid_from'] or row['valid_from']<=now()) and (not row['valid_until'] or row['valid_until']>now())
        known_keys={'track_id','track_ids','company_id','case_id','opportunity_id','purpose'}
        unresolved=bool(set(value['scope'])-known_keys)
        value['valid_now']=bool(current)
        value['response_state']='pending' if value['disposition']=='pending' else 'provided'
        value['reusable_here']=bool(value['response_state']=='provided' and current and not unresolved and answer_scope_matches(value['scope'],set(track_ids),case))
        value['value_reusable_here']=value['reusable_here'] and value['disposition']=='answered'
        value['scope_unresolved']=unresolved
        return value

    def context(self,task=None,case_id=None,track_id=None,source_id=None,claim_id=None,answer_id=None,limit=25,cursor=None,_track_ids=None):
        require(task in (None,'profile','contacts','packets','history','interview'),'INVALID_QUERY','Unknown task context')
        require(type(limit) is int and 1<=limit<=50,'LIMIT_EXCEEDED','Context limit must be 1..50')
        require(sum(bool(value) for value in (source_id,claim_id,answer_id))<=1,'INVALID_QUERY','Read one exact source/claim/answer at a time')
        scope=dict(task=task,case_id=case_id,track_id=track_id,source_id=source_id,claim_id=claim_id,answer_id=answer_id,limit=limit,track_ids=sorted(_track_ids) if _track_ids is not None else None)
        offsets={key:0 for key in ('tracks','claims','sources','answers')}
        if cursor:
            try:value=json.loads(base64.urlsafe_b64decode(cursor.encode()))
            except (ValueError,UnicodeError):raise CareerError('INVALID_CURSOR','Invalid context cursor')
            require(isinstance(value,dict) and value.get('revision')==self.revision and value.get('scope')==digest(scope),'REVISION_CONFLICT','Context changed; refresh this same scope',409)
            require(isinstance(value.get('offsets'),dict) and set(value['offsets'])==set(offsets) and all(type(n) is int and 0<=n<=10000000 for n in value['offsets'].values()),'INVALID_CURSOR','Invalid context offsets')
            offsets=value['offsets']
        case=self.get('case',case_id) if case_id else None
        selected_tracks={row['track_id'] for row in self.rows('SELECT track_id FROM case_tracks WHERE case_id=?',(case_id,))} if case else set()
        if _track_ids is not None:
            require(isinstance(_track_ids,list) and len(_track_ids)<=100,'INVALID_QUERY','Bounded intent track subset required')
            for selected_id in _track_ids:self.get('track',selected_id)
            require(not case or set(_track_ids)<=selected_tracks,'SCOPE_CONFLICT','Intent track subset no longer belongs to this case',409)
            selected_tracks=set(_track_ids)
        if track_id:
            self.get('track',track_id)
            require(not case or track_id in selected_tracks,'SCOPE_CONFLICT','Requested track does not belong to this case',409)
            selected_tracks={track_id}
        collections={key:[] for key in offsets};totals={key:0 for key in offsets};available={key:self.one('SELECT count(*) AS n FROM '+key)['n'] for key in offsets}
        track_where=' WHERE id IN(SELECT value FROM json_each(?))' if selected_tracks or _track_ids is not None else ''
        track_args=[canonical(sorted(selected_tracks))] if track_where else []
        totals['tracks']=self.one('SELECT count(*) AS n FROM tracks'+track_where,track_args)['n']
        raw_tracks=self.rows('SELECT * FROM tracks'+track_where+' ORDER BY id LIMIT ? OFFSET ?',[*track_args,min(limit,25),offsets['tracks']])
        for row in raw_tracks:
            value={key:row[key] for key in ('id','version','name','positioning','language')};value['selected']=bool(row['selected']);value['policies']=json.loads(row['policies']);value['claim_ids']=json.loads(row['detail']).get('claim_ids',[])
            collections['tracks'].append(value)
        profile=self.one('SELECT display_name,conversation_language FROM workspace')
        research=self.one('SELECT status,scope,expires_at FROM research');research['scope']=json.loads(research['scope'])
        result=self.envelope(profile=profile,tracks=collections['tracks'],preferences=self.preferences(),research=research,
            counts=dict(cases=self.one('SELECT count(*) AS n FROM cases')['n'],contacts=self.one('SELECT count(*) AS n FROM persons')['n'],pending_questions=self.one("SELECT count(*) AS n FROM answers WHERE disposition='pending' AND (valid_from IS NULL OR valid_from<=?) AND (valid_until IS NULL OR valid_until>?)",(now(),now()))['n']),next_missing_input=[])
        result['exports']=self.exports()
        result['recent_job_search']=self.one("SELECT id,requested_count,json_array_length(selected_ids) AS selected_count FROM batches WHERE task='job_search' ORDER BY rowid DESC LIMIT 1")
        active=contained(self.root,'.career-agent/active.json');installed=active.is_file()
        release=contained(self.root,json.loads(active.read_text())['release_dir']) if installed else None
        result['runtime']=dict(installed=installed,ui_available=bool(release and (release/'ui/index.html').is_file()))
        if case:result['case']=self.case_summary(case)
        if source_id:
            value=self.get('source',source_id);value['detail']=json.loads(value['detail']);result['source']=value
        if claim_id:result['claim']=self.public_claim(self.get('claim',claim_id))
        if answer_id:result['answer']=self.public_answer(self.get('answer',answer_id),selected_tracks,case)
        claim_ids=set();source_ids=set();claim_scope='shared_bank'
        if selected_tracks:
            for row in self.rows('SELECT detail FROM tracks WHERE id IN(SELECT value FROM json_each(?))',(canonical(sorted(selected_tracks)),)):
                claim_ids.update(json.loads(row['detail']).get('claim_ids',[]))
        if case:
            source_ids.update(json.loads(case['detail']).get('source_ids',[]))
            selected=self.one('SELECT v.used_claim_ids FROM case_selections c JOIN packets p ON p.id=c.packet_id JOIN packet_versions v ON v.id=p.selected_version_id WHERE c.case_id=?',(case_id,))
            if selected:claim_ids.update(json.loads(selected['used_claim_ids']))
        if claim_ids:claim_scope='linked_context'
        if _track_ids==[]:claim_scope='empty_intent_scope'
        if task:
            where=' WHERE 0' if _track_ids==[] else ' WHERE id IN(SELECT value FROM json_each(?))' if claim_ids else ''
            args=[canonical(sorted(claim_ids))] if claim_ids else []
            totals['claims']=self.one('SELECT count(*) AS n FROM claims'+where,args)['n']
            collections['claims']=[self.public_claim(row) for row in self.rows('SELECT * FROM claims'+where+' ORDER BY id LIMIT ? OFFSET ?',[*args,limit,offsets['claims']])]
            if claim_ids:
                source_ids.update(row['source_id'] for row in self.rows('SELECT DISTINCT source_id FROM claim_sources WHERE claim_id IN(SELECT value FROM json_each(?))',(canonical(sorted(claim_ids)),)))
            source_where=' WHERE 0' if _track_ids==[] else ' WHERE id IN(SELECT value FROM json_each(?))' if source_ids and (selected_tracks or case) else ''
            source_args=[canonical(sorted(source_ids))] if source_where and source_where!=' WHERE 0' else []
            totals['sources']=self.one('SELECT count(*) AS n FROM sources'+source_where,source_args)['n']
            for row in self.rows('SELECT id,version,locator,excerpt,observed_at,readable FROM sources'+source_where+' ORDER BY id LIMIT ? OFFSET ?',[*source_args,limit,offsets['sources']]):
                row['excerpt_truncated']=len(row['excerpt'])>2048;row['excerpt']=row['excerpt'][:2048];collections['sources'].append(row)
            conditions=['0'] if _track_ids==[] else [];answer_args=[]
            if selected_tracks:
                conditions.append("(json_extract(scope,'$.track_id') IS NULL OR json_extract(scope,'$.track_id') IN(SELECT value FROM json_each(?)))");answer_args.append(canonical(sorted(selected_tracks)))
                conditions.append("(json_type(scope,'$.track_ids') IS NULL OR EXISTS(SELECT 1 FROM json_each(scope,'$.track_ids') t WHERE t.value IN(SELECT value FROM json_each(?))))");answer_args.append(canonical(sorted(selected_tracks)))
            if case or selected_tracks:
                for key,expected in [('company_id',case['company_id'] if case else None),('case_id',case_id),('opportunity_id',case['opportunity_id'] if case else None)]:
                    conditions.append("(json_extract(scope,'$."+key+"') IS NULL OR json_extract(scope,'$."+key+"')=?)");answer_args.append(expected)
            answer_where=' WHERE '+' AND '.join(conditions) if conditions else ''
            totals['answers']=self.one('SELECT count(*) AS n FROM answers'+answer_where,answer_args)['n']
            collections['answers']=[self.public_answer(row,selected_tracks,case) for row in self.rows('SELECT * FROM answers'+answer_where+' ORDER BY id LIMIT ? OFFSET ?',[*answer_args,limit,offsets['answers']])]
            result['evidence']={key:collections[key] for key in ('claims','sources','answers')}
        # Budget trimming advances only returned rows, never silently skips removed rows.
        while sum(len(rows) for rows in collections.values())>96 or len(canonical(result).encode())>60000:
            candidates=[rows for rows in collections.values() if rows]
            if not candidates:break
            max(candidates,key=lambda rows:len(canonical(rows))).pop()
        require(len(canonical(result).encode())<63000,'CONTEXT_RECORD_TOO_LARGE','Use a narrower exact-record context')
        result['pagination']={key:dict(available=available[key],total=totals[key],offset=offsets[key],returned=len(collections[key]),remaining=max(0,totals[key]-offsets[key]-len(collections[key])),omitted_by_scope=max(0,available[key]-totals[key])) for key in collections if task or key=='tracks'}
        next_offsets={key:offsets[key]+len(collections[key]) for key in offsets}
        remaining=any(page['remaining'] for page in result['pagination'].values())
        result['partial']=remaining or any(row.get('excerpt_truncated') for row in collections['sources'])
        result['next_cursor']=base64.urlsafe_b64encode(canonical(dict(revision=self.revision,scope=digest(scope),offsets=next_offsets)).encode()).decode() if remaining and next_offsets!=offsets else None
        result['coverage']=dict(claim_scope=claim_scope,source_ids_with_more=[row['id'] for row in collections['sources'] if row.get('excerpt_truncated')])
        require(len(canonical(result).encode())<=65536,'CONTEXT_RECORD_TOO_LARGE','Use a narrower exact-record context')
        return result

    def research_check(self, scope=None):
        grant = self.one('SELECT * FROM research')
        granted = json.loads(grant['scope'])
        requested = scope or granted
        allowed = grant['status']=='active' and (not grant['expires_at'] or grant['expires_at']>now())
        if scope:
            allowed = allowed and set(requested.get('track_ids',[])) <= set(granted.get('track_ids',[])) and requested.get('purpose')==granted.get('purpose')
        return self.envelope(allowed=allowed,status=grant['status'],scope=granted,expires_at=grant['expires_at'],
                             issues=[] if allowed else [dict(code='RESEARCH_NOT_AUTHORIZED',message='Explicit unchanged scoped research authorization required')])

    def contact(self, record_id):
        from .policy import contact_issues
        person = self.get('person',record_id)
        detail = json.loads(person['detail'])
        observations = []
        for observation in detail['sources']:
            source = self.get('source',observation['source_id'])
            observations.append(dict(observation,readable=bool(source['readable'])))
        route = self.one('SELECT * FROM channels WHERE id=? AND person_id=?',(detail['selected_channel_id'],record_id)) if detail.get('selected_channel_id') else None
        if not route and not detail.get('selected_channel_id'):
            channels=self.rows('SELECT * FROM channels WHERE person_id=? LIMIT 2',(record_id,))
            route=channels[0] if len(channels)==1 else None
        if route:
            route['readable'] = bool(self.get('source',route['source_id'])['readable'])
        state = dict(person,valid_until=detail.get('valid_until'))
        issues = contact_issues(state,observations,route,now())
        return dict(id=person['id'],name=person['name'],version=person['version'],company_id=person['company_id'],company=self.get('company',person['company_id'])['name'],
                    affiliation=person['affiliation'],relevance=person['relevance'],sources=detail['sources'],track_rationales=detail.get('track_rationales',[]),
                    route={k:route[k] for k in ('kind','value','source_id')} if route else None,
                    qualified=not issues,issues=issues)

    def _paging(self, cursor, limit, scope):
        require(type(limit) is int and 1<=limit<=100,'INVALID_INPUT','limit must be 1..100')
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            except (ValueError,UnicodeError):
                raise CareerError('INVALID_CURSOR','Invalid cursor')
            require(isinstance(value,dict) and set(value)=={'revision','scope','offset'} and type(value['revision']) is int and isinstance(value['scope'],str) and type(value['offset']) is int and 0<=value['offset']<=10000000,'INVALID_CURSOR','Invalid bounded cursor')
            require(value['revision']==self.revision and value['scope']==digest(scope), 'REVISION_CONFLICT','Page changed; refresh active page',409)
            return value['offset']
        return 0

    def _cursor(self, offset, scope):
        return base64.urlsafe_b64encode(canonical(dict(revision=self.revision,offset=offset,scope=digest(scope))).encode()).decode()

    def contacts_page(self, limit=50, cursor=None, q='', company_id=None):
        scope = dict(q=q,company_id=company_id)
        offset = self._paging(cursor,limit,scope)
        where,args = ['name LIKE ?'],['%'+q+'%']
        if company_id:
            where.append('company_id=?');args.append(company_id)
        clause = ' WHERE '+' AND '.join(where)
        total = self.one('SELECT count(*) AS n FROM persons'+clause,args)['n']
        ids = self.rows('SELECT id FROM persons'+clause+' ORDER BY id LIMIT ? OFFSET ?',[*args,limit,offset])
        return self.envelope(items=[self.contact(row['id']) for row in ids],total=total,
                             next_cursor=self._cursor(offset+limit,scope) if offset+limit<total else None)

    def effective_coverage(self,version_id):
        """Resolve a bounded immutable audit chain without copying arrays into new versions."""
        chain=[];seen=set()
        while version_id:
            require(version_id not in seen and len(seen)<100,'COVERAGE_BASE_INVALID','Coverage chain is cyclic or exceeds 100 versions')
            seen.add(version_id)
            row=self.one('SELECT detail FROM reviews WHERE version_id=?',(version_id,))
            require(row,'COVERAGE_BASE_MISSING','Base coverage requires an attributable saved review')
            detail=json.loads(row['detail']);chain.append(detail['coverage']);version_id=detail.get('base_coverage_version_id')
        merged={}
        for entries in reversed(chain):merged.update((entry['claim_id'],entry) for entry in entries)
        return merged

    def numeric_context(self, case_id, claims, person_id=None):
        """Reuse canonical names and only the target/person/used-claim source scope."""
        case=self.get('case',case_id);company=self.get('company',case['company_id'])
        source_ids=set(json.loads(case['detail']).get('source_ids',[]))
        if person_id:
            person=self.get('person',person_id)
            source_ids.update(entry['source_id'] for entry in json.loads(person['detail']).get('sources',[]))
        for claim in claims:
            source_ids.update(row['source_id'] for row in self.rows('SELECT source_id FROM claim_sources WHERE claim_id=?',(claim['id'],)))
        require(len(source_ids)<=1000,'REVIEW_CONTEXT_TOO_LARGE','Narrow the numeric source context')
        sources=[self.get('source',source_id) for source_id in sorted(source_ids)]
        require(sum(len(source['excerpt']) for source in sources)<=8*1024*1024,'REVIEW_CONTEXT_TOO_LARGE','Numeric evidence exceeds the bounded context')
        return [company],sources

    def selection(self, packet_id, include_text=True,_contact=None,_eligibility=None,_packet=None,_case=None,version_id=None):
        from .contracts import issue
        packet = _packet if _packet and _packet['id']==packet_id else self.get('packet',packet_id)
        version_id = version_id or packet['selected_version_id']
        require(version_id,'REVIEW_REQUIRED','Packet has no saved selected version')
        version = self.get('version',version_id)
        require(version['packet_id']==packet_id,'SCOPE_CONFLICT','Version belongs to another packet',409)
        issues = []
        slots = []
        for slot in self.rows('SELECT * FROM slots WHERE version_id=? ORDER BY name',(version_id,)):
            if include_text:
                artifact,path = self.object(slot['artifact_id'])
                body = path.read_text() if artifact['media_type'] in ('text/markdown','text/plain') else None
            else:
                artifact=self._object_rows.get(slot['artifact_id']) or self.get('object',slot['artifact_id']);self._object_rows[slot['artifact_id']]=artifact;body=None
                try:self.object(slot['artifact_id'])
                except CareerError as error:
                    if error.code!='MATERIAL_CHANGED':raise
                    issues.extend(error.issues)
            slots.append(dict(name=slot['name'],artifact_id=artifact['id'],sha256=artifact['sha256'],media_type=artifact['media_type'],
                              text=body,download_url='/api/v1/artifacts/'+artifact['id']+'/download'))
        review = self.one('SELECT * FROM reviews WHERE version_id=?',(version_id,))
        if not review:
            issues.append(issue('REVIEW_REQUIRED','Selected draft requires fact and tone review'))
        else:
            detail = json.loads(review['detail'])
            issues.extend(detail.get('issues',[]))
        for dependency in self.rows('SELECT * FROM dependencies WHERE version_id=?',(version_id,)):
            record = self.get(dependency['kind'],dependency['record_id'])
            current_version=json.loads(record['detail']).get('semantic_version',1) if dependency['kind']=='case' and dependency['purpose']=='eligibility' else record['version']
            if current_version != dependency['record_version'] and dependency['purpose']!='mechanical-contact':
                issues.append(issue('REVIEW_STALE','Dependency changed: '+dependency['purpose'],dependency['record_id']))
            if dependency['kind']=='answer' and record['valid_until'] and record['valid_until']<=now() and dependency['purpose']!='mechanical-contact':
                issues.append(issue('ANSWER_EXPIRED','Dependent answer expired',record['id']))
            if dependency['kind']=='claim' and not self.one('SELECT 1 FROM claim_sources cs JOIN sources s ON s.id=cs.source_id WHERE cs.claim_id=? AND s.readable=1 AND length(trim(s.excerpt))>0 LIMIT 1',(record['id'],)):
                issues.append(issue('SOURCE_UNREADABLE','Used claim has no readable supporting observation',record['id']))
            if dependency['kind']=='claim' and (record['disclosure']!='allowed' or record['contradicted'] or record['confirmation']!='confirmed'):
                issues.append(issue('DISCLOSURE_BLOCKED','Used claim is no longer reusable',record['id']))
        case = _case if _case and _case['id']==packet['case_id'] else self.get('case',packet['case_id'])
        qualified = True
        if case['route']=='person':
            qualified = bool(packet['person_id']) and (_contact if _contact and _contact['id']==packet['person_id'] else self.contact(packet['person_id']))['qualified']
            if not qualified:
                issues.append(issue('CONTACT_CONDITIONAL','Selected recipient is not currently qualified'))
        names = {slot['name'] for slot in slots}
        if packet['purpose'] in ('application','referral'):
            required = {'resume','message','dossier','interview'}
            if case['route']=='form': required.add('answers')
            if not required<=names:
                issues.append(issue('PACKET_INCOMPLETE','Missing required slots: '+', '.join(sorted(required-names))))
        from .binary import contact_checks
        if include_text or self.applicable_answers(case['id']):
            if not include_text:
                for slot in slots:
                    try:artifact,path=self.object(slot['artifact_id'])
                    except CareerError as error:
                        if error.code=='MATERIAL_CHANGED':continue
                        raise
                    slot['text']=path.read_text() if artifact['media_type'] in ('text/markdown','text/plain') else None
            documents=[]
            for slot in slots:
                body=slot['text']
                if body is None:
                    extraction=self.one('SELECT extracted_artifact_id FROM extraction_receipts WHERE artifact_id=?',(slot['artifact_id'],))
                    if extraction:
                        try:
                            _,path=self.object(extraction['extracted_artifact_id']);body=path.read_text()
                        except CareerError as error:
                            if include_text or error.code!='MATERIAL_CHANGED':raise
                            issues.extend(error.issues)
                    elif slot['name'] in ('resume','message','answers'):issues.append(issue('EXTRACTION_REQUIRED','Binary has no actual byte-bound extraction'))
                if body is not None:documents.append(dict(slot=slot['name'],text=body))
            issues.extend(contact_checks(documents,self.applicable_answers(case['id'])))
        if json.loads(case['detail']).get('essential_policy')=='failed':
            issues.append(issue('ESSENTIAL_POLICY_FAILED','Confirmed essential policy prevents suitable-case credit'))
        unresolved=self.rows('SELECT a.id FROM activities a WHERE a.case_id=? AND a.kind="uncertain" AND NOT EXISTS(SELECT 1 FROM activities r WHERE r.resolves_activity_id=a.id) UNION SELECT a.id FROM packets p JOIN activities a ON a.packet_id=p.id WHERE p.person_id=? AND a.kind="uncertain" AND NOT EXISTS(SELECT 1 FROM activities r WHERE r.resolves_activity_id=a.id)',(packet['case_id'],packet['person_id']))
        eligibility=_eligibility or self.eligibility(case)
        progress=[]
        if include_text:
            progress=[self.assess(row['id'],_projection_only=True) for row in self.rows("SELECT id FROM batches WHERE task='job_search' AND EXISTS(SELECT 1 FROM json_each(selected_ids) i WHERE i.value=?) LIMIT 10",(case['id'],))]
        from .interview import project_interview_slot
        reference_versions={row['record_id']:row['record_version'] for row in self.rows("SELECT record_id,record_version FROM dependencies WHERE version_id=? AND kind='source' AND purpose='interview-reference'",(version_id,))} if include_text else {}
        def saved_dialogue_source(source_id):
            source=self.get('source',source_id)
            return source if reference_versions.get(source_id)==source['version'] else dict(source,readable=False)
        interview=[turn for slot in slots if slot['name']=='interview' for turn in project_interview_slot(slot,saved_dialogue_source)] if include_text else []
        return dict(reported_sent=bool(self.one("SELECT 1 FROM activities WHERE packet_id=? AND version_id=? AND kind='sent' LIMIT 1",(packet_id,version_id))) if include_text else None,is_selected=version_id==packet['selected_version_id'],created_at=version['created_at'],ordinal=version['ordinal'],interview=interview,task_progress=progress,delivery=dict(retry_blocked=bool(unresolved),unresolved_activity_ids=[r['id'] for r in unresolved]),packet_id=packet_id,version_id=version_id,case_id=packet['case_id'],person_id=packet['person_id'],
                    purpose=packet['purpose'],slots=slots,assessment=dict(saved=not any(entry['code']=='MATERIAL_CHANGED' for entry in issues),prepared=not issues,qualified=qualified,
                    issues=issues,unknowns=[entry['message'] for entry in eligibility['unknown_details']],unknown_details=eligibility['unknown_details'],conditional=eligibility['conditional'],eligibility=eligibility['status'],limitations=[dict(code='REVIEW_LIMITATION',message=review['limitations'])] if review else []),review=dict(id=review['id'],findings=review['findings'],limitations=review['limitations'],tone_findings=json.loads(review['detail']).get('tone_findings'),numeric_audit=detail.get('numeric_audit') if include_text else None) if review else None,
                    version=packet['version'],used_claim_ids=json.loads(version['used_claim_ids']),answer_ids=json.loads(version['answer_ids']))

    def case_summary(self, case):
        company = self.get('company',case['company_id'])
        packet = self.one('SELECT p.* FROM packets p JOIN case_selections s ON s.packet_id=p.id WHERE s.case_id=?',(case['id'],))
        recipient_id=packet['person_id'] if packet else case['person_id']
        contact=self.contact(recipient_id) if recipient_id else None
        eligibility=self.eligibility(case)
        selection = self.selection(packet['id'],include_text=False,_contact=contact,_eligibility=eligibility,_packet=packet,_case=case) if packet and packet['selected_version_id'] else None
        activities = self.rows('SELECT kind FROM activities WHERE case_id=? ORDER BY occurred_at',(case['id'],))
        kinds = {row['kind'] for row in activities}
        blockers = selection['assessment']['issues'] if selection else []
        if case['closed']:
            column = 'closed'
        elif kinds & {'human_reply','interview','offer','rejection','withdrawal','referral_agreed','referral_performed'}:
            column = 'response'
        elif 'sent' in kinds or self.one('SELECT 1 FROM activities a WHERE a.case_id=? AND a.kind="uncertain" AND NOT EXISTS(SELECT 1 FROM activities b WHERE b.resolves_activity_id=a.id) LIMIT 1',(case['id'],)):
            column = 'waiting'
        elif selection and selection['assessment']['prepared']:
            column = 'ready'
        elif case['route']=='unknown' or (case['route']=='person' and (not contact or not contact['qualified'])):
            column = 'qualify'
        else:
            column = 'prepare'
        actions = [dict(intent='case.reopen' if case['closed'] else 'case.close',label='Reopen' if case['closed'] else 'Close',requires_input=True),
                   dict(intent='case.note',label='Edit private note',requires_input=True)]
        if not case['closed']:
            actions.append(dict(intent='activity.record',label='Record actual activity',requires_input=True))
            actions.extend(dict(intent=intent,label=label,requires_input=True) for intent,label in [('agent.prepare','Ask agent to prepare'),('agent.review','Ask agent to review'),('agent.research','Ask agent to research')])
        return dict(prepared=bool(selection and selection['assessment']['prepared']),conditional=eligibility['conditional'],eligibility=eligibility['status'],unknown_details=eligibility['unknown_details'],qualified=eligibility['status']=='verified' and not case['closed'] and self.readable_target(case) and (not contact or contact['qualified']),id=case['id'],company_id=case['company_id'],company=company['name'],opportunity_id=case['opportunity_id'],title=case['title'],
                    kind=case['kind'],tracks=self.rows('SELECT t.id,t.name,ct.rationale FROM case_tracks ct JOIN tracks t ON t.id=ct.track_id WHERE ct.case_id=?',(case['id'],)),
                    route=case['route'],contact={k:contact[k] for k in ('id','name','qualified','relevance','affiliation','route')} if contact else None,column=column,
                    next_action={'qualify':'Establish useful evidenced route','prepare':'Prepare or revise selected packet','ready':'Human review',
                    'waiting':'Reconcile delivery and response coverage','response':'Review evidenced next step','closed':'Closed'}[column],
                    blockers=blockers,selected_packet_id=packet['id'] if packet else None,
                    selected_version_id=packet['selected_version_id'] if packet else None,allowed_actions=actions,version=case['version'])

    def cases_page(self, limit=50,cursor=None,view='table',column=None,track_id=None,q='',closed=False,counts_override=None):
        require(view in ('table','board'),'INVALID_INPUT','Unknown case view')
        require(column in (None,'qualify','prepare','ready','waiting','response','closed'),'INVALID_INPUT','Unknown board column')
        require(isinstance(q,str) and len(q)<=200,'INVALID_INPUT','Search text exceeds 200 characters')
        scope=dict(view=view,column=column,track_id=track_id,q=q,closed=closed)
        offset=self._paging(cursor,limit,scope)
        where,args=['p.search_text LIKE ?'],['%'+q.casefold()+'%']
        if not closed:where.append('p.closed=0')
        if track_id:
            where.append('EXISTS(SELECT 1 FROM case_tracks ct WHERE ct.case_id=p.case_id AND ct.track_id=?)');args.append(track_id)
        clause=' WHERE '+' AND '.join(where)
        if counts_override:
            columns,qualified=counts_override
        else:
            columns={key:0 for key in ('qualify','prepare','ready','waiting','response','closed')}
            for row in self.rows('SELECT p.column_key,count(*) AS n FROM case_projection_cache p'+clause+' GROUP BY p.column_key',args):columns[row['column_key']]=row['n']
            qualified=self.one('SELECT count(DISTINCT p.person_id) AS n FROM case_projection_cache p'+clause+' AND p.qualified=1',args)['n']
        if column:
            clause+=' AND p.column_key=?';args.append(column)
        rows=self.rows('SELECT p.body FROM case_projection_cache p'+clause+' ORDER BY p.case_id LIMIT ? OFFSET ?',[*args,limit,offset])
        matching=columns[column] if column else sum(columns.values())
        items=[json.loads(row['body']) for row in rows]
        self.verify_projection_materials(items)
        return self.envelope(items=items,next_cursor=self._cursor(offset+limit,scope) if offset+limit<matching else None,
            counts=dict(total=sum(columns.values()),columns=columns),qualified_people=qualified)

    def board_page(self,limit=50,track_id=None,q='',closed=False):
        first=self.cases_page(limit=limit,view='board',column='qualify',track_id=track_id,q=q,closed=closed)
        counts=first['counts'];qualified=first['qualified_people']
        columns={'qualify':dict(items=first['items'],next_cursor=first['next_cursor'])}
        for column in ('prepare','ready','waiting','response','closed'):
            page=self.cases_page(limit=limit,view='board',column=column,track_id=track_id,q=q,closed=closed,counts_override=(counts['columns'],qualified))
            columns[column]=dict(items=page['items'],next_cursor=page['next_cursor'])
        return self.envelope(columns=columns,counts=counts,qualified_people=qualified)

    def packet_summaries(self,where,args,limit=None,offset=0):
        query="""SELECT p.id,p.case_id,p.purpose,p.person_id,p.selected_version_id,
            person.name AS person_name,c.title AS case_title,company.name AS company,
            CASE WHEN cs.packet_id=p.id THEN 1 ELSE 0 END AS is_primary
            FROM packets p JOIN cases c ON c.id=p.case_id
            JOIN companies company ON company.id=c.company_id
            LEFT JOIN persons person ON person.id=p.person_id
            LEFT JOIN case_selections cs ON cs.case_id=p.case_id WHERE """+where+' ORDER BY p.purpose,person.name,p.id'
        if limit is not None:query+=' LIMIT ? OFFSET ?';args=[*args,limit,offset]
        return [dict(row,is_primary=bool(row['is_primary'])) for row in self.rows(query,args)]

    def contact_packets(self,record_id,limit=50,cursor=None):
        self.get('person',record_id)
        scope=dict(person_id=record_id,collection='packets');offset=self._paging(cursor,limit,scope)
        total=self.one('SELECT count(*) AS n FROM packets WHERE person_id=?',(record_id,))['n']
        return self.envelope(items=self.packet_summaries('p.person_id=?',[record_id],limit,offset),total=total,
            next_cursor=self._cursor(offset+limit,scope) if offset+limit<total else None)

    def packet_versions(self,record_id,limit=50,cursor=None):
        packet=self.get('packet',record_id);scope=dict(packet_id=record_id,collection='versions')
        offset=self._paging(cursor,limit,scope)
        total=self.one('SELECT count(*) AS n FROM packet_versions WHERE packet_id=?',(record_id,))['n']
        rows=self.rows('SELECT id,packet_id,ordinal,created_at FROM packet_versions WHERE packet_id=? ORDER BY ordinal DESC LIMIT ? OFFSET ?',(record_id,limit,offset))
        return self.envelope(items=[dict(row,is_selected=row['id']==packet['selected_version_id']) for row in rows],total=total,
            next_cursor=self._cursor(offset+limit,scope) if offset+limit<total else None)

    def case_history(self,record_id,limit=50,cursor=None):
        self.get('case',record_id);scope=dict(case_id=record_id,collection='history');offset=self._paging(cursor,limit,scope)
        total=self.one('SELECT count(*) AS n FROM activities WHERE case_id=?',(record_id,))['n']
        rows=self.rows('SELECT a.id,a.kind,a.occurred_at,a.evidence,COALESCE(a.packet_id,v.packet_id) AS packet_id,a.version_id FROM activities a LEFT JOIN packet_versions v ON v.id=a.version_id WHERE a.case_id=? ORDER BY a.occurred_at,a.id LIMIT ? OFFSET ?',(record_id,limit,offset))
        return self.envelope(items=[dict(row,payload_unknown=row['kind']=='sent' and not row['version_id']) for row in rows],total=total,
            next_cursor=self._cursor(offset+limit,scope) if offset+limit<total else None)

    def retained_history_sources(self):
        return self.rows("SELECT id,body FROM record_history WHERE kind='legacy:history_imports' ORDER BY id")

    def historical_observations(self,limit=25,cursor=None):
        scope=dict(collection='historical_observations');offset=self._paging(cursor,limit,scope)
        total=self.one("SELECT count(*) AS n FROM view_exports WHERE kind LIKE 'history_observation:%'")['n']
        original=self.one("SELECT count(*) AS n FROM record_history WHERE kind='legacy:history_imports'")['n']
        rows=self.rows("SELECT path FROM view_exports WHERE kind LIKE 'history_observation:%' ORDER BY kind LIMIT ? OFFSET ?",(limit,offset))
        return self.envelope(items=[json.loads(row['path']) for row in rows],total=total,pending_projection=max(0,original-total),projection_current=original==total,
            next_cursor=self._cursor(offset+limit,scope) if offset+limit<total else None)

    def exports(self):
        from .views import export_listing
        return export_listing(self)

    def case_detail(self, record_id):
        case = self.get('case',record_id)
        packets = self.packet_summaries('p.case_id=?',[record_id])
        selected = self.one('SELECT p.* FROM packets p JOIN case_selections s ON s.packet_id=p.id WHERE s.case_id=?',(record_id,))
        selection = self.selection(selected['id']) if selected and selected['selected_version_id'] else None
        interview = selection['interview'] if selection else []
        sources = [self.get('source',sid) for sid in json.loads(case['detail'])['source_ids']]
        history=self.case_history(record_id)
        opportunity=self.get('opportunity',case['opportunity_id']) if case['opportunity_id'] else None
        return self.envelope(case=self.case_summary(case),notes=case['notes'],packets=packets,selection=selection,
             history=history['items'],history_total=history['total'],history_next_cursor=history['next_cursor'],
             role=dict(url=opportunity['canonical_url'],reference=opportunity['requisition']) if opportunity else None,
             interview=interview,sources=sources)

    def readable_target(self,case):
        if not hasattr(self,'_source_readability'):self._source_readability={}
        for source_id in json.loads(case['detail']).get('source_ids',[]):
            if source_id not in self._source_readability:
                source=self.get('source',source_id);self._source_readability[source_id]=bool(source['readable'] and source['excerpt'].strip())
            if self._source_readability[source_id]:return True
        return False

    def eligibility(self,case):
        detail=json.loads(case['detail']);policy=detail.get('essential_policy','unknown');unknowns=[]
        if policy=='unknown':
            unknowns=[dict(entry,record_id=case['id'],kind='essential_policy',requires_response=True) for entry in detail.get('essential_unknowns',[])]
            if not unknowns:unknowns=[dict(code='ESSENTIAL_POLICY_UNKNOWN',subject='essential eligibility',message='Essential eligibility has not been established; this remains a conditional candidate.',record_id=case['id'],kind='essential_policy',requires_response=True)]
        if not hasattr(self,'_has_questions'):self._has_questions=bool(self.one("SELECT 1 FROM answers WHERE disposition IN ('pending','unknown') LIMIT 1"))
        if self._has_questions:
            if not hasattr(self,'_case_questions'):self._case_questions={}
            if case['id'] not in self._case_questions:
                tracks=[row['track_id'] for row in self.rows('SELECT track_id FROM case_tracks WHERE case_id=?',(case['id'],))]
                rows=self.rows("SELECT id,version,meaning,scope,'{}' AS units,disposition,'null' AS value,'' AS evidence,valid_from,valid_until FROM answers WHERE disposition IN ('pending','unknown') AND (json_extract(scope,'$.case_id') IS NULL OR json_extract(scope,'$.case_id')=?) AND (json_extract(scope,'$.company_id') IS NULL OR json_extract(scope,'$.company_id')=?) AND (json_extract(scope,'$.opportunity_id') IS NULL OR json_extract(scope,'$.opportunity_id')=?) AND (json_extract(scope,'$.track_id') IS NULL OR json_extract(scope,'$.track_id') IN(SELECT value FROM json_each(?))) AND (json_type(scope,'$.track_ids') IS NULL OR EXISTS(SELECT 1 FROM json_each(scope,'$.track_ids') t WHERE t.value IN(SELECT value FROM json_each(?)))) ORDER BY id LIMIT 26",(case['id'],case['company_id'],case['opportunity_id'],canonical(tracks),canonical(tracks)))
                self._case_questions[case['id']]=[self.public_answer(row,tracks,case) for row in rows]
            answers=self._case_questions[case['id']]
            for answer in answers[:25]:
                if answer['valid_now'] and not answer['scope_unresolved'] and answer['scope'].get('purpose','application') in ('application','external'):
                    unknowns.append(dict(code='OPEN_QUESTION' if answer['disposition']=='pending' else 'EXPLICIT_UNKNOWN',subject=answer['meaning'],message='Awaiting a response: '+answer['meaning'] if answer['disposition']=='pending' else 'User explicitly does not know: '+answer['meaning'],record_id=answer['id'],kind='question',requires_response=answer['disposition']=='pending'))
            if len(answers)>25:unknowns.append(dict(code='MORE_QUESTIONS',subject='question context',message='Additional scoped questions are available through paginated context.',record_id=case['id'],kind='question',requires_response=False))
        return dict(status='failed' if policy=='failed' else 'verified' if policy=='passed' else 'conditional',conditional=policy=='unknown' or any(x['requires_response'] for x in unknowns),unknown_details=unknowns)

    def contact_track_issues(self,person_id,track_ids):
        if not track_ids:return []
        person=self.get('person',person_id);detail=json.loads(person['detail'])
        for rationale in detail.get('track_rationales',[]):
            if rationale['track_id'] in track_ids and rationale.get('rationale') and any(self.get('source',sid)['readable'] for sid in rationale['source_ids']):return []
        rows=self.rows('SELECT DISTINCT c.detail FROM cases c JOIN case_tracks t ON t.case_id=c.id LEFT JOIN case_selections selected ON selected.case_id=c.id LEFT JOIN packets p ON p.id=selected.packet_id WHERE (CASE WHEN p.id IS NULL THEN c.person_id ELSE p.person_id END)=? AND t.track_id IN(SELECT value FROM json_each(?)) AND length(trim(t.rationale))>0',(person_id,canonical(track_ids)))
        if any(any(self.get('source',sid)['readable'] for sid in json.loads(row['detail']).get('source_ids',[])) for row in rows):return []
        return [dict(code='CONTACT_TRACK_RELEVANCE_UNKNOWN',message='No evidenced purpose-specific rationale matches the requested career tracks',record_id=person_id)]

    def batch_scope_issues(self,batch,record_id):
        requested=json.loads(batch['track_ids']) if isinstance(batch['track_ids'],str) else batch['track_ids']
        if batch['count_unit']=='people':return self.contact_track_issues(record_id,requested)
        actual={r['track_id'] for r in self.rows('SELECT track_id FROM case_tracks WHERE case_id=?',(record_id,))}
        return [] if not requested or actual&set(requested) else [dict(code='BATCH_SCOPE_MISMATCH',message='Selected case has no association with the requested track scope',record_id=record_id)]

    def assess(self,batch_id,_projection_only=False):
        batch=self.get('batch',batch_id);selected=list(dict.fromkeys(json.loads(batch['selected_ids'])))
        predicate=json.loads(batch['detail']).get('predicate',dict(kind='qualified_people' if batch['count_unit']=='people' else 'evidenced_cases' if batch['task']=='research' else 'prepared_cases',essential_policy='no_confirmed_failure'))
        saved=qualified=prepared=qualifying=retained_prepared=0;issues=[];items=[]
        for record_id in selected:
            scope_issues=self.batch_scope_issues(batch,record_id);in_scope=not scope_issues
            item=dict(id=record_id,in_scope=in_scope,qualified=False,prepared=False,saved=False,issues=list(scope_issues))
            if batch['count_unit']=='people':
                contact=self.contact(record_id);item['saved']=True;item['qualified']=in_scope and contact['qualified'];item['issues'].extend(contact['issues'])
                saved+=1;qualified+=int(item['qualified']);qualifying+=int(item['qualified'])
            else:
                case=self.get('case',record_id);detail=json.loads(case['detail']);cached=self.one('SELECT body,expires_at FROM case_projection_cache WHERE case_id=?',(record_id,)) if _projection_only else None
                summary=json.loads(cached['body']) if cached and (not cached['expires_at'] or cached['expires_at']>now()) else None
                if not summary or not {'prepared','qualified','unknown_details'}<=set(summary):summary=self.case_summary(case)
                readable=self.readable_target(case)
                policy_ok=detail.get('essential_policy')!='failed'
                if predicate['essential_policy']=='verified_pass':policy_ok=detail.get('essential_policy')=='passed'
                if not readable:item['issues'].append(dict(code='SOURCE_UNREADABLE',message='No readable target evidence',record_id=record_id))
                item['qualified']=in_scope and policy_ok and summary['qualified']
                item['unknown_details']=summary['unknown_details'];item['conditional']=summary['conditional']
                item['saved']=batch['task'] in ('research','job_search') or bool(summary['selected_version_id'])
                if summary['selected_version_id']:
                    item['prepared']=in_scope and summary['prepared'];retained_prepared+=int(not in_scope and summary['prepared'])
                    item['issues'].extend(summary['blockers'])
                saved+=int(item['saved']);qualified+=int(item['qualified']);prepared+=int(item['prepared'])
                qualifying+=int(item['qualified'] and (predicate['kind']=='evidenced_cases' or item['prepared']))
            issues.extend(item['issues']);items.append(item)
        outputs={}
        for output in json.loads(batch['required_outputs']):
            row=self.one('SELECT revision FROM view_exports WHERE kind=?',(output,));outputs[output]=bool(row and row['revision']==self.revision)
        result=self.envelope(batch_id=batch_id,requested=batch['requested_count'],saved=saved,qualified=qualified,prepared=prepared,qualifying=qualifying,
            retained_prepared=retained_prepared,conditional=len(selected)-qualifying,task_complete=qualifying>=batch['requested_count'] and all(outputs.values()),
            predicate=predicate,criterion_label=batch['criterion'],output_freshness=outputs,items=items,issues=issues,external_actions={'performed':0})
        result['scope_complete']=result['task_complete'];result['remaining_work']=[]
        if batch['task']=='job_search':
            remaining=[]
            if len(selected)<batch['requested_count']:remaining.append(dict(kind='find_cases',count=batch['requested_count']-len(selected),blocking=True))
            missing=[x['id'] for x in items if x.get('in_scope') and not x.get('prepared')]
            if missing:remaining.append(dict(kind='prepare_packet',case_ids=missing,count=len(missing),blocking=True))
            conditional=[x['id'] for x in items if not x.get('qualified')]
            if conditional:remaining.append(dict(kind='resolve_eligibility',case_ids=conditional,count=len(conditional),blocking=True))
            pending=sorted({u['record_id'] for item in items for u in item.get('unknown_details',[]) if u['kind']=='question' and u['requires_response']})
            if pending:remaining.append(dict(kind='open_question',answer_ids=pending,count=len(pending),blocking=False))
            stale=[key for key,value in outputs.items() if not value]
            if stale:remaining.append(dict(kind='refresh_outputs',formats=stale,count=len(stale),blocking=True))
            result['remaining_work']=remaining;result['task_complete']=not any(x['blocking'] for x in remaining) and qualifying>=batch['requested_count']
            result['task']=dict(id=batch_id,kind='job_search',requested_count=batch['requested_count'],track_ids=json.loads(batch['track_ids']),case_ids=selected,task_complete=result['task_complete'])
        elif json.loads(batch['detail']).get('parent_id'):
            parent=self.assess(json.loads(batch['detail'])['parent_id'],_projection_only=_projection_only)
            result.update(task=parent['task'],task_complete=parent['task_complete'],remaining_work=parent['remaining_work'])
        result['integrity_scope']='cached_review_state_with_selected_packet_check' if _projection_only else 'explicit_selected_set_readback'
        return result

    def plan_command(self, command):
        return compile_command(self,command)


TABLES = {'opportunity':'opportunities','source':'sources','claim':'claims','track':'tracks','answer':'answers','company':'companies',
          'person':'persons','case':'cases','packet':'packets','version':'packet_versions',
          'object':'objects','batch':'batches','activity':'activities'}


class Repository:
    @classmethod
    def assert_runtime(cls,root):
        root=Path(root).absolute();active=contained(root,'.career-agent/active.json')
        if not active.exists():require(os.environ.get('CAREER_AGENT_DEVELOPMENT')=='1','INSTALLED_COPY_REQUIRED','Install a verified release; source operations require explicit isolated development mode')
        else:
            locator=json.loads(active.read_text())
            require(locator.get('release_dir','').startswith('.career-agent/releases/'),'INVALID_ACTIVE','Unsafe installed locator')
            release=contained(root,locator['release_dir'])
            require(Path(__file__).resolve()==(release/'runtime/career/repository.py').resolve(),'INSTALLED_COPY_REQUIRED','Use the workspace installed launcher')

    def __init__(self, root):
        self.assert_runtime(root)
        self.root = Path(root).absolute()
        active=contained(self.root,'.career-agent/active.json')
        if active.exists():
            locator=json.loads(active.read_text())
            require(locator.get('release_dir','').startswith('.career-agent/releases/'),'INVALID_ACTIVE','Unsafe installed locator')
            release=contained(self.root,locator['release_dir'])
            require(Path(__file__).resolve()==(release/'runtime/career/repository.py').resolve(),
                    'INSTALLED_COPY_REQUIRED','Use this workspace installed .career-agent/career launcher; source/global runtime is refused')
        self.database = contained(self.root, 'Data/career.sqlite3')
        require(self.database.is_file(), 'IMPORT_REQUIRED' if (self.root/'Data/state.json').exists() else 'NOT_INITIALIZED',
                'Initialize a 1.0 workspace or use the separate legacy importer')

    @classmethod
    def initialize(cls, root, display_name, language='en',ui_locale='en'):
        from .localization import locale_tag
        locale_tag(ui_locale)
        cls.assert_runtime(root)
        root = Path(root).absolute()
        require(not root.is_symlink(), 'UNSAFE_PATH', 'Workspace cannot be a symlink')
        if (root / 'Data/career.sqlite3').exists():
            repo = cls(root)
            with repo.open() as snapshot:
                return snapshot.envelope(initialized=True, reused=True)
        require(not (root/'Data/state.json').exists(), 'IMPORT_REQUIRED', 'Legacy data requires an explicit isolated import')
        for name in ('Data', 'Objects', 'Originals', 'Views', 'Backups', '.career-agent/staging'):
            contained(root, name).mkdir(parents=True, exist_ok=True, mode=0o700)
        final_path=contained(root,'Data/career.sqlite3')
        db_path=contained(root,'Data/'+new_id('initializing')+'.sqlite3')
        # Exclusive creation prevents two initializers replacing one another.
        fd = os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        db = sqlite3.connect(db_path)
        try:
            db.executescript(Path(__file__).with_name('schema.sql').read_text())
            db.execute('INSERT INTO workspace VALUES (?,?,?,?,?)', (new_id('workspace'), FORMAT, 0, display_name, language))
            db.execute('INSERT INTO app_preferences(theme,singleton,ui_locale) VALUES (?,1,?)', ('system',ui_locale))
            db.execute('INSERT INTO research VALUES (1,?,?,?,NULL)', ('paused','{}','No research choice recorded'))
            db.commit()
        finally:
            db.close()
        try:os.link(db_path,final_path)
        except FileExistsError:pass
        else:db_path.unlink()
        with cls(root).open() as snapshot:
            return snapshot.envelope(initialized=True, reused=False)

    @staticmethod
    @contextmanager
    def code_switch(root):
        path=contained(Path(root),'Data/career.sqlite3')
        if not path.exists():
            yield;return
        db=sqlite3.connect(path,timeout=2,isolation_level=None)
        try:
            try:db.execute('BEGIN EXCLUSIVE')
            except sqlite3.OperationalError as error:raise CareerError('BUSY','Wait for bounded readers/writers before code switch',503) from error
            yield
        finally:db.rollback();db.close()

    def connect(self):
        active=contained(self.root,'.career-agent/active.json')
        if active.exists():
            release=contained(self.root,json.loads(active.read_text())['release_dir'])
            require(Path(__file__).resolve()==(release/'runtime/career/repository.py').resolve(),'INSTALLED_COPY_REQUIRED','Active code changed; resume with the installed launcher')
        db = sqlite3.connect(self.database, timeout=2, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=2000')
        db.execute('PRAGMA synchronous=FULL')
        if not getattr(self,'_delivery_indexes_ready',False):
            try:format_row=db.execute('SELECT format FROM workspace').fetchone()
            except sqlite3.DatabaseError as error:
                db.close();raise CareerError('UNSUPPORTED_FORMAT','Unrecognized SQLite workspace is not modified; use the separate importer') from error
            if not format_row or format_row['format']!=FORMAT:
                db.close();raise CareerError('UNSUPPORTED_FORMAT','Unrecognized SQLite workspace is not modified; use the separate importer')
            # Structural indexes only: no record/revision/permission changes on an older candidate.
            for name,statement in DELIVERY_INDEXES.items():
                if not db.execute('SELECT 1 FROM sqlite_master WHERE type="index" AND name=?',(name,)).fetchone():db.execute(statement)
            if not any(row['name']=='introduction_shown' for row in db.execute('PRAGMA table_info(app_preferences)')):db.execute('ALTER TABLE app_preferences ADD COLUMN introduction_shown INTEGER NOT NULL DEFAULT 0 CHECK(introduction_shown IN(0,1))')
            self._delivery_indexes_ready=True
        return db

    @contextmanager
    def open(self):
        db=self.connect();snapshot=None
        try:
            db.execute('BEGIN');snapshot=Snapshot(self,db);yield snapshot
        except sqlite3.DatabaseError as error:
            raise CareerError('STATE_CORRUPT','Database read failed') from error
        finally:
            db.rollback();db.close()
            if snapshot and snapshot.material_status:snapshot.integrity_changed=self.propagate_material_status(snapshot.material_status)

    def publish(self, content, extension='md', media_type='text/markdown'):
        require(isinstance(content, bytes) and len(content) <= 25*1024*1024, 'LIMIT_EXCEEDED', 'Object exceeds 25 MiB')
        require(re.fullmatch('[a-z0-9]{1,12}', extension), 'INVALID_INPUT', 'Invalid object extension')
        sha = digest(content)
        target = contained(self.root, 'Objects/' + sha + '.' + extension)
        if target.exists():
            require(target.read_bytes() == content, 'MATERIAL_CHANGED', 'Object collision or changed bytes')
        else:
            self.check_disk_space(extra=len(content))
            staged=contained(self.root,'.career-agent/staging/'+new_id('object'))
            fd=os.open(staged,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
            require(digest(staged.read_bytes())==sha,'MATERIAL_CHANGED','Staged object verification failed')
            try:os.link(staged,target)
            except FileExistsError:require(target.read_bytes()==content,'MATERIAL_CHANGED','Object collision; conflicting bytes preserved')
            staged.unlink()
        return dict(id='artifact_'+sha+'_'+extension, sha256=sha, extension=extension, size=len(content), media_type=media_type)

    def check_disk_space(self, extra=0):
        """Reserve a full checkpoint, rollback growth and bounded staging before writes."""
        required = self.database.stat().st_size * 2 + 64 * 1024 * 1024 + extra
        free = shutil.disk_usage(self.root).free
        if free < required:
            raise CareerError('DISK_SPACE_LOW', 'Insufficient space for a verified checkpoint and atomic write', 507,
                              [dict(code='DISK_SPACE_LOW', message='Recovery and transaction headroom required', required_bytes=required, free_bytes=free)])

    @staticmethod
    def storage_failure(error):
        return isinstance(error, OSError) and error.errno in (errno.ENOSPC, errno.EDQUOT) or any(
            value in str(error).lower() for value in ('database or disk is full', 'no space left', 'disk quota'))

    def backup(self, destination, expected_revision=None):
        """Publish a complete verified online backup atomically; partial files are never targets."""
        self.check_disk_space()
        target = contained(self.root, destination)
        require(not target.exists(), 'ALREADY_EXISTS', 'Backup target already exists')
        temporary = target.with_name('.' + target.name + '.' + new_id('partial'))
        source = backup = None
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            source = self.connect()
            backup = sqlite3.connect(temporary)
            source.backup(backup)
            require(backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok',
                    'BACKUP_INVALID', 'Backup integrity check failed')
            require(not list(backup.execute('PRAGMA foreign_key_check')), 'BACKUP_INVALID', 'Backup relationships failed')
            row = backup.execute('SELECT id,revision FROM workspace').fetchone()
            require(row and (expected_revision is None or row[1] == expected_revision),
                    'BACKUP_INVALID', 'Backup revision differs from the protected transaction')
            backup.close(); backup = None
            with temporary.open('rb') as stream: os.fsync(stream.fileno())
            checksum = self.file_digest(temporary)
            os.link(temporary, target)
            self.sync_directory(target.parent)
            return dict(workspace_id=row[0], revision=row[1], sha256=checksum, bytes=target.stat().st_size)
        except (OSError, sqlite3.Error) as error:
            if self.storage_failure(error):
                raise CareerError('DISK_SPACE_LOW', 'Storage exhausted while creating recovery checkpoint; nothing committed', 507) from error
            raise CareerError('BACKUP_FAILED', 'Recovery checkpoint could not be completed; nothing committed', 503) from error
        finally:
            if backup is not None: backup.close()
            if source is not None: source.close()
            if temporary.exists(): temporary.unlink()
            journal = temporary.with_name(temporary.name + '-journal')
            if journal.exists(): journal.unlink()

    @staticmethod
    def sync_directory(path):
        descriptor = os.open(path, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)

    @staticmethod
    def file_digest(path):
        import hashlib
        checksum = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): checksum.update(chunk)
        return checksum.hexdigest()

    def automatic_backup(self, revision, request_id, workspace_id, command_hash=None):
        # Only the new owned namespace rotates. Earlier/manual/export/migration copies are never adopted.
        directory = contained(self.root, 'Backups/Automatic')
        directory.mkdir(exist_ok=True, mode=0o700)
        path = contained(self.root, 'Backups/Automatic/r' + str(revision) + '-' + request_id + '.sqlite3')
        metadata = contained(self.root, str(path.with_suffix('.json').relative_to(self.root)))
        record = None
        if path.exists() or metadata.exists():
            try:
                require(path.is_file(), 'BACKUP_INVALID', 'Checkpoint database is missing')
                # Missing completion metadata has no trusted content digest. Preserve the orphan
                # and rebuild; SQLite structural integrity cannot prove unchanged business values.
                require(metadata.is_file(), 'BACKUP_INVALID', 'Checkpoint has no trusted completion metadata')
                record = self.revalidate_automatic_backup(path, revision, request_id, workspace_id, command_hash)
                if metadata.exists():
                    require(metadata.stat().st_size <= 4096, 'BACKUP_INVALID', 'Checkpoint metadata exceeds its bound')
                    stored = json.loads(metadata.read_text())
                    require(all(stored.get(key) == record[key] for key in ('format', 'workspace_id', 'revision', 'request_id', 'command_hash', 'bytes', 'sha256')),
                            'BACKUP_INVALID', 'Recovery metadata differs from its verified database')
                    record = stored
            except (CareerError, ValueError, sqlite3.Error):
                # Preserve incomplete/corrupt bytes, then rebuild from the still-protected live revision.
                quarantine = contained(self.root, 'Backups/Automatic/Quarantine')
                quarantine.mkdir(exist_ok=True, mode=0o700)
                suffix = new_id('incomplete')
                for existing in (path, metadata):
                    if existing.exists(): existing.rename(quarantine / (existing.name + '.' + suffix))
                self.sync_directory(directory); self.sync_directory(quarantine)
                record = None
        if record is None:
            record = self.backup(str(path.relative_to(self.root)), expected_revision=revision)
            record.update(format='career-agent.automatic-backup/1', request_id=request_id, command_hash=command_hash, created_at=now())
        if not metadata.exists():
            temporary = metadata.with_name('.' + metadata.name + '.' + new_id('partial'))
            try:
                descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, 'w') as stream:
                    stream.write(canonical(record)); stream.flush(); os.fsync(stream.fileno())
                os.link(temporary, metadata); self.sync_directory(directory)
            except OSError as error:
                if self.storage_failure(error): raise CareerError('DISK_SPACE_LOW', 'Checkpoint metadata could not be persisted; nothing committed', 507) from error
                raise CareerError('BACKUP_FAILED', 'Checkpoint metadata could not be persisted; nothing committed', 503) from error
            finally:
                if temporary.exists(): temporary.unlink()
        self.prune_automatic_backups(workspace_id, protected=metadata)

    def revalidate_automatic_backup(self, path, revision, request_id, workspace_id, command_hash):
        """Validate a completed checkpoint against the caller's persisted digest witness."""
        database = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            require(database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'BACKUP_INVALID', 'Recovery database integrity failed')
            require(not list(database.execute('PRAGMA foreign_key_check')), 'BACKUP_INVALID', 'Recovery database relationships failed')
            row = database.execute('SELECT id,revision FROM workspace').fetchone()
            require(tuple(row or ()) == (workspace_id, revision), 'BACKUP_INVALID', 'Recovery database identity/revision differs')
            require(database.execute('SELECT 1 FROM plans WHERE request_id=? AND base_revision=? AND (? IS NULL OR command_hash=?) LIMIT 1', (request_id, revision, command_hash, command_hash)).fetchone(),
                    'BACKUP_INVALID', 'Recovery database does not contain the protected request plan')
            require(not database.execute('SELECT 1 FROM commands WHERE request_id=?', (request_id,)).fetchone(),
                    'BACKUP_INVALID', 'Recovery database is not the pre-command state')
        finally: database.close()
        return dict(format='career-agent.automatic-backup/1', workspace_id=workspace_id, revision=revision,
                    request_id=request_id, command_hash=command_hash, sha256=self.file_digest(path), bytes=path.stat().st_size, created_at=now())

    def prune_automatic_backups(self, workspace_id, protected):
        """Keep latest ten plus earliest checkpoint on each of the latest seven UTC dates."""
        directory = contained(self.root, 'Backups/Automatic')
        records = []
        for metadata in directory.glob('r*.json'):
            if not re.fullmatch(r'r[0-9]+-[A-Za-z0-9_-]+\.json', metadata.name): continue
            metadata = contained(self.root, str(metadata.relative_to(self.root)))
            if metadata.stat().st_size > 4096: continue
            try: value = json.loads(metadata.read_text())
            except (OSError, ValueError): continue
            if value.get('format') != 'career-agent.automatic-backup/1' or value.get('workspace_id') != workspace_id: continue
            if type(value.get('revision')) is not int or not isinstance(value.get('created_at'), str): continue
            if not isinstance(value.get('request_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value['request_id']): continue
            if metadata.name != 'r' + str(value['revision']) + '-' + value['request_id'] + '.json': continue
            try: created = datetime.fromisoformat(value['created_at'].replace('Z', '+00:00')).astimezone(timezone.utc)
            except ValueError: continue
            path = contained(self.root, str(metadata.with_suffix('.sqlite3').relative_to(self.root)))
            if not path.is_file() or path.stat().st_size != value.get('bytes'): continue
            records.append((created, value['revision'], metadata, path, value))
        records.sort(key=lambda entry: (entry[1], entry[2].name))
        require(any(entry[2] == protected for entry in records), 'BACKUP_INVALID', 'Current verified checkpoint cannot be pruned')
        recent = [entry for entry in reversed(records) if entry[2] != protected][:9]
        keep = {protected} | {entry[2] for entry in recent}
        days = sorted({entry[0].date() for entry in records})[-7:]
        for day in days: keep.add(min((entry for entry in records if entry[0].date() == day), key=lambda entry: entry[0])[2])
        for _, _, metadata, path, value in records:
            if metadata in keep: continue
            require(self.file_digest(path) == value.get('sha256'), 'BACKUP_INVALID', 'A recovery file changed; automatic deletion refused')
            try: path.unlink(); metadata.unlink()
            except OSError as error:
                raise CareerError('BACKUP_RETENTION_FAILED', 'Automatic checkpoint retention failed; nothing committed', 503) from error
        self.sync_directory(directory)

    def store_plan(self, command, plan):
        self.check_disk_space()
        plan=dict(plan,validator_identity=self.code_identity())
        plan_id = new_id('plan')
        db = self.connect()
        try:
            db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?)', (plan_id, command.request_id, digest(command.wire()),
                       command.expected_revision, canonical(plan), now()))
        finally:
            db.close()
        return plan_id

    def status(self, request_id):
        with self.open() as snapshot:
            row = snapshot.one('SELECT receipt FROM commands WHERE request_id=?', (request_id,))
            require(row, 'NOT_FOUND', 'No committed command with this request ID', 404)
            return json.loads(row['receipt'])

    def apply(self, plan_id):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            snapshot = Snapshot(self, db)
            row = snapshot.one('SELECT * FROM plans WHERE id=?', (plan_id,))
            require(row, 'NOT_FOUND', 'Plan not found', 404)
            committed = snapshot.one('SELECT * FROM commands WHERE request_id=?', (row['request_id'],))
            if committed:
                require(committed['command_hash'] == row['command_hash'], 'REQUEST_ID_CONFLICT', 'Request ID reused with different input', 409)
                return json.loads(committed['receipt'])
            require(snapshot.revision == row['base_revision'], 'REVISION_CONFLICT', 'Refresh context and replan', 409)
            plan = json.loads(row['body'])
            require(plan.get('validator_identity')==self.code_identity(),'PLAN_CODE_CHANGED','Runtime changed; replan this bounded command without renewed user approval',409)
            for obj in plan['objects']:
                path = contained(self.root, 'Objects/'+obj['sha256']+'.'+obj['extension'])
                require(path.is_file() and digest(path.read_bytes()) == obj['sha256'], 'MATERIAL_CHANGED', 'Staged bytes changed')
            for guard in plan.get('time_guards', []):
                require(not guard or timestamp(guard) > datetime.now(timezone.utc), 'VALIDITY_EXPIRED', 'A time-dependent input expired; replan', 409)
            self.check_disk_space()
            self.automatic_backup(snapshot.revision, row['request_id'], snapshot.workspace_id, row['command_hash'])
            revision = snapshot.revision + 1
            for statement, args in plan['statements']:
                db.execute(statement, args)
            for case_id in plan.get('affected_case_ids',[]):
                snapshot.refresh_case_projection(case_id)
            db.execute('UPDATE workspace SET revision=?', (revision,))
            receipt = snapshot.envelope(request_id=row['request_id'], outcome=plan['outcome'],
                         saved_ids=plan['saved_ids'], selected_packet_ids=plan.get('selected_packet_ids', []),
                         issues=plan['issues'], external_actions={'performed':0})
            receipt['revision'] = revision
            db.execute('INSERT INTO commands VALUES (?,?,?,?)', (row['request_id'], row['command_hash'], revision, canonical(receipt)))
            db.execute('INSERT INTO change_log VALUES (?,?,?,?,?)', (revision,revision,canonical(plan['kinds']),
                        canonical(plan['saved_ids']),canonical(plan.get('projection_keys',['context','cases','contacts','selection']))))
            db.execute('DELETE FROM change_log WHERE cursor<=?', (revision-10000,))
            db.commit()
            return receipt
        except sqlite3.IntegrityError as error:
            raise CareerError('RELATION_CONFLICT', 'Relation constraint failed; nothing committed', 409) from error
        except sqlite3.OperationalError as error:
            if self.storage_failure(error):
                raise CareerError('DISK_SPACE_LOW', 'Storage exhausted; nothing committed. Check command status before retry', 507) from error
            if 'locked' in str(error):
                raise CareerError('BUSY', 'Workspace busy; resolve command status before retry',503) from error
            raise CareerError('STATE_CORRUPT','Database operation failed; nothing committed',500) from error
        finally:
            db.rollback()
            db.close()

    def propagate_material_status(self,statuses):
        """Derived integrity invalidation only; no career revision or semantic review renewal."""
        if not statuses:return False
        db=self.connect()
        try:
            keys=['material_status:'+artifact_id for artifact_id in statuses]
            known={row['kind']:row for row in db.execute('SELECT kind,path FROM view_exports WHERE kind IN(SELECT value FROM json_each(?))',(canonical(keys),))}
            changes={artifact_id:valid for artifact_id,valid in statuses.items() if (not valid and 'material_status:'+artifact_id not in known) or (valid and 'material_status:'+artifact_id in known)}
            if not changes:return False
            db.execute('BEGIN IMMEDIATE');snapshot=Snapshot(self,db);processed=set();pending=dict(changes);all_changed=set()
            while pending:
                current=pending;pending={};all_changed.update(current)
                for artifact_id,valid in current.items():
                    key='material_status:'+artifact_id
                    if valid:db.execute('DELETE FROM view_exports WHERE kind=?',(key,))
                    else:db.execute('INSERT OR REPLACE INTO view_exports VALUES (?,?,?,?)',(key,snapshot.revision,'invalid',canonical(dict(artifact_id=artifact_id,valid=False))))
                cases=snapshot.rows('SELECT DISTINCT p.case_id FROM slots s JOIN packet_versions v ON v.id=s.version_id JOIN packets p ON p.id=v.packet_id WHERE s.artifact_id IN(SELECT value FROM json_each(?))',(canonical(list(current)),))
                for row in cases:
                    if row['case_id'] not in processed:
                        snapshot.refresh_case_projection(row['case_id']);processed.add(row['case_id'])
                for artifact_id,valid in snapshot.material_status.items():
                    if artifact_id in all_changed:continue
                    existing=db.execute('SELECT 1 FROM view_exports WHERE kind=?',('material_status:'+artifact_id,)).fetchone()
                    if (not valid and not existing) or (valid and existing):pending[artifact_id]=valid
            from datetime import timedelta
            signal=dict(artifact_ids=sorted(all_changed)[:100],case_ids=sorted(processed)[:100],refresh_until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat().replace('+00:00','Z'))
            db.execute('INSERT OR REPLACE INTO view_exports VALUES (?,?,?,?)',('integrity_signal',snapshot.revision,new_id('integrity'),canonical(signal)))
            db.commit();return True
        except sqlite3.OperationalError as error:
            raise CareerError('BUSY','Integrity invalidation waits for the current bounded writer',503) from error
        finally:db.rollback();db.close()

    def cache_historical_observations(self,bundle):
        from .contracts import identifier
        require(isinstance(bundle,dict) and set(bundle)=={'format','workspace_id','revision','source_fingerprint','items'} and bundle['format']=='career-agent.history-projection/1','INVALID_PROJECTION','Typed history projection required')
        require(isinstance(bundle['items'],list) and len(bundle['items'])<=100000,'LIMIT_EXCEEDED','History projection exceeds bounds')
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE');snapshot=Snapshot(self,db)
            require(bundle['workspace_id']==snapshot.workspace_id and bundle['revision']==snapshot.revision,'REVISION_CONFLICT','Projection source changed; prepare it again',409)
            originals=snapshot.retained_history_sources()
            sources=[dict(record_history_id=row['id'],sha256=digest(json.loads(row['body']))) for row in originals]
            require(bundle['source_fingerprint']==digest(sources),'SOURCE_CHANGED','Retained historical source changed',409)
            expected={row['record_history_id']:row['sha256'] for row in sources};seen=set();total_bytes=0
            for item in bundle['items']:
                require(isinstance(item,dict) and item.get('format')=='career-agent.history-observation/1' and item.get('scope')=='unlinked' and item.get('case_id') is None and item.get('canonical_activity_created') is False,'INVALID_PROJECTION','Only unlinked read-only observations are accepted')
                required={'format','id','original_status','event_kind','evidence_level','employer','role','role_url','date','channel','evidence','source','historical_opportunity_reference','provider_message_id','provider_thread_id','case_id','scope','canonical_activity_created'}
                require(set(item)==required,'INVALID_PROJECTION','Invalid typed observation fields')
                for field in ('original_status','event_kind','evidence_level','employer','role','channel'):
                    require(isinstance(item[field],str) and len(item[field])<=32768,'INVALID_PROJECTION','Bounded observation text required')
                for field in ('role_url','evidence','historical_opportunity_reference','provider_message_id','provider_thread_id'):
                    require(item[field] is None or isinstance(item[field],str) and len(item[field])<=32768,'INVALID_PROJECTION','Bounded optional observation text required')
                date=item['date'];require(isinstance(date,dict) and set(date)=={'text','precision','occurred_at'} and isinstance(date['text'],str) and len(date['text'])<=32768 and date['precision'] in ('exact','approximate','unknown') and (date['occurred_at'] is None or isinstance(date['occurred_at'],str) and len(date['occurred_at'])<=32768),'INVALID_PROJECTION','Explicit historical date precision required')
                source=item.get('source',{});require(isinstance(source,dict) and set(source)=={'record_history_id','sha256','locator','kind'} and all(isinstance(source[field],str) and len(source[field])<=32768 for field in ('sha256','locator','kind')),'INVALID_PROJECTION','Typed source binding required')
                key=source.get('record_history_id');require(type(key) is int,'INVALID_PROJECTION','Physical source ID required');identifier(item.get('id'))
                require(item['id']=='observation_'+digest('legacy:history_imports:'+str(key))[:24],'INVALID_PROJECTION','Observation identity must bind its physical source')
                total_bytes+=len(canonical(item).encode());require(total_bytes<=64*1024*1024,'LIMIT_EXCEEDED','History projection exceeds byte budget')
                require(key in expected and key not in seen and source.get('sha256')==expected[key],'SOURCE_CHANGED','History binding missing, duplicate or changed',409)
                require(len(canonical(item).encode())<=65536,'LIMIT_EXCEEDED','Observation too large');seen.add(key)
            require(seen==set(expected),'INCOMPLETE_PROJECTION','Every retained observation must have one projection')
            db.execute("DELETE FROM view_exports WHERE kind LIKE 'history_observation:%'")
            for item in bundle['items']:
                db.execute('INSERT INTO view_exports VALUES (?,?,?,?)',('history_observation:'+item['id'],snapshot.revision,item['source']['sha256'],canonical(item)))
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()
        return dict(cached=len(bundle['items']),business_mutations=0,revision=bundle['revision'])

    def record_view_export(self,kind,revision,destination,sha256):
        db=self.connect()
        try:db.execute('INSERT INTO view_exports VALUES (?,?,?,?) ON CONFLICT(kind) DO UPDATE SET revision=excluded.revision,sha256=excluded.sha256,path=excluded.path',(kind,revision,sha256,destination))
        finally:db.close()

    def portable_export(self):
        """Revision-bound DB backup plus every registered immutable object and manifest."""
        with self.open() as snapshot:
            self.check_disk_space(extra=snapshot.one('SELECT coalesce(sum(size),0) AS n FROM objects')['n'])
            relative='Backups/export-r'+str(snapshot.revision)+'-'+new_id('export')
            output=contained(self.root,relative);(output/'Data').mkdir(mode=0o700,parents=True)
            (output/'Objects').mkdir(mode=0o700)
            self.backup(relative+'/Data/career.sqlite3')
            files={'Data/career.sqlite3':digest((output/'Data/career.sqlite3').read_bytes())}
            for row in snapshot.rows('SELECT id FROM objects ORDER BY id'):
                record,path=snapshot.object(row['id']);name='Objects/'+record['sha256']+'.'+record['extension']
                target=contained(output,name)
                if not target.exists():target.write_bytes(path.read_bytes());os.chmod(target,0o600)
                files[name]=record['sha256']
            manifest=dict(format='career-agent.export/1',workspace_id=snapshot.workspace_id,revision=snapshot.revision,files=files)
            (output/'manifest.json').write_text(canonical(manifest));os.chmod(output/'manifest.json',0o600)
            return snapshot.envelope(outcome='satisfied',destination=str(output),manifest_sha256=digest(canonical(manifest).encode()),files=len(files))

    def code_identity(self):
        active=contained(self.root,'.career-agent/active.json')
        if active.exists():return json.loads(active.read_text())['release_id']
        return 'development-'+digest({p.name:digest(p.read_bytes()) for p in Path(__file__).parent.iterdir() if p.is_file() and p.suffix in ('.py','.sql','.json')})

    def ensure_projection_cache(self, full=False):
        """Rebuild only missing/expired derived rows; never a second business-state owner."""
        db=self.connect()
        try:
            policy=projection_policy_identity()
            marker=db.execute('SELECT sha256 FROM view_exports WHERE kind=?',('case_projection_policy',)).fetchone()
            full=full or not marker or marker[0]!=policy
            missing=db.execute('SELECT (SELECT count(*) FROM cases)-(SELECT count(*) FROM case_projection_cache)').fetchone()[0]
            expired=db.execute('SELECT 1 FROM case_projection_cache WHERE expires_at<=? LIMIT 1',(now(),)).fetchone()
            if not full and not missing and not expired:return 0
            db.execute('BEGIN IMMEDIATE');snapshot=Snapshot(self,db)
            if full:ids=[row[0] for row in db.execute('SELECT id FROM cases')]
            else:ids=[row[0] for row in db.execute('SELECT c.id FROM cases c LEFT JOIN case_projection_cache p ON p.case_id=c.id WHERE p.case_id IS NULL OR p.expires_at<=?',(now(),))]
            for record_id in ids:snapshot.refresh_case_projection(record_id)
            db.execute('INSERT INTO view_exports VALUES (?,?,?,?) ON CONFLICT(kind) DO UPDATE SET revision=excluded.revision,sha256=excluded.sha256',('case_projection_policy',snapshot.revision,policy,'derived'))
            db.commit();return len(ids)
        finally:db.rollback();db.close()

    def doctor(self):
        with self.open() as snapshot:
            failures = [dict(row) for row in snapshot._db.execute('PRAGMA foreign_key_check')]
            integrity = snapshot.one('PRAGMA integrity_check')['integrity_check']
            objects = snapshot.rows('SELECT id FROM objects')
            for obj in objects:
                try:
                    snapshot.object(obj['id'])
                except CareerError as error:
                    failures.append(dict(id=obj['id'], code=error.code))
            return snapshot.envelope(integrity=integrity, objects=len(objects), failures=failures,
                                     healthy=integrity=='ok' and not failures)


def compile_command(snapshot, command):
    """Compile exactly one bounded intent into sealed repository-owned statements."""
    from .contracts import identifier, text, issue
    from .policy import safe_route, resolve_policy, mechanical_review
    data, intent = dict(command.input), command.intent
    for key in ('observed_at','occurred_at','valid_from','valid_until','expires_at'):
        if data.get(key):data[key]=timestamp(data[key]).astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
    statements, objects, saved, issues, kinds, guards = [], [], [], [], [], []
    selected_packets=[]

    def sql(statement, *args):
        statements.append((statement,list(args)))

    def capture(kind, prefix):
        record_id = data.get('id') or new_id(prefix)
        identifier(record_id)
        existing = snapshot.one('SELECT * FROM '+TABLES[kind]+' WHERE id=?',(record_id,))
        if existing:
            sql('INSERT INTO record_history(kind,record_id,version,body,revision) VALUES (?,?,?,?,?)',kind,record_id,existing['version'],canonical(existing),snapshot.revision)
        saved.append(record_id);kinds.append(kind)
        return record_id, (existing['version']+1 if existing else 1), existing

    def refs(kind, ids):
        require(isinstance(ids,list) and len(ids)<=100,'INVALID_INPUT','Expected bounded ID list')
        return [snapshot.get(kind,identifier(entry)) for entry in ids]

    def dependency(version_id, kind, row, purpose):
        sql('INSERT INTO dependencies VALUES (?,?,?,?,?)',version_id,kind,row['id'],row['version'],purpose)

    def add_object(content, extension='md', media_type='text/markdown'):
        obj=snapshot.repository.publish(content,extension,media_type);objects.append(obj)
        sql('INSERT OR IGNORE INTO objects VALUES (?,?,?,?,?)',*[obj[k] for k in ('id','sha256','extension','size','media_type')])
        return obj

    def evidence(value):
        text(value,'evidence',65536)

    if intent=='preferences.set':
        require(data,'INVALID_INPUT','At least one preference required')
        if 'theme' in data:
            require(data['theme'] in ('system','light','dark'),'INVALID_INPUT','Invalid theme')
            sql('UPDATE app_preferences SET theme=?',data['theme'])
        if 'introduction_shown' in data:
            require(type(data['introduction_shown']) is bool,'INVALID_INPUT','introduction_shown must be a display-state boolean')
            sql('UPDATE app_preferences SET introduction_shown=?',int(data['introduction_shown']))
        if 'ui_locale' in data:
            from .localization import locale_tag
            locale_tag(data['ui_locale']);sql('UPDATE app_preferences SET ui_locale=?',data['ui_locale'])
        kinds.append('preferences')
    elif intent=='locale.install':
        from .localization import validate_catalog
        validate_catalog(data,snapshot.builtin_catalog('en'))
        obj=add_object(canonical(data).encode(),'json','application/json')
        target=contained(snapshot.root,'.career-agent/customizations/locales/'+data['locale']+'-'+obj['sha256']+'.json')
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not target.exists():target.write_bytes(canonical(data).encode());os.chmod(target,0o600)
        sql('INSERT INTO locale_catalogs VALUES (?,1,?) ON CONFLICT(locale) DO UPDATE SET version=version+1,artifact_id=excluded.artifact_id',data['locale'],obj['id'])
        kinds.append('localization');saved.append(data['locale'])
    elif intent=='profile.update':
        text(data['display_name'],'display_name',200);text(data['conversation_language'],'conversation_language',40)
        sql('UPDATE workspace SET display_name=?,conversation_language=?',data['display_name'],data['conversation_language']);kinds.append('profile')
    elif intent=='source.capture':
        record_id,version,_=capture('source','source')
        text(data['locator'],'locator',4096);text(data['excerpt'],'excerpt',32768,empty=True)
        timestamp(data['observed_at'])
        require(type(data['readable']) is bool and (not data['readable'] or data['excerpt'].strip()),'INVALID_INPUT','Readable evidence requires an actual excerpt')
        sql('INSERT INTO sources VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,locator=excluded.locator,excerpt=excluded.excerpt,observed_at=excluded.observed_at,readable=excluded.readable,detail=excluded.detail',
            record_id,version,data['locator'],data['excerpt'],data['observed_at'],int(data['readable']),canonical({k:v for k,v in data.items() if k not in ('id','locator','excerpt','observed_at','readable')}))
    elif intent=='claim.save':
        record_id,version,old=capture('claim','claim')
        require(len(canonical(data).encode())<=48000,'LIMIT_EXCEEDED','One claim record exceeds the 48 KiB context limit')
        text(data['assertion'],'assertion');text(data['meaning'],'meaning')
        require(data['confirmation'] in ('confirmed','unconfirmed','unknown','disputed'),'INVALID_INPUT','Invalid confirmation')
        require(data['disclosure'] in ('allowed','private','unknown','withdrawn'),'INVALID_INPUT','Invalid disclosure')
        refs('source',data['source_ids'])
        require(data['source_ids'],'SOURCE_REQUIRED','Claim needs a source observation')
        require(type(data.get('contradicted',False)) is bool,'INVALID_INPUT','contradicted must be boolean')
        sql('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,assertion=excluded.assertion,meaning=excluded.meaning,confirmation=excluded.confirmation,disclosure=excluded.disclosure,contradicted=excluded.contradicted,detail=excluded.detail',
            record_id,version,data['assertion'],data['meaning'],data['confirmation'],data['disclosure'],int(data.get('contradicted',False)),canonical(dict(json.loads(old['detail']) if old else {},kind=data.get('kind',json.loads(old['detail']).get('kind','achievement') if old else 'achievement'),metrics=data.get('metrics',json.loads(old['detail']).get('metrics',[]) if old else []),coverage_disposition=data.get('coverage_disposition',json.loads(old['detail']).get('coverage_disposition','pending') if old else 'pending'))))
        sql('DELETE FROM claim_sources WHERE claim_id=?',record_id)
        for source_id in set(data['source_ids']): sql('INSERT INTO claim_sources VALUES (?,?)',record_id,source_id)
    elif intent=='track.save':
        record_id,version,old= capture('track','track')
        if old and 'claim_ids' not in data:data=dict(data,claim_ids=json.loads(old['detail']).get('claim_ids',[]))
        text(data['name'],'name',200);text(data['positioning'],'positioning');text(data['language'],'language',40)
        require(type(data['selected']) is bool,'INVALID_INPUT','selected must be boolean')
        require(isinstance(data['policies'],dict),'INVALID_POLICY','policies must be an object')
        resolve_policy({},data['policies'],{})
        refs('claim',data.get('claim_ids',[]))
        sql('INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,name=excluded.name,positioning=excluded.positioning,selected=excluded.selected,language=excluded.language,policies=excluded.policies,detail=excluded.detail',
            record_id,version,data['name'],data['positioning'],int(data['selected']),data['language'],canonical(data['policies']),canonical(dict(claim_ids=data.get('claim_ids',[]))))
    elif intent=='answer.save':
        require(len(canonical(data).encode())<=48000,'LIMIT_EXCEEDED','One answer record exceeds the 48 KiB context limit')
        match=snapshot.one('SELECT id FROM answers WHERE meaning=? AND scope=? AND units=?',(data['meaning'],canonical(data['scope']),canonical(data['units'])))
        if match:
            require(not data.get('id') or data['id']==match['id'],'ANSWER_SCOPE_CONFLICT','Update the existing exact scoped answer instead of creating competing choices')
            data=dict(data,id=match['id'])
        record_id,version,old=capture('answer','answer')
        require(data['disposition'] in ('answered','pending','unknown','confidential','declined','no_preference','omit'),'INVALID_INPUT','Invalid answer disposition')
        if data['disposition']=='unknown':require(data.get('response_state')=='provided','ANSWER_STATE_REQUIRED','Use pending for an unanswered question; explicit unknown requires a provided user response')
        if data['disposition']=='answered':require(data['value'] is not None,'ANSWER_VALUE_REQUIRED','An unanswered question uses pending, not an answered null value')
        if data['disposition']=='pending':require(data['value'] is None and data.get('response_state','pending')=='pending','INVALID_INPUT','An unanswered pending question has null value')
        elif 'response_state' in data:require(data['response_state']=='provided','INVALID_INPUT','A saved response must be provided')
        text(data['meaning'],'meaning',200);evidence(data['evidence'])
        require(isinstance(data['scope'],dict) and isinstance(data['units'],dict),'INVALID_INPUT','scope and units must be objects')
        require(not data['meaning'].startswith('agreement.'),'EXACT_CONSENT_REQUIRED','Employer agreement is not a reusable answer')
        for boundary in ('valid_from','valid_until'):
            if data.get(boundary):timestamp(data[boundary])
        if old:
            require(old['meaning']==data['meaning'] and json.loads(old['scope'])==data['scope'] and json.loads(old['units'])==data['units'],
                    'SCOPE_CONFLICT','An answer update must retain exact meaning, scope and units')
        sql('INSERT INTO answers VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,disposition=excluded.disposition,value=excluded.value,evidence=excluded.evidence,valid_from=excluded.valid_from,valid_until=excluded.valid_until',
            record_id,version,data['meaning'],canonical(data['scope']),canonical(data['units']),data['disposition'],canonical(data['value']),data['evidence'],data.get('valid_from'),data.get('valid_until'))
    elif intent=='company.capture':
        text(data['name'],'name',500)
        domain=data.get('domain')
        if domain:
            require(re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}',domain),'INVALID_INPUT','Use canonical company domain without scheme')
            match=snapshot.one('SELECT id FROM companies WHERE domain=?',(domain,))
            if match and not data.get('id'):
                data=dict(data,id=match['id'])
        record_id,version,_=capture('company','company')
        refs('source',data.get('source_ids',[]))
        sql('INSERT INTO companies VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,name=excluded.name,domain=excluded.domain,detail=excluded.detail',record_id,version,data['name'],domain,canonical(dict(source_ids=data.get('source_ids',[]))))
    elif intent=='contact.capture':
        text(data['name'],'name',500);text(data['relevance'],'relevance',8192)
        snapshot.get('company',data['company_id'])
        require(data['affiliation'] in ('current','unknown','conflicting','former'),'INVALID_INPUT','Invalid affiliation assessment')
        require(isinstance(data['sources'],list) and 1<=len(data['sources'])<=100,'SOURCE_REQUIRED','Contact needs bounded source assessments')
        for observation in data['sources']:
            require(isinstance(observation,dict) and set(observation)=={'source_id','axes','assessment'},'INVALID_INPUT','Contact source requires source_id, axes, assessment')
            snapshot.get('source',observation['source_id'])
            require(set(observation['axes'])<= {'identity','affiliation','relevance'} and observation['assessment'] in ('supports','conflicts','unknown'), 'INVALID_INPUT','Invalid source assessment')
        route=data['route']
        if route:
            require(isinstance(route,dict) and set(route)=={'kind','value','source_id'},'INVALID_INPUT','route requires kind,value,source_id')
            safe_route(route['kind'],route['value']);snapshot.get('source',route['source_id'])
        if data.get('valid_until'):timestamp(data['valid_until'])
        record_id,version,old=capture('person','person')
        if old:require(old['company_id']==data['company_id'],'IDENTITY_AMBIGUOUS','Company affiliation changes require a distinct reviewed identity decision')
        rationales=data.get('track_rationales',json.loads(old['detail']).get('track_rationales',[]) if old else [])
        require(isinstance(rationales,list) and len(rationales)<=100,'INVALID_INPUT','Track rationales must be bounded')
        for rationale in rationales:
            require(isinstance(rationale,dict) and set(rationale)=={'track_id','rationale','source_ids'},'INVALID_INPUT','Track rationale requires track_id/rationale/source_ids')
            snapshot.get('track',rationale['track_id']);text(rationale['rationale'],'track rationale',8192);refs('source',rationale['source_ids'])
        channel=None
        if route:channel=snapshot.one('SELECT id FROM channels WHERE person_id=? AND kind=? AND value=?',(record_id,route['kind'],route['value']))
        channel_id=(channel['id'] if channel else new_id('channel')) if route else None
        sql('INSERT INTO persons VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,name=excluded.name,affiliation=excluded.affiliation,relevance=excluded.relevance,detail=excluded.detail',
            record_id,version,data['name'],data['company_id'],data['affiliation'],data['relevance'],canonical(dict(sources=data['sources'],relationship=data.get('relationship'),valid_until=data.get('valid_until'),selected_channel_id=channel_id,track_rationales=rationales)))
        if route:sql('INSERT INTO channels VALUES (?,?,?,?,?,0) ON CONFLICT(person_id,kind,value) DO UPDATE SET source_id=excluded.source_id',channel_id,record_id,route['kind'],route['value'],route['source_id'])
        if data['affiliation']!='current':issues.append(issue('AFFILIATION_UNKNOWN','Retained provisional contact; not qualified',record_id))
    elif intent=='contact.suppress':
        person=snapshot.get('person',data['person_id']);safe_route(data['kind'],data['value']);evidence(data['evidence']);text(data['reason'],'reason',8192)
        channel=snapshot.one('SELECT * FROM channels WHERE person_id=? AND kind=? AND value=?',(person['id'],data['kind'],data['value']))
        require(channel,'NOT_FOUND','Known exact endpoint required',404)
        sql('UPDATE channels SET suppressed=1 WHERE id=?',channel['id'])
        sql('UPDATE persons SET version=version+1 WHERE id=?',person['id'])
        sql('INSERT INTO record_history(kind,record_id,version,body,revision) VALUES (?,?,?,?,?)','channel-suppression',channel['id'],1,canonical(data),snapshot.revision+1)
        saved.append(person['id']);kinds.append('person')
    elif intent=='case.capture':
        snapshot.get('company',data['company_id']);text(data['title'],'title',500)
        require(data['kind'] in ('vacancy','project','speculative'),'INVALID_INPUT','Invalid case kind')
        require(data['route'] in ('person','form','unknown'),'INVALID_INPUT','Invalid route')
        refs('source',data['source_ids'])
        if data.get('person_id'):
            person=snapshot.get('person',data['person_id'])
            require(person['company_id']==data['company_id'],'IDENTITY_CONFLICT','Recipient must match case employer')
        if data['route']=='person':require(data.get('person_id'),'ROUTE_REQUIRED','Person route requires a person')
        if data['route']=='form':require(data.get('fallback_reason'),'FALLBACK_REASON_REQUIRED','Secondary form route requires contact-search gap')
        require(isinstance(data['tracks'],list) and data['tracks'],'TRACK_REQUIRED','Case needs selected track rationale')
        for track in data['tracks']:
            require(set(track)=={'id','rationale'},'INVALID_INPUT','Track association requires id/rationale')
            snapshot.get('track',track['id']);text(track['rationale'],'rationale',8192)
        explicit=snapshot.one('SELECT * FROM cases WHERE id=?',(data.get('id'),)) if data.get('id') else None
        if explicit:
            require(explicit['company_id']==data['company_id'] and explicit['kind']==data['kind'],'IDENTITY_CONFLICT','Use a separate reviewed case for a different employer/opportunity kind',409)
            if explicit['opportunity_id']:
                original=snapshot.one('SELECT * FROM opportunities WHERE id=?',(explicit['opportunity_id'],))
                require(not data.get('canonical_url') or data['canonical_url']==original['canonical_url'],'IDENTITY_CONFLICT','Exact opportunity URL differs; retain original case and capture/reconcile the new role separately',409)
                require(not data.get('requisition') or data['requisition']==original['requisition'],'IDENTITY_CONFLICT','Exact employer requisition differs',409)
        opportunity=None
        if data['kind']!='speculative':
            require(data.get('requisition') or data.get('canonical_url'),'IDENTITY_REQUIRED','Exact role needs requisition or canonical URL')
            if data.get('canonical_url'):safe_route('website',data['canonical_url'])
            matches=snapshot.rows('SELECT * FROM opportunities WHERE (company_id=? AND requisition=? AND requisition IS NOT NULL) OR (canonical_url=? AND canonical_url IS NOT NULL)',(data['company_id'],data.get('requisition'),data.get('canonical_url')))
            require(len({r['id'] for r in matches})<=1,'IDENTITY_AMBIGUOUS','Identity keys refer to different opportunities')
            if matches:
                require(matches[0]['company_id']==data['company_id'],'IDENTITY_CONFLICT','Canonical URL belongs to another employer')
                require(not data.get('canonical_url') or not matches[0]['canonical_url'] or data['canonical_url']==matches[0]['canonical_url'],'IDENTITY_AMBIGUOUS','Different URL requires explicit evidenced identity reconciliation',409)
                opportunity=matches[0]['id']
                existing=snapshot.one('SELECT id FROM cases WHERE opportunity_id=?',(opportunity,))
                if existing and not data.get('id'):data=dict(data,id=existing['id'])
            else:
                opportunity=new_id('opportunity')
                sql('INSERT INTO opportunities VALUES (?,?,?,?,?,?)',opportunity,data['company_id'],data['kind'],data['title'],data.get('requisition'),data.get('canonical_url'))
        record_id,version,old=capture('case','case')
        require(not old or old['company_id']==data['company_id'],'IDENTITY_CONFLICT','Cannot change case employer')
        require(not old or old['opportunity_id']==opportunity,'IDENTITY_CONFLICT','Cannot retarget an existing case to another exact opportunity',409)
        essential_unknowns=data.get('essential_unknowns',json.loads(old['detail']).get('essential_unknowns',[]) if old else [])
        require(isinstance(essential_unknowns,list) and len(essential_unknowns)<=25,'INVALID_INPUT','Essential unknowns must be bounded')
        for unknown in essential_unknowns:
            require(isinstance(unknown,dict) and set(unknown)=={'code','subject','message','source_ids'},'INVALID_INPUT','Essential unknown requires code/subject/message/source_ids')
            for field in ('code','subject','message'):text(unknown[field],field,2048)
            refs('source',unknown['source_ids'])
        require(not essential_unknowns or data.get('essential_policy','unknown')=='unknown','INVALID_INPUT','Unresolved essentials cannot be declared verified or failed')
        data=dict(data,essential_unknowns=essential_unknowns)
        semantic=digest({key:data.get(key) for key in ('company_id','title','kind','route','person_id','fallback_reason','essential_policy','essential_unknowns','tracks')})
        old_detail=json.loads(old['detail']) if old else {}
        semantic_version=old_detail.get('semantic_version',1)+(1 if old and old_detail.get('semantic_sha256')!=semantic else 0)
        require(data.get('essential_policy','unknown') in ('unknown','passed','failed'),'INVALID_INPUT','Essential policy must be unknown/passed/failed')
        sql('INSERT INTO cases(id,version,company_id,opportunity_id,title,kind,route,person_id,detail) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,title=excluded.title,route=excluded.route,person_id=excluded.person_id,detail=excluded.detail',
            record_id,version,data['company_id'],opportunity,data['title'],data['kind'],data['route'],data.get('person_id'),canonical(dict(source_ids=data['source_ids'],fallback_reason=data.get('fallback_reason'),essential_policy=data.get('essential_policy','unknown'),essential_unknowns=essential_unknowns,semantic_version=semantic_version,semantic_sha256=semantic)))
        if opportunity:sql('UPDATE opportunities SET title=? WHERE id=?',data['title'],opportunity)
        sql('DELETE FROM case_tracks WHERE case_id=?',record_id)
        for track in data['tracks']:sql('INSERT INTO case_tracks VALUES (?,?,?)',record_id,track['id'],track['rationale'])
    elif intent in ('case.note','case.close','case.reopen'):
        case=snapshot.get('case',data['case_id']);saved.append(case['id']);kinds.append('case')
        if intent=='case.note':
            text(data['text'],'text',65536,empty=True);sql('UPDATE cases SET notes=?,version=version+1 WHERE id=?',data['text'],case['id'])
        elif intent=='case.close':
            text(data['reason'],'reason',8192);evidence(data['evidence'])
            sql('UPDATE cases SET closed=1,closure=?,version=version+1 WHERE id=?',canonical(dict(reason=data['reason'],evidence=data['evidence'])),case['id'])
        else:
            text(data['reason'],'reason',8192);sql('UPDATE cases SET closed=0,closure=NULL,version=version+1 WHERE id=?',case['id'])
    elif intent=='packet.create':
        case=snapshot.get('case',data['case_id'])
        record_id,version,old=capture('packet','packet')
        require(not old,'ALREADY_EXISTS','Packet identity already exists')
        require(data['purpose'] in ('application','referral','contact','interview'),'INVALID_INPUT','Unsupported packet purpose')
        person_id=data.get('person_id',case['person_id'])
        if person_id:require(snapshot.get('person',person_id)['company_id']==case['company_id'],'IDENTITY_CONFLICT','Recipient employer differs')
        sql('INSERT INTO packets VALUES (?,?,?,?,?,NULL)',record_id,1,case['id'],person_id,data['purpose'])
        sql('INSERT OR IGNORE INTO case_selections VALUES (?,?)',case['id'],record_id)
    elif intent=='packet.save':
        packet=snapshot.get('packet',data['packet_id'])
        require(isinstance(data['documents'],list) and 1<=len(data['documents'])<=6,'INVALID_INPUT','Packet requires 1..6 documents')
        dialogue_source_ids=set()
        names=set()
        for document in data['documents']:
            require(isinstance(document,dict) and set(document)=={'slot','text'} and document['slot'] in ('resume','message','dossier','answers','interview','notes'), 'INVALID_INPUT','Document requires declared slot and text')
            if document['slot']=='interview':
                from .interview import validate_interview_text
                dialogue=validate_interview_text(document['text'],lambda source_id:snapshot.get('source',source_id))
                if dialogue:dialogue_source_ids.update(source_id for turn in dialogue['turns'] for source_id in turn['source_ids'])
            require(document['slot'] not in names,'INVALID_INPUT','Duplicate document slot');names.add(document['slot'])
            text(document['text'],'document text',262144)
        source_version_id=data.get('source_version_id') or packet['selected_version_id']
        if source_version_id and not data.get('review'):
            previous=snapshot.get('version',source_version_id)
            require(previous['packet_id']==packet['id'],'IDENTITY_CONFLICT','Source version belongs to another packet')
            data=dict(data,used_claim_ids=list(set(data['used_claim_ids'])|set(json.loads(previous['used_claim_ids']))),
                      answer_ids=list(set(data.get('answer_ids',[]))|set(json.loads(previous['answer_ids']))),source_version_id=source_version_id)
        claims=refs('claim',data['used_claim_ids']);answers=refs('answer',data.get('answer_ids',[]))
        applicable=snapshot.applicable_answers(packet['case_id'])
        answers=list({a['id']:a for a in [*answers,*applicable]}.values())
        data=dict(data,answer_ids=[a['id'] for a in answers])
        from .binary import contact_checks
        issues.extend(contact_checks(data['documents'],applicable))
        review=data.get('review')
        numeric_case=snapshot.get('case',packet['case_id'])
        numeric_tracks=[row['track_id'] for row in snapshot.rows('SELECT track_id FROM case_tracks WHERE case_id=?',(packet['case_id'],))]
        numeric_answers=[answer for answer in answers if snapshot.public_answer(answer,numeric_tracks,numeric_case)['value_reusable_here']]
        numeric_entities,numeric_sources=snapshot.numeric_context(packet['case_id'],claims,packet['person_id'])
        numeric_audit={}
        issues.extend(mechanical_review(data['documents'],claims,review,numeric_answers,numeric_entities,numeric_sources,numeric_audit))
        for claim in claims:
            support=snapshot.one('SELECT 1 FROM claim_sources cs JOIN sources s ON s.id=cs.source_id WHERE cs.claim_id=? AND s.readable=1 AND length(trim(s.excerpt))>0 LIMIT 1',(claim['id'],))
            if not support:issues.append(issue('SOURCE_UNREADABLE','Used claim has no readable supporting observation; save actual confirming evidence separately',claim['id']))
        if review and 'resume' in names:
            overlay={entry['claim_id']:entry for entry in review['coverage']}
            base_id=review.get('base_coverage_version_id')
            if base_id:
                base_version=snapshot.get('version',base_id)
                base_review=snapshot.one('SELECT detail FROM reviews WHERE version_id=?',(base_id,))
                require(base_review,'COVERAGE_BASE_MISSING','Base resume coverage must be reviewed')
                base_detail=json.loads(base_review['detail'])
                require(not base_detail.get('issues'),'COVERAGE_BASE_CONDITIONAL','Conditional coverage cannot serve as approved base')
                # No copying of unchanged base audit arrays into every target overlay.
                baseline=snapshot.effective_coverage(base_id)
                effective=dict(baseline);effective.update(overlay)
                from .policy import coverage_issues
                issues.extend(coverage_issues(data['documents'],claims,dict(review,coverage=list(effective.values())),numeric_entities,numeric_sources))
                used=set(data['used_claim_ids'])
                for claim_id,entry in baseline.items():
                    choice=overlay.get(claim_id,entry)
                    if choice['disposition'] in ('included','condensed') and claim_id not in used:
                        issues.append(issue('COVERAGE_GAP','Supported base achievement disappeared without a specific overlay disposition',claim_id))
                for row in snapshot.rows('SELECT * FROM dependencies WHERE version_id=? AND kind="claim"',(base_id,)):
                    current=snapshot.get('claim',row['record_id'])
                    if current['version']!=row['record_version'] and current['id'] not in overlay:
                        issues.append(issue('COVERAGE_BASE_STALE','Changed base claim needs a current overlay disposition',current['id']))
            else:
                # Initial base audit is explicitly proportional; subsequent target overlays reuse it.
                for claim in snapshot.rows('SELECT id,detail FROM claims WHERE disclosure="allowed" AND confirmation="confirmed" AND contradicted=0'):
                    if json.loads(claim['detail']).get('kind','achievement')=='achievement' and claim['id'] not in overlay:
                        issues.append(issue('COVERAGE_GAP','Meaningful achievement lacks included/condensed/excluded disposition',claim['id']))
        version_id=new_id('version');ordinal=snapshot.one('SELECT coalesce(max(ordinal),0)+1 AS n FROM packet_versions WHERE packet_id=?',(packet['id'],))['n']
        if data.get('source_version_id'):require(snapshot.get('version',data['source_version_id'])['packet_id']==packet['id'],'IDENTITY_CONFLICT','Source version belongs to another packet')
        sql('INSERT INTO packet_versions VALUES (?,?,?,?,?,?,?)',version_id,packet['id'],ordinal,now(),canonical(data['used_claim_ids']),canonical(data.get('answer_ids',[])),data.get('source_version_id'))
        for document in data['documents']:
            obj=add_object(document['text'].encode());sql('INSERT INTO slots VALUES (?,?,?)',version_id,document['slot'],obj['id'])
        for claim in claims:
            dependency(version_id,'claim',claim,'content-review')
            for source in snapshot.rows('SELECT s.* FROM sources s JOIN claim_sources cs ON s.id=cs.source_id WHERE cs.claim_id=?',(claim['id'],)):
                # OR IGNORE avoids repeating a shared source dependency.
                statements.append(('INSERT OR IGNORE INTO dependencies VALUES (?,?,?,?,?)',[version_id,'source',source['id'],source['version'],'content-review']))
        for answer in answers:
            dependency(version_id,'answer',answer,'mechanical-contact' if answer['meaning'].startswith('contact.') else 'eligibility')
            if answer['valid_until']:guards.append(answer['valid_until'])
        numeric_refs={(entry['reference']['kind'],entry['reference']['record_id']) for entry in numeric_audit.get('occurrences',[]) if entry['role']=='reference'}
        for kind,record_id in sorted(numeric_refs):
            record=snapshot.get(kind,record_id)
            statements.append(('INSERT OR IGNORE INTO dependencies VALUES (?,?,?,?,?)',[version_id,kind,record_id,record['version'],'entity-reference']))
        for source in refs('source',sorted(dialogue_source_ids)):dependency(version_id,'source',source,'interview-reference')
        target=snapshot.get('case',packet['case_id'])
        target_detail=json.loads(target['detail'])
        dependency(version_id,'case',dict(target,version=target_detail.get('semantic_version',1)),'eligibility')
        target_sources=refs('source',target_detail['source_ids'])
        if not any(source['readable'] and source['excerpt'].strip() for source in target_sources):issues.append(issue('SOURCE_UNREADABLE','Target has no readable role/need evidence'))
        for source in target_sources:statements.append(('INSERT OR IGNORE INTO dependencies VALUES (?,?,?,?,?)',[version_id,'source',source['id'],source['version'],'content-review']))
        for track in snapshot.rows('SELECT t.* FROM tracks t JOIN case_tracks ct ON ct.track_id=t.id WHERE ct.case_id=?',(packet['case_id'],)):
            dependency(version_id,'track',track,'eligibility')
        if packet['person_id']:
            person=snapshot.get('person',packet['person_id']);dependency(version_id,'person',person,'qualification')
            expiry=json.loads(person['detail']).get('valid_until')
            if expiry:guards.append(expiry)
        if review:
            sql('INSERT INTO reviews VALUES (?,?,?,?,?)',new_id('review'),version_id,str(review['findings']),str(review['limitations']),canonical(dict(review,issues=issues,numeric_audit=numeric_audit)))
        sql('UPDATE packets SET selected_version_id=?,version=version+1 WHERE id=?',version_id,packet['id'])
        saved.extend([packet['id'],version_id]);kinds.extend(['packet','version']);selected_packets.append(packet['id'])
    elif intent=='artifact.attach':
        from .binary import extract_binary,check_conversion,contact_checks
        packet=snapshot.get('packet',data['packet_id']);selected=packet['selected_version_id']
        require(selected,'REVIEW_REQUIRED','Save selected source content before conversion')
        require(data['extension'] in ('docx','pdf') and data['slot'] in ('resume','message','answers'),'INVALID_INPUT','Unsupported converted slot/format')
        original=snapshot.one('SELECT * FROM slots WHERE version_id=? AND name=?',(selected,data['slot']))
        require(original and original['artifact_id']==data['source_artifact_id'],'SELECTION_CONFLICT','Conversion source must be the exact selected slot')
        artifact,source=snapshot.object(original['artifact_id'])
        require(artifact['media_type'] in ('text/markdown','text/plain'),'INVALID_INPUT','Convert from a selected text source')
        identifier(data['input_id']);require(data['input_id'].startswith('input_'),'INVALID_INPUT','Opaque staged input required')
        staged=contained(snapshot.root,'.career-agent/staging/'+data['input_id'])
        require(staged.is_file() and staged.stat().st_size<=25*1024*1024,'INPUT_MISSING','Staged binary missing or too large')
        extracted,extractor=extract_binary(staged,data['extension']);check_conversion(source.read_text(),extracted)
        issues.extend(contact_checks([dict(slot=data['slot'],text=extracted)],snapshot.applicable_answers(packet['case_id'])))
        require(not issues,'CONTACT_DISCLOSURE_BLOCKED','Converted bytes conflict with current contact/disclosure choice')
        binary=add_object(staged.read_bytes(),data['extension'],'application/pdf' if data['extension']=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        extracted_object=add_object(extracted.encode(),'txt','text/plain')
        sql('INSERT OR IGNORE INTO extraction_receipts VALUES (?,?,?,?,?)',binary['id'],artifact['id'],extractor,extracted_object['id'],binary['sha256'])
        old_version=snapshot.get('version',selected);version_id=new_id('version')
        ordinal=snapshot.one('SELECT max(ordinal)+1 AS n FROM packet_versions WHERE packet_id=?',(packet['id'],))['n']
        sql('INSERT INTO packet_versions VALUES (?,?,?,?,?,?,?)',version_id,packet['id'],ordinal,now(),old_version['used_claim_ids'],old_version['answer_ids'],selected)
        for slot in snapshot.rows('SELECT * FROM slots WHERE version_id=?',(selected,)):
            sql('INSERT INTO slots VALUES (?,?,?)',version_id,slot['name'],binary['id'] if slot['name']==data['slot'] else slot['artifact_id'])
        sql('INSERT INTO dependencies SELECT ?,kind,record_id,record_version,purpose FROM dependencies WHERE version_id=?',version_id,selected)
        previous_review=snapshot.one('SELECT * FROM reviews WHERE version_id=?',(selected,))
        if previous_review:sql('INSERT INTO reviews VALUES (?,?,?,?,?)',new_id('review'),version_id,previous_review['findings'],previous_review['limitations'],previous_review['detail'])
        sql('UPDATE packets SET selected_version_id=?,version=version+1 WHERE id=?',version_id,packet['id'])
        saved.extend([packet['id'],version_id,binary['id']]);kinds.extend(['packet','version','artifact']);selected_packets.append(packet['id'])
    elif intent=='packet.primary':
        packet=snapshot.get('packet',data['packet_id'])
        sql('INSERT INTO case_selections VALUES (?,?) ON CONFLICT(case_id) DO UPDATE SET packet_id=excluded.packet_id',packet['case_id'],packet['id'])
        saved.extend([packet['id'],packet['case_id']]);kinds.extend(['packet','case'])
    elif intent=='packet.select':
        packet=snapshot.get('packet',data['packet_id']);version=snapshot.get('version',data['version_id'])
        require(version['packet_id']==packet['id'],'IDENTITY_CONFLICT','Version belongs to another packet')
        sql('UPDATE packets SET selected_version_id=?,version=version+1 WHERE id=?',version['id'],packet['id'])
        saved.append(packet['id']);kinds.append('packet');selected_packets.append(packet['id'])
    elif intent=='batch.save':
        require(data['task'] in ('contacts','search','research','packets','interview','job_search'),'INVALID_INPUT','Unsupported task')
        require(type(data['requested_count']) is int and 0<data['requested_count']<=100,'INVALID_INPUT','requested_count must be 1..100')
        require(data['count_unit'] in ('people','cases'),'INVALID_INPUT','Count unit must be people or cases')
        require(data['task']!='job_search' or data['count_unit']=='cases','INVALID_INPUT','Original job search counts cases')
        refs('track',data['track_ids']);refs('person' if data['count_unit']=='people' else 'case',data['selected_ids'])
        text(data['criterion'],'criterion',8192)
        require(isinstance(data['required_outputs'],list) and set(data['required_outputs'])<={'csv','xlsx','profile','snapshot'},'INVALID_INPUT','Required outputs must be supported derived view formats')
        predicate=data.get('predicate',dict(kind='qualified_people' if data['count_unit']=='people' else 'evidenced_cases' if data['task']=='research' else 'prepared_cases',essential_policy='no_confirmed_failure'))
        expected_kind='qualified_people' if data['count_unit']=='people' else 'evidenced_cases' if data['task']=='research' else 'prepared_cases'
        require(isinstance(predicate,dict) and set(predicate)=={'kind','essential_policy'} and predicate['kind']==expected_kind and predicate['essential_policy'] in ('no_confirmed_failure','verified_pass'),'INVALID_CRITERION','Predicate must match the task/count contract and supported eligibility rule')
        parent_id=data.get('parent_id')
        if parent_id:
            parent=snapshot.get('batch',parent_id)
            require(parent['task']=='job_search' and data['task']!='job_search' and set(data['track_ids'])<=set(json.loads(parent['track_ids'])),'SCOPE_CONFLICT','Child must retain the original job-search track scope')
            if data['count_unit']=='cases':
                accumulated=list(dict.fromkeys(json.loads(parent['selected_ids'])+data['selected_ids']))
                require(len(accumulated)<=100,'LIMIT_EXCEEDED','Original job-search selection exceeds 100 cases')
                sql('UPDATE batches SET selected_ids=? WHERE id=?',canonical(accumulated),parent_id)
        for selected_id in set(data['selected_ids']):issues.extend(snapshot.batch_scope_issues(data,selected_id))
        record_id=data.get('id') or new_id('batch');saved.append(record_id);kinds.append('batch')
        if parent_id:saved.append(parent_id)
        previous=snapshot.one('SELECT * FROM batches WHERE id=?',(record_id,))
        if previous:
            same=(previous['task']==data['task'] and previous['requested_count']==data['requested_count'] and previous['count_unit']==data['count_unit'] and set(json.loads(previous['track_ids']))==set(data['track_ids']) and previous['criterion']==data['criterion'] and set(json.loads(previous['required_outputs']))==set(data['required_outputs']) and json.loads(previous['detail']).get('predicate',predicate)==predicate and json.loads(previous['detail']).get('parent_id')==parent_id)
            require(same,'BATCH_CONTRACT_CONFLICT','Create a distinct batch when changing scope, quota or criterion',409)
        sql('INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET selected_ids=excluded.selected_ids',record_id,data['task'],data['requested_count'],data['count_unit'],canonical(data['track_ids']),data['criterion'],canonical(list(dict.fromkeys(data['selected_ids']))),canonical(data['required_outputs']),canonical(dict(budget=data.get('budget'),predicate=predicate,parent_id=parent_id)))
    elif intent=='activity.record':
        case=snapshot.get('case',data['case_id']);timestamp(data['occurred_at']);evidence(data['evidence'])
        allowed=('sent','uncertain','not_sent','receipt','human_reply','interview','offer','rejection','bounce','withdrawal','referral_agreed','referral_performed','coverage')
        require(data['kind'] in allowed,'INVALID_INPUT','Unsupported activity kind')
        unresolved=snapshot.rows('SELECT a.id FROM activities a WHERE a.case_id=? AND a.kind="uncertain" AND NOT EXISTS(SELECT 1 FROM activities b WHERE b.resolves_activity_id=a.id)',(case['id'],))
        resolves=data.get('resolves_activity_id')
        if resolves:
            old=snapshot.get('activity',resolves)
            require(old['case_id']==case['id'] and old['kind']=='uncertain' and data['kind'] in ('sent','not_sent'), 'INVALID_RECONCILIATION','Reconciliation must resolve same-case uncertain action')
            require(data['occurred_at']==old['occurred_at'],'OCCURRENCE_CONFLICT','Reconciliation preserves original action time')
        if data['kind'] in ('sent','uncertain'):
            require(not unresolved or resolves in {r['id'] for r in unresolved},'UNKNOWN_EXTERNAL_OUTCOME','Resolve uncertain outcome before another transmission',409)
            packet=snapshot.get('packet',data.get('packet_id',''))
            version=snapshot.get('version',data.get('version_id',''))
            require(packet['case_id']==case['id'] and version['packet_id']==packet['id'],'SELECTION_CONFLICT','Actual report requires exact same-case packet bytes')
            if resolves:
                require(old['packet_id']==data.get('packet_id') and old['version_id']==data.get('version_id'),'SELECTION_CONFLICT','Reconciliation must preserve original transmitted pins')
            if data['kind']=='sent' and packet['selected_version_id']==data['version_id']:
                selection=snapshot.selection(packet['id'])
                if not selection['assessment']['prepared']:issues.append(issue('SENT_UNREVIEWED','Actual report retained; selected packet was not currently prepared',case['id']))
        channel=data.get('channel')
        if channel:
            require(isinstance(channel,dict) and set(channel)=={'kind','value'},'INVALID_INPUT','Actual channel requires kind/value')
            safe_route(channel['kind'],channel['value'])
        if data.get('related_activity_id'):
            related=snapshot.get('activity',data['related_activity_id']);require(related['case_id']==case['id'],'IDENTITY_CONFLICT','Related activity belongs to another case')
            if not channel:channel=json.loads(related['detail']).get('channel')
        if data['kind'] in ('sent','uncertain') and not channel and packet.get('person_id') and packet['selected_version_id']==data.get('version_id'):
            current=snapshot.contact(packet['person_id'])
            binding=snapshot.one('SELECT record_version FROM dependencies WHERE version_id=? AND kind="person" AND record_id=?',(data['version_id'],packet['person_id']))
            if current['route'] and binding and binding['record_version']==current['version']:channel={key:current['route'][key] for key in ('kind','value')}
        if data['kind']=='bounce' and channel:
            sql('UPDATE channels SET suppressed=1 WHERE kind=? AND value=? AND person_id IN(SELECT id FROM persons WHERE company_id=?)',channel['kind'],channel['value'],case['company_id'])
        record_id=new_id('activity');saved.extend([record_id,case['id']]);kinds.extend(['activity','case'])
        sql('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',record_id,case['id'],data['kind'],data['occurred_at'],now(),data['evidence'],data.get('packet_id'),data.get('version_id'),resolves,canonical(dict(coverage=data.get('coverage'),channel=channel,related_activity_id=data.get('related_activity_id'))))
    elif intent=='permission.record':
        require(data['status'] in ('active','revoked','consumed'),'INVALID_INPUT','Invalid permission status')
        evidence(data['evidence']);text(data['purpose'],'purpose',200)
        require(isinstance(data['scope'],dict) and data['scope'],'SCOPE_REQUIRED','Permission requires exact scope')
        if data.get('expires_at'):timestamp(data['expires_at'])
        record_id=data.get('id') or new_id('permission');saved.append(record_id);kinds.append('permission')
        sql('INSERT INTO permissions VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status',record_id,data['purpose'],canonical(data['scope']),data['status'],data['evidence'],data.get('expires_at'),int(data.get('one_time',True)))
    elif intent=='research.control':
        require(data['status'] in ('active','paused','revoked'),'INVALID_INPUT','Invalid research status')
        require(isinstance(data['scope'],dict) and set(data['scope'])=={'track_ids','purpose'},'SCOPE_REQUIRED','Research requires exact track_ids and purpose')
        refs('track',data['scope']['track_ids']);text(data['scope']['purpose'],'purpose',200);evidence(data['evidence'])
        if data.get('expires_at'):timestamp(data['expires_at'])
        sql('UPDATE research SET status=?,scope=?,evidence=?,expires_at=?',data['status'],canonical(data['scope']),data['evidence'],data.get('expires_at'));kinds.append('research')
    else:
        raise CareerError('UNKNOWN_INTENT','Unsupported intent')
    affected=set()
    if intent.startswith('case.'):
        affected.update([data.get('case_id') or (saved[0] if saved else None)])
    if intent.startswith(('packet.','artifact.')):
        if intent=='packet.create':affected.add(data['case_id'])
        elif data.get('packet_id'):affected.add(snapshot.get('packet',data['packet_id'])['case_id'])
    if intent=='activity.record':
        affected.add(data['case_id'])
        if data['kind']=='bounce' and channel:
            affected.update(r['id'] for r in snapshot.rows('SELECT DISTINCT c.id FROM cases c JOIN channels ch ON ch.person_id=c.person_id WHERE c.company_id=? AND ch.kind=? AND ch.value=? UNION SELECT DISTINCT c.id FROM cases c JOIN packets p ON p.case_id=c.id JOIN channels ch ON ch.person_id=p.person_id WHERE c.company_id=? AND ch.kind=? AND ch.value=?',(case['company_id'],channel['kind'],channel['value'])*2))
    if intent=='company.capture':
        affected.update(r['id'] for r in snapshot.rows('SELECT id FROM cases WHERE company_id=?',(saved[0],)))
    if intent in ('contact.capture','contact.suppress'):
        affected.update(r['id'] for r in snapshot.rows('SELECT id FROM cases WHERE person_id=?',(saved[0],)))
        affected.update(r['case_id'] for r in snapshot.rows('SELECT case_id FROM packets WHERE person_id=?',(saved[0],)))
    if intent in ('claim.save','source.capture','track.save','answer.save'):
        changed_kind={'claim.save':'claim','source.capture':'source','track.save':'track','answer.save':'answer'}[intent]
        affected.update(r['case_id'] for r in snapshot.rows('SELECT DISTINCT p.case_id FROM dependencies d JOIN packet_versions v ON v.id=d.version_id JOIN packets p ON p.id=v.packet_id WHERE d.kind=? AND d.record_id=?',(changed_kind,saved[0])))
        if intent=='source.capture':
            affected.update(r['id'] for r in snapshot.rows("SELECT DISTINCT c.id FROM cases c JOIN persons p ON p.id=c.person_id WHERE EXISTS(SELECT 1 FROM json_each(p.detail,'$.sources') o WHERE json_extract(o.value,'$.source_id')=?) OR EXISTS(SELECT 1 FROM channels ch WHERE ch.person_id=p.id AND ch.source_id=?) UNION SELECT DISTINCT pk.case_id AS id FROM packets pk JOIN persons p ON p.id=pk.person_id WHERE EXISTS(SELECT 1 FROM json_each(p.detail,'$.sources') o WHERE json_extract(o.value,'$.source_id')=?) OR EXISTS(SELECT 1 FROM channels ch WHERE ch.person_id=p.id AND ch.source_id=?)",(saved[0],)*4))
        if intent=='answer.save':
            scope=data['scope']
            candidates=snapshot.rows('SELECT c.id FROM cases c WHERE (? IS NULL OR c.company_id=?) AND (? IS NULL OR c.id=?) AND (? IS NULL OR EXISTS(SELECT 1 FROM case_tracks ct WHERE ct.case_id=c.id AND ct.track_id=?))',
                (scope.get('company_id'),scope.get('company_id'),scope.get('case_id'),scope.get('case_id'),scope.get('track_id'),scope.get('track_id')))
            if data['meaning'].startswith('contact.') or data['meaning']=='compensation.floor':affected.update(r['id'] for r in candidates)
    affected.discard(None)
    return dict(statements=statements,objects=objects,saved_ids=saved,kinds=list(set(kinds)),issues=issues,
                outcome='partial' if issues else 'satisfied',time_guards=guards,selected_packet_ids=selected_packets,affected_case_ids=list(affected))


def timestamp(value):
    require(isinstance(value,str),'INVALID_TIMESTAMP','Timestamp must be an ISO8601 string')
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        require(parsed.tzinfo is not None,'INVALID_TIMESTAMP','Timestamp requires timezone')
    except ValueError as error:
        raise CareerError('INVALID_TIMESTAMP','Expected ISO8601 timestamp with timezone') from error
    return parsed



def projection_policy_identity():
    """Fingerprint loaded policy code without installation paths or unrelated modules."""
    import types
    from .policy import contact_issues,answer_scope_matches
    from .binary import contact_checks
    def signature(code):
        constants=[]
        for value in code.co_consts:
            if isinstance(value,types.CodeType):constants.append(signature(value))
            elif isinstance(value,bytes):constants.append(value.hex())
            elif isinstance(value,(str,int,float,bool,type(None),tuple)):constants.append(value)
            else:constants.append(type(value).__name__)
        return dict(bytecode=code.co_code.hex(),constants=constants,names=code.co_names)
    return digest([signature(fn.__code__) for fn in (Snapshot.selection,Snapshot.case_summary,Snapshot.eligibility,Snapshot.readable_target,Snapshot.public_answer,Snapshot.applicable_answers,Snapshot.contact,contact_issues,answer_scope_matches,contact_checks)])


DELIVERY_INDEXES = {
    'answers_disposition': 'CREATE INDEX IF NOT EXISTS answers_disposition ON answers(disposition)',
    'batches_task': 'CREATE INDEX IF NOT EXISTS batches_task ON batches(task,id)',
    'packets_person': 'CREATE INDEX IF NOT EXISTS packets_person ON packets(person_id,id)',
    'activities_packet_kind': 'CREATE INDEX IF NOT EXISTS activities_packet_kind ON activities(packet_id,kind)'
}
