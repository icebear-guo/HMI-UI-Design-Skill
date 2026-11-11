"""Bundle a project-local editor runtime and relative, ASCII Windows launchers."""
from pathlib import Path
import argparse, json, shutil, sys
SKILL=Path(__file__).resolve().parent.parent

POWERSHELL=r'''param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$log = Join-Path $root 'launcher.log'
$starter = Join-Path $root 'runtime/scripts/start_editor.py'
$session = Join-Path $root 'session/session.json'
function Probe($exe, $prefix) {
    try {
        & $exe @prefix -c "import sys; import PIL; sys.exit(0 if sys.version_info >= (3,12) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}
try {
    $chosen = $null
    $prefix = @()
    $candidates = @(
        (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Python/Python313/python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Python/Python312/python.exe')
    )
    $buddy = Join-Path $env:USERPROFILE '.workbuddy/binaries/python/versions'
    if (Test-Path -LiteralPath $buddy) {
        $candidates += @(Get-ChildItem -LiteralPath $buddy -Directory | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' })
    }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -and (Probe $candidate @())) { $chosen = $candidate; break }
    }
    if (-not $chosen) {
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($py -and (Probe $py.Source @('-3'))) { $chosen = $py.Source; $prefix = @('-3') }
    }
    if (-not $chosen) {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($python -and (Probe $python.Source @())) { $chosen = $python.Source }
    }
    if (-not $chosen) { throw 'Python 3.12+ with Pillow is required. A Store alias is not a Python interpreter.' }
    $argv = @('-X', 'utf8', $starter, '--session', $session)
    if ($NoOpen) { $argv += '--no-open' }
    & $chosen @prefix @argv 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "Editor exited with code $LASTEXITCODE. See launcher.log." }
} catch {
    $_.Exception.Message | Add-Content -LiteralPath $log -Encoding UTF8
    Write-Host $_.Exception.Message
    exit 1
}
'''
CMD='''@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-editor.ps1"
if errorlevel 1 (
  echo See launcher.log for details.
  pause
)
endlocal
'''

def add_runtime(out, session_relative='session/session.json'):
    out=Path(out).resolve();session=(out/session_relative).resolve()
    if out.is_relative_to(SKILL.resolve()):raise ValueError('Create runtime bundles outside the skill directory')
    if not session.is_relative_to(out) or session_relative!='session/session.json' or not session.is_file():
        raise ValueError('Portable runtime expects a project-local session/session.json')
    runtime=out/'runtime'
    if runtime.exists() or (out/'open-editor.cmd').exists() or (out/'open-editor.ps1').exists():
        raise ValueError('Portable runtime/launchers already exist; use a new batch')
    (runtime/'scripts').mkdir(parents=True)
    shutil.copy2(SKILL/'scripts/start_editor.py',runtime/'scripts/start_editor.py')
    shutil.copytree(SKILL/'assets/editor-kit',runtime/'assets/editor-kit',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (out/'open-editor.ps1').write_text(POWERSHELL,encoding='ascii')
    (out/'open-editor.cmd').write_text(CMD,encoding='ascii')

def bundle(session_file,out):
    from prepare_editor_session import prepare
    sys.path.insert(0,str(SKILL/'assets/editor-kit'))
    from runtime_context import Session
    context=Session(session_file);out=Path(out)
    if out.exists():raise ValueError('Use a new portable directory')
    out.mkdir(parents=True)
    catalog={'schema':'hmi-ui-editor-pages/2.0-test','revision':context.catalog['revision'],'pages':context.catalog['pages']}
    (out/'pages.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    prepare(None,out/'session',context.port,context.copy_authorized,out/'pages.json',binding_mode=context.binding_mode)
    add_runtime(out)
    return out/'open-editor.cmd'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:print(bundle(a.session,a.out))
    except (ValueError,OSError,KeyError,TypeError) as error:p.exit(1,str(error)+'\n')
