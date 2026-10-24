#!/usr/bin/env python3
"""Source build entrypoint. Production uses the verified installed bin/career launcher."""
from career.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
