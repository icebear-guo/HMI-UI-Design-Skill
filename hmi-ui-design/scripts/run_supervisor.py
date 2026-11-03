"""Locate the sibling supervisor skill; never substitutes a local pass report."""
from pathlib import Path
import os, subprocess, sys

def main():
    here=Path(__file__).resolve()
    roots=[here.parents[2]]
    roots.extend(Path(p).expanduser() for p in os.environ.get('HMI_MCGS_SKILLS_DIR','').split(os.pathsep) if p)
    roots.extend(Path(os.environ[k]).expanduser()/'skills' for k in ('CODEX_HOME','WORKBUDDY_HOME') if os.environ.get(k))
    roots.extend([Path.home()/'.codex/skills',Path.home()/'.workbuddy/skills'])
    candidates=[root/'hmi-mcgs-supervisor/supervisor.py' for root in roots]
    target=next((p for p in candidates if p.is_file()),None)
    if target is None:
        print('总控器skill未安装：将hmi-mcgs-supervisor安装到当前skills目录，或用HMI_MCGS_SKILLS_DIR指定技能父目录。不能把未执行写成通过。')
        return 1
    return subprocess.call([sys.executable,'-B',str(target),*sys.argv[1:]])

if __name__=='__main__':sys.exit(main())
