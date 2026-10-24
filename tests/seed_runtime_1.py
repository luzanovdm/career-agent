#!/usr/bin/env python3
"""Populate a disposable fictional 1.0 integration workspace; not a forward evaluator."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_runtime_1 import Fixture

if __name__=='__main__':
    fixture=Fixture(sys.argv[1]).seed()
    print(json.dumps(fixture.tasks.context(),indent=2))
