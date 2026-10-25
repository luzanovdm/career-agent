#!/usr/bin/env python3
"""Prepare a typed, rebuildable view of retained unlinked historical observations.

This maintenance utility does not create activities, role links or permissions.
Normal application reads consume the typed derived projection, not legacy JSON.
Use the installed workspace Python for execution; no network behavior is included.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

FORMAT = 'career-agent.history-observation/1'
BUNDLE_FORMAT = 'career-agent.history-projection/1'
MAX_RECORDS = 100000
MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_TEXT = 32768


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def _text(record, key, nullable=False):
    value = record.get(key)
    if value is None and nullable:
        return None
    if value is None:
        return ''
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ValueError('Historical '+key+' must be bounded text; no value was truncated')
    return value


def normalize_history_record(record, record_history_id):
    """Preserve one physical observation without guessing its role or date identity."""
    if not isinstance(record, dict) or type(record_history_id) is not int or record_history_id < 1:
        raise ValueError('A retained object and positive physical record ID are required')
    precision = record.get('date_precision', 'unknown')
    if precision not in ('exact', 'approximate', 'unknown'):
        raise ValueError('Unrecognized historical date precision; source retained unchanged')
    return dict(
        format=FORMAT,
        id='observation_'+digest('legacy:history_imports:'+str(record_history_id))[:24],
        original_status=_text(record, 'status') or 'unknown',
        event_kind=_text(record, 'event_kind') or 'unknown',
        evidence_level=_text(record, 'evidence_level') or 'unknown',
        employer=_text(record, 'employer'),
        role=_text(record, 'role'),
        role_url=_text(record, 'role_url', True),
        date=dict(text=_text(record, 'date_text'), precision=precision,
                  occurred_at=_text(record, 'occurred_at', True)),
        channel=_text(record, 'channel'),
        evidence=_text(record, 'evidence', True),
        source=dict(record_history_id=record_history_id, sha256=digest(record),
                    locator=_text(record, 'source_locator'), kind=_text(record, 'source_kind')),
        historical_opportunity_reference=_text(record, 'opportunity_id', True),
        provider_message_id=_text(record, 'provider_message_id', True),
        provider_thread_id=_text(record, 'provider_thread_id', True),
        case_id=None, scope='unlinked', canonical_activity_created=False,
    )


def prepare_projection(repository):
    """Take one owner snapshot and bind every normalized observation to original bytes."""
    with repository.open() as snapshot:
        if not hasattr(snapshot, 'retained_history_sources'):
            raise ValueError('Installed runtime does not provide the history projection owner')
        rows = snapshot.retained_history_sources()
        if len(rows) > MAX_RECORDS:
            raise ValueError('Retained history exceeds the projection record bound')
        rows = sorted(rows, key=lambda row: row['id'])
        items = []
        fingerprint = []
        input_bytes = 0
        projected_bytes = 0
        for row in rows:
            if not isinstance(row['body'], str) or len(row['body'].encode()) > 1024*1024:
                raise ValueError('Retained history record exceeds the input bound')
            input_bytes += len(row['body'].encode())
            if input_bytes > MAX_BUNDLE_BYTES:
                raise ValueError('Retained history exceeds the input byte bound')
            record = json.loads(row['body'])
            item = normalize_history_record(record, row['id'])
            projected_bytes += len(canonical(item).encode())
            if projected_bytes > MAX_BUNDLE_BYTES:
                raise ValueError('Historical projection exceeds the byte bound; nothing was applied')
            items.append(item)
            fingerprint.append(dict(record_history_id=row['id'], sha256=digest(record)))
        result = dict(format=BUNDLE_FORMAT, workspace_id=snapshot.workspace_id,
                      revision=snapshot.revision, source_fingerprint=digest(fingerprint), items=items)
    if len(canonical(result).encode()) > MAX_BUNDLE_BYTES:
        raise ValueError('Historical projection exceeds the byte bound; nothing was applied')
    return result


def _contained(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Installed release requires a contained relative path')
    result = root
    for part in path.parts:
        result = result / part
        if result.is_symlink():
            raise ValueError('Installed release path cannot contain symlinks')
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Installed release escaped its workspace')
    return result


def installed_repository(workspace):
    """Verify active application bytes before importing the installed SQL owner."""
    root = Path(workspace).absolute()
    if root.is_symlink():
        raise ValueError('Workspace must not be a symlink')
    active = _contained(root, '.career-agent/active.json')
    if not active.is_file() or active.stat().st_size > 65536:
        raise ValueError('An installed workspace is required')
    locator = json.loads(active.read_text())
    if not locator['release_dir'].startswith('.career-agent/releases/'):
        raise ValueError('Installed locator has an invalid release location')
    release = _contained(root, locator['release_dir'])
    manifest_path = _contained(release, 'RELEASE.json')
    raw = manifest_path.read_bytes()
    if digest(raw) != locator['manifest_sha256']:
        raise ValueError('Installed release manifest changed')
    manifest = json.loads(raw)
    python = _contained(release, manifest['python_executable'])
    if Path(sys.executable).resolve() != python.resolve():
        raise ValueError('Run this utility with this workspace release Python and -I -B')
    for name, record in manifest['files'].items():
        if not name.startswith(('runtime/career/', 'bin/')):
            continue
        path = _contained(release, name)
        if not path.is_file() or path.stat().st_size != record['size'] or digest(path.read_bytes()) != record['sha256']:
            raise ValueError('Installed application bytes changed')
    sys.path.insert(0, str(release/'runtime'))
    from career.installation import verified_active
    verified_active(root)
    from career.repository import Repository
    return Repository(root)


def apply_projection(repository, bundle, expected_source_fingerprint):
    if not isinstance(expected_source_fingerprint, str) or not re.fullmatch('[a-f0-9]{64}', expected_source_fingerprint):
        raise ValueError('An exact reviewed source fingerprint is required for apply')
    if bundle.get('format') != BUNDLE_FORMAT or bundle.get('source_fingerprint') != expected_source_fingerprint:
        raise ValueError('Reviewed projection fingerprint does not match; nothing was applied')
    if not hasattr(repository, 'cache_historical_observations'):
        raise ValueError('Installed runtime does not provide the history projection cache owner')
    return repository.cache_historical_observations(bundle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output', help='New private projection file; preparation never overwrites a file')
    parser.add_argument('--input', help='Previously reviewed private projection file for apply')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-source-fingerprint')
    args = parser.parse_args(argv)
    try:
        if bool(args.output) == bool(args.input):
            raise ValueError('Choose exactly one new --output or reviewed --input file')
        if args.input and not args.apply:
            raise ValueError('--input is only used with explicit --apply')
        if args.apply and not args.expected_source_fingerprint:
            raise ValueError('--apply requires --expected-source-fingerprint from review')
        repository = installed_repository(args.workspace)
        if args.input:
            path = Path(args.input)
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
                raise ValueError('Projection input must be a bounded regular file')
            bundle = json.loads(path.read_text())
        else:
            bundle = prepare_projection(repository)
            destination = Path(args.output).absolute()
            if destination.exists() or destination.is_symlink():
                raise ValueError('Projection destination already exists; nothing was overwritten')
            descriptor = os.open(destination, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                stream.write(canonical(bundle)); stream.flush(); os.fsync(stream.fileno())
        result = dict(prepared=True, applied=False, workspace_id=bundle['workspace_id'], revision=bundle['revision'],
                      observations=len(bundle['items']), source_fingerprint=bundle['source_fingerprint'],
                      canonical_activities_created=0, external_actions=dict(performed=0))
        if args.apply:
            result['cache_result'] = apply_projection(repository, bundle, args.expected_source_fingerprint)
            result['applied'] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps(dict(error=dict(code='HISTORY_PROJECTION_FAILED', message=str(error)))), file=sys.stderr)
        return 2
    except Exception as error:
        # The installed owner reports stale revision/fingerprint and other domain
        # refusals using its typed error; do not mask unrelated programming errors.
        if hasattr(error, 'wire') and callable(error.wire):
            print(json.dumps(error.wire()), file=sys.stderr)
            return 2
        raise


if __name__ == '__main__':
    raise SystemExit(main())
