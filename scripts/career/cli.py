"""Typed task CLI shared with the HTTP application adapter."""
import argparse
import json
from pathlib import Path
import sys
from .contracts import CareerError, VERSION, schema
from .facade import Tasks
from .repository import Repository


def parser():
    root=argparse.ArgumentParser(description=__doc__)
    root.add_argument('--workspace',required=True)
    root.add_argument('--version',action='version',version=VERSION)
    sub=root.add_subparsers(dest='operation',required=True)
    init=sub.add_parser('init');init.add_argument('--name',required=True);init.add_argument('--language',default='en');init.add_argument('--ui-locale',default='en')
    resolve=sub.add_parser('resolve-intent');resolve.add_argument('--input',default='-')
    stage=sub.add_parser('stage');stage.add_argument('file')
    context=sub.add_parser('context');context.add_argument('--task',choices=('profile','contacts','packets','history','interview'));context.add_argument('--case-id');context.add_argument('--track-id');context.add_argument('--source-id');context.add_argument('--claim-id');context.add_argument('--answer-id');context.add_argument('--cursor');context.add_argument('--limit',type=int,default=25)
    sub.add_parser('doctor');sub.add_parser('backup');sub.add_parser('research-check')
    contract=sub.add_parser('schema');contract.add_argument('intent',nargs='?')
    for op in ('plan','command'):
        entry=sub.add_parser(op);entry.add_argument('--input',default='-',help='Bounded JSON request file, or stdin')
    apply=sub.add_parser('apply');apply.add_argument('plan_id')
    status=sub.add_parser('command-status');status.add_argument('request_id')
    query=sub.add_parser('query');query.add_argument('kind',choices=('board','cases','contacts','contact-packets','versions','case-history','historical-observations','case','selection','changes','assess'))
    query.add_argument('--id',dest='record_id');query.add_argument('--version-id');query.add_argument('--limit',type=int,default=50);query.add_argument('--after',type=int,default=0);query.add_argument('--cursor');query.add_argument('--q',default='');query.add_argument('--view',choices=('board','table'),default='table');query.add_argument('--column');query.add_argument('--track-id');query.add_argument('--company-id');query.add_argument('--closed',action='store_true')
    deliver=sub.add_parser('deliver');deliver.add_argument('packet_id')
    render=sub.add_parser('render');render.add_argument('--format',choices=('csv','xlsx','profile','snapshot'),default='csv')
    ui=sub.add_parser('ui');ui.add_argument('action',choices=('open','status','stop','restart','serve'));ui.add_argument('--no-browser',action='store_true')
    app=sub.add_parser('app');app.add_argument('action',choices=('init','status','verify','update','rollback'));app.add_argument('--archive');app.add_argument('--sha256');app.add_argument('--name');app.add_argument('--ui-locale',default='en');app.add_argument('--language',default='en')
    return root


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        active=Path(args.workspace)/'.career-agent/active.json'
        if active.exists():
            locator=json.loads(active.read_text());release=Path(args.workspace)/locator['release_dir']
            if Path(__file__).resolve()!=(release/'runtime/career/cli.py').resolve():raise CareerError('INSTALLED_COPY_REQUIRED','Use the workspace installed .career-agent/career launcher')
            journal=Path(args.workspace)/'.career-agent/install-journal.json'
            if journal.exists() and json.loads(journal.read_text()).get('stage')=='switching':
                import os
                if os.environ.get('CAREER_AGENT_BOOTSTRAP')!=locator['release_id'] or args.operation not in ('context','init'):raise CareerError('BUSY','Verified code switch is completing; retry after installation',503)
        else:
            import os
            if os.environ.get('CAREER_AGENT_DEVELOPMENT')!='1':raise CareerError('INSTALLED_COPY_REQUIRED','Install a verified release; source CLI is available only in explicit development mode')
        if args.operation=='init':
            result=Repository.initialize(args.workspace,args.name,args.language,args.ui_locale)
        elif args.operation=='schema':
            result=schema(args.intent)
        elif args.operation=='ui':
            from .lifecycle import ui_command
            result=ui_command(args.workspace,args.action,not args.no_browser)
        elif args.operation=='app':
            from .installation import app_command
            if args.action in ('init','update'):
                from .installation import install_archive
                if not args.archive or not args.sha256:raise CareerError('ARCHIVE_REQUIRED','Approved complete archive and exact digest required')
                result=install_archive(args.archive,args.workspace,args.sha256,args.name,args.language,args.ui_locale)
            else:result=app_command(args.workspace,args.action)
        else:
            tasks=Tasks(args.workspace)
            if args.operation=='stage':
                from .repository import contained,new_id,digest
                source=Path(args.file);content=source.read_bytes()
                if len(content)>25*1024*1024:raise CareerError('LIMIT_EXCEEDED','Staged input exceeds 25 MiB')
                input_id=new_id('input');target=contained(tasks.repository.root,'.career-agent/staging/'+input_id)
                with target.open('xb') as stream:stream.write(content)
                target.chmod(0o600);result=dict(input_id=input_id,sha256=digest(content),size=len(content))
            elif args.operation=='context':result=tasks.context(task=args.task,case_id=args.case_id,track_id=args.track_id,source_id=args.source_id,claim_id=args.claim_id,answer_id=args.answer_id,limit=args.limit,cursor=args.cursor)
            elif args.operation=='doctor':result=tasks.repository.doctor()
            elif args.operation=='backup':result=tasks.repository.portable_export()
            elif args.operation=='research-check':result=tasks.query('research-check')
            elif args.operation in ('plan','command','resolve-intent'):
                content=sys.stdin.read(1024*1024+1) if args.input=='-' else Path(args.input).read_text()
                if len(content.encode())>1024*1024:raise CareerError('LIMIT_EXCEEDED','Request exceeds 1 MiB')
                result=tasks.query('resolve-intent',descriptor=json.loads(content)) if args.operation=='resolve-intent' else getattr(tasks,args.operation)(json.loads(content))
            elif args.operation=='apply':result=tasks.apply(args.plan_id)
            elif args.operation=='command-status':result=tasks.repository.status(args.request_id)
            elif args.operation=='query':
                filters={'limit':args.limit} if args.kind in ('contacts','cases') else {'after':args.after} if args.kind=='changes' else {'record_id':args.record_id}
                if args.kind in ('cases','board'):filters=dict(limit=args.limit,q=args.q,track_id=args.track_id,closed=args.closed)
                if args.kind=='cases':filters.update(cursor=args.cursor,view=args.view,column=args.column)
                if args.kind=='selection' and args.version_id:filters['version_id']=args.version_id
                if args.kind=='historical-observations':filters=dict(limit=args.limit,cursor=args.cursor)
                if args.kind in ('versions','case-history'):filters.update(limit=args.limit,cursor=args.cursor)
                if args.kind=='contact-packets':filters.update(limit=args.limit,cursor=args.cursor)
                if args.kind=='contacts':filters.update(cursor=args.cursor,q=args.q,company_id=args.company_id)
                result=tasks.query(args.kind,**filters)
            elif args.operation=='deliver':
                result=tasks.query('selection',record_id=args.packet_id);result['outcome']='satisfied' if result['assessment']['prepared'] and not result['assessment']['conditional'] else 'partial'
            elif args.operation=='render':
                from .views import render
                result=render(tasks.repository,args.format)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 3 if result.get('outcome')=='partial' or result.get('task_complete') is False or result.get('allowed') is False else 0
    except (CareerError,OSError,ValueError) as error:
        result=error.wire() if isinstance(error,CareerError) else {'error':{'code':'INVALID_INPUT','message':str(error),'issues':[]}}
        print(json.dumps(result),file=sys.stderr)
        return 2
