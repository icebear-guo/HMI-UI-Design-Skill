from check_standalone_generation import run
from pathlib import Path
import argparse,json
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=run(a.out);print(json.dumps({'all_pass':r['all_pass'],'checks':len(r['checks'])},ensure_ascii=False))
