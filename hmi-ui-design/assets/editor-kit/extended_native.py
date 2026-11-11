"""Measured native branches; unknown fields and compiled bindings are retained."""
import struct,hashlib
from runtime_context import context
from control_schema import EXTRA,check
from mcs_window_archive import Reader,write_cstring,ControlRecord
from mcs_button_control import ButtonArchive,_picture
from mcs_input_text import read_font
from 原生界面样式 import CommonEnvelope
from native_ui_style import colorref,style_button

TYPES={'navigation':0x5027,'alarm_strip':0x503d,'alarm_browser':0x503d,'gauge':0x5032,'percentage_fill':0x5031,'realtime_trend':0x502d}
CLASSES={'navigation':'CDrawButton','alarm_strip':'CDrawDll','alarm_browser':'CDrawDll','gauge':'CDrawRotateTbl','percentage_fill':'CDrawSliderFill','realtime_trend':'CDrawPic'}
def need(ok,message):
    if not ok:raise ValueError(message)
def plugin(content,kind):
    q=Reader(content);path,raw,wide=q.cstring();core=q.take(q.u32());need(q.pos==len(content),'插件边界不符')
    if kind=='alarm_strip':need(path.endswith('AlarmScrollBar.ui#报警条[3.51]') and len(core)==160 and struct.unpack_from('<I',core,16)[0]==24,'报警条供体分支不匹配')
    else:need(path.endswith('AlarmTableView.ui#报警浏览[3.52]') and len(core)==494 and struct.unpack_from('<I',core,16)[0]==0x55b1b,'报警浏览供体分支不匹配')
    return raw,core
def gauge_parts(content):
    need(len(content)>=44,'仪表头不完整');gate=struct.unpack_from('<I',content,40)[0];need(gate in (0,1),'仪表图片分支未知')
    q=Reader(content,44);pic=_picture(q) if gate else b'';tail=content[q.pos:]
    # Derive the offset through the actual font CString, not a fixed font length.
    r=Reader(tail);r.take(32);read_font(r);r.take(9*4);offset=r.pos
    expression=r.cstring()[0];cache=r.byte_array()[0];expression_end=r.pos
    upper=r.cstring()[0];r.byte_array();lower=r.cstring()[0];r.byte_array()
    need(upper=='120' and lower=='0','本轮仪表需已验证0～120分支')
    return gate,pic,tail,offset,expression,cache,expression_end
def fill_parts(content):
    q=Reader(content,148);text,raw,wide=q.cstring();expression,sep,hextext=text.partition('\x01');need(bool(sep),'填充表达式格式不匹配')
    r=Reader(bytes.fromhex(hextext));lo,lo_raw,_=r.cstring();hi,_,hiwide=r.cstring();suffix=r.data[r.pos:]
    need(lo=='0' and len(suffix)==70 and suffix[56]==0x11,'填充量程分支不匹配')
    need(struct.unpack_from('<I',suffix,57)[0]==int(hi) and struct.unpack_from('<2f',content,q.pos)==(0.,float(hi)),'填充量程缓存不一致')
    return expression,lo_raw,int(hi),hiwide,suffix,wide,q.pos
def set_fill_max(content,maximum):
    expression,lo,old,hiwide,suffix,wide,end=fill_parts(content);suffix=bytearray(suffix);struct.pack_into('<I',suffix,57,maximum)
    nested=lo+write_cstring(str(maximum),hiwide)+suffix
    tail=bytearray(content[end:]);struct.pack_into('<f',tail,4,float(maximum))
    return content[:148]+write_cstring(expression+'\x01'+nested.hex(),wide)+tail
def trend_parts(content):
    # Curve 1 CString and DWORD byte-count delimit the cache. Subsequent styles
    # are unchanged; offsets follow its measured serialized extent.
    r=Reader(content,250);r.cstring();r.take(r.u32());cache_end=r.pos
    descriptor_start=cache_end+156;color_offset=cache_end+12
    need(len(content)-descriptor_start==580,'趋势归档分支不匹配')
    q=Reader(content,descriptor_start);text,_,wide=q.cstring();need(text.startswith('\x01'),'趋势范围描述符不匹配')
    inner=bytes.fromhex(text[1:]);need(len(inner)==140,'趋势嵌套分支不匹配')
    r=Reader(inner);upper,_,uw=r.cstring();need(r.pos==14,'趋势上限字符串长度未标定');lower=r.cstring()[0]
    r=Reader(inner,98);minutes,_,mw=r.cstring();need(r.pos==106,'趋势时间字符串长度未标定')
    need(lower=='0.0' and struct.unpack_from('<d',inner,47)[0]==float(upper),'趋势上限缓存不一致')
    need(struct.unpack_from('<I',inner,129)[0]==int(minutes) and struct.unpack_from('<f',content,165)[0]==float(minutes),'趋势时间缓存不一致')
    return inner,wide,q.pos,uw,mw,descriptor_start,color_offset
