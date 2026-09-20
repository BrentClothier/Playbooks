#!/usr/bin/env python3
from pathlib import Path
import re

# Production cleanup for the known-good v53 stack.
# Keep behavior and error/critical guards unchanged, but demote historical success/diagnostic
# instrumentation from INFO/WARNING to DEBUG so normal *:Info logs remain readable.
MARKER = re.compile(r'V\\d+_(?:DIAG|FIX|COMPAT)')
ROOT = Path('src')
changed_files = 0
changed_calls = 0

for path in ROOT.rglob('*'):
    if not path.is_file() or path.suffix not in {'.cpp', '.h', '.inl'}:
        continue
    lines = path.read_text().splitlines(True)
    out = []
    i = 0
    file_changed = False
    while i < len(lines):
        line = lines[i]
        if 'LOG_INFO(' in line or 'LOG_WARNING(' in line:
            block = [line]
            j = i + 1
            while j < len(lines) and j < i + 20 and ');' not in ''.join(block):
                block.append(lines[j])
                j += 1
            text = ''.join(block)
            if MARKER.search(text):
                new_text = text.replace('LOG_INFO(', 'LOG_DEBUG(', 1).replace(
                    'LOG_WARNING(', 'LOG_DEBUG(', 1
                )
                if new_text != text:
                    out.append(new_text)
                    changed_calls += 1
                    file_changed = True
                    i = j
                    continue
        out.append(line)
        i += 1
    if file_changed:
        path.write_text(''.join(out))
        changed_files += 1

print(f'v54 cleanup: demoted {changed_calls} historical log calls across {changed_files} files')
