#!/usr/bin/env python3
"""Offline one-time importer. Source stays authoritative; no live switch or runtime fallback."""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from career.contracts import CareerError, canonical, digest, require
from career.repository import contained
from import_repository import ImportRepository as Repository


from import_archive import ImportLimits, inventory, file_hash, preserve_originals, verify_originals, write_report

def normalize_reference(source,path,value,materials,artifact_by_path):
    require(isinstance(value,dict),'UNKNOWN_REFERENCE','Reference is not an object')
    material_id=value.get('material_id')
    material=materials.get(material_id,{})
    if 'link_mode' in value and 'relative_target' in value:
        target=(path.parent/value['relative_target']).resolve()
        shape='relative-target'
    elif {'material_id','path','sha256','version'}<=set(value):
        target=(source/value['path']).resolve();shape='legacy-material-pin'
    else:raise CareerError('UNKNOWN_REFERENCE','Unrecognized attempt reference shape')
    require(target.is_relative_to(source.resolve()) and target.is_file(),'UNSAFE_REFERENCE','Reference target missing or outside restored source')
    sha=file_hash(target,ImportLimits().file_bytes);expected=value.get('sha256') or material.get('sha256')
    require(expected and sha==expected,'REFERENCE_HASH_MISMATCH','Historical pin does not match actual bytes')
    relative=target.relative_to(source.resolve()).as_posix()
    require(relative in artifact_by_path,'REFERENCE_MISSING','Reference target not inventoried')
    return dict(shape=shape,material_id=material_id,version=value.get('version',material.get('version')),sha256=sha,
                artifact_id=artifact_by_path[relative]['id'],original_path=path.relative_to(source).as_posix(),target_path=relative)


