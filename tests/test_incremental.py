"""Observable incremental behavior; browser fixtures stay separate from customer projects."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
SCRIPTS=REPO/'hmi-ui-design/scripts'
sys.path.insert(0,str(SCRIPTS))
from sync_component_sources import sync
from prepare_render_manifest import prepare

NODE=os.environ.get('HMI_TEST_NODE') or shutil.which('node')
BROWSER=os.environ.get('HMI_TEST_BROWSER')


def workspace(prefix):
    root=os.environ.get('HMI_TEST_WORK')
    if root:Path(root).mkdir(parents=True,exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix,dir=root))


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace('source-check-')
        self.plan=self.root/'plan.json'
        self.data={'schema_version':'hmi-source-files/1.0','files':[
            {'file':'a.html','content':'A','component_ids':['a'],'page_ids':['p1']},
            {'file':'b.html','content':'B','component_ids':['b'],'page_ids':['p2']}]}

    def run_sync(self,workflow=None):
        self.plan.write_text(json.dumps(self.data),encoding='utf-8')
        return sync(self.plan,self.root/'draft',workflow)

    def test_unchanged_files_keep_timestamps_and_single_change_is_local(self):
        self.assertEqual(self.run_sync()['changed_files'],2)
        before={p.name:p.stat().st_mtime_ns for p in (self.root/'draft').iterdir()}
        self.assertEqual(self.run_sync()['changed_files'],0)
        self.assertEqual(before,{p.name:p.stat().st_mtime_ns for p in (self.root/'draft').iterdir()})
        self.data['files'][0]['content']='A changed'
        result=self.run_sync()
        self.assertEqual(result['changed_files'],1)
        self.assertEqual(result['affected_component_ids'],['a'])
        self.assertEqual((self.root/'draft/b.html').stat().st_mtime_ns,before['b.html'])

    def test_obsolete_source_is_preserved(self):
        self.run_sync();self.data['files'].pop()
        self.assertEqual(self.run_sync()['obsolete_files_preserved'],['b.html'])
        self.assertTrue((self.root/'draft/b.html').exists())

    def test_invalid_plan_does_not_partially_update(self):
        self.data['files'][1]['file']='../escape.html'
        with self.assertRaises(ValueError):self.run_sync()
        self.assertFalse((self.root/'draft').exists())

    def test_frozen_review_is_untouched(self):
        self.run_sync()
        workflow=self.root/'workflow.json'
        workflow.write_text(json.dumps({'stages':{'interactive_ui':{'artifact_dir':'draft','status':'confirmed'}}}))
        self.data['files'][0]['content']='overwrite'
        with self.assertRaises(ValueError):self.run_sync(workflow)
        with self.assertRaises(ValueError):sync(self.plan,self.root/'new/../draft',workflow)
        self.assertEqual((self.root/'draft/a.html').read_text(),'A')

    def test_geometry_is_derived_once_for_render_and_delivery(self):
        (self.root/'source').mkdir();(self.root/'source/a.html').write_text('<div></div>')
        delivery={'schema_version':'1.2','assets':[{'id':'plate-s0','file':'old.png','design_size_px':[40,30]}],
                  'pages':[{'id':'overview','preview':'oldpage.png','design_size_px':[100,80]}]}
        (self.root/'delivery.json').write_text(json.dumps(delivery))
        project={'schema_version':'hmi-render-project/1.0','browser':'browser','delivery_manifest':'delivery.json',
            'captures':{'assets':{'plate-s0':{'html':'source/a.html','selector':'#asset'}},
                        'pages':{'overview':{'html':'source/a.html','selector':'#page','brand_selector':'#brand'}}}}
        p=self.root/'project.json';p.write_text(json.dumps(project))
        result=prepare(p,self.root/'render.json')
        manifest=json.loads((self.root/'render.json').read_text())
        derived=json.loads(Path(result['delivery_manifest']).read_text())
        self.assertEqual([x['width'] for x in manifest['components']],[40,100])
        self.assertEqual(derived['assets'][0]['file'],'render_png/plate_s0.png')
        with self.assertRaises((ValueError,FileExistsError)):prepare(p,self.root/'render.json')


@unittest.skipUnless(NODE and BROWSER,'Set HMI_TEST_BROWSER and supply Node to run real browser checks')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace('render-check-');(self.root/'source').mkdir()
        (self.root/'source/common.css').write_text('body{margin:0}.box{width:40px;height:30px;background:#456789}')
        for name in ('a','b'):
            (self.root/f'source/{name}.html').write_text('<link rel="stylesheet" href="common.css"><div id="one" class="box"></div><div id="two" class="box"></div>')
        self.manifest={'schema_version':'component-render/1.0','browser':BROWSER,
            'optimization':{'static':True,'source_root':'source','cache_dir':'cache'},
            'components':[{'id':n,'html':f'source/{n}.html','selector':'#one','width':40,'height':30,'file':n+'.png'} for n in ('a','b')]}
        self.count=0

    def render(self,expected=0,extra=()):
        self.count+=1;out=self.root/f'batch-{self.count}'
        p=self.root/'manifest.json';p.write_text(json.dumps(self.manifest))
        result=subprocess.run([NODE,str(SCRIPTS/'render_components.mjs'),str(p),str(out),*extra],
            capture_output=True,text=True,encoding='utf-8',timeout=45)
        report=json.loads((out/'render-report.json').read_text())
        self.assertEqual(result.returncode,expected,str(report)+result.stderr)
        return report,out

    def test_single_component_dependency_change_and_unrelated_file(self):
        cold,_=self.render();self.assertEqual(cold['metrics']['rendered_components'],2)
        (self.root/'source/unrelated.txt').write_text('new unrelated file')
        warm,_=self.render();self.assertEqual(warm['metrics']['reused_components'],2)
        self.assertEqual(warm['metrics']['page_loads'],0);self.assertIsNone(warm['runtime_profile'])
        p=self.root/'source/a.html';p.write_text(p.read_text()+'<style>#one{background:red}</style>')
        changed,_=self.render()
        self.assertEqual((changed['metrics']['rendered_components'],changed['metrics']['reused_components']),(1,1))
        a=next(x for x in changed['components'] if x['id']=='a')
        self.assertEqual(a['cache_miss']['files'],['a.html'])

    def test_shared_style_invalidates_only_dependents(self):
        self.render();p=self.root/'source/common.css';p.write_text(p.read_text()+'.box{background:red}')
        changed,_=self.render();self.assertEqual(changed['metrics']['rendered_components'],2)
        self.assertTrue(all('common.css' in x['cache_miss']['files'] for x in changed['components']))

    def test_same_document_is_loaded_once_and_matches_legacy_pixels(self):
        self.manifest['components'][1]['html']='source/a.html';self.manifest['components'][1]['selector']='#two'
        grouped,new=self.render();self.assertEqual(grouped['metrics']['page_loads'],1)
        self.manifest.pop('optimization')
        old,legacy=self.render();self.assertEqual(old['metrics']['page_loads'],2)
        from PIL import Image
        for file in ('a.png','b.png'):
            with Image.open(new/file) as a,Image.open(legacy/file) as b:self.assertEqual(a.convert('RGBA').tobytes(),b.convert('RGBA').tobytes())

    def test_corrupt_cache_rebuilds_only_that_component(self):
        self.render()
        entry=next((self.root/'cache').rglob('*.json'))
        metadata=json.loads(entry.read_text());(entry.parent/metadata['png']).write_bytes(b'broken')
        repaired,_=self.render()
        self.assertEqual((repaired['metrics']['rendered_components'],repaired['metrics']['reused_components']),(1,1))

    def test_failure_preserves_progress_and_retry_reuses_success(self):
        self.manifest['components'][1]['selector']='#missing'
        failed,prior=self.render(expected=1)
        self.assertEqual(len(failed['components']),1);self.assertTrue((prior/'a.png').is_file())
        self.assertTrue((prior/'checkpoints.jsonl').is_file())
        self.manifest['components'][1]['selector']='#one'
        repaired,_=self.render()
        self.assertEqual((repaired['metrics']['rendered_components'],repaired['metrics']['reused_components']),(1,1))
        self.assertEqual(json.loads((prior/'render-report.json').read_text())['status'],'fail')

    def test_dom_probe_is_live_and_reports_mechanical_hints(self):
        html='<div id="page" style="width:40px;height:30px;position:relative" data-hmi-page="p"><div data-hmi-component="label" data-hmi-kind="label" style="position:absolute;left:35px;width:30px;height:20px;overflow:hidden">LongLongLongText</div></div>'
        (self.root/'source/a.html').write_text(html)
        self.manifest['components']=[dict(self.manifest['components'][0],selector='#page',capture=False,collect_hmi=True)]
        report,_=self.render();codes={x['code'] for x in report['components'][0]['hmi']['layout_issues']['issues']}
        self.assertIn('outside_page',codes);self.assertIn('text_overflow_hint',codes)
        repeat,_=self.render();self.assertEqual(repeat['metrics']['reused_components'],0)

    def test_external_resources_are_rejected_without_cache_entry(self):
        (self.root/'source/a.html').write_text('<img src="https://example.invalid/test.png"><div id="one" class="box"></div>')
        self.manifest['components']=self.manifest['components'][:1]
        failed,_=self.render(expected=1);self.assertEqual(failed['status'],'fail')
        self.assertFalse(list((self.root/'cache').rglob('*.json')))

    def test_no_cache_revalidates_all_without_changing_prior_outputs(self):
        first,out=self.render();before=hashlib.sha256((out/'a.png').read_bytes()).hexdigest()
        fresh,_=self.render(extra=('--no-cache',));self.assertEqual(fresh['metrics']['rendered_components'],2)
        self.assertEqual(hashlib.sha256((out/'a.png').read_bytes()).hexdigest(),before)


if __name__=='__main__':unittest.main()
