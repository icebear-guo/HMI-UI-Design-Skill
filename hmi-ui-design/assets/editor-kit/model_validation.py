import re,math,xml.etree.ElementTree as ET
from control_schema import EXTRA,check
from canvas_profile import dimensions
ALLOWED={'picture','label','numeric_output','numeric_input','bit_switch','lamp'}|EXTRA
def svg_source(value):
    if not isinstance(value,str):raise ValueError('SVG source required')
    root=ET.fromstring(value)
    if root.tag.split('}')[-1]!='svg':raise ValueError('Expected SVG source')
    for node in root.iter():
        if node.tag.split('}')[-1] in ('script','foreignObject','style','text'):raise ValueError('SVG must retain native text separately and contain no active content')
        for key,value in node.attrib.items():
            local=key.split('}')[-1].lower()
            if local.startswith('on') or re.search(r'(?:javascript:|https?:|file:|@import)',value,re.I):raise ValueError('SVG active/external attribute refused')
            if local in ('href','src') and not (value.startswith('#') or re.fullmatch(r'data:image/(png|jpeg);base64,[A-Za-z0-9+/=\s]+',value)):raise ValueError('External SVG image/use refused')
    return value
def validate(model):
    if model.get('schema')!='hmi-ui-editor-model/2.0-test':raise ValueError('Expected hmi-ui-editor-model/2.0-test')
    width,height=dimensions(model.get('width'),model.get('height'))
    if not isinstance(model.get('revision'),str) or not model['revision']:raise ValueError('Revision required')
    nodes=model.get('components');seen=set()
    if not isinstance(nodes,list) or not 1<=len(nodes)<=300:raise ValueError('Expected1..300 explicit components')
    variables=model.get('variables',[])
    if not isinstance(variables,list):raise ValueError('Variables must be explicit')
    variable_names=set();variable_ids=set()
    for v in variables:
        if not isinstance(v,dict) or not isinstance(v.get('name'),str) or not v['name'] or v.get('kind') not in (1,2) or type(v.get('source_id')) is not int or v['source_id']<0 or v['name'] in variable_names or v['source_id'] in variable_ids:raise ValueError('变量名/身份须唯一且类型有效')
        variable_names.add(v['name']);variable_ids.add(v['source_id'])
    for n in nodes:
        ident=n.get('id');kind=n.get('kind')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}',ident) or ident in seen:raise ValueError('Component ID must be unique ASCII letters/digits/underscore, maximum32')
        seen.add(ident)
        if kind not in ALLOWED:raise ValueError('Unsupported editor/native factory: '+str(kind)+'; retain the design and use an available route')
        rect=n.get('rect');
        if not isinstance(rect,list) or len(rect)!=4 or not all(type(v)is int for v in rect) or not (0<=rect[0]<rect[2]<=width and 0<=rect[1]<rect[3]<=height):raise ValueError('Invalid bounds: '+ident)
        if kind=='picture' and not isinstance(n.get('svg'),str):raise ValueError('Picture SVG source required: '+ident)
        if kind=='picture':svg_source(n['svg'])
        if kind in ('label','numeric_output','numeric_input','bit_switch','navigation'):
            font=n.get('font',{})
            if set(font)!={'family','size_px','weight','color'} or not isinstance(font['family'],str) or not font['family'] or '\0' in font['family'] or type(font['size_px'])is not int or not 8<=font['size_px']<=64 or font['weight'] not in (400,700) or not re.fullmatch(r'#[0-9a-fA-F]{6}',str(font['color'])):raise ValueError('Explicit font family/size/weight/color required: '+ident)
        if kind in ('numeric_input','numeric_output','bit_switch','lamp','gauge','percentage_fill','realtime_trend'):
            binding=n.get('binding',{});expected=1 if kind in ('bit_switch','lamp') else 2
            if binding.get('kind')!=expected:raise ValueError('绑定类型不符：'+ident)
            if not any(v.get('name')==binding.get('name') and v.get('kind')==expected and v.get('source_id')==binding.get('id') for v in variables):raise ValueError('Unresolved/wrong-type variable: '+ident)
        if kind in ('numeric_input','numeric_output') and (type(n.get('digits'))is not int or not 0<=n['digits']<=6):raise ValueError('Numeric decimal places required: '+ident)
        if kind=='label' and not isinstance(n.get('text'),str):raise ValueError('Label text required: '+ident)
        if kind in ('bit_switch','lamp') and set(n.get('states',{}))!={'s0','s1'}:raise ValueError('Both state sources required: '+ident)
        if kind in ('bit_switch','lamp'):
            for value in n['states'].values():svg_source(value)
        if kind=='bit_switch' and (set(n.get('captions',{}))!={'s0','s1'} or set(n.get('state_colors',{}))!={'s0','s1'}):raise ValueError('Explicit two-state captions and colors required: '+ident)
        if n.get('background') and (n['background'].get('native_owner')!=ident or not isinstance(n['background'].get('svg'),str)):raise ValueError('Explicit owned skin required: '+ident)
        if n.get('background'):svg_source(n['background']['svg'])
        if kind=='numeric_input' and not (type(n.get('min')) in (int,float) and type(n.get('max')) in (int,float) and math.isfinite(n['min']) and math.isfinite(n['max']) and -1e9<=n['min']<n['max']<=1e9):raise ValueError('输入量程无效：'+ident)
        if kind in EXTRA or kind=='bit_switch':check(n)
        if kind=='navigation':
            for value in n['states'].values():svg_source(value)
    return model
