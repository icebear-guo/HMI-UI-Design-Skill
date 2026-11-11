"""Check the customer's declared content against the actual generated page catalog."""
from pathlib import Path
import argparse, json, sys
from project_source import load, check_coverage, save_json
from page_catalog import load_catalog

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True);p.add_argument('--pages', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a=p.parse_args()
    try:
        if a.out.exists():raise ValueError('Use a new report path')
        source, expected, report=load(a.source)
        if a.pages:
            catalog=load_catalog(a.pages)
            report=check_coverage(source,catalog)
            expected_hash=expected['pages'][0]['model']['source_project']['sha256']
            drift=[page['id'] for page in catalog['pages'] if page['model'].get('source_project',{}).get('sha256')!=expected_hash]
            missing=set(p['id'] for p in expected['pages'])-set(p['id'] for p in catalog['pages'])
            if drift or missing:
                report['status']='fail';report['errors']+=['Source identity drift: '+','.join(drift),'Missing project pages: '+','.join(sorted(missing))]
        save_json(a.out,report);print(json.dumps(report,ensure_ascii=False,indent=2))
        sys.exit(0 if report['status']=='complete' else 3 if report['status']=='partial' else 1)
    except (ValueError,OSError,KeyError,TypeError) as error:
        p.exit(1,str(error)+'\n')
