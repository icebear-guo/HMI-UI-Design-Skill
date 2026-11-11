"""Compile one project source into the exact models used by HTML and native copy.

Coverage compares the separately declared content requirements with actual nodes.
It cannot discover requirements missing from both the brief and the source.
"""
from pathlib import Path
import base64, copy, hashlib, json, math, re, sys

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / 'assets/editor-kit'))
from model_validation import validate, svg_source
from text_layout import layout_model, REVISION as TEXT_LAYOUT_REVISION
from canvas_profile import dimensions, details as canvas_details

ID = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,31}\Z')
ROLES = {
    'static': {'label', 'picture'}, 'graphic': {'picture'},
    'reading': {'numeric_output', 'gauge', 'percentage_fill', 'realtime_trend'},
    'parameter': {'numeric_input'}, 'command': {'bit_switch'}, 'indicator': {'lamp'},
    'navigation': {'navigation'}, 'alarm_strip': {'alarm_strip'},
    'alarm_realtime': {'alarm_browser'}, 'alarm_history': {'alarm_browser'},
    'object': {'picture', 'label', 'numeric_output', 'numeric_input', 'bit_switch', 'lamp'},
}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

def typed(value, kind):
    return type(value) is bool if kind == 1 else number(value)

def local_file(root, value):
    need(isinstance(value, str) and value, 'Asset file needs a relative path')
    rel = Path(value)
    target = (root / rel).resolve()
    need(not rel.is_absolute() and target.is_relative_to(root.resolve()) and target.is_file(), 'Asset must be inside the project: ' + value)
    need(not any(p.is_symlink() or p.is_junction() for p in (root / rel, *(root / rel).parents)), 'Linked assets are unsupported')
    return target

def normalize_assets(source, root):
    result = copy.deepcopy(source)
    assets = result.get('assets', {})
    need(isinstance(assets, dict), 'assets must be an object')
    for ident, item in assets.items():
        need(bool(ID.fullmatch(ident)) and isinstance(item, dict), 'Asset ID/source invalid: ' + str(ident))
        if 'svg_file' in item:
            source_file = local_file(root, item['svg_file'])
            need(source_file.suffix.lower() == '.svg', 'Use svg_file for SVG only')
            svg = source_file.read_text(encoding='utf-8-sig')
        elif 'image_file' in item:
            source_file = local_file(root, item['image_file'])
            need(source_file.suffix.lower() in ('.png', '.jpg', '.jpeg'), 'Use PNG/JPEG images')
            from PIL import Image
            with Image.open(source_file) as image:
                w, h = image.size
            mime = 'png' if source_file.suffix.lower() == '.png' else 'jpeg'
            encoded = base64.b64encode(source_file.read_bytes()).decode('ascii')
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" href="data:image/{mime};base64,{encoded}"/></svg>'
        else:
            svg = item.get('svg')
        svg_source(svg)
        assets[ident] = {'svg': svg, 'sha256': hashlib.sha256(svg.encode('utf-8')).hexdigest()}
    return result

def preview_contract(node, variables):
    spec = node.get('preview')
    if spec is None:
        return
    need(node['kind'] in ('bit_switch', 'numeric_input'), 'Local effects belong to a command/input: ' + node['id'])
    need(isinstance(spec, dict) and set(spec) <= {'requires', 'on_press', 'on_release', 'on_toggle', 'on_commit'}, 'Unknown preview behavior: ' + node['id'])
    action = node.get('action', 'toggle')
    for phase, changes in spec.items():
        need(isinstance(changes, dict), 'Preview phase must contain variable assignments')
        if phase == 'on_commit':
            need(node['kind'] == 'numeric_input', 'on_commit needs numeric input')
        if phase in ('on_press', 'on_release'):
            need(node['kind'] == 'bit_switch' and action == 'momentary', 'Press/release effects need a momentary button')
        if phase == 'on_toggle':
            need(node['kind'] == 'bit_switch' and action == 'toggle', 'Toggle effects need a toggle button')
        for name, value in changes.items():
            need(name in variables, 'Unknown local variable: ' + name)
            kind = variables[name]['kind']
            if isinstance(value, dict):
                need(phase != 'requires' and set(value) == {'from'} and value['from'] in variables and variables[value['from']]['kind'] == kind, 'Invalid local source assignment')
            else:
                need(typed(value, kind), 'Preview value has wrong type: ' + name)
                if kind == 2:
                    need(variables[name]['min'] <= value <= variables[name]['max'], 'Preview effect outside declared range: ' + name)

