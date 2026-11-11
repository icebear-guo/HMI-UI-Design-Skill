"""Build a project-local session using built-in native structures."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'assets/editor-kit'))
from model_validation import validate
from page_catalog import load_catalog
def prepare(model_path,out,port=18767,allow_copy=False,pages_path=None,template_previews=None,binding_mode='unbound'):
    catalog=load_catalog(pages_path) if pages_path else None
    model=catalog['pages'][0]['model'] if catalog else validate(json.loads(model_path.read_text(encoding='utf-8')))
    if out.exists():raise ValueError('会话目录已存在，请使用新批次')
    if binding_mode not in ('unbound','names'):raise ValueError('不支持的绑定方式')
    out.mkdir(parents=True);(out/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
    config={'schema':'hmi-ui-editor-session/2.0-test','model':'model.json','port':port,'copy_authorized':allow_copy,'binding_mode':binding_mode}
    if template_previews:config['template_previews']=str(template_previews.resolve())
    if catalog:
        stored={'schema':'hmi-ui-editor-pages/2.0-test','revision':catalog['revision'],'pages':[]};(out/'models').mkdir()
        for page in catalog['pages']:
            rel='models/'+page['id']+'.json';(out/rel).write_text(json.dumps(page['model'],ensure_ascii=False,indent=2),encoding='utf-8')
            stored['pages'].append({'id':page['id'],'name':page['name'],'model':rel})
        (out/'pages.json').write_text(json.dumps(stored,ensure_ascii=False,indent=2),encoding='utf-8');config['pages']='pages.json'
    (out/'session.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');return out/'session.json'
if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--model',type=Path);group.add_argument('--pages',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=18767);p.add_argument('--allow-copy',action='store_true');p.add_argument('--template-previews',type=Path);p.add_argument('--binding-mode',choices=['unbound','names'],default='unbound');a=p.parse_args()
    print(prepare(a.model,a.out,a.port,a.allow_copy,a.pages,a.template_previews,a.binding_mode))
