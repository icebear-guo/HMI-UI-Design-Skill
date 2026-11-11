"""Check or expand an existing model using the shared, measured text layout."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'assets/editor-kit'))
from model_validation import validate
from text_layout import layout_model

def run(model_file, report_file, out_file=None, policy='check'):
    model_file=Path(model_file);report_file=Path(report_file)
    if report_file.exists() or out_file and Path(out_file).exists():
        raise ValueError('Use new output/report files; existing models are retained')
    model=validate(json.loads(model_file.read_text(encoding='utf-8-sig')))
    fitted,report=layout_model(model,policy)
    report_file.parent.mkdir(parents=True,exist_ok=True)
    report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if report['errors']: return 1
    if out_file:
        validate(fitted);Path(out_file).parent.mkdir(parents=True,exist_ok=True)
        Path(out_file).write_text(json.dumps(fitted,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--out',type=Path);p.add_argument('--policy',choices=['check','grow'],default='check')
    a=p.parse_args()
    try:sys.exit(run(a.model,a.report,a.out,a.policy))
    except (OSError,ValueError) as error:p.exit(1,str(error)+'\n')
