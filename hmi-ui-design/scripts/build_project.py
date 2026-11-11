"""Build a portable HTML/editor/native-copy session from one project source."""
from pathlib import Path
import argparse, json
from project_source import SKILL, load, save_json
from prepare_editor_session import prepare
from create_editor_launcher import add_runtime

def build(source_file, out, port=18767, allow_copy=False, binding_mode='unbound'):
    source, catalog, coverage = load(source_file)
    out = Path(out)
    if out.resolve().is_relative_to(SKILL.resolve()):
        raise ValueError('Build the project outside the installed skill directory')
    if out.exists():
        raise ValueError('Use a new output batch; existing sources/sessions are retained')
    out.mkdir(parents=True)
    save_json(out / 'coverage.json', coverage)
    text_reports = [{'page_id': p['id'], 'page_name': p['name'], **p['model']['text_layout_report']} for p in catalog['pages']]
    save_json(out / 'text-layout.json', {'pages': text_reports, 'status': 'fail' if any(r['errors'] for r in text_reports) else 'pass'})
    if any(r['errors'] for r in text_reports):
        raise ValueError('文字适配有裁切、缺字体、越界或新碰撞；调整源布局后使用新批次。详见 ' + str(out / 'text-layout.json'))
    if coverage['status'] == 'fail':
        raise ValueError('Content coverage failed; see ' + str(out / 'coverage.json'))
    (out / 'source').mkdir()
    save_json(out / 'source/project.json', source)
    save_json(out / 'pages.json', catalog)
    session = prepare(None, out / 'session', port=port, allow_copy=allow_copy, pages_path=out / 'pages.json', binding_mode=binding_mode)
    add_runtime(out, 'session/session.json')
    save_json(out / 'build-report.json', {'source_sha256': coverage['source_sha256'], 'coverage': coverage['status'],
              'pages': [{'id': p['id'], 'name': p['name'], 'components': len(p['model']['components'])} for p in catalog['pages']],
              'session': 'session/session.json', 'launcher': 'open-editor.cmd', 'native_application': 'not_run',
              'preview_only_behaviors': coverage['preview_only_behaviors']})
    return session

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--port', type=int, default=18767); p.add_argument('--allow-copy', action='store_true')
    p.add_argument('--binding-mode', choices=['unbound','names'], default='unbound')
    a = p.parse_args()
    try:
        print(build(a.source, a.out, a.port, a.allow_copy, a.binding_mode))
    except (ValueError, OSError, KeyError, TypeError) as error:
        p.exit(1, str(error) + '\n')
