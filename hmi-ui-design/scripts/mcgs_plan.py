"""Compile a validated UI component model into symbolic McgsPro layout fields.

No MDB access, donor cloning, raw byte offsets, device IDs, or PLC addressing is invented here.
The MCGS skill resolves templates and IDs, preflights, writes a new project, and reads it back.
"""
import copy,hashlib,re
from pathlib import Path
from text_layout_policy import validate_text_layout
from handoff_policy import validate_control,validate_branding,validate_signals

TYPES={'picture':0x5009,'button':0x5027,'indicator':0x502a,'state_switch':0x5028,'label':0x5008,'numeric_input':0x5025,'numeric_display':0x5008,'rectangle':0x5004,'rounded_rectangle':0x5005,'group':None}
PREFIX={'picture':'PIC','button':'BTN','indicator':'LAMP','state_switch':'SW','label':'LBL','numeric_input':'NUMIN','numeric_display':'NUMOUT','rectangle':'RECT','rounded_rectangle':'RPANEL','group':'GROUP'}

def bounds(rect):
    x,y,w,h=rect;return [x,y,x+w,y+h]
def color(value):
    raw=bytes.fromhex(value.lstrip('#'))
    if len(raw)!=3:raise ValueError('RGB colour must contain three bytes')
    return {'rgb':value,'colorref':int.from_bytes(raw+b'\0','little')}
def object_name(control):
    if control.get('mcgs_object_name'):
        name=control['mcgs_object_name']
        if not re.fullmatch(r'[A-Za-z0-9_\u4e00-\u9fff]{1,32}',name):raise ValueError('Invalid native object name: '+name)
        return name
    stem=re.sub(r'[^A-Za-z0-9_\u4e00-\u9fff]','_',control['id'])
    # A stable suffix prevents ID normalization/truncation from conflating two components.
    suffix=hashlib.sha256(control['id'].encode()).hexdigest()[:6]
    return (PREFIX[control['kind']]+'_'+stem)[:25]+'_'+suffix
def native_text(t,control):
    local=t['rect_px'] if t['text_owner']=='component' else [t['rect_px'][0]-control['rect_px'][0],t['rect_px'][1]-control['rect_px'][1],*t['rect_px'][2:]]
    absolute=[control['rect_px'][0]+local[0],control['rect_px'][1]+local[1],*local[2:]]
    return {'id':t['id'],'caption':t['text'],'owner':t['text_owner'],'state':t['state'],'local_bounds':bounds(local),'absolute_bounds':bounds(absolute),'font':{'family':t['font_family'],'height_px':t['font_size_px'],'lfHeight':-t['font_size_px'],'weight':t['font_weight']},'color':color(t['color']),'alignment':t['align'],'vertical_alignment':t.get('vertical_align'),'line_height_px':t['line_height_px']}