def migrate(source,destination,expected_state_sha256,allow_partial=False,limits=None):
    from dataclasses import asdict
    import resource,time,shutil
    limits=(limits or ImportLimits()).validate();started=time.monotonic()
    source=Path(source).absolute();destination=Path(destination).absolute()
    require(source.is_dir() and not source.is_symlink(),'UNSAFE_SOURCE','Source must be a regular restored directory')
    require(source!=destination and not destination.exists() and not destination.resolve().is_relative_to(source.resolve()),'UNSAFE_DESTINATION','Use an absent sibling disposable destination')
    state_path=contained(source,'Data/state.json')
    require(state_path.stat().st_size<=limits.state_bytes,'IMPORT_RESOURCE_LIMIT','Legacy state exceeds the explicit state byte limit')
    with state_path.open('rb') as stream:raw=stream.read(limits.state_bytes+1)
    require(len(raw)<=limits.state_bytes,'IMPORT_RESOURCE_LIMIT','Legacy state grew beyond the explicit state byte limit')
    state_sha=digest(raw);require(state_sha==expected_state_sha256,'SOURCE_CHANGED','Exact approved state fingerprint required')
    state=json.loads(raw);del raw
    require(isinstance(state,dict) and state.get('schema_version') in (1,2),'UNSUPPORTED_FORMAT','Importer supports explicit legacy schema1/2 only')
    require(len(state)<=limits.groups and sum(len(v) if isinstance(v,list) else 1 for v in state.values())<=limits.records,'IMPORT_RESOURCE_LIMIT','Legacy state exceeds group/record-count limits')
    before=inventory(source,limits);manifest_sha=digest(before);by_path={row['path']:row for row in before}
    required_free=sum(row.get('size',0) for row in before)*2+state_path.stat().st_size*4+256*1024*1024
    require(shutil.disk_usage(destination.parent).free>=required_free,'IMPORT_RESOURCE_LIMIT','Insufficient free space for conservative bounded archive/database staging')
    # An incomplete destination is blocked at bootstrap even if a later stage fails.
    (destination/'Data').mkdir(parents=True,mode=0o700)
    report_path=destination/'Data/import-report.json'
    report=dict(format='career-agent.import/1',status='in_progress',limits=asdict(limits),source_state_sha256=state_sha,source_authoritative=True,strict_pass=False,activation_allowed=False,quarantine=[])
    write_report(report_path,report,limits)
    try:
        Repository.initialize(destination,'Imported profile pending confirmation');repository=Repository(destination)
        originals,objects=preserve_originals(repository,source,before,limits)
        artifact_by_path={};quarantine=[row for row in before if row.get('status')=='quarantined']
        def register(relative):
            if relative in artifact_by_path:return artifact_by_path[relative]
            entry=by_path.get(relative)
            if not entry or entry.get('status')=='quarantined' or entry['size']>25*1024*1024:return None
            path=source/relative
            content=path.read_bytes();require(len(content)==entry['size'] and digest(content)==entry['sha256'],'SOURCE_CHANGED','Registered original changed after inventory')
            suffix=path.suffix.lstrip('.').lower()
            if not suffix.isalnum() or len(suffix)>12:suffix='bin'
            obj=repository.publish(content,suffix or 'bin',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            artifact_by_path[relative]=obj;objects.append(obj);return obj
        for row in state.get('materials',[]):
            if isinstance(row,dict):register(row.get('path',''))
        references=[];materials={row['id']:row for row in state.get('materials',[]) if isinstance(row,dict) and 'id' in row}
        sidecar_counts=dict(inspected=0,large_quarantined=0)
        for entry in before:
            relative=entry['path']
            if entry.get('status')=='quarantined' or not relative.endswith('.json') or not (relative.startswith('Applications/') or relative.endswith('.reference.json')):continue
            if entry['size']>limits.reference_bytes:
                disposition=dict(path=relative,status='quarantined',reason='REFERENCE_RESOURCE_LIMIT',sha256=entry['sha256']);references.append(disposition);quarantine.append(disposition);sidecar_counts['large_quarantined']+=1;continue
            sidecar_counts['inspected']+=1;path=source/relative
            try:value=json.loads(path.read_text())
            except (ValueError,UnicodeError):continue
            if isinstance(value,dict) and ('material_id' in value or 'relative_target' in value or 'link_mode' in value):
                try:
                    target=(path.parent/value['relative_target']).resolve() if 'relative_target' in value else (source/value.get('path','')).resolve()
                    if target.is_relative_to(source.resolve()):register(target.relative_to(source.resolve()).as_posix())
                    references.append(dict(status='resolved',**normalize_reference(source,path,value,materials,artifact_by_path)))
                except CareerError as error:
                    disposition=dict(path=relative,status='quarantined',reason=error.code,sha256=entry['sha256']);references.append(disposition);quarantine.append(disposition)
        result=repository.import_legacy_records(state,objects,artifact_by_path);quarantine.extend(result['quarantined_records'])
        require(digest(inventory(source,limits))==manifest_sha,'SOURCE_CHANGED','Source changed during import; destination is not accepted')
        archived_verification=verify_originals(repository,originals,before,limits)
        verified=repository.doctor()
        strict=not quarantine and verified['healthy']
        report.update(status='complete',source_revision=state.get('revision'),source_inventory_sha256=manifest_sha,source_files=before,originals_archive=dict(originals,verification=archived_verification),artifact_by_path=artifact_by_path,
            record_counts={key:len(value) for key,value in state.items() if isinstance(value,list)},mappings=result['mappings'],normalized_records=result.get('normalized_records',[]),archived_records=result.get('archived_records',[]),references=references,reference_search=dict(scope=['Applications/**/*.json','**/*.reference.json'],**sidecar_counts),quarantine=quarantine,
            activation_allowed=strict,strict_pass=strict,partial_accepted=allow_partial and not strict,database_revision=result['revision'],doctor=verified,
            resources=dict(conservative_free_space_required=required_free,elapsed_seconds=time.monotonic()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),input_bytes=sum(row.get('size',0) for row in before),entries=len(before)),
            rollback=dict(kind='discard-unactivated-destination',source_unchanged=True,later_writes_forbid_blind_rollback=True))
        write_report(report_path,report,limits)
        return dict(outcome='satisfied' if strict else 'partial',accepted=strict or allow_partial,**({} if strict or allow_partial else dict(code='IMPORT_QUARANTINED')),destination=str(destination),report=str(report_path),quarantined=len(quarantine),references=len(references),source_unchanged=True,activation_allowed=strict)
    except Exception as error:
        report.update(status='failed',strict_pass=False,activation_allowed=False,error_code=error.code if isinstance(error,CareerError) else type(error).__name__)
        write_report(report_path,report,limits);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--destination',required=True);parser.add_argument('--state-sha256',required=True);parser.add_argument('--allow-partial',action='store_true');parser.add_argument('--max-state-mib',type=int,default=256);parser.add_argument('--internal-worker',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
    try:
        limits=ImportLimits(state_bytes=args.max_state_mib*1024*1024).validate()
        if not args.internal_worker:
            from import_supervision import supervise
            return supervise(Path(__file__).resolve(),sys.argv[1:],args.destination,limits)
        require(os.environ.get('CAREER_IMPORT_WORKER')==str(os.getppid()),'IMPORT_RESOURCE_OBSERVATION','Internal worker requires the owning supervisor')
        result=migrate(args.source,args.destination,args.state_sha256,args.allow_partial,limits);print(json.dumps(result,indent=2));return 3 if result['outcome']=='partial' else 0
    except MemoryError:
        print(json.dumps({'error':{'code':'IMPORT_MEMORY_LIMIT','message':'Import exceeded the controlled process memory budget; partial destination remains unactivated'}}));return 2
    except (CareerError,OSError,ValueError) as error:
        print(json.dumps(error.wire() if isinstance(error,CareerError) else {'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
