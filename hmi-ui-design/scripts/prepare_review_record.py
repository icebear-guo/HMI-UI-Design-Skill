"""Create a schema-1.1 review record from actual artifact/evidence inputs.

The agent supplies the real customer message; this tool never invents consent.
Paths are relative to the evidence/output directory. It hashes actual snapshots.
"""
from pathlib import Path
import argparse, copy, json
from check_project_workflow import STAGES, stage_result, relative, no_links

def build(evidence_file,out):
    evidence_file=Path(evidence_file).resolve();out=Path(out).resolve()
    if out.exists() or out.parent!=evidence_file.parent:raise ValueError('Use a new record beside the evidence input')
    data=json.loads(evidence_file.read_text(encoding='utf-8-sig'))
    if data.get('schema')!='hmi-review-evidence/1.0':raise ValueError('Expected hmi-review-evidence/1.0')
    record=json.loads((Path(__file__).resolve().parent.parent/'assets/project-workflow.template.json').read_text(encoding='utf-8'))
    record['project_revision']=data['project_revision'];record['page_ids']=data['page_ids'];record['page_count']=len(data['page_ids'])
    if data.get('delegation') is not None:record['review_policy']=copy.deepcopy(data['delegation'])
    prior={}
    for name in STAGES:
        item=data.get('stages',{}).get(name)
        stage=record['stages'][name]
        if item is not None:
            stage.update({k:item[k] for k in ('revision','artifact_dir','entry','status')})
            folder=out.parent/relative(stage['artifact_dir']);no_links(folder)
            if not folder.is_dir():raise ValueError('Actual review directory missing: '+str(folder))
            existing=set(item.get('existing_assets',[]))
            stage['files']=[]
            import hashlib
            for file in sorted(folder.rglob('*')):
                no_links(file)
                if file.is_file():
                    rel=file.relative_to(folder).as_posix()
                    stage['files'].append({'file':rel,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                                           'origin':'existing_asset' if rel in existing else 'generated'})
            stage['depends_on']={k:prior[k]['review_digest'] for k in prior}
            if name=='interactive_ui':stage['pages']=copy.deepcopy(item['pages'])
            confirmation=item.get('customer_confirmation')
            if stage['status']=='confirmed' and not confirmation:raise ValueError('Actual customer evidence required; use awaiting_customer while pending')
            if stage['status']=='delegated' and name not in record.get('review_policy',{}).get('stages',[]):raise ValueError('Explicit delegation evidence and stage scope required')
            stage['customer_confirmation']=None
            pending=stage_result(record,name,out.parent,prior)
            if stage['status']=='confirmed':
                stage['customer_confirmation']={**confirmation,'reviewed_digest':pending['review_digest']}
        prior[name]=stage_result(record,name,out.parent,prior)
    # Use the maintained parser, not a second hand-written workflow schema.
    from check_project_workflow import fields, ID
    if not record['page_ids'] or any(not isinstance(i,str) or not ID.fullmatch(i) for i in record['page_ids']):raise ValueError('Explicit valid page IDs required')
    out.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from check_project_workflow import check
    result=check(out,'delivery')
    return {'record':str(out),'status':result['status'],'stages':result['stages']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(build(a.evidence,a.out),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:p.exit(1,str(error)+'\n')