def replace_gauge_binding(content,name):
    gate,pic,tail,begin,old,cache,end=gauge_parts(content)
    return content[:44]+pic+tail[:begin]+write_cstring(name)+struct.pack('<H',0)+tail[end:]
def replace_fill_binding(content,name):
    q=Reader(content,148);text,_,wide=q.cstring();inner=text.partition('\x01')[2]
    return content[:148]+write_cstring(name+'\x01'+inner,wide)+content[q.pos:]
def replace_trend_binding(content,name):
    q=Reader(content,250);q.cstring();q.take(q.u32())
    return content[:250]+write_cstring(name)+struct.pack('<I',0)+content[q.pos:]

def preserved_binding(env,kind):
    if kind=='gauge':return gauge_parts(env.content)[4]
    if kind=='percentage_fill':return fill_parts(env.content)[0]
    # Current realtime-trend branch carries its curve expression after its cache.
    # Verify against the genuine donor's parsed source descriptor supplied by extraction.
    return None
def validate_prototype(n,record):
    ctx=context();env=CommonEnvelope.parse(record);k=n['kind'];check(n)
    need(not env.animations,'扩展原生默认结构不能带未知动画')
    if k in ('alarm_strip','alarm_browser'):plugin(env.content,k)
    elif k=='gauge':
        gate,pic,tail,off,expr,cache,end=gauge_parts(env.content)
        need(expr=='' and cache==b'','仪表默认结构含旧绑定')
        need(not n['show_background'] or bool(pic),'内置仪表背景缺失')
    elif k=='percentage_fill':need(fill_parts(env.content)[0]=='','填充默认结构含旧绑定')
    elif k=='realtime_trend':
        trend_parts(env.content);q=Reader(env.content,250);need(q.cstring()[0]=='' and q.u32()==0,'趋势默认结构含旧绑定')
    else:
        a=ButtonArchive.parse(record);p=a.metadata.properties
        need(len(p.texts_down.items)>1 and len(p.ids_up.items)>1,'内置导航结构不符')
        need(not p.press_script.value and not a.release_script.value,'内置导航不能带脚本')
        need(isinstance(n['target_name'],str) and 0<len(n['target_name'])<=30,'跳转目标名称无效')

def make(n,record,assets,embedded):
    validate_prototype(n,record);k=n['kind'];ctx=context();env=CommonEnvelope.parse(record)
    if k=='navigation':
        a=ButtonArchive.parse(record);a.name.value=n['id'];a.rect=tuple(n['rect']);p=a.metadata.properties
        target={'name':n['target_name'],'id':0xffffffff}
        p.texts_down.items[1].value=target['name'];p.ids_up.items[1]=target['id']
        w,h=n['rect'][2]-n['rect'][0],n['rect'][3]-n['rect'][1]
        p.picture=embedded(assets[n['id']+':s0'],w,h);p.words[16]=1;a.picture=embedded(assets[n['id']+':s1'],w,h)
        style={'caption':n['text'],'font':{key:n['font'][key] for key in ('family','size_px','weight')},'color':n['font']['color'],'horizontal':'center','vertical':'center'}
        return style_button(a.to_record(),{'s0':style,'s1':style})
    env.name.value=n['id'];env.set_rect(n['rect'])
    if k in ('alarm_strip','alarm_browser'):
        path,core=plugin(env.content,k);c=bytearray(core)
        struct.pack_into('<I',c,20,colorref(n['background_color']) if k=='alarm_strip' else int(n['alarm_mode']=='history'))
        env.content=path+struct.pack('<I',len(c))+c
    elif k=='gauge':
        env.content=replace_gauge_binding(env.content,ctx.native_name(n));gate,pic,tail,*_=gauge_parts(env.content);c=bytearray(env.content[:44]);struct.pack_into('<III',c,12,colorref(n['needle_color']),n['needle_margin'],n['needle_width'])
        struct.pack_into('<I',c,40,int(n['show_background']));env.content=bytes(c)+(pic if n['show_background'] else b'')+tail
    elif k=='percentage_fill':
        c=bytearray(set_fill_max(replace_fill_binding(env.content,ctx.native_name(n)),n['max']))
        def native_color(key,offset):
            old=struct.unpack_from('<I',c,offset)[0];value=0x84 if n[key] is None else (old&0xff000000 or 0x01000000)|colorref(n[key]);struct.pack_into('<I',c,offset,value)
        native_color('text_color',39);native_color('background_color',43);struct.pack_into('<I',c,51,int(n['hide_text']))
        # Preserve the source direction word. Native saving derives it from geometry;
        # only geometry-based behavior has runtime evidence, not an enum setter.
        env.content=bytes(c);prefix=bytearray(env.prefix);old=struct.unpack_from('<I',prefix,env.brush_offset+6)[0]
        struct.pack_into('<I',prefix,env.brush_offset+6,(old&0xff000000)|colorref(n['fill_color']));env.prefix=bytes(prefix)
    elif k=='realtime_trend':
        env.content=replace_trend_binding(env.content,ctx.native_name(n));inner,wide,end,uw,mw,descriptor_start,color_offset=trend_parts(env.content);inner=bytearray(inner)
        upper=write_cstring(f"{float(n['y_max']):.1f}",uw);minutes=write_cstring(str(n['time_minutes']),mw)
        need(len(upper)==14 and len(minutes)==8,'趋势变长属性本轮未开放')
        inner[:14]=upper;inner[98:106]=minutes;struct.pack_into('<d',inner,47,n['y_max']);struct.pack_into('<I',inner,129,n['time_minutes'])
        c=bytearray(env.content);struct.pack_into('<I',c,0,n['y_major']);struct.pack_into('<I',c,40,n['x_major']);struct.pack_into('<f',c,165,n['time_minutes']);struct.pack_into('<I',c,color_offset,colorref(n['curve_color']))
        env.content=bytes(c[:descriptor_start])+write_cstring('\x01'+inner.hex(),wide)+bytes(c[end:])
    result=env.to_record();need(CommonEnvelope.parse(result).to_record().payload==result.payload,'扩展对象无法精确回环')
    return result

