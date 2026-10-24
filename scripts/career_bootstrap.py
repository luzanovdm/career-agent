#!/usr/bin/env python3
"""Offline bootstrap exception. Career work subsequently uses installed code only."""
import argparse
import json
from career.installation import install_archive
from career.contracts import CareerError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive');parser.add_argument('--workspace',required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--ui-locale',default='en');parser.add_argument('--name');parser.add_argument('--language',default='en');args=parser.parse_args()
    try:
        result=install_archive(args.archive,args.workspace,args.sha256,args.name,args.language,args.ui_locale)
        print(json.dumps(result,indent=2));return 3 if result.get('code')=='IMPORT_REQUIRED' else 0
    except (CareerError,OSError,ValueError) as error:
        print(json.dumps(error.wire() if isinstance(error,CareerError) else {'error':str(error)}));return 2

if __name__=='__main__':raise SystemExit(main())
