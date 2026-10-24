PRAGMA foreign_keys=ON;
CREATE TABLE workspace(id TEXT PRIMARY KEY, format TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0), display_name TEXT NOT NULL, conversation_language TEXT NOT NULL);
CREATE TABLE app_preferences(singleton INTEGER PRIMARY KEY CHECK(singleton=1),theme TEXT NOT NULL CHECK(theme IN ('system','light','dark')),ui_locale TEXT NOT NULL DEFAULT 'en',introduction_shown INTEGER NOT NULL DEFAULT 0 CHECK(introduction_shown IN(0,1)));
CREATE TABLE objects(id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, extension TEXT NOT NULL, size INTEGER NOT NULL, media_type TEXT NOT NULL, UNIQUE(sha256,extension));
CREATE TABLE sources(id TEXT PRIMARY KEY,version INTEGER NOT NULL,locator TEXT NOT NULL,excerpt TEXT NOT NULL,observed_at TEXT NOT NULL,readable INTEGER NOT NULL,detail TEXT NOT NULL);
CREATE TABLE claims(id TEXT PRIMARY KEY,version INTEGER NOT NULL,assertion TEXT NOT NULL,meaning TEXT NOT NULL,confirmation TEXT NOT NULL,disclosure TEXT NOT NULL,contradicted INTEGER NOT NULL,detail TEXT NOT NULL);
CREATE TABLE claim_sources(claim_id TEXT REFERENCES claims(id),source_id TEXT REFERENCES sources(id),PRIMARY KEY(claim_id,source_id));
CREATE TABLE tracks(id TEXT PRIMARY KEY,version INTEGER NOT NULL,name TEXT NOT NULL,positioning TEXT NOT NULL,selected INTEGER NOT NULL,language TEXT NOT NULL,policies TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE answers(id TEXT PRIMARY KEY,version INTEGER NOT NULL,meaning TEXT NOT NULL,scope TEXT NOT NULL,units TEXT NOT NULL,disposition TEXT NOT NULL,value TEXT NOT NULL,evidence TEXT NOT NULL,valid_from TEXT,valid_until TEXT);
CREATE INDEX answer_scope ON answers(meaning,scope,units);
CREATE TABLE companies(id TEXT PRIMARY KEY,version INTEGER NOT NULL,name TEXT NOT NULL,domain TEXT UNIQUE,detail TEXT NOT NULL);
CREATE TABLE persons(id TEXT PRIMARY KEY,version INTEGER NOT NULL,name TEXT NOT NULL,company_id TEXT REFERENCES companies(id),affiliation TEXT NOT NULL,relevance TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE channels(id TEXT PRIMARY KEY,person_id TEXT NOT NULL REFERENCES persons(id),kind TEXT NOT NULL,value TEXT NOT NULL,source_id TEXT REFERENCES sources(id),suppressed INTEGER NOT NULL DEFAULT 0,UNIQUE(person_id,kind,value));
CREATE TABLE opportunities(id TEXT PRIMARY KEY,company_id TEXT NOT NULL REFERENCES companies(id),kind TEXT NOT NULL,title TEXT NOT NULL,requisition TEXT,canonical_url TEXT,UNIQUE(company_id,requisition),UNIQUE(canonical_url));
CREATE TABLE cases(id TEXT PRIMARY KEY,version INTEGER NOT NULL,company_id TEXT NOT NULL REFERENCES companies(id),opportunity_id TEXT UNIQUE REFERENCES opportunities(id),title TEXT NOT NULL,kind TEXT NOT NULL,route TEXT NOT NULL,person_id TEXT REFERENCES persons(id),closed INTEGER NOT NULL DEFAULT 0,closure TEXT,notes TEXT NOT NULL DEFAULT '',detail TEXT NOT NULL);
CREATE TABLE case_tracks(case_id TEXT REFERENCES cases(id),track_id TEXT REFERENCES tracks(id),rationale TEXT NOT NULL,PRIMARY KEY(case_id,track_id));
CREATE TABLE packets(id TEXT PRIMARY KEY,version INTEGER NOT NULL,case_id TEXT NOT NULL REFERENCES cases(id),person_id TEXT REFERENCES persons(id),purpose TEXT NOT NULL,selected_version_id TEXT REFERENCES packet_versions(id));
CREATE TABLE packet_versions(id TEXT PRIMARY KEY,packet_id TEXT NOT NULL REFERENCES packets(id),ordinal INTEGER NOT NULL,created_at TEXT NOT NULL,used_claim_ids TEXT NOT NULL,answer_ids TEXT NOT NULL,source_version_id TEXT REFERENCES packet_versions(id),UNIQUE(packet_id,ordinal));
CREATE TABLE slots(version_id TEXT REFERENCES packet_versions(id),name TEXT NOT NULL,artifact_id TEXT NOT NULL REFERENCES objects(id),PRIMARY KEY(version_id,name));
CREATE TABLE reviews(id TEXT PRIMARY KEY,version_id TEXT NOT NULL UNIQUE REFERENCES packet_versions(id),findings TEXT NOT NULL,limitations TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE dependencies(version_id TEXT NOT NULL REFERENCES packet_versions(id),kind TEXT NOT NULL,record_id TEXT NOT NULL,record_version INTEGER NOT NULL,purpose TEXT NOT NULL,PRIMARY KEY(version_id,kind,record_id,purpose));
CREATE INDEX reverse_dependencies ON dependencies(kind,record_id);
CREATE TABLE activities(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(id),kind TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL,evidence TEXT NOT NULL,packet_id TEXT REFERENCES packets(id),version_id TEXT REFERENCES packet_versions(id),resolves_activity_id TEXT REFERENCES activities(id),detail TEXT NOT NULL);
CREATE INDEX case_activities ON activities(case_id,occurred_at);
CREATE TABLE permissions(id TEXT PRIMARY KEY,purpose TEXT NOT NULL,scope TEXT NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL,expires_at TEXT,one_time INTEGER NOT NULL);
CREATE TABLE research(singleton INTEGER PRIMARY KEY CHECK(singleton=1),status TEXT NOT NULL,scope TEXT NOT NULL,evidence TEXT NOT NULL,expires_at TEXT);
CREATE TABLE batches(id TEXT PRIMARY KEY,task TEXT NOT NULL,requested_count INTEGER NOT NULL,count_unit TEXT NOT NULL,track_ids TEXT NOT NULL,criterion TEXT NOT NULL,selected_ids TEXT NOT NULL,required_outputs TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE record_history(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,record_id TEXT NOT NULL,version INTEGER NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL);
CREATE TABLE plans(id TEXT PRIMARY KEY,request_id TEXT NOT NULL,command_hash TEXT NOT NULL,base_revision INTEGER NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE commands(request_id TEXT PRIMARY KEY,command_hash TEXT NOT NULL,revision INTEGER NOT NULL,receipt TEXT NOT NULL);
CREATE TABLE change_log(cursor INTEGER PRIMARY KEY,revision INTEGER NOT NULL,kinds TEXT NOT NULL,ids TEXT NOT NULL,projection_keys TEXT NOT NULL);
CREATE TABLE view_exports(kind TEXT PRIMARY KEY,revision INTEGER NOT NULL,sha256 TEXT NOT NULL,path TEXT NOT NULL);
CREATE TABLE extraction_receipts(artifact_id TEXT PRIMARY KEY REFERENCES objects(id),source_artifact_id TEXT NOT NULL REFERENCES objects(id),extractor TEXT NOT NULL,extracted_artifact_id TEXT NOT NULL REFERENCES objects(id),binary_hash TEXT NOT NULL);

CREATE TABLE locale_catalogs(locale TEXT PRIMARY KEY,version INTEGER NOT NULL,artifact_id TEXT NOT NULL REFERENCES objects(id));

CREATE TABLE case_selections(case_id TEXT PRIMARY KEY REFERENCES cases(id),packet_id TEXT NOT NULL REFERENCES packets(id));
CREATE INDEX packets_case ON packets(case_id);
CREATE INDEX activities_case_kind ON activities(case_id,kind);
CREATE INDEX activities_resolution ON activities(resolves_activity_id);
CREATE INDEX cases_person ON cases(person_id);
CREATE INDEX cases_company ON cases(company_id);
CREATE INDEX case_tracks_track ON case_tracks(track_id,case_id);
CREATE TABLE case_projection_cache(case_id TEXT PRIMARY KEY REFERENCES cases(id),column_key TEXT NOT NULL,closed INTEGER NOT NULL,search_text TEXT NOT NULL,person_id TEXT,qualified INTEGER NOT NULL,body TEXT NOT NULL,expires_at TEXT);
CREATE INDEX case_projection_filter ON case_projection_cache(closed,column_key,case_id);
CREATE INDEX case_projection_expiry ON case_projection_cache(expires_at);

CREATE INDEX IF NOT EXISTS slots_artifact ON slots(artifact_id,version_id);

CREATE INDEX IF NOT EXISTS packets_person ON packets(person_id,id);
CREATE INDEX IF NOT EXISTS activities_packet_kind ON activities(packet_id,kind);

CREATE INDEX IF NOT EXISTS batches_task ON batches(task,id);

CREATE INDEX IF NOT EXISTS answers_disposition ON answers(disposition);
