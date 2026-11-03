"""Synthetic complete design fixtures; no customer confirmation or native MCP writes."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import os
import subprocess
from PIL import Image

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'hmi-ui-design/scripts'))
from mcgs_plan import compile_plan
from execution_profile import validate
from export_handoff import export
from check_project_workflow import check as check_workflow


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def profile():
    raw=(REPO/'tests/fixtures/mcgs-execution-profile-1.0.json').read_bytes()
    result=json.loads(raw);result['profile_sha256']=hashlib.sha256(raw).hexdigest()
    return result


def model(with_button=True):
    result=json.loads((REPO/'hmi-ui-design/assets/handoff-spec.template.json').read_text(encoding='utf-8'))
    result['target_execution_profile']=profile()
    for a in result['assets']:a['sha256']='a'*64
    if with_button:
        binding={'name':'UI_command','semantic':'synthetic local request','data_type':'number','access':'read_write',
                 'signal_role':'command','initial':0,'min':0,'max':1,'decimal_places':0,'address':None}
        result['variable_definitions']={'UI_command':binding}
        button={'id':'start','kind':'button','role':'action_button','rect_px':[400,100,120,40],
            'parent_id':None,'z':30,'binding':None,'target_page_id':None,
            'states':[{'id':s,'asset_id':'start_'+s,'semantic':s} for s in ('s0','s1')],
            'texts':[{'id':'caption','text':'START','state':None,'text_owner':'component','rect_px':[0,0,120,40],
                      'font_family':'sans-serif','font_size_px':12,'font_weight':400,'color':'#173047',
                      'align':'center','vertical_align':'center','line_height_px':16}],
            'interaction':{'type':'momentary','scope':'local_demo','command_binding':'UI_command',
                           'press_value':1,'release_value':0,'cancel_value':0}}
        result['pages'][0]['controls'].append(button)
        for state in ('s0','s1'):
            result['assets'].append({'id':'start_'+state,'file':'start_'+state+'.png','component_id':'start','page_id':'io',
                'state':state,'design_size_px':[120,40],'export_method':'component_render','source_component_id':'start',
                'text_baked':False,'sha256':'a'*64,'content_expectation':{'mode':'visible','required_bbox_px':[0,0,120,40]}})
    result['source_inventory']=[{'page_id':p['id'],'component_id':c['id'],'role':c['role']} for p in result['pages'] for c in p['controls']]
    result['source_inventory_sha256']=canonical(result['source_inventory'])
    return result


def numeric_input(result,datatype):
    c=copy.deepcopy(next(c for c in result['pages'][0]['controls'] if c['id']=='io_value'))
    c.update(id='setpoint',kind='numeric_input',role='setpoint',parent_id=None,rect_px=[400,200,120,40])
    c['binding'].update(name='UI_setpoint',data_type=datatype,initial=0 if datatype=='number' else False,access='read_write',signal_role='setpoint')
    c['interaction']={'type':'value_edit','scope':'local_demo','command_binding':'UI_setpoint'}
    result['pages'][0]['controls'].append(c)
    result['source_inventory'].append({'page_id':'io','component_id':'setpoint','role':'setpoint'})
    result['source_inventory_sha256']=canonical(result['source_inventory'])
    return c


class InterfaceRegressionTests(unittest.TestCase):
    def test_legal_local_demo_and_boolean_display(self):
        plan=compile_plan(model())
        self.assertEqual(validate(plan,profile())['profile_id'],profile()['profile_id'])

    def test_plc_momentary_is_rejected_before_automatic_export(self):
        source=model();source['pages'][0]['controls'][-1]['interaction']['scope']='plc_unverified'
        with self.assertRaises(ValueError):compile_plan(source)

    def test_numeric_role_cannot_bypass_layout_validation(self):
        plan=compile_plan(model(False));c=next(c for c in plan['windows'][0]['controls'] if c['component_id']=='io_value')
        c['role']='measurement';c['numeric_layout']['horizontal']='right'
        with self.assertRaises(ValueError):validate(plan,profile())

    def test_boolean_numeric_input_is_not_current_adapter_input(self):
        source=model(False);numeric_input(source,'boolean')
        with self.assertRaises(ValueError):compile_plan(source)

    def test_number_numeric_input_keeps_current_route(self):
        source=model(False);numeric_input(source,'number')
        self.assertEqual(compile_plan(source)['windows'][0]['controls'][-1]['factory'],'native_input_with_format')

    def test_button_right_alignment_is_not_calibrated(self):
        source=model();source['pages'][0]['controls'][-1]['texts'][0]['align']='right'
        with self.assertRaises(ValueError):compile_plan(source)

    def test_button_caption_subrect_cannot_be_silently_ignored(self):
        source=model();source['pages'][0]['controls'][-1]['texts'][0]['rect_px']=[5,0,100,40]
        with self.assertRaises(ValueError):compile_plan(source)

    def test_factory_and_native_type_must_match(self):
        plan=compile_plan(model(False));c=next(c for c in plan['windows'][0]['controls'] if c['component_id']=='io_value')
        c['native_type']='0x5009'
        with self.assertRaises(ValueError):validate(plan,profile())

    def test_business_role_changes_preserve_numeric_factory(self):
        source=model(False);next(c for c in source['pages'][0]['controls'] if c['id']=='io_value')['role']='measurement'
        plan=compile_plan(source)
        numeric=next(c for c in plan['windows'][0]['controls'] if c['component_id']=='io_value')
        self.assertEqual(numeric['factory'],'existing_numeric_output_or_verified_factory')
        self.assertEqual(plan['execution_compatibility']['status'],'codec_constraints_matched')
        self.assertFalse(plan['execution_compatibility']['automatic_execution_ready'])

    def test_button_bottom_alignment_is_unsupported_but_source_is_preserved(self):
        source=model();source['pages'][0]['controls'][-1]['texts'][0]['vertical_align']='bottom'
        snapshot=copy.deepcopy(source)
        plan=compile_plan(source,profile_mode='symbolic')
        self.assertEqual(plan['execution_compatibility']['status'],'unsupported')
        self.assertEqual(source,snapshot)

    def test_missing_button_vertical_alignment_cannot_be_guessed(self):
        source=model();source['pages'][0]['controls'][-1]['texts'][0].pop('vertical_align')
        with self.assertRaises(ValueError):compile_plan(source)

    def test_unknown_profile_or_forged_content_never_claims_support(self):
        plan=compile_plan(model(False))
        unknown=profile();unknown['profile_id']='unreviewed-profile'
        with self.assertRaises(ValueError):validate(plan,unknown)
        forged=profile();forged['numeric_core_layout']['horizontal']='right'
        with self.assertRaises(ValueError):validate(plan,forged)

    def test_boolean_local_request_needs_numeric_adapter_values(self):
        source=model();source['variable_definitions']['UI_command'].update(data_type='boolean',initial=False)
        plan=compile_plan(source)
        self.assertEqual(plan['execution_compatibility']['status'],'codec_constraints_matched')
        source['pages'][0]['controls'][-1]['interaction']['press_value']=True
        with self.assertRaises(ValueError):compile_plan(source)

    def test_changed_button_style_mirror_cannot_bypass_caption_checks(self):
        plan=compile_plan(model());c=plan['windows'][0]['controls'][-1]
        c['button_text_styles']['s1']['horizontal']='right'
        with self.assertRaises(ValueError):validate(plan,profile())

    def test_native_cancel_blur_and_execution_remain_unverified(self):
        plan=compile_plan(model());item=plan['execution_compatibility']['unverified_native_behaviors'][0]
        self.assertEqual([item[k] for k in ('cancel_reset','blur_reset','device_execution')],['not_verified']*3)

    def test_numeric_input_plc_scope_is_not_confused_with_local_momentary_limit(self):
        source=model(False);c=numeric_input(source,'number');c['interaction']['scope']='plc_unverified'
        result=compile_plan(source)['execution_compatibility']
        self.assertEqual(result['status'],'codec_constraints_matched')
        self.assertFalse(result['automatic_execution_ready'])

    def test_numeric_output_checks_font_and_unit_independent_of_role(self):
        source=model(False);plan=compile_plan(source)
        c=next(c for c in plan['windows'][0]['controls']if c['component_id']=='io_value')
        c['role']='measurement';c['binding'].update(unit='bar',unit_owner='internal');c['font']['size_px']=0
        from execution_profile import check
        fields={i['field']for i in check(plan,profile())['issues']}
        self.assertTrue({'font','binding.unit_owner'}<=fields)

    def test_plan_profile_identity_is_not_silently_replaced(self):
        plan=compile_plan(model(False));plan['execution_profile']['profile_id']='changed-in-plan'
        with self.assertRaises(ValueError):validate(plan,profile())

    def test_representative_preflight_needs_no_png_or_placeholder_hash(self):
        root=Path(tempfile.mkdtemp(prefix='representative-profile-'))
        source=model()
        for a in source['assets']:a.pop('sha256')
        path=root/'design.json';path.write_text(json.dumps(source),encoding='utf-8')
        before=path.read_bytes()
        result=subprocess.run([sys.executable,'-X','utf8','-B',str(REPO/'hmi-ui-design/scripts/execution_profile.py'),
            '--spec',str(path),'--profile',str(REPO/'tests/fixtures/mcgs-execution-profile-1.0.json')],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'codec_constraints_matched')
        self.assertEqual(path.read_bytes(),before)
        self.assertFalse(list(root.rglob('*.png')))

    def test_representative_preflight_returns_exact_component_field(self):
        root=Path(tempfile.mkdtemp(prefix='unsupported-profile-'));source=model()
        source['pages'][0]['controls'][-1]['interaction']['scope']='plc_unverified'
        path=root/'design.json';path.write_text(json.dumps(source),encoding='utf-8')
        result=subprocess.run([sys.executable,'-X','utf8','-B',str(REPO/'hmi-ui-design/scripts/execution_profile.py'),
            '--spec',str(path),'--profile',str(REPO/'tests/fixtures/mcgs-execution-profile-1.0.json')],capture_output=True,text=True,encoding='utf-8')
        report=json.loads(result.stdout);self.assertEqual(result.returncode,2)
        issue=next(i for i in report['issues']if i['field']=='interaction.scope')
        self.assertEqual((issue['page_id'],issue['component_id'],issue['requested']),('io','start','plc_unverified'))


class HandoffExportTests(unittest.TestCase):
    def setUp(self):
        base=os.environ.get('HMI_TEST_WORK')
        if base:Path(base).mkdir(parents=True,exist_ok=True)
        self.root=Path(tempfile.mkdtemp(prefix='mcgs-interface-',dir=base))
        self.source=model();self.assets=self.root/'assets';self.assets.mkdir()
        self.workflow=self.root/'workflow.json';self.spec=self.root/'spec.json'
        fonts=[('Arial',Path('C:/Windows/Fonts/arial.ttf')),
               ('DejaVu Sans',Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))]
        self.family,self.font=next((family,p)for family,p in fonts if p.is_file())

    def prepare(self):
        self.source['design_revision']='u1'
        self.source['branding']['company_name']='Test Company'
        for p in self.source['pages']:
            for c in p['controls']:
                if c.get('font'):c['font']['family']=self.family
                for t in c['texts']:
                    t['font_family']=self.family;t['font_file']=str(self.font)
                    if c['id']=='company_brand':t['text']='Test Company'
                    elif c['id']=='io_description':t['text']='Low level'
                    elif c['id']=='plc_description':t['text']='PLC status'
        self.source['source_inventory']=[{'page_id':p['id'],'component_id':c['id'],'role':c['role']}for p in self.source['pages']for c in p['controls']]
        self.source['source_inventory_sha256']=canonical(self.source['source_inventory'])
        for ordinal,a in enumerate(self.source['assets']):
            Image.new('RGBA',a['design_size_px'],(40+ordinal*50,90,120,255)).save(self.assets/a['file'])
            a['sha256']=hashlib.sha256((self.assets/a['file']).read_bytes()).hexdigest()
        record=json.loads((REPO/'hmi-ui-design/assets/project-workflow.template.json').read_text(encoding='utf-8'))
        record.update(page_count=1,page_ids=['io'])
        nodes=[]
        for c in self.source['pages'][0]['controls']:
            x,y,w,h=c['rect_px'];text=' '.join(t['text']for t in c['texts'])
            nodes.append(f'<div data-hmi-component="{c["id"]}" data-hmi-kind="{c["kind"]}" style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px">{text}</div>')
        html='<!doctype html><meta charset="utf-8"><title>SYNTHETIC interface fixture</title><div data-hmi-page="io" style="position:relative;width:1024px;height:600px">'+''.join(nodes)+'</div>'
        for name,stage in record['stages'].items():
            directory=self.root/stage['artifact_dir'];directory.mkdir(parents=True)
            (directory/stage['entry']).write_text('SYNTHETIC parameter review' if name=='parameters' else html,encoding='utf-8')
            if name=='interactive_ui':
                stage['pages']=[{'id':'io','entry':stage['entry']}]
                (directory/'component-inventory.json').write_text(json.dumps(self.source['source_inventory']),encoding='utf-8')
                self.source['source_sha256']=hashlib.sha256((directory/stage['entry']).read_bytes()).hexdigest()
            stage['files']=[{'file':p.relative_to(directory).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in sorted(directory.rglob('*'))if p.is_file()]
        def write():self.workflow.write_text(json.dumps(record),encoding='utf-8')
        write()
        for name,stage in record['stages'].items():
            results={r['stage']:r for r in check_workflow(self.workflow,'delivery')['stages']}
            stage['depends_on']={k:results[k]['review_digest'] for k in stage['depends_on']};write()
            digest=next(r['review_digest']for r in check_workflow(self.workflow,'delivery')['stages']if r['stage']==name)
            stage.update(status='confirmed',customer_confirmation={'customer_message':'SYNTHETIC TEST ONLY: accept this fixture version',
                'message_ref':'synthetic-interface-test','confirmed_at':'2026-11-03T10:00:00+08:00','reviewed_digest':digest})
            write()
        ui=next(r for r in check_workflow(self.workflow,'delivery')['stages']if r['stage']=='interactive_ui')
        record['mcgs_export']={'decision':'export','design_revision':'u1','reviewed_digest':ui['review_digest'],
            'customer_message':'SYNTHETIC TEST ONLY: export this fixture','message_ref':'synthetic-export',
            'confirmed_at':'2026-11-03T10:01:00+08:00'};write()
        self.spec.write_text(json.dumps(self.source),encoding='utf-8')
        self.assertEqual(check_workflow(self.workflow,'mcgs_export')['status'],'ready')

    def test_complete_valid_export_keeps_profile_and_native_styles(self):
        numeric_input(self.source,'number');self.prepare();out=self.root/'export'
        report=export(self.spec,self.assets,out,self.workflow)
        self.assertEqual(report['execution_profile_status'],'codec_constraints_matched')
        self.assertFalse(report['automatic_execution_ready'])
        plan=json.loads((out/'mcgs-plan.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['schema_version'],'mcgs-layout-plan/1.1')
        self.assertEqual(plan['execution_profile']['profile_sha256'],profile()['profile_sha256'])
        start=next(c for c in plan['windows'][0]['controls']if c['component_id']=='start')
        self.assertEqual(start['button_text_styles']['s1']['vertical'],'center')
        setpoint=next(c for c in plan['windows'][0]['controls']if c['component_id']=='setpoint')
        self.assertEqual(setpoint['binding']['data_type'],'number')
        self.assertTrue((out/'execution-compatibility.json').is_file())
        for a in self.source['assets']:
            self.assertEqual(hashlib.sha256((out/'assets'/a['file']).read_bytes()).hexdigest(),a['sha256'])

    def test_plc_export_strictly_blocks_but_explicit_symbolic_keeps_original_requirement(self):
        self.source['pages'][0]['controls'][-1]['interaction']['scope']='plc_unverified';self.prepare()
        with self.assertRaises(ValueError):export(self.spec,self.assets,self.root/'blocked',self.workflow)
        self.assertFalse((self.root/'blocked').exists())
        command=[sys.executable,'-X','utf8','-B',str(REPO/'hmi-ui-design/scripts/export_handoff.py'),
                 '--spec',str(self.spec),'--assets',str(self.assets),'--workflow',str(self.workflow)]
        rejected=subprocess.run(command+['--out',str(self.root/'cli-blocked')],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(rejected.returncode,1)
        self.assertEqual(json.loads(rejected.stdout)['execution_compatibility']['status'],'unsupported')
        before=self.spec.read_bytes();out=self.root/'symbolic'
        allowed=subprocess.run(command+['--out',str(out),'--allow-symbolic-unsupported'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(allowed.returncode,0,allowed.stdout+allowed.stderr)
        report=json.loads(allowed.stdout)
        self.assertEqual(report['execution_profile_status'],'unsupported')
        self.assertFalse((out/'mcgs-plan.json').exists())
        plan=json.loads((out/'mcgs-plan.symbolic.json').read_text(encoding='utf-8'))
        self.assertEqual(plan['windows'][0]['controls'][-1]['interaction']['scope'],'plc_unverified')
        self.assertEqual(self.spec.read_bytes(),before)
        issue=next(i for i in report['execution_profile_issues']if i['field']=='interaction.scope')
        self.assertEqual((issue['page_id'],issue['component_id']),('io','start'))

    def test_measurement_role_still_blocks_right_aligned_numeric_export(self):
        c=next(c for c in self.source['pages'][0]['controls']if c['id']=='io_value')
        c['role']='measurement';c['numeric_layout']['horizontal']='right';self.prepare()
        with self.assertRaises(ValueError):export(self.spec,self.assets,self.root/'blocked',self.workflow)

    def test_boolean_numeric_input_is_blocked_during_formal_export(self):
        numeric_input(self.source,'boolean');self.prepare()
        with self.assertRaises(ValueError):export(self.spec,self.assets,self.root/'blocked',self.workflow)

    def test_button_subrect_blocks_formal_export(self):
        self.source['pages'][0]['controls'][-1]['texts'][0]['rect_px']=[5,0,100,40];self.prepare()
        with self.assertRaises(ValueError):export(self.spec,self.assets,self.root/'blocked',self.workflow)

    def test_profile_override_requires_target_recheck(self):
        self.prepare();changed=profile();changed['profile_id']='unreviewed'
        with self.assertRaisesRegex(ValueError,'differs from the reviewed'):
            export(self.spec,self.assets,self.root/'blocked',self.workflow,changed)

    def test_stale_asset_hash_and_changed_revision_are_rejected(self):
        self.prepare();asset=self.source['assets'][0]
        Image.new('RGBA',asset['design_size_px'],(10,10,10,255)).save(self.assets/asset['file'])
        with self.assertRaisesRegex(ValueError,'asset file hash changed'):
            export(self.spec,self.assets,self.root/'stale-asset',self.workflow)
        self.source['design_revision']='u2';self.spec.write_text(json.dumps(self.source),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'revision differs'):
            export(self.spec,self.assets,self.root/'stale-revision',self.workflow)


if __name__=='__main__':unittest.main()
