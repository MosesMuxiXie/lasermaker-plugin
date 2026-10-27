"""Compact read-only status without printing canonical geometry from the event log."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
summary = root.parent/(root.name+'-summary.json')
if summary.exists():
    print(summary.read_text(encoding='utf-8'))
else:
    log = root.parent/(root.name+'-events.jsonl')
    with log.open('rb') as stream:
        stream.seek(0, 2)
        end = stream.tell()
        stream.seek(max(0, end-1024*1024))
        lines = stream.read().decode('utf-8', errors='replace').splitlines()
    result = {}
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if 'last_tool' not in result and 'tool' in item:
            result.update(last_tool=item['tool'], cycle=item['cycle'], session=item['session'],
                          is_error=item['is_error'], at=item['at'])
        if 'completed_cycles' in item:
            result.update({k:v for k,v in item.items() if k not in ('result',)})
            break
    print(json.dumps(result, ensure_ascii=False))
