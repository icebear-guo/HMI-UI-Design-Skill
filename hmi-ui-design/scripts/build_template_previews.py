"""Instantiate reusable layout sources; native project data stays outside skill."""
from pathlib import Path
import argparse,datetime,importlib.util,json,sys
SKILL=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(SKILL/'assets/editor-kit'))
from model_validation import validate
from text_layout import layout_model, LayoutError
from canvas_profile import details as canvas_details
spec=importlib.util.spec_from_file_location('template_library',SKILL/'assets/template-library/library.py');lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
def build(out):
    if out.exists():raise ValueError('输出已存在，请使用新批次')
    variables=[{'name':'process_value','kind':2,'source_id':1,'scope':'design_only'},{'name':'command','kind':1,'source_id':2,'scope':'design_only'}]
    bindings={k:{'name':'process_value','kind':2,'id':1} for k in ('numeric','gauge','percentage_fill','realtime_trend')};bindings['bit']={'name':'command','kind':1,'id':2}
    targets=[{'name':style['page'],'id':0xffffffff} for style in lib.STYLES.values()]
    out.mkdir(parents=True);pages=[];stamp=datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    for style in lib.STYLES:
        model,layout=layout_model(lib.make(style,variables,bindings,targets,'template-'+style+'-'+stamp),'grow')
        if layout['errors']:raise LayoutError('模板文字尺寸适配失败：'+style+'；'+str(layout['errors']))
        model['text_layout_report']=layout
        model['canvas_profile']=canvas_details(model['width'],model['height'])
        model=validate(model);name=lib.STYLES[style]['page'];pages.append({'id':style,'name':name,'model':style+'.json'})
        (out/(style+'.json')).write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8');(out/(style+'.html')).write_text(lib.preview_html(model),encoding='utf-8')
    catalog={'schema':'hmi-ui-editor-pages/2.0-test','revision':'templates-'+stamp,'pages':pages}
    (out/'pages.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    cards=''.join(f'<a href="{key}.html"><b>{style["title"]}</b><span>{style["page"]} · 1024×600</span></a>' for key,style in lib.STYLES.items())
    index='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>工业HMI模板库</title><style>body{margin:60px auto;max-width:1100px;padding:24px;background:#eef2f6;font:16px Microsoft YaHei;color:#26394c}h1{font-size:32px}p{color:#697d92;line-height:1.8}section{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:36px}a{display:flex;flex-direction:column;gap:24px;background:white;border-radius:14px;padding:36px 24px;color:#26394c;text-decoration:none;border-top:5px solid #2878ed}a:nth-child(2){border-color:#12bfa5}a:nth-child(3){border-color:#d48a29}span{font-size:13px;color:#758698}</style><h1>工业 HMI 布局与配色模板</h1><p>选择布局预览。每套包含独立组件源与模型，公共样式按参数复用；文字、变量和原生控件分别保留。<br>点击进入后可修改模拟数值，检查布局与配色。模板文件可离线打开。</p><section>'+cards+'</section></html>'
    (out/'index.html').write_text(index,encoding='utf-8')
    return {'pages':str(out/'pages.json'),'preview':str(out/'index.html'),'templates':list(lib.STYLES),'native_structures':'built_in','mcp_required':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.out),ensure_ascii=False))
