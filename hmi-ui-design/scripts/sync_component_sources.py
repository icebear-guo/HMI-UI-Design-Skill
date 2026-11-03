"""Update changed draft sources only; never deletes files or alters frozen reviews."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import uuid


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_file(root, value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Use nonempty relative POSIX file paths')
    parts = value.split('/')
    if any(p in ('', '.', '..') or re.search(r'[<>:"|?*\x00-\x1f]', p)
           or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',p,re.I)
           or p.endswith(('.', ' ')) for p in parts):
        raise ValueError('Unsafe source file path: ' + value)
    target = root.joinpath(*parts)
    for node in (target, *target.parents):
        if node.is_symlink() or node.is_junction():
            raise ValueError('Linked source paths are unsupported')
    return target


def sync(plan_path, draft_root, workflow=None):
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
    if plan.get('schema_version') != 'hmi-source-files/1.0' or not isinstance(plan.get('files'), list) or not plan['files']:
        raise ValueError('Expected hmi-source-files/1.0 with nonempty files')
    unresolved = Path(draft_root).absolute()
    for node in (unresolved, *unresolved.parents):
        if node.is_symlink() or node.is_junction():
            raise ValueError('Linked draft roots are unsupported')
    root = unresolved.resolve()
    frozen = []
    if workflow:
        record_path = Path(workflow).resolve()
        record = json.loads(record_path.read_text(encoding='utf-8-sig'))
        frozen = [(record_path.parent / stage['artifact_dir']).resolve()
                  for stage in record.get('stages', {}).values()
                  if stage.get('status') in ('confirmed', 'delegated')]
    state_path = safe_file(root, '.hmi-source-state.json')
    if state_path.exists() and any(root.is_relative_to(p) for p in frozen):
        raise ValueError('Confirmed/delegated review snapshots cannot be edited')
    old = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'files': []}
    entries, seen = [], set()
    # Validate the entire input before writing any source.
    for item in plan['files']:
        file = item.get('file')
        target = safe_file(root, file)
        if file.casefold() in seen or file.casefold() == '.hmi-source-state.json':
            raise ValueError('Duplicate or reserved source path: ' + file)
        seen.add(file.casefold())
        if not isinstance(item.get('content'), str):
            raise ValueError('Source content must be text')
        if any(target.is_relative_to(p) for p in frozen):
            raise ValueError('Refusing to modify a frozen review: ' + file)
        for field in ('component_ids', 'page_ids'):
            values = item.get(field, [])
            if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values):
                raise ValueError(field + ' must be an array of IDs')
        raw = item['content'].encode('utf-8')
        unchanged = target.is_file() and target.read_bytes() == raw
        entries.append((target, raw, {'file': file, 'sha256': digest(raw),
                        'component_ids': item.get('component_ids', []),
                        'page_ids': item.get('page_ids', []),
                        'status': 'unchanged' if unchanged else 'changed'}))
    root.mkdir(parents=True, exist_ok=True)
    for target, raw, item in entries:
        if item['status'] == 'unchanged':
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.writing-' + uuid.uuid4().hex)
        temp.write_bytes(raw)
        os.replace(temp, target)  # Replace only this changed, unfrozen draft file.
    rows = [item for _, _, item in entries]
    obsolete = sorted(x['file'] for x in old.get('files', []) if x['file'].casefold() not in seen)
    stable = {'schema_version': 'hmi-source-state/1.0',
              'files': [{k: v for k, v in x.items() if k != 'status'} for x in rows]}
    state_raw = (json.dumps(stable, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if not state_path.exists() or state_path.read_bytes() != state_raw:
        temp = state_path.with_name(state_path.name + '.writing-' + uuid.uuid4().hex)
        temp.write_bytes(state_raw)
        os.replace(temp, state_path)
    changed = [x for x in rows if x['status'] == 'changed']
    return {'status': 'pass', 'scope': 'draft_source_sync', 'files': rows,
            'changed_files': len(changed), 'unchanged_files': len(rows) - len(changed),
            'affected_component_ids': sorted({c for x in changed for c in x['component_ids']}),
            'affected_page_ids': sorted({p for x in changed for p in x['page_ids']}),
            'obsolete_files_preserved': obsolete, 'deleted_files': 0,
            'limitation': 'Declared impact hints are not proof; renderer dependency hashes decide asset reuse.'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan', required=True, type=Path)
    ap.add_argument('--draft-root', required=True, type=Path)
    ap.add_argument('--workflow', type=Path)
    args = ap.parse_args()
    try:
        print(json.dumps(sync(args.plan, args.draft_root, args.workflow), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        ap.exit(1, str(error) + '\n')
