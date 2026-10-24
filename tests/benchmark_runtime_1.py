#!/usr/bin/env python3
"""Reproducible synthetic performance fixture; direct SQL is fixture setup only."""
import argparse
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.contracts import canonical
from career.repository import Repository
from career.facade import Tasks


def create(root,count=10000):
    Repository.initialize(root,'Performance Example')
    repo=Repository(root);obj=repo.publish(b'Fictional supported contribution.');db=repo.connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO objects VALUES (?,?,?,?,?)',tuple(obj[k] for k in ('id','sha256','extension','size','media_type')))
        db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?)',('source_bench',1,'https://benchmark.example/team','Fictional current professional team and supported contribution.','2026-10-24T00:00:00Z',1,'{}'))
        db.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?)',('claim_bench',1,'Fictional supported contribution.','Fictional supported contribution.','confirmed','allowed',0,'{}'))
        for i in range(6):db.execute('INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)',('track_'+str(i),1,'Track '+str(i),'Fictional profession-neutral positioning.',1,'en','{}','{}'))
        for i in range(100):db.execute('INSERT INTO companies VALUES (?,?,?,?,?)',('company_'+str(i),1,'Demo Company '+str(i),'company-'+str(i)+'.example','{}'))
        for i in range(count):
            suffix=str(i).zfill(6);person='person_'+suffix;case='case_'+suffix;packet='packet_'+suffix;version='version_'+suffix;company='company_'+str(i%100)
            db.execute('INSERT INTO persons VALUES (?,?,?,?,?,?,?)',(person,1,'Professional Example '+suffix,company,'current','A useful colleague.',canonical(dict(sources=[dict(source_id='source_bench',axes=['identity','affiliation','relevance'],assessment='supports')],valid_until=None))))
            db.execute('INSERT INTO channels VALUES (?,?,?,?,?,0)',('channel_'+suffix,person,'profile','https://benchmark.example/team/'+suffix,'source_bench'))
            db.execute('INSERT INTO cases(id,version,company_id,title,kind,route,person_id,detail) VALUES (?,?,?,?,?,?,?,?)',(case,1,company,'Fictional role '+suffix,'speculative','person',person,canonical(dict(source_ids=['source_bench'],essential_policy='unknown'))))
            db.execute('INSERT INTO case_tracks VALUES (?,?,?)',(case,'track_'+str(i%6),'Supported distinct track rationale.'))
            db.execute('INSERT INTO packets VALUES (?,?,?,?,?,NULL)',(packet,1,case,person,'application'))
            db.execute('INSERT INTO packet_versions VALUES (?,?,?,?,?,?,NULL)',(version,packet,1,'2026-10-24T00:00:00Z','["claim_bench"]','[]'))
            for name in ('resume','message','dossier','interview'):db.execute('INSERT INTO slots VALUES (?,?,?)',(version,name,obj['id']))
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('review_'+suffix,version,'Synthetic concrete review.','Benchmark fixture is not semantic acceptance.',canonical(dict(issues=[]))))
            db.execute('INSERT INTO dependencies VALUES (?,?,?,?,?)',(version,'claim','claim_bench',1,'content-review'))
            db.execute('UPDATE packets SET selected_version_id=? WHERE id=?',(version,packet))
            db.execute('INSERT INTO case_selections VALUES (?,?)',(case,packet))
            db.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)',('activity_'+suffix,case,'sent' if i%3==0 else 'receipt','2026-10-24T00:00:00Z','2026-10-24T00:00:00Z','Fictional benchmark report.',packet,version,None,'{}'))
        db.commit()
    finally:db.close()


def measure(root,runs=3):
    tasks=Tasks(root);timings={};payloads={}
    operations={'context':lambda:tasks.context(),'list':lambda:tasks.query('cases',limit=50),'filter':lambda:tasks.query('cases',limit=50,q='0000'),'detail':lambda:tasks.query('case',record_id='case_000001'),'contacts':lambda:tasks.query('contacts',limit=50)}
    for name,call in operations.items():
        samples=[]
        for _ in range(runs):
            started=time.perf_counter();result=call();samples.append((time.perf_counter()-started)*1000)
        timings[name]=dict(samples_ms=samples,p50_ms=statistics.median(samples),p95_ms=max(samples))
        payloads[name]=len(canonical(result).encode())
    return dict(hardware=platform.platform(),python=sys.version,sqlite=sqlite3.sqlite_version,method='wall-clock perf_counter; first sample cold connection, subsequent warm OS cache; p95 is max with small n',timings=timings,payload_bytes=payloads)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('workspace');parser.add_argument('--create',action='store_true');parser.add_argument('--count',type=int,default=10000);parser.add_argument('--runs',type=int,default=3);args=parser.parse_args()
    if args.create:create(args.workspace,args.count)
    print(json.dumps(measure(args.workspace,args.runs),indent=2))
