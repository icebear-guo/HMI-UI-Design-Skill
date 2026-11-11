"""Publish only MCGS's named business format; verify all requested bytes."""
import ctypes as C
from ctypes import wintypes as W
import hashlib,time

u=C.WinDLL('user32',use_last_error=True);k=C.WinDLL('kernel32',use_last_error=True)
def bind(lib,name,restype,*args):
    f=getattr(lib,name);f.restype=restype;f.argtypes=args;return f
Open=bind(u,'OpenClipboard',W.BOOL,W.HWND)
Close=bind(u,'CloseClipboard',W.BOOL)
Empty=bind(u,'EmptyClipboard',W.BOOL)
Register=bind(u,'RegisterClipboardFormatW',W.UINT,W.LPCWSTR)
Set=bind(u,'SetClipboardData',W.HANDLE,W.UINT,W.HANDLE)
Get=bind(u,'GetClipboardData',W.HANDLE,W.UINT)
Sequence=bind(u,'GetClipboardSequenceNumber',W.DWORD)
Create=bind(u,'CreateWindowExW',W.HWND,W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p)
Destroy=bind(u,'DestroyWindow',W.BOOL,W.HWND)
Alloc=bind(k,'GlobalAlloc',W.HGLOBAL,W.UINT,C.c_size_t)
Free=bind(k,'GlobalFree',W.HGLOBAL,W.HGLOBAL)
Lock=bind(k,'GlobalLock',C.c_void_p,W.HGLOBAL)
Unlock=bind(k,'GlobalUnlock',W.BOOL,W.HGLOBAL)
Size=bind(k,'GlobalSize',C.c_size_t,W.HGLOBAL)
def required(v):
    if not v:raise C.WinError(C.get_last_error())
    return v
def publish(data,expected_sequence,format_name='MCGS_DRAW_OBJ_PRO1'):
    if format_name not in ('MCGS_DRAW_OBJ_PRO1','MCGS_WND_USER_PRO1'):raise ValueError('Unsupported clipboard format')
    if not 0<len(data)<=16*1024*1024:raise ValueError('Invalid clipboard size')
    window=required(Create(0,'STATIC','Local Mcgs UI copy',0,0,0,0,0,W.HWND(-3),None,None,None))
    memory=None;opened=False;transferred=False
    try:
        fmt=required(Register(format_name))
        memory=required(Alloc(0x42,len(data)));pointer=required(Lock(memory))
        try:C.memmove(pointer,data,len(data))
        finally:Unlock(memory)
        for _ in range(10):
            if Open(window):opened=True;break
            time.sleep(.05)
        if not opened:raise RuntimeError('剪贴板正被其他程序占用，请重试。')
        if Sequence()!=expected_sequence:raise RuntimeError('生成期间剪贴板已改变，请再点击复制。')
        required(Empty());required(Set(fmt,memory));transferred=True
        handle=required(Get(fmt));size=Size(handle)
        assert len(data)<=size<=16*1024*1024
        pointer=required(Lock(handle))
        try:readback=C.string_at(pointer,size)
        finally:Unlock(handle)
        assert readback[:len(data)]==data and not any(readback[len(data):]),'Clipboard readback mismatch'
        return {'format':format_name,'bytes':len(data),'allocated_bytes':size,'sha256':hashlib.sha256(data).hexdigest(),'exact_readback':True,'sequence_after':Sequence()}
    finally:
        if opened:Close()
        if memory and not transferred:Free(memory)
        Destroy(window)
