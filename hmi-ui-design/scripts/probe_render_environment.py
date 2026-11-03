"""Read-only hardware inventory; does not claim a renderer actually used GPU."""
import argparse,json,os,platform,shutil,subprocess,sys
from pathlib import Path
import hashlib,time,uuid

def probe():
    result={'schema_version':'render-environment/1.1','hostname':platform.node(),'recorded_epoch':time.time(),'platform':platform.system(),'cpu_logical_count':os.cpu_count(),'gpu_backend_verified':False,'render_backend':'not_tested','tools':{x:shutil.which(x) for x in ('node','python','blender','nvidia-smi')},'hardware':None,'inventory_error':None}
    result['tools']['python']=sys.executable
    if platform.system()=='Windows':
        script="$ErrorActionPreference='Stop'; $c=Get-CimInstance Win32_Processor; $o=Get-CimInstance Win32_OperatingSystem; $g=Get-CimInstance Win32_VideoController; @{cpu=@($c | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors); memory_total_kb=$o.TotalVisibleMemorySize; memory_free_kb=$o.FreePhysicalMemory; gpus=@($g | Select-Object Name,AdapterRAM,DriverVersion,VideoProcessor)} | ConvertTo-Json -Depth 4 -Compress"
        try:
            r=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,text=True,timeout=25,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode:raise RuntimeError(r.stderr.strip())
            result['hardware']=json.loads(r.stdout)
        except Exception as e:result['inventory_error']=str(e)
    result['selection_guidance']={'html_svg_webgl_3d':'prefer available hardware renderer; verify actual device/backend','small_png_text_files':'CPU is appropriate; avoid GPU startup/transfer overhead','concurrency':'choose after checking memory and representative workload','software_fallback':'record reason and measured backend; do not claim GPU acceleration'}
    hardware=result['hardware'] or {}
    identity={k:result[k] for k in ('hostname','platform','cpu_logical_count','tools')}
    identity['gpus']=hardware.get('gpus');identity['cpu']=hardware.get('cpu')
    result['cache_identity']=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path)
    group=ap.add_mutually_exclusive_group();group.add_argument('--reuse',action='store_true');group.add_argument('--refresh',action='store_true')
    ap.add_argument('--max-age-hours',type=float,default=6);args=ap.parse_args();r=None
    if args.max_age_hours<=0:ap.error('max-age-hours must be positive')
    if args.reuse and args.out and args.out.is_file():
        try:
            old=json.loads(args.out.read_text(encoding='utf-8'))
            if (old.get('schema_version')=='render-environment/1.1' and old.get('hostname')==platform.node()
                and 0<=time.time()-old['recorded_epoch']<=args.max_age_hours*3600
                and old['tools']['python']==sys.executable):
                r=dict(old,cache_hit=True,report_path=str(args.out))
        except (ValueError,OSError,KeyError,TypeError):pass
    if r is None:r=dict(probe(),cache_hit=False)
    if args.out:
        if not r['cache_hit']:
            destination=args.out
            if destination.exists() and (args.reuse or args.refresh):
                destination=destination.with_name(destination.stem+'-'+uuid.uuid4().hex[:10]+destination.suffix)
            r['report_path']=str(destination)
            with destination.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps(r,ensure_ascii=False,indent=2))
