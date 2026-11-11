"""Load explicit project pages without manufacturing example pages."""
from pathlib import Path
import copy,json,re
from model_validation import validate

def load_catalog(path):
    path=Path(path);raw=json.loads(path.read_text(encoding='utf-8'))
    if raw.get('schema')!='hmi-ui-editor-pages/2.0-test' or not isinstance(raw.get('revision'),str) or not raw['revision']:
        raise ValueError('Expected explicit editor pages schema and revision')
    pages=raw.get('pages')
    if not isinstance(pages,list) or not 1<=len(pages)<=6:raise ValueError('Current tested window batch covers1..6 pages')
    seen=set();names=set();revisions=set();result=[]
    for item in pages:
        ident=item.get('id');name=item.get('name')
        if not isinstance(ident,str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,31}',ident) or ident in seen:raise ValueError('Page IDs must be unique and path-safe')
        if not isinstance(name,str) or name!=name.strip() or not re.fullmatch(r'[^\\/:*?"<>|\x00-\x1f]{1,30}',name) or name.casefold() in names:raise ValueError('Page names must be valid and unique')
        value=item.get('model')
        if isinstance(value,str):
            source=Path(value);source=source if source.is_absolute() else path.parent/source
            value=json.loads(source.read_text(encoding='utf-8'))
        model=validate(copy.deepcopy(value))
        if model['revision'] in revisions:raise ValueError('Each page needs its own model revision for isolated drafts')
        seen.add(ident);names.add(name.casefold());revisions.add(model['revision'])
        result.append({'id':ident,'name':name,'model':model})
    return {'revision':raw['revision'],'pages':result,'limit':6}

def single_catalog(model):
    name=str(model.get('title') or '页面').strip()[:30]
    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',name) or '页面'
    return {'revision':model['revision'],'pages':[{'id':'page01','name':name,'model':model}],'limit':6}
