"""CLI/HTTP application boundary. All adapters share this owner."""
from .contracts import Command, CareerError, digest, require
from .repository import Repository


class Tasks:
    def __init__(self, workspace):
        self.repository = Repository(workspace)

    def context(self,**filters):
        with self.repository.open() as snapshot:
            return snapshot.context(**filters)

    def plan(self, value):
        command = Command.parse(value)
        try:
            receipt = self.repository.status(command.request_id)
        except CareerError as error:
            if error.code != 'NOT_FOUND':
                raise
        else:
            with self.repository.open() as snapshot:
                stored = snapshot.command_hash(command.request_id)
                require(stored == digest(command.wire()), 'REQUEST_ID_CONFLICT','Request ID reused with different input',409)
            return dict(committed=True, receipt=receipt)
        with self.repository.open() as snapshot:
            require(snapshot.revision == command.expected_revision,'REVISION_CONFLICT','Refresh context and replan',409)
            plan = snapshot.plan_command(command)
            preview = snapshot.envelope(outcome=plan['outcome'], saved_ids=plan['saved_ids'],issues=plan['issues'])
        plan_id = self.repository.store_plan(command, plan)
        return dict(plan_id=plan_id, preview=preview)

    def apply(self, plan_id):
        return self.repository.apply(plan_id)

    def command(self, value):
        planned = self.plan(value)
        return planned['receipt'] if planned.get('committed') else self.apply(planned['plan_id'])

    def query(self,kind,**filters):
        if kind in ('cases','board'):self.repository.ensure_projection_cache()
        for attempt in range(2):
            with self.repository.open() as snapshot:result=self._query(snapshot,kind,filters)
            if kind not in ('cases','board') or not snapshot.integrity_changed:return result
        raise CareerError('MATERIAL_CHANGED','Selected files changed repeatedly during this bounded read')

    @staticmethod
    def _query(snapshot,kind,filters):
        if kind=='localization':return snapshot.localization(filters.get('locale'))
        if kind=='agent-intent':return snapshot.agent_intent(filters['intent'],filters.get('case_id'),filters.get('track_id'))
        if kind=='resolve-intent':return snapshot.resolve_intent(filters['descriptor'])
        if kind=='board':return snapshot.board_page(**filters)
        if kind=='cases':return snapshot.cases_page(**filters)
        if kind=='contacts':return snapshot.contacts_page(**filters)
        if kind=='case':return snapshot.case_detail(filters['record_id'])
        if kind=='selection':return snapshot.envelope(**snapshot.selection(filters['record_id']))
        if kind=='changes':return snapshot.changes(filters['after'])
        if kind=='research-check':return snapshot.research_check(filters.get('scope'))
        if kind=='assess':return snapshot.assess(filters['record_id'])
        raise CareerError('INVALID_QUERY','Unknown query')
