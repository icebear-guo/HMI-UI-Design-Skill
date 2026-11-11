"""Start a session, or reopen only a service with the exact same identity."""
from pathlib import Path
import argparse, http.client, json, runpy, socket, sys, webbrowser

def existing_service(port, expected):
    # Some Windows hosts time out instead of refusing a connect to an unused
    # loopback port. Test availability locally; the server still reserves it
    # exclusively when it starts, so a race cannot attach to another service.
    probe=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        try:probe.bind(('127.0.0.1',port))
        except OSError:pass
        else:return False
    finally:probe.close()
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
    try:
        try:connection.connect()
        except ConnectionRefusedError:return False
        connection.request('GET','/api/identity',headers={'Host':f'127.0.0.1:{port}'})
        response=connection.getresponse();identity=json.loads(response.read(65536))
        if response.status!=200 or identity.get('schema')!='hmi-editor-identity/1.0' or identity.get('identity')!=expected:
            raise ValueError('Port belongs to a different or older session; choose a new session port. No page was opened.')
        return True
    except (OSError,ValueError,http.client.HTTPException) as error:
        raise ValueError('Existing service could not be matched: '+str(error)) from error
    finally:connection.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,required=True);p.add_argument('--no-open',action='store_true');a=p.parse_args()
    kit=Path(__file__).resolve().parent.parent/'assets/editor-kit';sys.path.insert(0,str(kit))
    from runtime_context import configure
    try:
        context=configure(a.session)
        if existing_service(context.port,context.identity):
            url=f'http://127.0.0.1:{context.port}';print('Matched existing session: '+url,flush=True)
            if not a.no_open:webbrowser.open(url)
        else:
            sys.argv=[str(kit/'server.py')]+(['--no-open'] if a.no_open else [])
            runpy.run_path(str(kit/'server.py'),run_name='__main__')
    except (ValueError,OSError) as error:p.exit(1,str(error)+'\n')
