"""Bounded CLI subprocess supervision for offline imports; no arbitrary process targets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from career.contracts import CareerError,require
from import_archive import write_report


def resident_bytes(process):
    # This child is not reaped until poll/wait: its PID cannot be recycled during observation.
    if sys.platform=='darwin':
        result=subprocess.run(['/bin/ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True,timeout=2)
        if process.poll() is not None:return 0
        require(result.returncode==0 and result.stdout.strip().isdigit(),'IMPORT_RESOURCE_OBSERVATION','Cannot observe the owned import worker RSS')
        return int(result.stdout.strip())*1024
    if sys.platform.startswith('linux'):
        status=Path('/proc')/str(process.pid)/'status'
        try:lines=status.read_text().splitlines()
        except FileNotFoundError:
            if process.poll() is not None:return 0
            raise CareerError('IMPORT_RESOURCE_OBSERVATION','Owned import worker disappeared during resource observation')
        for line in lines:
            if line.startswith('VmRSS:'):return int(line.split()[1])*1024
        if process.poll() is not None:return 0
    raise CareerError('IMPORT_RESOURCE_OBSERVATION','No supported resident-memory observer for this offline importer platform')


def supervise(script,arguments,destination,limits):
    """Sample only our live Popen child. Terminate/wait that owned child on budget failure."""
    require(not Path(destination).exists(),'UNSAFE_DESTINATION','Use an absent disposable destination; supervisor never writes to an existing workspace')
    environment=dict(os.environ,CAREER_IMPORT_WORKER=str(os.getpid()))
    process=subprocess.Popen([sys.executable,'-I','-B',str(script),*arguments,'--internal-worker'],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    started=time.monotonic();peak=0;failure=None
    try:
        while process.poll() is None:
            peak=max(peak,resident_bytes(process))
            require(peak<=limits.memory_bytes,'IMPORT_RESOURCE_LIMIT','Owned import worker exceeded the resident-memory budget')
            require(time.monotonic()-started<=limits.seconds,'IMPORT_RESOURCE_LIMIT','Owned import worker exceeded the elapsed-time budget')
            time.sleep(0.25)
    except Exception as error:
        failure=error
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    output,errors=process.communicate(timeout=10)
    observation=dict(memory_budget_bytes=limits.memory_bytes,elapsed_budget_seconds=limits.seconds,peak_observed_rss_bytes=peak,poll_interval_ms=250,elapsed_seconds=time.monotonic()-started,status='budget_failed' if failure else 'completed')
    root=Path(destination)
    if failure:
        # Never leave a just-completed report activatable after a resource budget failure.
        if root.exists():
            report=root/'Data/import-report.json'
            if report.exists():report.rename(report.with_name('import-report-before-resource-failure.json'))
            report.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            write_report(report,dict(format='career-agent.import/1',status='failed',strict_pass=False,activation_allowed=False,error_code=getattr(failure,'code','IMPORT_RESOURCE_OBSERVATION'),supervision=observation),limits)
        raise failure
    if (root/'Data').is_dir():write_report(root/'Data/import-supervision.json',observation,limits)
    if errors:sys.stderr.write(errors)
    sys.stdout.write(output)
    return process.returncode
