"""Experimental three-class clipboard factory; no MCP writes."""
from pathlib import Path
import sys,struct,copy,hashlib,io,json
from PIL import Image

from runtime_context import context
CTX=context()
ROOT=CTX.root
sys.path.insert(0,str(CTX.codec_root))
import native_support
from mcs_window_archive import ControlRecord,write_count,Reader
from mcs_button_control import ButtonArchive,_picture
from mcs_input_text import LabelRecord
from 原生界面样式 import CommonEnvelope,set_font,fonts
from native_ui_style import style_button,colorref
from native_picture_control import validate_static_donor

KINDS={'button':0x5027,'picture':0x5009,'label':0x5008}
CLASSES={'button':b'CDrawButton','picture':b'CDrawBitmap','label':b'CDrawLabel'}
def record(kind,payload):return ControlRecord(KINDS[kind],payload,write_count(len(payload)),0)
def prototype(kind,component_id=None):return record(kind,CTX.prototype_bytes(kind,component_id))
def embedded(png,w,h):
    if len(png)>4*1024*1024:raise ValueError('Asset too large')
    with Image.open(io.BytesIO(png)) as im:
        assert im.format=='PNG' and im.size==(w,h),'PNG size/type mismatch'
        im.verify()
    out=struct.pack('<4I',2,w,h,len(png))+png
    r=Reader(out);assert _picture(r)==out and r.pos==len(out)
    return out

def compile_model(model,assets):
    from canvas_profile import dimensions
    canvas_width,canvas_height=dimensions(model.get('width',CTX.model['width']),model.get('height',CTX.model['height']))
    expected={n['id']+':'+state for n in model['components'] for state in (['s0','s1'] if n['kind']=='button' else ['s0'] if n['kind']=='picture' else [])}
    if set(assets)!=expected:raise ValueError('Asset inventory mismatch')
    items=[]
    for n in model['components']:
        kind=n['kind'];l,t,r,b=n['rect'];w,h=r-l,b-t
        assert 0<=l<r<=canvas_width and 0<=t<b<=canvas_height
        name=n['id'];assert len(name)<=32
        if kind=='picture':
            a=CommonEnvelope.parse(prototype(kind,name));validate_static_donor(type('D',(),{'common':a})())
            assert not a.animations
            old=Reader(a.content);_picture(old);assert old.pos==len(a.content)
            a.name.value=name;a.set_rect(n['rect']);a.content=embedded(assets[name+':s0'],w,h)
            rec=a.to_record();check=CommonEnvelope.parse(rec)
            assert check.to_record().payload==rec.payload and check.content==a.content
        elif kind=='label':
            a=LabelRecord.parse(prototype(kind,name));a.common.name=name;a.common.set_rect(n['rect']);a.caption=n['text'];a.unit=''
            a.colour=a.appearance_prefix[0]=colorref(n['font']['color'])
            a.style=a.appearance_prefix[1]=1 # measured center enum
            a.font=set_font(a.font,height=n['font']['size_px'],family=n['font']['family'],weight=n['font']['weight'])
            assert a.appearance_suffix[3]==0 and a.background_picture==b''
            rec=record(kind,a.to_bytes());env=CommonEnvelope.parse(rec);prefix=bytearray(env.prefix)
            struct.pack_into('<H',prefix,env.pen_offset,0);struct.pack_into('<H',prefix,env.brush_offset,0)
            env.prefix=bytes(prefix);rec=env.to_record();check=LabelRecord.parse(rec)
            assert check.to_bytes()==rec.payload and check.caption==n['text']
            assert all(f['height_raw']==-n['font']['size_px'] for f in fonts(check.font))
        elif kind=='button':
            a=ButtonArchive.parse(prototype(kind,name));a.name.value=name;a.rect=tuple(n['rect']);p=a.metadata.properties
            p.clear_actions();a.action_texts.clear_values();a.action_ids.clear_values(0xffffffff);a.action_modes.clear_values(0)
            a.action_words[:]=[0,0];a.enabled_expression.value='';a.enable_compiled.value=b'';a.enabled_invert=0
            a.release_script.value='';a.release_compiled.value=b''
            p.picture=embedded(assets[name+':s0'],w,h);p.words[16]=1;p.words[17]=0
            a.picture=embedded(assets[name+':s1'],w,h)
            style={'caption':n['text'],'font':{k:n['font'][k] for k in ('family','size_px','weight')},'color':n['font']['color'],'horizontal':'center','vertical':'center'}
            rec=style_button(a.to_record(),{'s0':style,'s1':style});check=ButtonArchive.parse(rec)
            assert check.to_bytes()==rec.payload and not check.release_script.value and not check.metadata.properties.press_script.value
        else:raise ValueError('Unsupported kind')
        env=CommonEnvelope.parse(rec)
        assert env.name.value==name and list(env.rect)==n['rect'] and not env.animations
        items.append((kind,rec.payload))
    # MFC CArchive map: a new class and every serialized object consume slots.
    # This restricted branch has no nested class objects (only raw PNG/fonts).
    out=write_count(len(items));classes={};next_index=1;spans=[]
    for kind,payload in items:
        head=len(out)
        if kind not in classes:
            classes[kind]=next_index;next_index+=1;c=CLASSES[kind]
            out+=struct.pack('<HHH',0xffff,0,len(c))+c
        else:out+=struct.pack('<H',0x8000|classes[kind])
        start=len(out);out+=payload;next_index+=1
        spans.append({'kind':kind,'header_start':head,'body_start':start,'body_end':len(out),'sha256':hashlib.sha256(payload).hexdigest()})
    # Decode every class header independently and compare all exact body extents.
    reader=Reader(out);assert reader.count()==len(items);map_classes={};slot=1
    for (kind,payload),span in zip(items,spans):
        tag=reader.u16()
        if tag==0xffff:
            assert reader.u16()==0;c=reader.take(reader.u16());map_classes[slot]=c;slot+=1
        else:c=map_classes[tag&0x7fff]
        assert c==CLASSES[kind] and reader.pos==span['body_start']
        assert reader.take(len(payload))==payload;slot+=1
    assert reader.pos==len(out)
    return out,{'status':'memory_roundtrip_pass','count':len(items),'class_map':classes,'bytes':len(out),'sha256':hashlib.sha256(out).hexdigest(),'spans':spans,'native_paste':'not_checked','native_reopen':'not_checked','native_runtime':'not_checked'}
