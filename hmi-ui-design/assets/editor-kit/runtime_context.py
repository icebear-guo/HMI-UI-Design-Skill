"""Self-contained native clipboard session: no MCP, external donor or codec paths."""
from pathlib import Path
import hashlib,json,sys,contextvars
from model_validation import validate
from page_catalog import load_catalog,single_catalog
_context=None
_request_mode=contextvars.ContextVar("native_binding_mode",default=None)
KIT=Path(__file__).resolve().parent
RUNTIME_REVISION='v211-resolution-test5'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
class Session:
    def __init__(self,session_file):
        self.file=Path(session_file).resolve();self.root=self.file.parent
        self.config=json.loads(self.file.read_text(encoding='utf-8'))
        if self.config.get('schema')!='hmi-ui-editor-session/2.0-test':raise ValueError('Unsupported session schema')
        self.model=validate(json.loads(self.resolve(self.config['model']).read_text(encoding='utf-8')))
        self.catalog=load_catalog(self.resolve(self.config['pages'])) if self.config.get('pages') else single_catalog(self.model)
        self.model=self.catalog['pages'][0]['model'];self.port=int(self.config.get('port',18767))
        self.runtime_revision=RUNTIME_REVISION
        self.identity=hashlib.sha256(json.dumps({'file':str(self.file),'config':self.config,'catalog':self.catalog,'runtime':RUNTIME_REVISION},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
        if not 1024<=self.port<=65535:raise ValueError('Session port out of range')
        self.copy_authorized=self.config.get('copy_authorized') is True
        self._binding_mode=self.config.get('binding_mode','unbound')
        if self.binding_mode not in ('unbound','names'):raise ValueError('绑定方式支持 unbound 或 names')
        if self.config.get('native_profile'):raise ValueError('本版使用内置结构，无需工程供体配置；请重新建立会话')
        self.codec_root=KIT/'native_codec';self.native_error=None;self.window_error=None
        self.profile={'alignment_calibration':{'center_header_prefix_hex':'01000100','horizontal_center_u16':1,'vertical_center_u16':1},
            'navigation_targets':[{'name':p['name'],'id':0xffffffff} for p in self.catalog['pages']]}
        self.bank=None
        try:
            guard=json.loads((KIT/'codec-guard.json').read_text(encoding='utf-8'))
            for rel,want in guard['files'].items():
                p=self.codec_root/rel
                if not p.is_file() or sha(p)!=want:raise ValueError('内置序列化代码损坏或版本不符：'+rel)
            if sha(KIT/'native-structures.json')!=guard['structure_sha256']:raise ValueError('内置原生结构校验失败')
            self.bank=json.loads((KIT/'native-structures.json').read_text(encoding='utf-8'))
            if self.bank['schema']!='hmi-native-structures/2.1-test' or self.bank['mcgs_version']!='3.5.1.6963':raise ValueError('未支持的内置原生版本')
            sys.path.insert(0,str(self.codec_root))
        except Exception as error:self.native_error=str(error);self.window_error=str(error)
        from canvas_profile import details
        self.canvas_profiles=[details(p['model']['width'],p['model']['height']) for p in self.catalog['pages']]
        if self.native_error is None and self.copy_authorized and any(not p['copy_verified'] for p in self.canvas_profiles):
            self.native_error='分辨率尚未纳入当前原生复制范围；请保留需求并补充适配，不能自动更改画布。'
            self.window_error=self.native_error
    def resolve(self,value):
        p=Path(value);return p.resolve() if p.is_absolute() else (self.root/p).resolve()
    def prototype_bytes(self,kind,component_id=None):
        if self.native_error:raise ValueError(self.native_error)
        item=self.bank['controls'].get(kind)
        if not item:raise ValueError('尚未实现的内置原生类型：'+kind)
        raw=bytes.fromhex(item['payload_hex'])
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('内置结构字段校验失败：'+kind)
        return raw
    @property
    def binding_mode(self):return _request_mode.get() or self._binding_mode
    def request_binding(self,mode):
        mode=mode or self._binding_mode
        if mode not in ('unbound','names'):raise ValueError('绑定方式无效')
        return _request_mode.set(mode)
    def reset_request_binding(self,token):_request_mode.reset(token)
    def native_name(self,node):return node['binding']['name'] if self.binding_mode=='names' else ''
    def native_ready(self):return self.copy_authorized and self.native_error is None
    def window_ready(self):return self.native_ready() and self.window_error is None
def configure(session_file):
    global _context
    if _context is not None:raise RuntimeError('Session already configured')
    _context=Session(session_file)
    if _context.native_error is None and _context.copy_authorized:
        try:
            from native_adapter import validate_builtin_structures
            original=_context.model
            try:
                for page in _context.catalog['pages']:_context.model=page['model'];validate_builtin_structures()
            finally:_context.model=original
            from window_adapter import window_template
            window_template()
        except Exception as error:_context.native_error='原生结构预检未通过：'+str(error);_context.window_error=_context.native_error
    return _context
def context():
    if _context is None:raise RuntimeError('Use start_editor.py --session')
    return _context