def compile_source(raw, root):
    need(isinstance(raw, dict) and raw.get('schema') == 'hmi-ui-project/1.0', 'Expected hmi-ui-project/1.0')
    need(isinstance(raw.get('revision'), str) and raw['revision'].strip(), 'Project revision required')
    canvas=raw.get('canvas')
    need(isinstance(canvas,dict) and set(canvas)=={'width','height'},'显式画布宽高必填')
    canvas_width,canvas_height=dimensions(canvas['width'],canvas['height'])
    context = raw.get('context', {})
    need(isinstance(context, dict) and context.get('equipment') and context.get('tasks'), 'Record equipment/use and operator tasks before building a project')
    source = normalize_assets(raw, Path(root))
    digest = hashlib.sha256(canonical(source).encode('utf-8')).hexdigest()
    variables, native_variables, initials = {}, [], {}
    need(isinstance(source.get('variables'), list), 'Explicit global variables required')
    for index, item in enumerate(source['variables']):
        name, kind = item.get('name'), item.get('kind')
        need(isinstance(name, str) and re.fullmatch(r'[A-Za-z_\u3400-\u9fff][A-Za-z0-9_\u3400-\u9fff]{0,63}',name) and name not in variables and type(kind) is int and kind in (1, 2), 'Global variable name/type invalid or duplicate')
        need(typed(item.get('initial'), kind), 'Typed initial value required: ' + name)
        if kind == 2:
            need(number(item.get('min')) and number(item.get('max')) and -1e9 <= item['min'] < item['max'] <= 1e9, 'Numeric variable needs an explicit range: ' + name)
            need(item['min'] <= item['initial'] <= item['max'], 'Initial value outside declared range: ' + name)
        variables[name] = item
        native_variables.append({'name': name, 'kind': kind, 'source_id': index + 1, 'scope': 'design_only'})
        initials[name] = item['initial']
    native_by_name = {v['name']: v for v in native_variables}
    pages = source.get('pages')
    need(isinstance(pages, list) and 1 <= len(pages) <= 6, 'Current native batch supports 1..6 project pages')
    output, page_ids, page_names = [], set(), set()
    effects = []
    default_font = source.get('font', {'family': '微软雅黑', 'size_px': 16, 'weight': 400, 'color': '#24334A'})
    def resolve_svg(value):
        if isinstance(value, str) and value.startswith('@'):
            need(value[1:] in source.get('assets', {}), 'Unknown asset: ' + value)
            return source['assets'][value[1:]]['svg']
        return value
    for page in pages:
        pid, name = page.get('id'), page.get('name')
        need(isinstance(pid, str) and ID.fullmatch(pid) and pid not in page_ids, 'Unique page ID required')
        need(isinstance(name, str) and 0 < len(name) <= 30 and name.casefold() not in page_names, 'Unique page name required')
        page_ids.add(pid); page_names.add(name.casefold())
        nodes = copy.deepcopy(page.get('components'))
        need(isinstance(nodes, list), 'Explicit components required: ' + pid)
        for index, node in enumerate(nodes):
            node.setdefault('z', index)
            kind = node.get('kind')
            if kind in ('label', 'numeric_output', 'numeric_input', 'bit_switch', 'navigation'):
                node['font'] = {**default_font, **node.get('font', {})}
            binding = node.pop('variable', None)
            if binding is not None:
                need(binding in variables, 'Unknown component variable: ' + str(binding))
                v = native_by_name[binding]
                node['binding'] = {'name': binding, 'kind': v['kind'], 'id': v['source_id']}
                if kind in ('numeric_input', 'numeric_output'):
                    node.setdefault('digits', variables[binding].get('digits', 0))
                    node.setdefault('min', variables[binding].get('min'))
                    node.setdefault('max', variables[binding].get('max'))
                    if kind == 'numeric_input':
                        need(node['min'] <= initials[binding] <= node['max'], 'Input initial value is outside control range')
            if 'svg' in node:
                node['svg'] = resolve_svg(node['svg'])
            if 'states' in node:
                node['states'] = {state: resolve_svg(svg) for state, svg in node['states'].items()}
            if 'skin' in node:
                need(kind in ('numeric_input', 'numeric_output'), 'Owned skin belongs to numeric control')
                node['background'] = {'native_owner': node['id'], 'svg': resolve_svg(node.pop('skin'))}
            preview_contract(node, variables)
            if any(phase != 'requires' and changes for phase, changes in node.get('preview', {}).items()):
                effects.append({'page_id': pid, 'component_id': node['id'], 'status': 'local_preview_only', 'native_logic': 'requires_external_implementation'})
        model = {'schema': 'hmi-ui-editor-model/2.0-test', 'revision': source['revision'] + '_' + pid + '_' + digest[:12] + '_text2',
                 'title': name, 'width': canvas_width, 'height': canvas_height, 'variables': copy.deepcopy(native_variables),
                 'canvas_profile':canvas_details(canvas_width,canvas_height),
                 'text_layout': copy.deepcopy(source.get('text_layout', {})),
                 'preview_initial': copy.deepcopy(initials), 'components': nodes,
                 'source_project': {'schema': source['schema'], 'revision': source['revision'], 'sha256': digest, 'page_id': pid}}
        validate(model)
        model, text_report = layout_model(model, policy='grow')
        output.append({'id': pid, 'name': name, 'model': model})
    for page in output:
        for node in page['model']['components']:
            if node['kind'] == 'navigation':
                need(node['target_name'].casefold() in page_names, 'Navigation target is absent: ' + node['target_name'])
    catalog = {'schema': 'hmi-ui-editor-pages/2.0-test', 'revision': source['revision'] + '_' + digest[:12], 'pages': output}
    coverage = check_coverage(source, catalog)
    coverage.update({'source_sha256': digest, 'preview_only_behaviors': effects,
                     'text_layout_revision': TEXT_LAYOUT_REVISION,
                     'native_logic_status': 'pending_external_implementation' if effects else 'not_claimed',
                     'native_application_validation': 'not_run', 'binding_default': 'unbound'})
    return source, catalog, coverage

