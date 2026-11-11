"""Explicit numeric, input, bit-switch and lamp factories for this fixture."""
from pathlib import Path
import sys,struct,hashlib,copy,importlib.util,json,collections
from runtime_context import context
CTX=context()
ROOT=CTX.root
spec=importlib.util.spec_from_file_location('validated_static_adapter',Path(__file__).parent/'static_adapter.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
from mcs_window_archive import ControlRecord,write_count,Reader,write_cstring
from mcs_button_control import CString,_picture
from mcs_input_text import InputRecord,LabelRecord,InputMetadata,unit_slot
from 原生界面样式 import CommonEnvelope,MultiState,MultiButtonTail,GenericMetadata,set_font,fonts
from native_numeric import output as numeric_output,input as numeric_input
from native_capabilities import profile
from native_ui_style import colorref
import extended_native as extra

KINDS={'picture':0x5009,'label':0x5008,'button':0x5027,'numeric_input':0x5025,'numeric_output':0x5008,'bit_switch':0x5028,'lamp':0x502a}
CLASSES={'picture':'CDrawBitmap','label':'CDrawLabel','button':'CDrawButton','numeric_input':'CDrawEdit','numeric_output':'CDrawLabel','bit_switch':'CDrawMulBtn','lamp':'CDrawMulDis'}
KINDS.update(extra.TYPES);CLASSES.update(extra.CLASSES)
def rec(kind,payload):return ControlRecord(KINDS[kind],payload,write_count(len(payload)),0)
def prototype(kind,component_id=None):
    return rec(kind,CTX.prototype_bytes(kind,component_id))

def validate_multistate_binding(n,a):
    if n['kind']=='bit_switch':
        t=MultiButtonTail.parse(a.tail)
        if t.input_expression.value or t.output_expression.value or t.input_words[0]!=0xffffffff or t.output_words[0]!=0xffffffff:raise ValueError('内置位结构必须无旧工程绑定')
    else:
        r=Reader(a.tail)
        if r.u32()!=1 or r.cstring()[0]:raise ValueError('内置指示灯结构必须未绑定')

def validate_builtin_structures():
    for n in CTX.model['components']:
        r=prototype(n['kind'],n['id']);env=CommonEnvelope.parse(r)
        if n['kind'] in ('bit_switch','lamp'):
            a=MultiState.parse(r)
            # Native samples retain ten opaque metadata bytes after the
            # zero-event count. Their values are not required to be zero.
            if env.animations or len(env.metadata.value)!=12 or GenericMetadata.parse(env.metadata.value).events:raise ValueError(n['id']+'：未支持的多态动画/事件分支。')
            if a.levels!=[0,1] or any(len(g)!=1 for g in a.images):raise ValueError(n['id']+'：内置双态结构不完整。')
            validate_multistate_binding(n,a)
        elif n['kind']=='numeric_input':
            a=InputRecord.parse(r);a.disable_images()
        elif n['kind']=='numeric_output':
            if len(env.animations)!=1 or env.animations[0]['class_name']!='CAniOutput' or env.metadata.value!=bytes(12):raise ValueError(n['id']+'：未支持的数值输出分支。')
            LabelRecord.parse(env.project_without_animations())
        elif n['kind']=='label':
            if env.animations or env.metadata.value!=bytes(12):raise ValueError(n['id']+'：内置文字结构含未知动画/事件。')
            LabelRecord.parse(r)
        elif n['kind']=='picture':
            base.validate_static_donor(type('D',(),{'common':env})())
        elif n['kind'] in extra.EXTRA:extra.validate_prototype(n,r)
        else:raise ValueError('未支持的原生工厂：'+n['kind'])
def geometry(c,rect):
    l,t,r,b=rect;local=[0,0,r-l,b-t];header=bytearray(c.header)
    struct.pack_into('<4i',header,8,*local);struct.pack_into('<4i',header,24,*rect)
    struct.pack_into('<4d',header,40,*map(float,local));c.header=bytes(header)

def input_image_slot(body):
    """The same proven appearance layout used by InputRecord.disable_images."""
    reader=Reader(body);reader.take(20);reader.cstring();reader.u32()
    flag=reader.pos;enabled=reader.u32();reader.take(12);reader.cstring();reader.u32()
    begin=reader.pos
    assert enabled in (0,1)
    picture=_picture(reader) if enabled else b''
    return flag,begin,reader.pos,enabled,picture

def input_image_mirrors(record):
    a=InputRecord.parse(record);metadata=InputMetadata.parse(a.common.metadata,a.appearance)
    return [input_image_slot(body) for body in (metadata.properties.value,a.appearance)]

def attach_input_image(record,png,width,height):
    """Enable and insert one image in both native input appearance mirrors."""
    a=InputRecord.parse(record);metadata=InputMetadata.parse(a.common.metadata,a.appearance)
    picture=base.embedded(png,width,height)
    def attached(body):
        flag,begin,end,enabled,old=input_image_slot(body)
        assert enabled==0 and not old
        out=bytearray(body[:begin]+picture+body[end:]);struct.pack_into('<I',out,flag,1)
        return bytes(out)
    metadata.properties.value=attached(metadata.properties.value)
    a.appearance=attached(a.appearance);metadata.normalize_counts();a.common.metadata=metadata.to_bytes()
    result=rec('numeric_input',a.to_bytes());checked=InputRecord.parse(result)
    mirrors=input_image_mirrors(result)
    assert all(slot[3]==1 and slot[4]==picture for slot in mirrors)
    # Removing just the requested image restores all other native properties.
    checked.disable_images();assert checked.to_bytes()==record.payload
    return result

def attach_output_image(record,png,width,height):
    env=CommonEnvelope.parse(record);label=LabelRecord.parse(env.project_without_animations())
    assert label.appearance_suffix[3]==0 and not label.background_picture
    picture=base.embedded(png,width,height)
    label.appearance_suffix[3]=1;label.background_picture=picture
    projected=rec('numeric_output',label.to_bytes());result=env.restore_projected(projected)
    checked=LabelRecord.parse(CommonEnvelope.parse(result).project_without_animations())
    assert checked.appearance_suffix[3]==1 and checked.background_picture==picture
    checked.appearance_suffix[3]=0;checked.background_picture=b''
    reverted=env.restore_projected(rec('numeric_output',checked.to_bytes()))
    assert reverted.payload==record.payload
    return result

def center_text_child(child):
    calibration=CTX.profile['alignment_calibration']
    assert calibration['center_header_prefix_hex']=='01000100'
    header=bytearray(child.header)
    struct.pack_into('<HH',header,0,calibration['horizontal_center_u16'],calibration['vertical_center_u16'])
    child.header=bytes(header)

def make_numeric(n,assets):
    p=profile();name=CTX.native_name(n)
    plan={'object_name':n['id'],'bounds':n['rect'],'numeric_layout':p['numeric_core_layout'],'appearance':p['numeric_core_appearance'],'font':n['font'],
      'binding':{'name':name or '0','decimal_places':n['digits'],'unit':'','unit_owner':'external','min':n.get('min',0),'max':n.get('max',100)}}
    if n['kind']=='numeric_output':result=numeric_output(prototype('numeric_output',n['id']),plan)
    else:
        plan['binding']['name']=name
        result=numeric_input(prototype('numeric_input',n['id']),plan,{'name':name,'kind':2,'id':0xffffffff})
    if n.get('background'):
        w=n['rect'][2]-n['rect'][0];h=n['rect'][3]-n['rect'][1]
        result=(attach_input_image if n['kind']=='numeric_input' else attach_output_image)(result,assets[n['id']+':s0'],w,h)
    return result

def make_multistate(n,assets):
    a=MultiState.parse(prototype(n['kind'],n['id']));validate_multistate_binding(n,a);a.common.name.value=n['id'];a.common.set_rect(n['rect'])
    assert a.levels==[0,1] and not a.common.animations
    w=n['rect'][2]-n['rect'][0];h=n['rect'][3]-n['rect'][1]
    for si,state in enumerate(('s0','s1')):
        assert len(a.images[si])==1
        c=a.images[si][0];geometry(c,n['rect']);c.picture=base.embedded(assets[n['id']+':'+state],w,h)
        if n['kind']=='bit_switch':
            assert len(a.texts[si])==1;c=a.texts[si][0];geometry(c,n['rect'])
            c.caption.value=n['captions'][state];c.font=set_font(c.font,height=n['font']['size_px'],family=n['font']['family'],weight=n['font']['weight'])
            c.set_text_color(colorref(n['state_colors'][state]))
            center_text_child(c)
        else:assert not a.texts[si]
    # Input/output IDs remain unresolved; source-project identities are never copied.
    if n['kind']=='bit_switch':
        t=MultiButtonTail.parse(a.tail);t.input_expression.value=t.output_expression.value=CTX.native_name(n)
        t.input_words=t.output_words=[0xffffffff,0,1,0];a.tail=t.to_bytes()
    else:
        q=Reader(a.tail);q.u32();q.cstring();a.tail=struct.pack('<I',1)+write_cstring(CTX.native_name(n))+a.tail[q.pos:]
    if n['kind']=='bit_switch' and n.get('action','preserve')!='preserve':
        tail=MultiButtonTail.parse(a.tail);rest=bytearray(tail.rest);struct.pack_into('<I',rest,8,3 if n['action']=='momentary' else 2);tail.rest=bytes(rest);a.tail=tail.to_bytes()
    result=a.to_record();checked=MultiState.parse(result)
    assert checked.to_record().payload==result.payload
    return result

def describe(n,record):
    if n['kind'] in extra.EXTRA:return extra.describe(n,record)
    env=CommonEnvelope.parse(record);assert env.name.value==n['id'] and list(env.rect)==n['rect']
    info={'id':n['id'],'kind':n['kind'],'native_type':hex(record.type_id),'rect':list(env.rect),'animations':env.animations}
    if n['kind']=='numeric_output':
        assert len(env.animations)==1
        a=env.animations[0];assert a['class_name']=='CAniOutput' and a['expression']==(CTX.native_name(n) or '0') and a['fields'][:2]==[1,n['digits']]
        label=LabelRecord.parse(env.project_without_animations());assert bool(label.appearance_suffix[3])==bool(n.get('background'))
        info.update(binding=CTX.native_name(n),digits=a['fields'][1],fonts=fonts(label.font),native_image_enabled=bool(label.appearance_suffix[3]),image_owner=n['id'] if n.get('background') else None)
    elif n['kind']=='numeric_input':
        a=InputRecord.parse(record)
        meta=InputMetadata.parse(a.common.metadata,a.appearance)
        decimal_fields=[struct.unpack_from('<i',body,unit_slot(body,20)[1]+12)[0] for body in (meta.properties.value,a.appearance)]
        assert decimal_fields==[n['digits'],n['digits']], '固定小数位两个原生字段必须与网页一致'
        assert a.variable==CTX.native_name(n) and a.variable_id==0xffffffff and a.variable_type==2
        assert a.min_raw==struct.pack('<f',n['min']) and a.max_raw==struct.pack('<f',n['max'])
        mirrors=input_image_mirrors(record)
        if n.get('background'):
            assert mirrors[0][3:]==mirrors[1][3:] and mirrors[0][3]==1
            mode,width,height,length=struct.unpack_from('<4I',mirrors[0][4])
            assert mode==2 and (width,height)==(n['rect'][2]-n['rect'][0],n['rect'][3]-n['rect'][1])
        info.update(binding=a.variable,variable_id=a.variable_id,min=n['min'],max=n['max'],digits=decimal_fields[0],native_decimal_mirrors=decimal_fields,fonts=fonts(a.font),native_image_mirrors=[bool(slot[3]) for slot in mirrors],image_owner=n['id'] if n.get('background') else None)
    elif n['kind'] in ('bit_switch','lamp'):
        assert not env.animations
        a=MultiState.parse(record);children=0
        for groups in (a.images,a.texts):
            for group in groups:
                for c in group:
                    assert list(c.parent_rect)==n['rect']
                    assert c.rect==(0,0,n['rect'][2]-n['rect'][0],n['rect'][3]-n['rect'][1])
                    assert c.double_rect==tuple(map(float,c.rect));children+=1
        if n['kind']=='bit_switch':
            tail=MultiButtonTail.parse(a.tail)
            assert tail.input_expression.value==tail.output_expression.value==CTX.native_name(n)
            assert tail.input_words==tail.output_words==[0xffffffff,0,1,0]
            assert [a.texts[i][0].caption.value for i in range(2)]==[n['captions'][s] for s in ('s0','s1')]
            assert all(struct.unpack_from('<HH',children[0].header)==(1,1) for children in a.texts)
            info['text_alignment_u16']=[list(struct.unpack_from('<HH',children[0].header)) for children in a.texts]
            info['native_action_rest_hex']=tail.rest.hex()
            if n.get('action','preserve')!='preserve':assert struct.unpack_from('<I',tail.rest,8)[0]==(3 if n['action']=='momentary' else 2)
            info['action']=n.get('action','preserve')
        else:
            reader=Reader(a.tail);assert reader.u32()==1 and reader.cstring()[0]==CTX.native_name(n)
        info.update(binding=CTX.native_name(n),child_rectangles_checked=children,states=2)
    elif n['kind']=='label':
        assert not env.animations
        a=LabelRecord.parse(record);assert a.caption==n['text']
        info.update(caption=a.caption,fonts=fonts(a.font))
    else:assert not env.animations
    return info

def compile_model(model,assets):
    from text_layout import require_fit
    text_report=require_fit(model)
    skin_kinds=('bit_switch','lamp','button','navigation')
    expected={n['id']+':'+s for n in model['components'] for s in (['s0','s1'] if n['kind'] in skin_kinds else ['s0'] if n['kind']=='picture' or n.get('background') else [])}
    if set(assets)!=expected:raise ValueError('Asset inventory mismatch')
    static=[n for n in model['components'] if n['kind'] in ('picture','label','button')]
    static_assets={key:value for key,value in assets.items() if key.split(':')[0] in {n['id'] for n in static}}
    blob,report=base.compile_model({'components':static,'width':model['width'],'height':model['height']},static_assets)
    static_records={n['id']:rec(n['kind'],blob[s['body_start']:s['body_end']]) for n,s in zip(static,report['spans'])}
    items=[];inventory=[]
    for n in model['components']:
        if n['kind'] in ('numeric_input','numeric_output'):r=make_numeric(n,assets)
        elif n['kind'] in ('bit_switch','lamp'):r=make_multistate(n,assets)
        elif n['kind'] in extra.EXTRA:r=extra.make(n,prototype(n['kind'],n['id']),assets,base.embedded)
        else:r=static_records[n['id']]
        info=describe(n,r)
        if n['kind'] in ('label','numeric_input','numeric_output'):
            info['text_layout']=next(row for row in text_report['items'] if row['id']==n['id'])
        inventory.append(info);items.append((n,r))

    # Correct MFC ordering: reserve each top-level object BEFORE serializing its
    # nested animation objects. Class IDs are shared by labels and outputs.
    classes={};next_slot=1
    def class_object_tag(name):
        nonlocal next_slot
        if name in classes:tag=struct.pack('<H',0x8000|classes[name])
        else:
            classes[name]=next_slot;next_slot+=1;c=name.encode('ascii');tag=struct.pack('<HHH',0xffff,0,len(c))+c
        next_slot+=1
        return tag
    out=write_count(len(items));spans=[]
    for n,r in items:
        head=len(out);out+=class_object_tag(CLASSES[n['kind']]);start=len(out);payload=r.payload
        if n['kind']=='numeric_output':
            env=CommonEnvelope.parse(r);anim=Reader(env.prefix,env.animation_start)
            assert anim.count()==1 and anim.u16()==0xffff and anim.u16()==0
            assert anim.take(anim.u16())==b'CAniOutput'
            payload=payload[:env.animation_start]+write_count(1)+class_object_tag('CAniOutput')+payload[anim.pos:]
        out+=payload;spans.append({'id':n['id'],'kind':n['kind'],'header_start':head,'body_start':start,'body_end':len(out)})
    # Resolve the written map from the actual stream. Restore canonical class
    # declarations for strict codecs, then compare every complete object body.
    reader=Reader(out);assert reader.count()==len(items);read_classes={};slot=1
    def read_class_object():
        nonlocal slot
        tag=reader.u16()
        if tag==0xffff:
            assert reader.u16()==0;name=reader.take(reader.u16()).decode('ascii');read_classes[slot]=name;slot+=1
        else:
            assert tag&0x8000 and tag!=0xffff;name=read_classes[tag&0x7fff]
        slot+=1;return name
    for (n,r),span in zip(items,spans):
        assert reader.pos==span['header_start'] and read_class_object()==CLASSES[n['kind']] and reader.pos==span['body_start']
        env=CommonEnvelope.parse(r)
        if n['kind']=='numeric_output':
            before=reader.take(env.animation_start);assert reader.count()==1
            assert read_class_object()=='CAniOutput';c=b'CAniOutput'
            canonical=before+write_count(1)+struct.pack('<HHH',0xffff,0,len(c))+c+reader.take(span['body_end']-reader.pos)
        else:canonical=reader.take(span['body_end']-reader.pos)
        assert canonical==r.payload
        describe(n,rec(n['kind'],canonical))
        assert reader.pos==span['body_end']
    assert reader.pos==len(out)
    return out,{'status':'memory_roundtrip_pass','count':len(items),'types':dict(collections.Counter(n['kind'] for n,_ in items)),'bytes':len(out),'sha256':hashlib.sha256(out).hexdigest(),'class_map':classes,'spans':spans,'inventory':inventory,'all_state_child_parent_rectangles':sum(x.get('child_rectangles_checked',0) for x in inventory),'new_variables':0,'bindings':list(dict.fromkeys(x['binding'] for x in inventory if x.get('binding'))),'binding_mode':CTX.binding_mode,'binding_status':'unbound' if CTX.binding_mode=='unbound' else 'names_pending_native_compile','source_mcp_required':False,'native_paste':'not_checked','native_reopen':'not_checked','native_runtime':'not_checked'}
