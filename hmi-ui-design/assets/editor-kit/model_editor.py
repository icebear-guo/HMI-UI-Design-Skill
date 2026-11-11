"""Validate a bounded component patch against the fixed, user-owned design."""
import copy,math,re,hashlib,json,struct
from control_schema import FIELDS,EXTRA,check

NUMERIC={'numeric_input','numeric_output'}
COMMON={'id','kind','rect'}
def need(ok,message):
    if not ok:raise ValueError(message)
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def apply_edits(baseline,patches):
    need(isinstance(patches,list) and len(patches)<=len(baseline['components']),'修改列表无效。')
    model=copy.deepcopy(baseline);by_id={n['id']:n for n in model['components']};seen=set()
    for patch in patches:
        need(isinstance(patch,dict),'控件修改格式无效。')
        ident=patch.get('id');need(isinstance(ident,str) and ident in by_id and ident not in seen,'控件不存在或重复。');seen.add(ident)
        n=by_id[ident];original=copy.deepcopy(n);kind=patch.get('kind',n['kind'])
        need(kind==n['kind'] or n['kind'] in NUMERIC and kind in NUMERIC,'当前只支持数值显示与数值输入互换。')
        allowed=COMMON|({'digits','min','max','binding_name','font','skin_mode','skin_color','skin_radius','text_layout'} if kind in NUMERIC else {'text','font','text_layout'} if kind=='label' else {'captions','font','state_colors','action','binding_name'} if kind=='bit_switch' else FIELDS.get(kind,set())|({'binding_name'} if n.get('binding') else set()))
        need(set(patch)<=allowed,'包含尚未支持的修改属性。')
        n['kind']=kind
        if 'rect' in patch:
            rect=patch['rect'];need(isinstance(rect,list) and len(rect)==4 and all(type(v)is int for v in rect),'位置和尺寸必须为整数。')
            l,t,r,b=rect;need(0<=l<r<=baseline['width'] and 0<=t<b<=baseline['height'],f"控件必须位于{baseline['width']}×{baseline['height']}画面内。")
            need((r-l>=1 and b-t>=1) if kind=='picture' else (r-l>=16 and b-t>=12),'编辑后的控件尺寸过小。');n['rect']=rect
        if 'font' in patch:
            font=patch['font'];need(isinstance(font,dict) and set(font)=={'family','size_px','weight','color'},'字体属性不完整。')
            need(font['family']==original.get('font',{}).get('family','微软雅黑') and type(font['size_px']) is int and 8<=font['size_px']<=64 and font['weight'] in (400,700),'当前支持微软雅黑8～64像素、常规或粗体。')
            need(isinstance(font['color'],str) and re.fullmatch('#[0-9a-fA-F]{6}',font['color']),'文字颜色无效。')
            if kind not in NUMERIC|{'label'}:need(font['size_px']<=n['rect'][3]-n['rect'][1],'字号不能超过控件高度。')
            n['font']=copy.deepcopy(font)
        if 'text_layout' in patch:
            n['text_layout']=copy.deepcopy(patch['text_layout'])
        if 'binding_name' in patch and n.get('binding'):
            name=patch['binding_name'];need(isinstance(name,str) and re.fullmatch(r'[A-Za-z_\u3400-\u9fff][A-Za-z0-9_\u3400-\u9fff]{0,63}',name),'请输入有效变量名，不支持表达式或PLC地址。')
            expected=1 if kind in ('bit_switch','lamp') else 2
            matches=[v for v in model['variables'] if v['name']==name]
            need(not matches or matches[0]['kind']==expected,'同名变量的数据类型不同。')
            if not matches:
                v={'name':name,'kind':expected,'source_id':max([v['source_id'] for v in model['variables']]+[0])+1,'scope':'design_name_pending_native_compile'}
                model['variables'].append(v);matches=[v]
            n['binding']={'name':name,'kind':expected,'id':matches[0]['source_id']}
        if kind in NUMERIC:
            digits=patch.get('digits',n['digits']);need(type(digits)is int and 0<=digits<=6,'小数位支持0～6。');n['digits']=digits
            low=patch.get('min',n.get('min',0));high=patch.get('max',n.get('max',100))
            need(finite(low) and finite(high) and -1e9<=low<high<=1e9,'请输入有效范围，下限须小于上限，且在±10亿以内。')
            n['min']=low;n['max']=high
            name=patch.get('binding_name',n['binding']['name'])
            candidates=[v for v in model['variables'] if v['kind']==2 and v['name']==name]
            need(len(candidates)==1,'只能选择工程中已标定的数值型变量。')
            n['binding']={'name':name,'kind':2,'id':candidates[0]['source_id']}
            mode=patch.get('skin_mode','keep');need(mode in ('keep','none','solid'),'底图模式无效。')
            if mode=='none':n.pop('background',None)
            elif mode=='solid':
                color=patch.get('skin_color','#f0f5fc');radius=patch.get('skin_radius',6)
                need(isinstance(color,str) and re.fullmatch('#[0-9a-fA-F]{6}',color),'底图颜色无效。')
                need(type(radius)is int and 0<=radius<=24,'圆角支持0～24像素。')
                l,t,r,b=n['rect'];w,h=r-l,b-t
                need(radius<=min(w,h)/2,'圆角不能超过短边的一半。')
                svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" rx="{radius}" fill="{color}"/></svg>'
                n['background']={'id':ident+'_skin','svg':svg,'native_owner':ident,'native_slot':'numeric_owned_image','anchor':'top_left','role':'dedicated_numeric_skin'}
        if kind=='label' and 'text' in patch:
            need(isinstance(patch['text'],str) and 0<len(patch['text'])<=120 and not any(c in patch['text'] for c in '\0\r\n'),'本轮只支持1～120字的单行文字。');n['text']=patch['text']
        if kind=='bit_switch':
            if 'action' in patch:n['action']=patch['action']
            if 'captions' in patch:
                captions=patch['captions'];need(isinstance(captions,dict) and set(captions)=={'s0','s1'} and all(isinstance(v,str) and 0<len(v)<=16 and not any(c in v for c in '\0\r\n') for v in captions.values()),'请填写两态文字，每态1～16字。');n['captions']=copy.deepcopy(captions)
            if 'state_colors' in patch:
                colors=patch['state_colors'];need(isinstance(colors,dict) and set(colors)=={'s0','s1'} and all(isinstance(v,str) and re.fullmatch('#[0-9a-fA-F]{6}',v) for v in colors.values()),'两态文字颜色无效。');n['state_colors']=copy.deepcopy(colors)
        if kind in EXTRA:
            for field in FIELDS[kind]-{'font'}:
                if field in patch:n[field]=copy.deepcopy(patch[field])
        if kind in EXTRA or kind=='bit_switch':check(n)
        # Do not silently change the source asset inventory or existing IDs.
        need(n['id']==original['id'],'控件身份不可更改。')
    model['editor']={'patch_count':len(patches),'modified_ids':sorted(seen),'base_revision':baseline['revision'],'patch_sha256':hashlib.sha256(json.dumps(patches,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}
    from text_layout import layout_model
    model,report=layout_model(model,policy='grow',component_ids=seen)
    need(not report['errors'],'文字适配未完成：'+'；'.join(e['id']+'：'+e['message'] for e in report['errors'][:4]))
    from model_validation import validate
    return validate(model)

def choose_components(model,selection):
    if selection is None:return model
    need(isinstance(selection,list) and len(selection)==1 and isinstance(selection[0],str),'局部复制每次选择一个控件。')
    matches=[n for n in model['components'] if n['id']==selection[0]];need(len(matches)==1,'选中控件不存在。')
    result=copy.deepcopy(model);result['components']=matches;result['export_selection']=selection
    return result
