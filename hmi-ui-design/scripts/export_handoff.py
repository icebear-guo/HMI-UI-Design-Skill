"""Validate same-source component specifications and export complete machine tables."""
import argparse,csv,hashlib,json,re,sys,copy,shutil,os
from pathlib import Path
from PIL import Image,ImageFont
from check_project_workflow import check as check_workflow
from mcgs_plan import compile_plan
from text_layout_policy import validate_text_layout
from asset_quality import inspect_asset
from handoff_policy import validate_control,validate_branding,validate_signals
from check_equipment_flow import check as check_equipment_flow

ASSET_NAME=re.compile(r'[A-Za-z0-9_]+\Z');HEX=re.compile(r'#[0-9a-fA-F]{6}\Z')
KINDS={'picture','button','indicator','state_switch','label','numeric_input','numeric_display','rectangle','rounded_rectangle','group'}
def need(ok,message):
    if not ok:raise ValueError(message)
def rect(a,label):
    need(isinstance(a,list) and len(a)==4 and all(type(x)is int for x in a) and min(a)>=0 and a[2]>0 and a[3]>0,label+' invalid x/y/w/h')
    return a
def check(spec,assets_root):
    data=copy.deepcopy(spec);need(data['schema_version']=='1.05','handoff schema 1.05 required; migrate old source explicitly, do not relabel an old export');need(data['design_revision'],'missing design revision');need(re.fullmatch('[a-f0-9]{64}',data['source_sha256']),'missing source SHA256')
    validate_branding(data)
    for page in data['pages']:
        for control in page['controls']:validate_control(control)
    validate_signals(data)
    inventory=data.get('source_inventory')
    need(isinstance(inventory,list) and bool(inventory),'frozen source_inventory required; do not derive inventory from exported backgrounds')
    expected={}
    for item in inventory:
        key=(item['page_id'],item['component_id']);need(key not in expected,'duplicate source inventory component');expected[key]=item
    inventory_sha=hashlib.sha256(json.dumps(inventory,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    need(data.get('source_inventory_sha256')==inventory_sha,'source inventory SHA differs from frozen inventory')
    pages={p['id']:p for p in data['pages']};need(len(pages)==len(data['pages']),'duplicate page ID')
    common_pages={p['common_page_id'] for p in data['pages'] if p.get('common_page_id') is not None}
    for page in data['pages']:
        current=page['id'];seen=set()
        while current is not None:
            need(current in pages,'missing common page')
            need(current not in seen,'common page self-reference/cycle');seen.add(current);current=pages[current].get('common_page_id')
    assets={a['id']:a for a in data['assets']};need(len(assets)==len(data['assets']),'duplicate asset ID');filenames=set();asset_rows=[];controls=[];texts=[];refs=set();ownership={}
    for a in data['assets']:
        p=Path(a['file']);need(not p.is_absolute() and len(p.parts)==1 and p.suffix=='.png' and ASSET_NAME.fullmatch(p.stem),'invalid MCGS asset filename: '+a['file'])
        need(p.name.casefold() not in filenames,'case-insensitive duplicate filename');filenames.add(p.name.casefold())
        need(a['export_method']=='component_render' and a['source_component_id'],'asset must be rendered from a source component')
        need(a['text_baked'] is False,'native text must not be baked in graphic PNG')
        path=assets_root/p;need(path.is_file(),'missing PNG '+str(path))
        with Image.open(path) as im:
            need(im.format=='PNG' and list(im.size)==a['design_size_px'],'PNG is not exact 1:1 size: '+p.name)
            alpha=im.convert('RGBA').getchannel('A').getextrema();a['alpha_range']=list(alpha)
            rgba_sha=hashlib.sha256(im.convert('RGBA').tobytes()).hexdigest()
            need(not a.get('rgba_sha256') or a['rgba_sha256']==rgba_sha,'asset pixel hash changed; regenerate the affected source mapping: '+a['id'])
            a['rgba_sha256']=rgba_sha
        a['content_check']=inspect_asset(path,a.get('content_expectation'))
        actual_sha=hashlib.sha256(path.read_bytes()).hexdigest()
        need(not a.get('sha256') or a['sha256']==actual_sha,'asset file hash changed; regenerate the affected source mapping: '+a['id'])
        a['sha256']=actual_sha;asset_rows.append(a)
    for page in data['pages']:
        w,h=page['canvas_px'];need(type(w)is int and type(h)is int and min(w,h)>0,'invalid page canvas')
        need(page.get('common_page_id') is None or page['common_page_id'] in pages,'missing common page')
        cs={c['id']:c for c in page['controls']};need(len(cs)==len(page['controls']),'duplicate component ID in '+page['id'])
        for c in page['controls']:
            validate_text_layout(c)
            validate_control(c)
            source_item=expected.get((page['id'],c['id']))
            need(source_item is not None and source_item['role']==c['role'],'component missing from frozen source inventory or role changed')
            need(c['kind'] in KINDS,'unsupported kind');x,y,cw,ch=rect(c['rect_px'],c['id']);need(x+cw<=w and y+ch<=h,'component outside page')
            need(c.get('delivery_mode')!='merged' and not c.get('merged_into'),'independent component cannot be baked into parent background')
            if c['kind']=='picture':need(c.get('binding') is None,'static picture gallery reference does not require variable binding')
            if c['role'] in ('background','layout','decoration_block','decoration_icon'):need(c['kind'] not in ('indicator','state_switch'),'static graphic cannot be a fake variable-bound lamp')
            need(c.get('parent_id') is None or c['parent_id'] in cs,'missing parent component')
            cur=c;seen=set()
            while cur.get('parent_id') is not None:
                need(cur['id'] not in seen,'component parent cycle');seen.add(cur['id']);cur=cs[cur['parent_id']]
            states={s['id']:s for s in c['states']};need(len(states)==len(c['states']),'duplicate state')
            if c['kind']=='picture':need(len(states)==1 and all(s.get('asset_id') for s in c['states']),'static picture needs one independent exported graphic')
            if c['kind'] in ('button','indicator','state_switch'):need({'s0','s1'}<=states.keys(),'missing state for '+c['id'])
            if c['kind'] in ('indicator','numeric_input','numeric_display','state_switch'):need(isinstance(c.get('binding'),dict) and c['binding'].get('semantic'),'missing variable semantic')
            if c.get('binding') is not None:need(c['binding'].get('data_type') in ('boolean','number','string') and isinstance(c['binding'].get('semantic'),str),'explicit variable semantic/data_type required')
            if c['kind'] in ('numeric_input','numeric_display'):
                need(isinstance(c.get('font'),dict) and {'family','size_px','weight','color'}<=c['font'].keys(),'numeric font fields required; no template fallback')
                f=c['font'];need(isinstance(f['family'],str) and bool(f['family']) and type(f['size_px'])is int and f['size_px']>0 and type(f['weight'])is int and 100<=f['weight']<=1000 and HEX.fullmatch(f['color']),'invalid explicit numeric font')
                need(isinstance(c.get('appearance'),dict) and all(type(c['appearance'].get(k))is bool for k in ('fill_enabled','border_enabled','image_enabled')),'numeric fill/border/image settings required')
                if c['binding'].get('unit'):
                    need(c['binding'].get('unit_owner') in ('internal','external'),'explicit unit ownership required')
                    if c['binding']['unit_owner']=='external':need(c['binding'].get('unit_component_id') in cs and cs[c['binding']['unit_component_id']]['kind']=='label','external unit must refer to its separate label component')
            shared=c['role'] in ('navigation_button','global_header','global_status','global_alarm')
            if shared and 'mcgs' in data['target'].lower():need(page['id'] in common_pages,'shared navigation/status must be in a referenced common page')
            if c.get('target_page_id') is not None:
                need(c['target_page_id'] in pages and c['kind']=='button','navigation requires button and valid target')
                if 'mcgs' in data['target'].lower():need(page['id'] in common_pages,'navigation button must be in common page')
                for state in ('s0','s1'):
                    need(any(t.get('text_owner')=='component' and t.get('state') in (None,state) and t.get('text') for t in c['texts']),'navigation caption must be native text inside the same button in both states')
            for s in c['states']:
                need(s['semantic'],'state semantic required');aid=s.get('asset_id')
                if c['kind'] in ('button','indicator','state_switch') and 'mcgs' in data['target'].lower():need(aid,'MCGS buttons/indicators require an independently exported image for every state')
                if aid:
                    need(aid in assets,'missing asset '+aid);a=assets[aid]
                    own=a['component_id']==c['id'] and a['page_id']==page['id']
                    shared=bool(c.get('asset_master_id')) and a.get('master_id')==c['asset_master_id'] and a['source_component_id']==c['asset_master_id']
                    need((own or shared) and a['state']==s['id'],'asset ownership/state mismatch; shared assets need an explicit matching master ID')
                    need(a['design_size_px']==[cw,ch],'skin canvas differs from component');refs.add(aid)
            if c['kind'] in ('button','indicator','state_switch') and 'mcgs' in data['target'].lower():
                need(assets[states['s0']['asset_id']]['rgba_sha256']!=assets[states['s1']['asset_id']]['rgba_sha256'],'s0/s1 need visibly distinct decoded graphics, not identical pixels under different names')
            tids=set()
            for t in c['texts']:
                need(t['id'] not in tids,'duplicate text ID');tids.add(t['id'])
                need(isinstance(t['text'],str) and bool(t['text']),'full text required')
                need(t['state'] is None or t['state'] in states,'text state missing')
                need(t['text_owner'] in ('component','external'),'explicit text_owner required')
                tx,ty,tw,th=rect(t['rect_px'],'text '+t['id'])
                if t['text_owner']=='component':need(tx+tw<=cw and ty+th<=ch,'internal text outside parent');absolute=[x+tx,y+ty,tw,th]
                else:
                    need(c['kind']=='label','external text must belong to an independent label control');need(tx+tw<=w and ty+th<=h,'external text outside page')
                    need(t['rect_px']==c['rect_px'],'external label must declare its actual final text rectangle, not a parent container');absolute=t['rect_px']
                need(HEX.fullmatch(t['color']) and t['font_family'] and type(t['font_size_px']) is int and t['font_size_px']>0,'invalid font or colour')
                need(type(t['font_weight']) is int and 100<=t['font_weight']<=1000 and t['align'] in ('left','center','right'),'font weight/alignment required')
                need(t['line_height_px']>=t['font_size_px'],'invalid line height')
                lines=t['text'].splitlines();need(th>=t['line_height_px']*len(lines),'text height insufficient')
                ff=t.get('font_file')
                if not ff and sys.platform=='win32' and t['font_family'] in ('微软雅黑','Microsoft YaHei'):
                    windows_root=Path(os.environ.get('WINDIR') or os.environ.get('SystemRoot') or 'C:/Windows')
                    ff=str(windows_root/'Fonts'/('msyhbd.ttc' if t['font_weight']>=600 else 'msyh.ttc'))
                need(ff and Path(ff).is_file(),'resolved font_file required for '+t['id'])
                ft=ImageFont.truetype(ff,t['font_size_px']);measured=max(ft.getlength(s) for s in lines);margin=t.get('width_margin_px',10)
                need(type(margin)in (int,float) and margin>=0,'invalid width margin');need(measured+margin<=tw,'text width insufficient: '+t['text'])
                texts.append({'page_id':page['id'],'component_id':c['id'],**t,'absolute_rect_px':absolute,'measured_width_px':measured,'width_margin_px':margin})
            controls.append({'page_id':page['id'],**c})
    need(set(assets)==refs,'orphan asset(s): '+str(set(assets)-refs))
    need(set(expected)=={(c['page_id'],c['id']) for c in controls},'missing source components; cannot collapse independent elements into backgrounds')
    return data,controls,texts,asset_rows

def table(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    if not keys:keys=['id']
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def verify_export_choice(spec,workflow_path):
    need(workflow_path is not None,'MCGS export requires the final user export decision and reviewed workflow record')
    result=check_workflow(workflow_path,'mcgs_export');need(result['status']=='ready','MCGS export not confirmed for current design: '+json.dumps(result.get('mcgs_export'),ensure_ascii=False))
    record=json.loads(workflow_path.read_text(encoding='utf-8-sig'));stage=record['stages']['interactive_ui']
    need(spec['design_revision']==stage['revision'],'handoff design revision differs from reviewed UI')
    need(spec['source_sha256'] in {f['sha256'] for f in stage['files']},'handoff source SHA is not in the confirmed UI snapshot')
    relative=Path(spec.get('source_inventory_file',''))
    need(bool(spec.get('source_inventory_file')) and not relative.is_absolute() and all(p not in ('..','.') for p in relative.parts),'source_inventory_file must be a safe reviewed relative path')
    need(relative.as_posix() in {f['file'] for f in stage['files']},'source inventory file was not part of the reviewed UI')
    path=workflow_path.resolve().parent/stage['artifact_dir']/relative
    need(json.loads(path.read_text(encoding='utf-8-sig'))==spec['source_inventory'],'source inventory differs from confirmed snapshot')
    if spec.get('equipment_required') or any(c.get('role') in ('equipment','part') for p in spec['pages'] for c in p['controls']):
        rel=Path(spec.get('equipment_catalog_file',''))
        need(bool(spec.get('equipment_catalog_file')) and not rel.is_absolute() and '..' not in rel.parts,'Equipment projects need an actual reviewed equipment_catalog_file')
        need(rel.as_posix() in {f['file'] for f in stage['files']},'Equipment flow/atlas catalog is not in reviewed sources')
        catalog_path=workflow_path.resolve().parent/stage['artifact_dir']/rel
        catalog=json.loads(catalog_path.read_text(encoding='utf-8-sig'))
        need(catalog['design_revision']==spec['design_revision'],'Equipment flow/atlas revision differs from UI')
        check_equipment_flow(catalog,catalog_path.parent,'atlas')
    return {'status':result['mcgs_export']['state'],'design_revision':stage['revision'],'reviewed_digest':record['mcgs_export']['reviewed_digest'],'decision_message_ref':record['mcgs_export']['message_ref']}

def export(spec_path,assets_root,out,workflow_path=None,execution_profile=None,*,allow_symbolic_unsupported=False):
    need(not out.exists(),'output already exists');raw=spec_path.read_bytes();spec=json.loads(raw.decode('utf-8-sig'))
    decision=verify_export_choice(spec,workflow_path);data,cs,ts,assets=check(spec,assets_root)
    embedded=spec.get('target_execution_profile')
    if execution_profile is None:execution_profile=embedded
    elif embedded is not None and execution_profile!=embedded:
        raise ValueError('Selected execution profile differs from the reviewed target_execution_profile; recheck the target before export')
    if execution_profile is not None:data['target_execution_profile']=copy.deepcopy(execution_profile)
    plan=compile_plan(data,profile_mode='symbolic' if allow_symbolic_unsupported else 'strict')
    compatibility=plan.get('execution_compatibility',{'schema_version':'hmi-execution-check/1.0','status':'not_supplied',
        'issues':[],'automatic_execution_ready':False,'template_resolution':'not_run','native_display':'not_run','native_behavior':'not_run'})
    unsupported=execution_profile is not None and compatibility['status']!='codec_constraints_matched'
    if execution_profile is not None:
        data['target_execution_profile']=copy.deepcopy(plan['execution_profile'])
        for rows in (cs,ts,assets):
            for row in rows:
                row['execution_profile_id']=plan['execution_profile'].get('profile_id')
                row['execution_profile_sha256']=plan['execution_profile'].get('profile_sha256')
    report={'status':'partial','scope':'machine_spec_and_asset_content','checks':{'machine_spec':'pass','asset_content':'pass','rendered_composition':'not_checked','source_visual_inventory':'not_checked','native_display':'not_run','native_behavior':'not_run'},'spec_sha256':hashlib.sha256(raw).hexdigest(),'design_revision':data['design_revision'],'pages':len(data['pages']),'controls':len(cs),'texts':len(ts),'assets':len(assets),'source_components':len(data['source_inventory']),'missing_registered_components':0,'source_visual_inventory_verified':False,'native_software_validation':'not_run'}
    plan_name='mcgs-plan.symbolic.json' if unsupported else 'mcgs-plan.json'
    report['mcgs_export_decision']=decision;report['native_plan']=plan_name
    report['native_plan_status']='unsupported_symbolic_requirements_only' if unsupported else 'symbolic_fields_require_template_resolution'
    report['execution_profile_status']=compatibility['status'];report['automatic_execution_ready']=False
    report['execution_compatibility_report']='execution-compatibility.json'
    report['execution_profile_issues']=compatibility['issues']
    out.mkdir(parents=True)
    (out/'assets').mkdir()
    for a in assets:
        shutil.copyfile(assets_root/a['file'],out/'assets'/a['file'])
        need(hashlib.sha256((out/'assets'/a['file']).read_bytes()).hexdigest()==a['sha256'],'copied asset hash differs')
    workflow_record=json.loads(workflow_path.read_text(encoding='utf-8-sig'));review=workflow_record['stages']['interactive_ui']
    (out/'source').mkdir()
    for f in review['files']:
        source=workflow_path.resolve().parent/review['artifact_dir']/f['file'];dest=out/'source'/f['file'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        need(hashlib.sha256(dest.read_bytes()).hexdigest()==f['sha256'],'reviewed source changed during export')
    report['asset_directory']='assets';report['reviewed_component_source_directory']='source'
    (out/'handoff-spec.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/plan_name).write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'execution-compatibility.json').write_text(json.dumps(compatibility,ensure_ascii=False,indent=2),encoding='utf-8')
    table(out/'content-spec.csv',cs);table(out/'text-spec.csv',ts);table(out/'asset-spec.csv',assets)
    (out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--spec',type=Path,required=True);ap.add_argument('--assets',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--workflow',type=Path,required=True);ap.add_argument('--execution-profile',type=Path)
    ap.add_argument('--allow-symbolic-unsupported',action='store_true',help='Preserve unsupported requirements under mcgs-plan.symbolic.json; never marks automatic execution ready')
    a=ap.parse_args()
    try:
        from execution_profile import load_profile
        selected=load_profile(a.execution_profile) if a.execution_profile else None
        print(json.dumps(export(a.spec,a.assets,a.out,a.workflow,selected,allow_symbolic_unsupported=a.allow_symbolic_unsupported),ensure_ascii=False,indent=2))
    except (ValueError,KeyError,OSError,TypeError) as e:
        error={'status':'fail','error':str(e)}
        if hasattr(e,'report'):error['execution_compatibility']=e.report
        print(json.dumps(error,ensure_ascii=False));sys.exit(1)