def compile_plan(model, *, profile_mode='strict', asset_hashes_required=True):
    if profile_mode not in ('strict','symbolic'):raise ValueError('profile_mode must be strict or symbolic')
    if model.get('schema_version')!='1.05':raise ValueError('handoff schema 1.05 required; explicit source migration needed')
    validate_branding(model)
    for page in model['pages']:
        for control in page['controls']:validate_control(control)
    signal_definitions=validate_signals(model)
    assets={a['id']:a for a in model['assets']};windows=[];requirements=[]
    if asset_hashes_required and any(not isinstance(a.get('sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',a['sha256']) for a in assets.values()):
        raise ValueError('Declared asset SHA256 required for a production plan; use the design capability preflight before PNG export')
    common_ids={p['common_page_id'] for p in model['pages'] if p.get('common_page_id') is not None}
    window_names={p['id']:p['name'] for p in model['pages']}
    if len(set(window_names.values()))!=len(window_names):raise ValueError('Native window names must be unique')
    for page in model['pages']:
        controls=[];names=set()
        for c in page['controls']:
            validate_text_layout(c)
            validate_control(c)
            kind=c['kind'];name=object_name(c)
            if name in names:raise ValueError('Duplicate native object name within page')
            names.add(name);texts=[native_text(t,c) for t in c['texts']];states=[]
            for state in c['states']:
                a=assets.get(state.get('asset_id'));state_texts=[t for t in texts if t['state'] in (None,state['id']) and t['owner']=='component']
                states.append({'id':state['id'],'semantic':state['semantic'],'gallery_image':None if a is None else a.get('gallery_name',Path(a['file']).stem),'asset_id':None if a is None else a['id'],'caption':state_texts[0]['caption'] if len(state_texts)==1 else None,'text_children':state_texts})
            binding=copy.deepcopy(c.get('binding'))
            if binding is not None:
                if not binding.get('name'):
                    binding['name']='UI_'+hashlib.sha256((page['id']+'/'+c['id']+'/'+binding['semantic']).encode()).hexdigest()[:16]
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}',binding['name']):raise ValueError('Variable name needs an explicit valid MCGS mapping')
                binding['resolved_id']=None
                binding['address_status']='provided_unverified' if binding.get('address') else 'local_ui_only'
            factory={'picture':'static_picture_from_verified_donor','button':'native_button_from_verified_donor','indicator':'native_indicator_with_children','state_switch':'native_state_switch_from_verified_donor','label':'native_editable_label','numeric_input':'native_input_with_format','numeric_display':'existing_numeric_output_or_verified_factory','rectangle':'verified_native_shape_or_independent_picture','rounded_rectangle':'verified_native_shape_or_independent_picture','group':'design_assembly_only'}[kind]
            out={'component_id':c['id'],'object_name':name,'native_type':None if TYPES[kind] is None else hex(TYPES[kind]),'factory':factory,'role':c['role'],'bounds':bounds(c['rect_px']),'parent_component_id':c.get('parent_id'),'z':c['z'],'binding':binding,'states':states,'texts':texts,'target_window':window_names.get(c.get('target_page_id')),'font':copy.deepcopy(c.get('font')),'appearance':copy.deepcopy(c.get('appearance'))}
            out['interaction']=copy.deepcopy(c.get('interaction'))
            out['numeric_layout']=copy.deepcopy(c.get('numeric_layout'))
            if kind=='button':
                out['button_text_styles']={}
                for state in states:
                    if len(state['text_children'])==1:
                        t=state['text_children'][0]
                        out['button_text_styles'][state['id']]={'caption':t['caption'],
                            'font':{'family':t['font']['family'],'size_px':t['font']['height_px'],'weight':t['font']['weight']},
                            'color':t['color']['rgb'],'horizontal':t['alignment'],'vertical':t['vertical_alignment']}
            if c.get('native_multi_text_layout_verified'):
                out['native_multi_text_layout_verified']=copy.deepcopy(c['native_multi_text_layout_verified'])
            if out['font']:
                out['font']['lfHeight']=-out['font']['size_px'];out['font']['native_color']=color(out['font']['color'])
            if kind=='picture':
                if binding is not None:raise ValueError('Static gallery picture cannot carry variable binding')
                if len(states)!=1 or not states[0]['gallery_image']:raise ValueError('Static picture needs one actual gallery image')
                out['image']=states[0]['gallery_image']
            if kind=='button' and out['target_window']:
                if any(s['caption'] is None for s in states):raise ValueError('Navigation needs one native caption run per state')
                out['same_properties']=False;out['actual_size']=True;out['image_enabled_by_state']={s['id']:True for s in states}
            if kind!='group':requirements.append({'page_id':page['id'],'component_id':c['id'],'factory':factory,'resolve_from':'frozen_target_project_or_supplied_native_donor'})
            controls.append(out)
        windows.append({'page_id':page['id'],'name':page['name'],'page_kind':'common' if page['id'] in common_ids else 'business','canvas_px':page['canvas_px'],'delete_flag':0,'resolved_id':None,'common_page_id':page.get('common_page_id'),'common_window':window_names.get(page.get('common_page_id')),'controls':controls})
    result={'schema_version':'mcgs-layout-plan/1.1','variable_definitions':copy.deepcopy(signal_definitions),'branding':copy.deepcopy(model['branding']),'target_version':'McgsPro 3.5.1.6963','design_revision':model['design_revision'],'source_sha256':model['source_sha256'],'source_inventory_sha256':model['source_inventory_sha256'],'stage':'symbolic_layout_and_behavior_requirements' if asset_hashes_required else 'design_capability_preflight_only','asset_hash_status':'declared_not_reverified' if asset_hashes_required else 'not_required_for_design_capability_check','requires_template_resolution':True,'asset_directory':'assets','assets':[{'id':a['id'],'file':a['file'],'gallery_name':a.get('gallery_name',Path(a['file']).stem),'size_px':a['design_size_px'],'sha256':a.get('sha256'),'component_id':a['component_id'],'state':a['state']} for a in model['assets']],'windows':windows,'common_windows':{w['name']:w['common_window'] for w in windows if w['common_window']},'factory_requirements':requirements,'required_checks':['frozen_source_sha','native_factory_available','all_source_components_mapped','image_references','text_rect_font_and_fit','button_images_and_native_captions','active_window_targets','business_common_window_references','numeric_style_and_units','numeric_layout','interaction_effects','field_consumption','full_database_readback'],'native_gui_compile_runtime':'not_tested','scope':'symbolic requirements only; each behavior still requires native implementation and validation'}

    if model.get('target_execution_profile') is not None:
        from execution_profile import validate,check
        selected=model['target_execution_profile']
        result['execution_profile']=validate(result,selected) if profile_mode=='strict' else copy.deepcopy(selected)
        result['execution_compatibility']=check(result,selected)
        if result['execution_compatibility']['status']!='codec_constraints_matched':
            result['stage']='symbolic_requirements_with_unsupported_execution'
    return result
