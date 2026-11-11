"""Check relocated native generation without MCP, donor or external codec access."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys
SKILL=Path(__file__).resolve().parent.parent
PROBE='''from pathlib import Path
import base64,copy,io,json,sys
from PIL import Image
root=Path(sys.argv[1]);session=Path(sys.argv[2]);sys.path.insert(0,str(root/'assets/editor-kit'))
original_read=Path.read_bytes
def guarded_read(path):
    if path.suffix.lower() in ('.mcp','.mdb'):raise AssertionError('Native generation must not read a project')
    return original_read(path)
Path.read_bytes=guarded_read
from runtime_context import configure
c=configure(session);assert c.native_ready() and c.window_ready(),c.native_error
from native_adapter import compile_model
from window_adapter import compile_windows
checks=[]
def check(name,value):
    checks.append({'name':name,'pass':bool(value)})
    if not value:raise AssertionError(name)
def assets_for(model):
    assets={}
    for n in model['components']:
        states=['s0','s1'] if n.get('states') else ['s0'] if n['kind']=='picture' or n.get('background') else []
        for state in states:
            im=Image.new('RGBA',(n['rect'][2]-n['rect'][0],n['rect'][3]-n['rect'][1]),'#2878ed');stream=io.BytesIO();im.save(stream,format='PNG');assets[n['id']+':'+state]=stream.getvalue()
    return assets
specs=[];types=set()
for page in c.catalog['pages']:
    model=page['model'];assets=assets_for(model);blob,report=compile_model(model,assets);types.update(report['types'])
    check(page['id']+'_unbound_native_generation',report['binding_mode']=='unbound' and not report['source_mcp_required'])
    changed=copy.deepcopy(model);mapping={v['name']:'新项目_'+str(i) for i,v in enumerate(changed['variables'])}
    for v in changed['variables']:v['source_id']+=30000;v['name']=mapping[v['name']]
    for n in changed['components']:
        if n.get('binding'):n['binding']['name']=mapping[n['binding']['name']];n['binding']['id']+=30000
    independent,other=compile_model(changed,assets);check(page['id']+'_unbound_bytes_ignore_design_ids_and_names',independent==blob)
    token=c.request_binding('names')
    try:
        named,named_report=compile_model(changed,assets);check(page['id']+'_unicode_names_without_old_ids',named_report['binding_status']=='names_pending_native_compile')
    finally:c.reset_request_binding(token)
    specs.append({'id':page['id'],'name':page['name'],'revision':model['revision'],'patches':[],
        'assets':{key:base64.b64encode(data).decode('ascii') for key,data in assets.items()}})
check('all_twelve_types',len(types)==12)
windows,report,exports=compile_windows(c.catalog,{'revision':c.catalog['revision'],'pages':specs})
check('windows_generate_without_template_files',report['window_count']==3 and report['count']>0)
check('no_database_modules_imported',not any(name in sys.modules for name in ('pro_lib','mcgs_file','native_format','pyodbc')))
check('codecs_are_inside_relocated_skill',all(str(c.codec_root) in str(sys.modules[name].__file__) for name in ('mcs_window_archive','mcs_button_control','mcs_input_text')))
print(json.dumps({'checks':checks,'all_pass':all(x['pass'] for x in checks),'clipboard_written':False,'source_mcp_required':False,'window_bytes':len(windows)},ensure_ascii=False))
'''
def run(out):
    out=out.resolve()
    if out.exists() or out.is_relative_to(SKILL.resolve()):raise ValueError('请使用skill目录外的新检查目录')
    out.mkdir(parents=True);moved=out/'全新任务 Different Environment'/'hmi-ui-design'
    shutil.copytree(SKILL,moved,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    templates=out/'新模板';session=out/'新会话'
    commands=[[str(moved/'scripts/build_template_previews.py'),'--out',str(templates)],
        [str(moved/'scripts/prepare_editor_session.py'),'--pages',str(templates/'pages.json'),'--out',str(session),'--allow-copy','--port','18776']]
    for args in commands:
        p=subprocess.run([sys.executable,'-X','utf8',*args],capture_output=True,text=True,encoding='utf-8')
        if p.returncode:raise ValueError(p.stderr or p.stdout)
    probe=out/'native_probe.py';probe.write_text(PROBE,encoding='utf-8')
    p=subprocess.run([sys.executable,'-X','utf8',str(probe),str(moved),str(session/'session.json')],capture_output=True,text=True,encoding='utf-8')
    if p.returncode:raise ValueError(p.stderr or p.stdout)
    report=json.loads(p.stdout);report['relocated_skill']=str(moved);report['session']=str(session/'session.json')
    (out/'portability-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=run(a.out);print(json.dumps({'all_pass':r['all_pass'],'checks':len(r['checks']),'session':r['session']},ensure_ascii=False))