def describe(n,record):
    env=CommonEnvelope.parse(record);k=n['kind'];need(env.name.value==n['id'] and list(env.rect)==n['rect'],'扩展对象名字/外框不符')
    info={'id':n['id'],'kind':k,'native_type':hex(record.type_id),'rect':list(env.rect),'animations':env.animations}
    if k=='navigation':
        a=ButtonArchive.parse(record);p=a.metadata.properties;need(p.texts_down.items[1].value==n['target_name'] and a.caption.value==p.caption.value==n['text'],'导航回读不符')
        info.update(target=n['target_name'],target_id=p.ids_up.items[1],target_status='name_pending_native_resolution',caption=n['text'])
    elif k in ('alarm_strip','alarm_browser'):
        path,c=plugin(env.content,k);need(struct.unpack_from('<I',c,20)[0]==(colorref(n['background_color']) if k=='alarm_strip' else int(n['alarm_mode']=='history')),'报警属性回读不符')
        info.update(plugin_kind=k)
    elif k=='gauge':
        gate,pic,tail,offset,expr,cache,end=gauge_parts(env.content)
        need(gate==int(n['show_background']) and struct.unpack_from('<III',env.content,12)==(colorref(n['needle_color']),n['needle_margin'],n['needle_width']),'仪表外观回读不符')
        need(expr==context().native_name(n),'仪表绑定回读不符');info.update(binding=expr,binding_status='unbound' if not expr else 'name_pending_native_compile',range=[0,120],native_cache_sha256=hashlib.sha256(cache).hexdigest())
    elif k=='percentage_fill':
        expr,lo,hi,*_=fill_parts(env.content);need(hi==n['max'] and expr==context().native_name(n),'填充范围/绑定不符')
        need(struct.unpack_from('<I',env.prefix,env.brush_offset+6)[0]&0xffffff==colorref(n['fill_color']),'填充色回读不符')
        for key,offset in [('text_color',39),('background_color',43)]:need(struct.unpack_from('<I',env.content,offset)[0]==0x84 if n[key] is None else struct.unpack_from('<I',env.content,offset)[0]&0xffffff==colorref(n[key]),'填充文字/背景回读不符')
        need(struct.unpack_from('<I',env.content,51)[0]==int(n['hide_text']),'填充文字显隐不符')
        info.update(binding=expr,range=[0,hi],orientation='vertical' if n['rect'][3]-n['rect'][1]>n['rect'][2]-n['rect'][0] else 'horizontal')
    else:
        inner,_,_,_,_,descriptor_start,color_offset=trend_parts(env.content);need(struct.unpack_from('<I',env.content,0)[0]==n['y_major'] and struct.unpack_from('<I',env.content,40)[0]==n['x_major'],'趋势刻线回读不符')
        need(struct.unpack_from('<f',env.content,165)[0]==n['time_minutes'] and struct.unpack_from('<d',inner,47)[0]==n['y_max'] and struct.unpack_from('<I',env.content,color_offset)[0]==colorref(n['curve_color']),'趋势时间/量程/颜色回读不符')
        info.update(binding=context().native_name(n),binding_status='unbound' if context().binding_mode=='unbound' else 'name_pending_native_compile',time_minutes=n['time_minutes'],y_max=n['y_max'])
    return info