def check_coverage(source, catalog):
    requirements = source.get('requirements')
    need(isinstance(requirements, list) and bool(requirements), 'Declare content requirements separately before mapping components')
    actual = {(p['id'], c['id']): c for p in catalog['pages'] for c in p['model']['components']}
    covered, seen, errors, rows = set(), set(), [], []
    for item in requirements:
        ident, role = item.get('id'), item.get('role')
        need(item.get('status','mapped') in ('mapped','deferred'), 'Requirement status supports mapped/deferred only')
        need(isinstance(ident, str) and ident and ident not in seen and role in ROLES, 'Requirement ID/role invalid or duplicate')
        seen.add(ident)
        refs = item.get('component_ids', [])
        need(isinstance(refs, list) and len(refs) == len(set(refs)), 'Requirement component IDs must be an explicit unique list')
        if item.get('status') == 'deferred':
            need(isinstance(item.get('reason'), str) and item['reason'].strip() and not refs, 'Deferred requirement needs a reason and no false mapping')
            rows.append({'id': ident, 'role': role, 'status': 'deferred', 'reason': item['reason']})
            continue
        problems = []
        if not refs:
            problems.append('No mapped components')
        for cid in refs:
            key = (item.get('page_id'), cid)
            node = actual.get(key)
            if node is None:
                problems.append('Missing component: ' + str(key))
                continue
            covered.add(key)
            if node['kind'] not in ROLES[role]:
                problems.append('Wrong native kind for ' + role + ': ' + cid + '/' + node['kind'])
            if role in ('reading','parameter','command','indicator'):
                if not isinstance(item.get('variable'),str) or node.get('binding',{}).get('name')!=item['variable']:
                    problems.append('Wrong/missing semantic variable for '+cid)
            if role.startswith('alarm_') and role != 'alarm_strip' and node.get('alarm_mode') != ('history' if role == 'alarm_history' else 'realtime'):
                problems.append('Wrong alarm mode: ' + cid)
        rows.append({'id': ident, 'role': role, 'status': 'missing' if problems else 'mapped', 'problems': problems})
        errors.extend(ident + ': ' + text for text in problems)
    unmapped = [{'page_id': p, 'component_id': c} for p, c in sorted(actual.keys() - covered)]
    errors.extend('Unmapped component: ' + r['page_id'] + '/' + r['component_id'] for r in unmapped)
    pending = sum(r['status'] == 'deferred' for r in rows)
    return {'schema': 'hmi-project-coverage/1.0', 'status': 'fail' if errors else 'partial' if pending else 'complete',
            'requirements_total': len(rows), 'mapped': sum(r['status'] == 'mapped' for r in rows), 'deferred': pending,
            'requirements': rows, 'errors': errors, 'unmapped_components': unmapped,
            'limitation': 'Checks declared requirements only; compare the declaration with the actual customer brief.'}

def load(path):
    path = Path(path)
    return compile_source(json.loads(path.read_text(encoding='utf-8-sig')), path.parent)

def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
