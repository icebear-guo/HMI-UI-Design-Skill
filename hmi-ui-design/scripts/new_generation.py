"""Allocate fresh UI source/render/delivery paths. Never deletes or moves history."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import uuid
from check_generation_policy import check


def allocate(root,prefix='ui',scripts=()):
    root=Path(root).absolute()
    if '..' in root.parts:raise ValueError('Generation root must not contain parent traversal')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}',prefix):raise ValueError('Use a short path-free generation prefix')
    for path in (root,*root.parents):
        if path.is_symlink() or path.is_junction():raise ValueError('Linked generation roots are unsupported')
    policy=check(list(scripts))
    if policy['status']!='pass':raise ValueError('Generated builder contains deletion/reset operations: '+json.dumps(policy['findings'],ensure_ascii=False))
    root.mkdir(parents=True,exist_ok=True)
    run=root/(prefix+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:10])
    run.mkdir()
    (run/'components').mkdir()
    report={'status':'allocated','generation_dir':str(run),'component_source_dir':str(run/'components'),
            'manifest':str(run/'render-manifest.json'),'render_out':str(run/'png'),
            'delivery_out':str(run/'delivery'),'failed_outputs':'preserve for diagnosis; do not delete on retry',
            'policy_check':policy,'native_profile_or_asset_validation':'not_performed_by_directory_allocator'}
    (run/'generation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--prefix',default='ui')
    parser.add_argument('--check',action='append',default=[],type=Path)
    args=parser.parse_args()
    print(json.dumps(allocate(args.root,args.prefix,args.check),ensure_ascii=False,indent=2))
