"""Consume the engineering profile; guard the audited legacy subset without changing its schema."""
import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path

FACTORIES={
    'static_picture_from_verified_donor':('0x5009','picture'),
    'native_button_from_verified_donor':('0x5027','button'),
    'native_indicator_with_children':('0x502a','indicator'),
    'native_state_switch_from_verified_donor':('0x5028','state_switch'),
    'native_editable_label':('0x5008','label'),
    'native_input_with_format':('0x5025','numeric_input'),
    'existing_numeric_output_or_verified_factory':('0x5008','numeric_output'),
    'verified_native_shape_or_independent_picture':('shape','shape'),
    'design_assembly_only':(None,'group'),
}
GUARD=Path(__file__).resolve().parent.parent/'assets/legacy-execution-guard.json'


def content_sha(profile):
    value={k:v for k,v in profile.items() if k!='profile_sha256'}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def load_profile(path):
    """Keep the engineering identity; exact content is checked against the pinned guard."""
    raw=Path(path).read_bytes();document=json.loads(raw.decode('utf-8-sig'))
    if not isinstance(document,dict):raise ValueError('Execution profile must be an object')
    selected=copy.deepcopy(document.get('execution_profile',document))
    if not isinstance(selected,dict):raise ValueError('Execution profile must be an object')
    selected.setdefault('profile_sha256',hashlib.sha256(raw).hexdigest())
    return selected


class ExecutionProfileError(ValueError):
    def __init__(self,report):
        self.report=report
        locations=['/'.join(str(x) for x in (i['page_id'],i['component_id'],i['field']) if x is not None)
                   for i in report['issues']]
        super().__init__('MCGS execution constraints blocked: '+'; '.join(locations[:8]))


