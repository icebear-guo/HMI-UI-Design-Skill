"""Repeatable synthetic capture benchmark; keeps evidence and never deletes prior batches."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from PIL import Image


def compare_outputs(baseline, current, components, rgb_tolerance=1):
    exact_differences,failures=[],[];max_rgb=max_alpha=0
    for component in components:
        with Image.open(baseline/component['file']) as a,Image.open(current/component['file']) as b:
            if a.size!=b.size:
                failures.append(component['id']);continue
            pairs=zip(a.convert('RGBA').get_flattened_data(),b.convert('RGBA').get_flattened_data()) if hasattr(a,'get_flattened_data') else zip(list(a.convert('RGBA').getdata()),list(b.convert('RGBA').getdata()))
            rgb=alpha=0
            for x,y in pairs:
                rgb=max(rgb,*(abs(x[i]-y[i])for i in range(3)));alpha=max(alpha,abs(x[3]-y[3]))
            max_rgb,max_alpha=max(max_rgb,rgb),max(max_alpha,alpha)
            if rgb or alpha:exact_differences.append(component['id'])
            if rgb>rgb_tolerance or alpha:failures.append(component['id'])
    return {'status':'fail' if failures else 'pass','rgb_tolerance_per_channel':rgb_tolerance,
            'alpha_tolerance':0,'max_rgb_delta':max_rgb,'max_alpha_delta':max_alpha,
            'exact_difference_ids':exact_differences,'outside_tolerance_ids':failures,
            'scope':'mechanical pixel comparison with explicit gradient/compositing rounding allowance; no aesthetic acceptance'}


def run(browser, node, output, count=260, pages=7, baseline_renderer=None, rgb_tolerance=1):
    output=Path(output).absolute();output.mkdir()
    source=output/'source';source.mkdir()
    (source/'shared.css').write_text('body{margin:0}.asset{position:absolute;width:32px;height:24px;border-radius:5px;background:linear-gradient(#76a3bb,#285171);box-shadow:inset 0 0 0 1px #123}',encoding='utf-8')
    components=[]
    for p in range(pages):
        nodes=[]
        for i in range(p,count,pages):
            position=i//pages
            nodes.append(f'<div class="asset" id="asset_{i}" style="left:{(position%16)*48}px;top:{(position//16)*40}px"></div>')
            components.append({'id':f'asset_{i}','html':f'source/page_{p}.html','selector':f'#asset_{i}',
                               'width':32,'height':24,'file':f'asset_{i}.png'})
        (source/f'page_{p}.html').write_text('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="shared.css">'+''.join(nodes),encoding='utf-8')
    manifest={'schema_version':'component-render/1.0','browser':browser,'components':components}
    script=Path(__file__).resolve().parents[1]/'hmi-ui-design/scripts/render_components.mjs'
    results=[]
    def capture(name,renderer):
        (output/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        t=time.perf_counter()
        process=subprocess.run([node,str(renderer),str(output/'manifest.json'),str(output/name)],
                               capture_output=True,text=True,encoding='utf-8',timeout=240)
        elapsed=time.perf_counter()-t
        report=json.loads((output/name/'render-report.json').read_text(encoding='utf-8'))
        if process.returncode:raise RuntimeError(json.dumps(report)+process.stderr)
        row={'run':name,'wall_seconds':elapsed,'reported_seconds':report['seconds'],
             'components':len(report['components']),'metrics':report.get('metrics')}
        results.append(row);print(json.dumps(row),flush=True)
        return row
    capture('baseline_reload',baseline_renderer or script)
    manifest['optimization']={'static':True,'source_root':'source','cache_dir':'cache','backend_key':'synthetic-static-benchmark'}
    capture('optimized_cold',script)
    capture('optimized_unchanged',script)
    comparison=compare_outputs(output/'baseline_reload',output/'optimized_cold',components,rgb_tolerance)
    p=source/'page_0.html';p.write_text(p.read_text(encoding='utf-8')+'<style>#asset_0{background:#934522}</style>',encoding='utf-8')
    capture('optimized_changed_page_source',script)
    summary={'scope':'synthetic static captures; excludes model planning, illustration, human waiting and production-project runtime',
             'capture_count':count,'source_documents':pages,'pixel_comparison':comparison,'runs':results,
             'changed_source':'page_0.html; all captures depending on this file conservatively invalidate',
             'deleted_prior_files':0}
    (output/'benchmark-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if comparison['status']!='pass':raise RuntimeError('Pixels differ outside explicit tolerance: '+str(comparison))
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--browser',required=True);ap.add_argument('--node',default='node')
    ap.add_argument('--out',required=True,type=Path);ap.add_argument('--count',type=int,default=260)
    ap.add_argument('--pages',type=int,default=7);ap.add_argument('--baseline-renderer',type=Path)
    ap.add_argument('--rgb-tolerance',type=int,default=1)
    args=ap.parse_args()
    if not 1<=args.pages<=args.count:ap.error('Require 1 <= pages <= count')
    if args.rgb_tolerance not in (0,1):ap.error('Use 0 for exact comparison or 1 for gradient rounding allowance')
    run(args.browser,args.node,args.out,args.count,args.pages,args.baseline_renderer,args.rgb_tolerance)
