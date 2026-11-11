"""Loopback-only, fixed-model UI preview and Windows custom clipboard bridge."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import json,base64,secrets,hashlib,datetime,sys,webbrowser,io,socket,threading
from runtime_context import context
CTX=context()
from clipboard_win import Sequence,publish
from model_editor import apply_edits,choose_components
from window_adapter import compile_windows
from asset_store import store as store_assets

KIT=Path(__file__).resolve().parent
ROOT=CTX.root
MODEL=CTX.model
CATALOG=CTX.catalog
TOKEN=secrets.token_urlsafe(32)
PORT=CTX.port
ORIGIN=f'http://127.0.0.1:{PORT}'
CLIPBOARD_LOCK=threading.Lock()
class LocalServer(ThreadingHTTPServer):
    allow_reuse_address=False
    daemon_threads=True
    def server_bind(self):
        # Windows SO_REUSEADDR permits multiple listeners on one address.
        # Reserve this helper's port exclusively so another launch cannot
        # intercept requests from an already open page.
        self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()
    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(20)
        return connection,address
class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def send(self,status,data,kind='application/json; charset=utf-8',script_hash=None):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        scripts="'self'"+(" 'sha256-"+script_hash+"'" if script_hash else '')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src "+scripts+"; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(data)
    def valid_host(self):return self.headers.get('Host')==f'127.0.0.1:{PORT}'
    def do_GET(self):
        if not self.valid_host():return self.send(403,{'error':'Host refused'})
        files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/editor.js':('editor.js','text/javascript; charset=utf-8'),'/windows.js':('windows.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if self.path in files:
            file,kind=files[self.path];return self.send(200,(KIT/file).read_bytes(),kind)
        if self.path in ('/templates/','/templates/index.html','/templates/blue.html','/templates/graphite.html','/templates/sand.html') and CTX.config.get('template_previews'):
            folder=CTX.resolve(CTX.config['template_previews']);name=self.path.rsplit('/',1)[1] or 'index.html'
            body=(folder/name).read_text(encoding='utf-8');script=body.partition('<script>')[2].rpartition('</script>')[0]
            script_hash=base64.b64encode(hashlib.sha256(script.encode('utf-8')).digest()).decode('ascii') if script else None
            return self.send(200,body.encode('utf-8'),'text/html; charset=utf-8',script_hash)
        if self.path in ('/extra_controls.js','/asset_cache.js','/preview_runtime.js'):return self.send(200,(KIT/self.path[1:]).read_bytes(),'text/javascript; charset=utf-8')
        if self.path=='/api/config':return self.send(200,{'model':MODEL,'pageId':CATALOG['pages'][0]['id'],'catalog':CATALOG,'binding_mode':CTX.binding_mode,'initial_window_selection':CTX.config.get('initial_window_selection'),'templates_ready':bool(CTX.config.get('template_previews')),'navigation_targets':(CTX.profile or {}).get('navigation_targets',[]),'native_ready':CTX.native_ready(),'native_status':CTX.native_error or ('原生复制已就绪' if CTX.copy_authorized else '当前会话未启用复制'),'window_ready':CTX.window_ready(),'window_status':CTX.window_error or ('窗口复制已就绪' if CTX.copy_authorized else '当前会话未启用复制'),'token':TOKEN,'sequence':Sequence()})
        if self.path=='/favicon.ico':return self.send(204,b'','image/x-icon')
        if self.path=='/api/identity':return self.send(200,{'schema':'hmi-editor-identity/1.0','identity':CTX.identity,'runtime_revision':CTX.runtime_revision,'catalog_revision':CATALOG['revision']})
        if self.path=='/api/status':return self.send(200,{'revision':MODEL['revision'],'catalog_revision':CATALOG['revision'],'sequence':Sequence()})
        return self.send(404,{'error':'Not found'})
    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin')!=ORIGIN or self.headers.get('X-Local-Token')!=TOKEN:
            return self.send(403,{'error':'Local request refused'})
        if self.path not in ('/api/copy','/api/check','/api/model','/api/windows/check','/api/windows/copy'):return self.send(404,{'error':'Not found'})
        binding_token=None
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<16*1024*1024:raise ValueError('Request size out of bounds')
            request=json.loads(self.rfile.read(length))
            binding_token=CTX.request_binding(request.get('binding_mode'))
            if self.path.startswith('/api/windows/'):
                if CTX.native_error:raise ValueError(CTX.native_error)
                if CTX.window_error:raise ValueError(CTX.window_error)
                if self.path.endswith('/copy') and not CTX.copy_authorized:raise ValueError('当前会话未启用原生复制。')
                data,report,exports=compile_windows(CATALOG,request)
                if self.path=='/api/windows/check':return self.send(200,{'ok':True,'check_only':True,'report':report})
                with CLIPBOARD_LOCK:receipt=publish(data,request['sequence'],'MCGS_WND_USER_PRO1')
                batch=ROOT/'copies'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');batch.mkdir(parents=True)
                (batch/'mcgs_windows.bin').write_bytes(data)
                models=[]
                for item in exports:
                    folder=batch/item['id'];folder.mkdir();(folder/'assets').mkdir()
                    item['asset_cache']=store_assets(ROOT,folder/'assets',item.pop('assets'))
                    (folder/'model.json').write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding='utf-8');models.append(item)
                (batch/'windows.json').write_text(json.dumps(models,ensure_ascii=False,indent=2),encoding='utf-8')
                result={'ok':True,'receipt':receipt,'report':report,'batch':str(batch)}
                (batch/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                return self.send(200,result)
            baseline=next((p['model'] for p in CATALOG['pages'] if p['id']==request.get('page_id',CATALOG['pages'][0]['id'])),None) if isinstance(request,dict) else None
            if baseline is None or set(request)-{'revision','assets','sequence','patches','selection','page_id','binding_mode'} or request.get('revision')!=baseline['revision']:raise ValueError('页面版本已更新，请刷新后重试。')
            edited_model=apply_edits(baseline,request.get('patches',[]))
            if self.path=='/api/model':return self.send(200,{'ok':True,'model':edited_model})
            if CTX.native_error:raise ValueError(CTX.native_error)
            if self.path=='/api/copy' and not CTX.copy_authorized:raise ValueError('当前会话未启用原生复制。')
            from native_adapter import compile_model
            export_model=choose_components(edited_model,request.get('selection'))
            assets={key:base64.b64decode(value,validate=True) for key,value in request['assets'].items()}
            data,report=compile_model(export_model,assets)
            report['editor']=edited_model['editor'];report['export_selection']=request.get('selection')
            if self.path=='/api/check':return self.send(200,{'ok':True,'check_only':True,'report':report})
            with CLIPBOARD_LOCK:
                receipt=publish(data,request['sequence'])
            stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            batch=ROOT/'copies'/stamp;batch.mkdir(parents=True)
            (batch/'mcgs_ui.bin').write_bytes(data)
            (batch/'model.json').write_text(json.dumps(edited_model,ensure_ascii=False,indent=2),encoding='utf-8')
            (batch/'export-model.json').write_text(json.dumps(export_model,ensure_ascii=False,indent=2),encoding='utf-8')
            (batch/'patches.json').write_text(json.dumps(request.get('patches',[]),ensure_ascii=False,indent=2),encoding='utf-8')
            (batch/'assets').mkdir()
            report['asset_cache']=store_assets(ROOT,batch/'assets',assets)
            result={'ok':True,'receipt':receipt,'report':report,'batch':str(batch)}
            (batch/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return self.send(200,result)
        except Exception as exc:
            return self.send(400,{'error':str(exc)})
        finally:
            if binding_token is not None:CTX.reset_request_binding(binding_token)

if __name__=='__main__':
    try:server=LocalServer(('127.0.0.1',PORT),Handler)
    except OSError:
        raise SystemExit('Port busy. Choose a distinct session port; no unrelated page was opened.')
    print(ORIGIN,flush=True)
    if '--no-open' not in sys.argv:webbrowser.open(ORIGIN)
    server.serve_forever()