def check(plan,profile):
    """Structured differences only. Matching codecs never establishes template/runtime readiness."""
    issues=[]
    def issue(page,component,field,requested,supported,resolution='Keep the design requirement; obtain a dedicated verified engineering adapter.'):
        issues.append({'page_id':page,'component_id':component,'field':field,'requested':copy.deepcopy(requested),
            'supported':copy.deepcopy(supported),'blocking_stage':'execution_profile_preflight','resolution':resolution})
    report={'schema_version':'hmi-execution-check/1.0','status':'not_checked','issues':issues,
        'automatic_execution_ready':False,'template_resolution':'not_run','native_display':'not_run','native_behavior':'not_run',
        'unverified_native_behaviors':[],
        'engineering_reader_requirements':['dispatch_by_factory_and_native_type','resolve_actual_template_donors',
                                          'respect_unsupported_symbolic_artifact_boundary'],
        'limitations':['A generic tool profile is not actual template donor evidence.',
                      'No general mcgs-plan to MCP executor is claimed.',
                      'Cancel/blur reset and device execution require separate native evidence.']}
    if not isinstance(profile,dict):
        issue(None,None,'execution_profile',None,'versioned MCGS-owned profile')
        report['status']='blocked';return report
    report['profile_identity']={k:profile.get(k) for k in ('schema_version','profile_id','profile_sha256','target_version')}
    guard=json.loads(GUARD.read_text(encoding='utf-8'))
    report['compatibility_guard_sha256']=hashlib.sha256(GUARD.read_bytes()).hexdigest()
    expected=guard['profile']
    for key in ('schema_version','profile_id','profile_sha256','target_version'):
        if profile.get(key)!=expected[key]:
            issue(None,None,'execution_profile.'+key,profile.get(key),expected[key],
                  'Unknown or changed profiles require jointly verified capability rules; do not assume legacy limits apply.')
    if content_sha(profile)!=expected['content_sha256']:
        issue(None,None,'execution_profile.content_sha256',content_sha(profile),expected['content_sha256'],
              'Profile content changed; reverify the engineering profile and compatibility guard together.')
    if issues:
        report['status']='blocked';return report
    report['compatibility_basis']='pinned_legacy_1.0_profile_and_audited_codec_restrictions'
    report['engineering_installation_verified']=False
    report['audited_engineering_source_sha256']=guard['engineering_sources']
    if not isinstance(plan,dict):
        issue(None,None,'plan',plan,'mcgs-layout-plan/1.1 object')
        report['status']='blocked';return report
    if plan.get('schema_version')!='mcgs-layout-plan/1.1':
        issue(None,None,'plan.schema_version',plan.get('schema_version'),'mcgs-layout-plan/1.1')
        report['status']='blocked';return report
    embedded=plan.get('execution_profile')
    if embedded is not None and embedded!=profile:
        issue(None,None,'plan.execution_profile',embedded,report['profile_identity'],
              'Recompile against the same reviewed profile; do not silently override the plan identity.')
        report['status']='blocked';return report
    limits=guard['constraints']
    variables=plan.get('variable_definitions') or {}
    names={w.get('page_id'):w.get('name') for w in plan.get('windows',[])}
    for window in plan.get('windows',[]):
        page=window.get('page_id');controls={c.get('component_id'):c for c in window.get('controls',[])}
        for c in window.get('controls',[]):
            component=c.get('component_id');factory=c.get('factory');native=c.get('native_type')
            pair=FACTORIES.get(factory)
            if not pair or (pair[0]=='shape' and native not in ('0x5004','0x5005')) or (pair[0]!='shape' and native!=pair[0]):
                issue(page,component,'factory/native_type',{'factory':factory,'native_type':native},FACTORIES)
                continue
            family=pair[1];binding=c.get('binding') or {};action=c.get('interaction') or {}
            if family in ('numeric_input','numeric_output'):
                for field,expected_value in (('numeric_layout',profile['numeric_core_layout']),('appearance',profile['numeric_core_appearance'])):
                    if c.get(field)!=expected_value:issue(page,component,field,c.get(field),expected_value)
                supported=limits[family]['data_types']
                if binding.get('data_type') not in supported:
                    issue(page,component,'binding.data_type',binding.get('data_type'),supported)
                access='read_write' if family=='numeric_input' else 'read_only'
                if binding.get('access')!=access:issue(page,component,'binding.access',binding.get('access'),access)
                font=c.get('font') or {}
                valid_font=(isinstance(font,dict) and isinstance(font.get('family'),str) and bool(font['family'])
                            and type(font.get('size_px')) is int and font['size_px']>0
                            and type(font.get('weight')) is int and 100<=font['weight']<=1000
                            and isinstance(font.get('color'),str) and bool(re.fullmatch(r'#[A-Fa-f0-9]{6}',font['color'])))
                if not valid_font:
                    issue(page,component,'font',font,['family','size_px','weight','color'])
                if binding.get('unit'):
                    owners=['external'] if family=='numeric_output' else ['internal','external']
                    if binding.get('unit_owner') not in owners:
                        issue(page,component,'binding.unit_owner',binding.get('unit_owner'),owners)
                    elif binding['unit_owner']=='external':
                        label=controls.get(binding.get('unit_component_id'),{})
                        if (label.get('factory'),label.get('native_type'))!=('native_editable_label','0x5008'):
                            issue(page,component,'binding.unit_component_id',binding.get('unit_component_id'),'an independent native label on this page')
                if family=='numeric_input':
                    if action.get('type')!='value_edit':
                        issue(page,component,'interaction.type',action.get('type'),'value_edit',
                              'The numeric input adapter does not implement additional action scripts.')
                    report['unverified_native_behaviors'].append({'page_id':page,'component_id':component,
                        'variable_type_resolution':'actual_ObjData_kind_2_required_in_engineering',
                        'variable_address':'not_verified','device_execution':'not_verified'})
            elif family=='button':
                if action.get('type') not in profile['automatic_actions']:
                    issue(page,component,'interaction.type',action.get('type'),profile['automatic_actions'])
                elif action['type']=='navigate':
                    target=names.get(action.get('target_page_id'))
                    if not target or target!=c.get('target_window'):
                        issue(page,component,'interaction.target_page_id',action.get('target_page_id'),names)
                elif action['type']=='momentary':
                    report['unverified_native_behaviors'].append({'page_id':page,'component_id':component,
                        'press_release':'source_codec_available_native_not_run','cancel_reset':'not_verified',
                        'blur_reset':'not_verified','device_execution':'not_verified'})
                    if action.get('scope') not in limits['momentary']['scopes']:
                        issue(page,component,'interaction.scope',action.get('scope'),limits['momentary']['scopes'])
                    command=variables.get(action.get('command_binding'),{})
                    if command.get('data_type') not in limits['momentary']['command_data_types']:
                        issue(page,component,'interaction.command_binding.data_type',command.get('data_type'),limits['momentary']['command_data_types'])
                    if command.get('access')!='read_write':
                        issue(page,component,'interaction.command_binding.access',command.get('access'),'read_write')
                    for key in ('press_value','release_value','cancel_value'):
                        value=action.get(key)
                        valid=type(value) in (int,float) and math.isfinite(value)
                        if not valid or command.get('data_type')=='boolean' and value not in (0,1):
                            issue(page,component,'interaction.'+key,value,'finite numeric 0/1' if command.get('data_type')=='boolean' else 'finite numeric value')
                    if action.get('cancel_value')!=action.get('release_value'):
                        issue(page,component,'interaction.cancel_value',action.get('cancel_value'),action.get('release_value'))
                states=c.get('states') or [];bounds=c.get('bounds') or [0,0,0,0]
                full=[0,0,bounds[2]-bounds[0],bounds[3]-bounds[1]]
                if {s.get('id') for s in states}!=set(limits['button_text']['states']) or len(states)!=2:
                    issue(page,component,'states',[s.get('id') for s in states],limits['button_text']['states'])
                for state in states:
                    field='states.'+str(state.get('id'))+'.caption'
                    texts=state.get('text_children') or []
                    if len(texts)!=1 or texts[0].get('owner')!='component':
                        issue(page,component,field,texts,'one explicit internal caption/style per state');continue
                    t=texts[0]
                    for key,supported in (('alignment',limits['button_text']['horizontal']),('vertical_alignment',limits['button_text']['vertical'])):
                        if t.get(key) not in supported:issue(page,component,field+'.'+key,t.get(key),supported)
                    if t.get('local_bounds')!=full:issue(page,component,field+'.local_bounds',t.get('local_bounds'),full)
                    if state.get('caption')!=t.get('caption'):
                        issue(page,component,field,state.get('caption'),t.get('caption'))
                    expected_style={'caption':t.get('caption'),
                        'font':{'family':t['font']['family'],'size_px':t['font']['height_px'],'weight':t['font']['weight']},
                        'color':t['color']['rgb'],'horizontal':t.get('alignment'),'vertical':t.get('vertical_alignment')}
                    actual_style=(c.get('button_text_styles') or {}).get(state.get('id'))
                    if actual_style!=expected_style:
                        issue(page,component,'button_text_styles.'+str(state.get('id')),actual_style,expected_style,
                              'Recompile the style from the same native caption; do not keep inconsistent mirrors.')
            elif family in ('state_switch','shape'):
                issue(page,component,'factory',factory,'dedicated adapter verification before automatic execution')
    report['status']='unsupported' if issues else 'codec_constraints_matched'
    return report


def validate(plan,profile):
    report=check(plan,profile)
    if report['status']!='codec_constraints_matched':raise ExecutionProfileError(report)
    return copy.deepcopy(profile)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    inputs=ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--plan',type=Path);inputs.add_argument('--spec',type=Path)
    ap.add_argument('--profile',required=True,type=Path)
    args=ap.parse_args()
    try:
        selected=load_profile(args.profile)
        if args.spec:
            from mcgs_plan import compile_plan
            source=json.loads(args.spec.read_text(encoding='utf-8-sig'))
            if source.get('target_execution_profile') is not None and source['target_execution_profile']!=selected:
                raise ValueError('Selected profile differs from the design target_execution_profile')
            source['target_execution_profile']=selected
            plan=compile_plan(source,profile_mode='symbolic',asset_hashes_required=False)
            result=plan['execution_compatibility']
            result['input_scope']='design_capability_preflight; no PNG, customer review or template validation'
        else:
            result=check(json.loads(args.plan.read_text(encoding='utf-8-sig')),selected)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(0 if result['status']=='codec_constraints_matched' else 2)
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'status':'invalid','error':str(error)},ensure_ascii=False));raise SystemExit(1)
