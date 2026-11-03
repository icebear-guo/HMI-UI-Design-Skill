"""Flag destructive reset patterns in generated builders before execution.

Best-effort static prevention, not a security sandbox or replacement for host
approval. It never executes the inspected project scripts.
"""
import argparse
import ast
import json
from pathlib import Path
import re

SHELL_DELETE = re.compile(r'(?im)(?:^|[\s;&|])(?:Remove-Item\b|rmdir\b|rd\s+/|del\b|rm\s|unlink\s)')
JS_DELETE = re.compile(r'\b(?:rm|rmSync|rmdir|rmdirSync|unlink|unlinkSync)\s*\(')


def inspect(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    findings = []
    if path.suffix.lower() == '.py':
        tree = ast.parse(text, filename=str(path))
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names: aliases[item.asname or item.name] = item.name
            if isinstance(node, ast.ImportFrom):
                for item in node.names: aliases[item.asname or item.name] = (node.module or '') + '.' + item.name
        def qualified(node):
            if isinstance(node, ast.Name):return aliases.get(node.id,node.id)
            if isinstance(node, ast.Attribute):return qualified(node.value)+'.'+node.attr
            return ''
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):continue
            name=qualified(node.func)
            destructive = name.endswith(('.rmtree','.unlink','.rmdir','.removedirs')) or name in ('os.remove','os.unlink')
            if name in ('os.system','subprocess.run','subprocess.call','subprocess.Popen','subprocess.check_call','subprocess.check_output') and node.args:
                strings=[n.value for n in ast.walk(node.args[0]) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
                destructive = destructive or bool(SHELL_DELETE.search(' '.join(strings)))
            if destructive:
                findings.append({'file':str(path),'line':node.lineno,'code':'DESTRUCTIVE_GENERATION_RESET',
                    'operation':name,'action':'Keep prior output; allocate a fresh generation directory. Explicit cleanup is a separate user-authorized task.'})
    elif path.suffix.lower() in ('.ps1','.sh','.cmd','.bat'):
        for index,line in enumerate(text.splitlines(),1):
            if SHELL_DELETE.search(line):findings.append({'file':str(path),'line':index,'code':'DESTRUCTIVE_GENERATION_RESET','operation':'shell deletion'})
    elif path.suffix.lower() in ('.js','.mjs','.cjs'):
        for index,line in enumerate(text.splitlines(),1):
            if JS_DELETE.search(line):findings.append({'file':str(path),'line':index,'code':'DESTRUCTIVE_GENERATION_RESET','operation':'possible JavaScript filesystem deletion'})
    else:raise ValueError('Inspect generated Python, JavaScript or shell scripts, not whole dependency directories')
    return findings


def check(paths):
    findings=[f for p in paths for f in inspect(p)]
    return {'schema_version':'hmi-generation-policy/1.0','status':'fail' if findings else 'pass',
            'files_checked':len(paths),'findings':findings,'scope':'static known deletion patterns only; indirect/dynamic code and host approval remain separate'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts',nargs='+',type=Path)
    args=parser.parse_args()
    result=check(args.scripts)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['status']=='pass' else 2)
