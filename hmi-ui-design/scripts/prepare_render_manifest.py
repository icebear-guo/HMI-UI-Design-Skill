"""Derive capture sizes/filenames from delivery data, instead of maintaining them twice."""
import argparse
import json
from pathlib import Path
import re


def prepare(project_path, output):
    project_path, output = Path(project_path).resolve(), Path(output).absolute()
    root = project_path.parent
    if output.parent.resolve() != root:
        raise ValueError('Write the manifest beside the project config so relative source paths stay valid')
    project = json.loads(project_path.read_text(encoding='utf-8-sig'))
    if project.get('schema_version') != 'hmi-render-project/1.0':
        raise ValueError('Expected hmi-render-project/1.0')
    relative = Path(project['delivery_manifest'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Delivery input must stay within the project')
    delivery = json.loads((root / relative).read_text(encoding='utf-8-sig'))
    derived = output.with_name(output.stem + '.delivery.json')
    png_dir = output.stem + '_png'
    if output.exists() or derived.exists():
        raise ValueError('Manifest and derived delivery paths must be new')
    captures = project['captures']
    rows, names = [], set()
    for kind, items in (('assets', delivery['assets']), ('pages', delivery['pages'])):
        mappings = captures.get(kind, {})
        if set(mappings) != {item['id'] for item in items}:
            raise ValueError(kind + ' capture IDs must exactly match delivery IDs')
        for item in items:
            mapping = dict(mappings[item['id']])
            if set(mapping) - {'html', 'selector', 'fragment', 'brand_selector', 'collect_hmi'}:
                raise ValueError('Capture map defines source/selectors only; sizes come from delivery data')
            if not mapping.get('html') or not mapping.get('selector'):
                raise ValueError('Capture html/selector required')
            source = (root / mapping['html']).resolve()
            if not source.is_relative_to(root) or not source.is_file():
                raise ValueError('Missing or out-of-project source HTML')
            size = item['design_size_px']
            if not isinstance(size, list) or len(size) != 2 or any(type(x) is not int or x < 1 for x in size):
                raise ValueError('Direct 1:1 export requires positive integer design sizes')
            file = re.sub(r'[^A-Za-z0-9_]', '_', item['id']) + ('_preview' if kind == 'pages' else '') + '.png'
            if not re.fullmatch(r'[A-Za-z0-9_]+\.png', file) or file.casefold() in names:
                raise ValueError('Use unique renderer-safe PNG basenames')
            names.add(file.casefold())
            item['file' if kind == 'assets' else 'preview'] = png_dir + '/' + file
            row = dict(mapping, id=item['id'], width=size[0], height=size[1], file=file)
            if kind == 'pages':
                row['role'] = 'page_preview'
                if not row.get('brand_selector'):
                    raise ValueError('Each page needs its visible company label selector')
            rows.append(row)
    manifest = {'schema_version':'component-render/1.0', 'browser':project['browser'],
                'company_name':delivery.get('company_name'),
                'software_rendering':project.get('software_rendering',False), 'components':rows}
    if 'optimization' in project:
        manifest['optimization'] = project['optimization']
    with output.open('x',encoding='utf-8') as stream:
        json.dump(manifest,stream,ensure_ascii=False,indent=2)
    with derived.open('x',encoding='utf-8') as stream:
        json.dump(delivery,stream,ensure_ascii=False,indent=2)
    return {'status':'pass','captures':len(rows),'manifest':str(output),
            'delivery_manifest':str(derived),'png_output_dir':str(root/png_dir),
            'scope':'render manifest derived from delivery geometry; no customer approval or PNG generated'}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    args=ap.parse_args()
    try:
        print(json.dumps(prepare(args.project,args.out),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:
        ap.exit(1,str(error)+'\n')
