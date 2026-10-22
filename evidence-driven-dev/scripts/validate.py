#!/usr/bin/env python3
"""Use the same validator as the CLI and hooks; no second state authority."""
import sys
from edd import main

if __name__ == '__main__':
    sys.exit(main(['validate', *sys.argv[1:]]))
