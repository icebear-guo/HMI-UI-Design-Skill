"""Properties that must survive the design -> handoff -> symbolic plan interface."""
from branding import resolve_brand


def need(value, message):
    if not value:
        raise ValueError(message)

def validate_binding(binding):
    need(isinstance(binding.get('name'),str) and bool(binding['name']), 'explicit binding.name required for shared signal resolution')
    need(binding.get('data_type') in ('boolean','number','string'),'binding.data_type must use the shared schema')
    need(binding.get('access') in ('read_only','read_write'),'binding.access required; distinguish feedback from commands')
    need(binding.get('signal_role') in ('command','feedback','measurement','setpoint','local_demo'),'binding.signal_role required')
    need(binding['access']!='read_write' or binding['signal_role'] not in ('feedback','measurement'),'device feedback/measurement must not be written by a UI control')


def validate_control(control):
    kind = control['kind']
    binding = control.get('binding')
    if binding:
        validate_binding(binding)
    if kind in ('numeric_input', 'numeric_display'):
        need(isinstance(binding,dict),'numeric controls require an explicit binding')
        layout = control.get('numeric_layout')
        need(isinstance(layout, dict), 'numeric_layout required; do not discard _align during export')
        need(layout.get('horizontal') in ('left', 'center', 'right') and
             layout.get('vertical') in ('top', 'center', 'bottom'), 'explicit numeric horizontal/vertical alignment required')
        padding = layout.get('padding_px')
        need(isinstance(padding, list) and len(padding) == 4 and
             all(type(v) is int and v >= 0 for v in padding), 'numeric padding_px must be [left,top,right,bottom]')
        need(padding[0] + padding[2] < control['rect_px'][2] and
             padding[1] + padding[3] < control['rect_px'][3], 'numeric padding consumes the entire control')
        need(binding.get('access') == ('read_write' if kind == 'numeric_input' else 'read_only'),
             'numeric kind and read/write access disagree')
    for text in control.get('texts',[]):
        if 'vertical_align' in text:
            need(text['vertical_align'] in ('top','center','bottom'),'vertical_align must be top, center or bottom')
    if kind not in ('button', 'state_switch', 'numeric_input'):
        return
    interaction = control.get('interaction')
    need(isinstance(interaction, dict), 'interaction required for ' + control['id'])
    action = interaction.get('type')
    if control.get('target_page_id') is not None:
        need(kind == 'button' and action == 'navigate' and
             interaction.get('target_page_id') == control['target_page_id'], 'navigation behavior and target_page_id disagree')
        return
    need(action in ('momentary', 'toggle_command', 'set_value', 'value_edit', 'copy_values', 'acknowledge', 'custom'),
         'non-navigation control needs an explicit action; self-page jump is not a command')
    need(interaction.get('scope') in ('local_demo', 'plc_unverified'), 'interaction scope must distinguish local demo from unverified PLC behavior')
    if action == 'copy_values':
        pairs = interaction.get('copies')
        need(isinstance(pairs, list) and bool(pairs) and
             all(isinstance(v, dict) and v.get('from') and v.get('to') and v['from'] != v['to'] for v in pairs),
             'save/restore needs explicit from/to variable copies')
    elif action == 'custom':
        need(interaction.get('engineering_spec_ref') and interaction.get('required_effect'), 'custom behavior needs a specification and observable effect')
    else:
        command = interaction.get('command_binding')
        need(isinstance(command, str) and bool(command), 'action needs command_binding')
        if kind in ('numeric_input', 'state_switch'):
            need(binding and command == binding['name'] and binding['access'] == 'read_write', 'writable control must bind its command signal')
        feedback = interaction.get('feedback_binding')
        need(not feedback or feedback != command, 'command and device feedback must use different variables')
        if action == 'momentary':
            need('press_value' in interaction and 'release_value' in interaction and
                 interaction.get('cancel_value') == interaction['release_value'], 'momentary needs press/release/cancel values')
        if action == 'set_value':
            need('value' in interaction, 'set_value needs an explicit value')


def validate_branding(model):
    branding = model.get('branding')
    need(isinstance(branding, dict), 'branding required; system title does not replace company name')
    expected = resolve_brand(branding.get('company_name'))
    refs = branding.get('text_refs')
    need(isinstance(refs, list) and bool(refs), 'branding.text_refs must point to visible native text')
    pages = {p['id']: p for p in model['pages']}
    for ref in refs:
        page = pages.get(ref.get('page_id'))
        need(page is not None, 'brand page missing')
        control = next((c for c in page['controls'] if c['id'] == ref.get('component_id')), None)
        need(control is not None and control['kind'] == 'label', 'company name must remain a separate native label')
        text = next((t for t in control['texts'] if t['id'] == ref.get('text_id')), None)
        need(text is not None and text['text'] == expected and text['state'] is None and text['text_owner'] == 'external',
             'visible brand label must equal ' + expected)
    return expected


def validate_signals(model):
    definitions = dict(model.get('variable_definitions', {}))
    for name,binding in definitions.items():
        need(binding.get('name')==name,'variable definition name/key mismatch');validate_binding(binding)
    for page in model['pages']:
        for control in page['controls']:
            binding = control.get('binding')
            if not binding:
                continue
            validate_binding(binding)
            name = binding['name']
            existing = definitions.get(name)
            if existing:
                for key in ('data_type','initial','min','max','decimal_places','unit','signal_role','access'):
                    need(existing.get(key) == binding.get(key), 'shared variable definitions disagree: ' + name + '/' + key)
            else:
                definitions[name] = binding
    for page in model['pages']:
        for control in page['controls']:
            interaction = control.get('interaction') or {}
            names = [interaction[k] for k in ('command_binding','feedback_binding') if interaction.get(k)]
            for pair in interaction.get('copies', []):
                names.extend((pair['from'],pair['to']))
            need(all(name in definitions for name in names), 'behavior references an undefined variable: ' + control['id'])
            command = interaction.get('command_binding')
            if command:
                definition=definitions[command]
                need(definition.get('access')=='read_write' and definition.get('signal_role') not in ('feedback','measurement'), 'command needs a declared writable signal')
            for pair in interaction.get('copies', []):
                source,target=definitions[pair['from']],definitions[pair['to']]
                need(source.get('data_type')==target.get('data_type') and target.get('access')=='read_write' and target.get('signal_role') not in ('feedback','measurement'), 'copy type/target permission mismatch')
    return definitions
