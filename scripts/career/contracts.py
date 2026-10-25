"""Public bounded task contracts. No SQL, filesystem or host providers."""
from dataclasses import dataclass
import hashlib
import json
import re

FORMAT = 'career-agent.workspace/1'
PROTOCOL = 'career-agent.local/1'
VERSION = '1.0.2'
MAX_ITEMS = 100


class CareerError(Exception):
    def __init__(self, code, message, status=422, issues=None):
        super().__init__(message)
        self.code, self.status, self.issues = code, status, issues or []

    def wire(self):
        return {'error': {'code': self.code, 'message': str(self), 'issues': self.issues}}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def issue(code, message, record_id=None):
    return dict(code=code, message=message, **({'record_id': record_id} if record_id else {}))


def require(condition, code, message, status=422):
    if not condition:
        raise CareerError(code, message, status)


def text(value, name, maximum=65536, empty=False):
    require(isinstance(value, str) and len(value) <= maximum and (empty or value.strip()),
            'INVALID_INPUT', name + ' must be bounded text')
    return value


def identifier(value):
    text(value, 'ID', 128)
    require(re.fullmatch(r'[A-Za-z0-9_-]+', value), 'INVALID_INPUT', 'Invalid ID')
    return value


@dataclass(frozen=True)
class Command:
    request_id: str
    expected_revision: int
    intent: str
    input: dict

    @classmethod
    def parse(cls, value):
        require(isinstance(value, dict) and set(value) == {'request_id', 'expected_revision', 'intent', 'input'},
                'INVALID_INPUT', 'Command requires request_id, expected_revision, intent and input')
        identifier(value['request_id'])
        require(type(value['expected_revision']) is int and value['expected_revision'] >= 0,
                'INVALID_INPUT', 'expected_revision must be a nonnegative integer')
        require(value['intent'] in SCHEMAS, 'UNKNOWN_INTENT', 'Unknown command intent')
        validate_input(value['intent'], value['input'])
        return cls(**value)

    def wire(self):
        return dict(request_id=self.request_id, expected_revision=self.expected_revision, intent=self.intent, input=self.input)


# Required and optional fields; operation-specific semantic checks belong to domain owners.
SCHEMAS = {
    'preferences.set': ([], ['theme','ui_locale','introduction_shown']),
    'locale.install': (['locale','plural_categories','messages'], []),
    'packet.primary': (['packet_id'], []),
    'profile.update': (['display_name', 'conversation_language'], []),
    'source.capture': (['locator', 'excerpt', 'observed_at', 'readable'], ['id', 'kind', 'published_at', 'precision', 'supports']),
    'claim.save': (['assertion', 'meaning', 'source_ids', 'confirmation', 'disclosure'], ['id', 'kind', 'metrics', 'contradicted', 'coverage_disposition']),
    'track.save': (['name', 'positioning', 'selected', 'language', 'policies'], ['id', 'claim_ids']),
    'answer.save': (['meaning', 'scope', 'units', 'disposition', 'value', 'evidence'], ['id', 'valid_from', 'valid_until','response_state']),
    'company.capture': (['name'], ['id', 'domain', 'source_ids']),
    'contact.suppress': (['person_id','kind','value','reason','evidence'], []),
    'contact.capture': (['name', 'company_id', 'affiliation', 'relevance', 'sources', 'route'], ['id', 'relationship', 'valid_until','track_rationales']),
    'case.capture': (['company_id', 'title', 'kind', 'route', 'tracks', 'source_ids'], ['id', 'requisition', 'canonical_url', 'person_id', 'fallback_reason', 'essential_policy','essential_unknowns']),
    'case.note': (['case_id', 'text'], []),
    'case.close': (['case_id', 'reason', 'evidence'], []),
    'case.reopen': (['case_id', 'reason'], []),
    'packet.create': (['case_id', 'purpose'], ['person_id', 'id']),
    'packet.save': (['packet_id', 'documents', 'used_claim_ids'], ['review', 'answer_ids', 'source_version_id']),
    'packet.select': (['packet_id', 'version_id'], []),
    'artifact.attach': (['packet_id','slot','input_id','source_artifact_id','extension'], []),
    'batch.save': (['task', 'requested_count', 'count_unit', 'track_ids', 'criterion', 'selected_ids', 'required_outputs'], ['id', 'budget','predicate','parent_id']),
    'activity.record': (['case_id', 'kind', 'occurred_at', 'evidence'], ['packet_id', 'version_id', 'resolves_activity_id', 'coverage','channel','related_activity_id']),
    'permission.record': (['purpose', 'scope', 'evidence', 'status'], ['id', 'expires_at', 'one_time']),
    'research.control': (['status', 'scope', 'evidence'], ['expires_at']),
}


def validate_input(intent, value):
    require(isinstance(value, dict), 'INVALID_INPUT', 'input must be an object')
    required, optional = SCHEMAS[intent]
    require(set(required) <= set(value) <= set(required + optional), 'INVALID_INPUT',
            'Expected fields for ' + intent + ': ' + ', '.join(required + optional))
    require(len(canonical(value).encode()) <= 1024 * 1024, 'LIMIT_EXCEEDED', 'Command exceeds 1 MiB')
    for key, entry in value.items():
        if isinstance(entry, list):
            require(len(entry) <= MAX_ITEMS, 'LIMIT_EXCEEDED', key + ' exceeds 100 items')


def schema(intent=None):
    from .command_schemas import describe
    return describe(intent)
