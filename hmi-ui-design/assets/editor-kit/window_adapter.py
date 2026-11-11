"""Generate native window frames from current edited models; no MCP writes."""
from pathlib import Path
import base64, copy, hashlib, json, re, struct
from model_editor import apply_edits, need

from runtime_context import context

def window_template():
    from mcs_window_archive import Reader,WindowSettings
    ctx=context();item=ctx.bank['window']
    prefix=bytes.fromhex(item['document_prefix_hex']);settings=WindowSettings.parse(bytes.fromhex(item['settings_hex']))
    r=Reader(prefix);r.take(12);need(r.cstring()[0]=='MCGS-SET DOCUMENT;VERSION 01.00','内置窗口标识不符')
    need(len(settings.properties)==21 and [settings.properties[i].value for i in (6,7)]==[1024,600],'内置窗口规格不符')
    need(not settings.password_data and len(settings.event_tail)==101,'内置新窗口状态不符')
    need(struct.unpack_from('<i',settings.event_tail,len(settings.event_tail)-8)[0]==-1,'内置窗口不能引用其他工程公共页')
    return prefix,settings,bytes.fromhex(item['suffix_hex']),bytes.fromhex(item['allocation_remainder_hex']),{'window_id_seed':item['id_seed']}


def compile_windows(catalog,request):
    from native_adapter import compile_model
    from mcs_window_archive import Reader,WindowSettings
    need(isinstance(request,dict) and not set(request)-{'revision','sequence','pages','binding_mode'},'窗口复制请求无效。')
    need(request.get('revision')==catalog['revision'],'页面集合已更新，请刷新后重试。')
    specs=request.get('pages');need(isinstance(specs,list) and 1<=len(specs)<=catalog['limit'],'请选择1～6个窗口。')
    prefix,settings,suffix,remainder,manifest=window_template()
    page_map={p['id']:p for p in catalog['pages']};seen=set();names=set();frames=[];reports=[];exports=[]
    renamed={page_map[s['id']]['name']:s['name'] for s in specs if isinstance(s,dict) and s.get('id') in page_map and isinstance(s.get('name'),str)}
    for spec in specs:
        need(isinstance(spec,dict) and set(spec)=={'id','name','revision','patches','assets'},'窗口字段不完整。')
        ident=spec['id'];need(isinstance(ident,str) and ident in page_map and ident not in seen,'窗口不存在或重复。');seen.add(ident)
        name=spec['name'];need(isinstance(name,str) and name==name.strip() and re.fullmatch(r'[^\\/:*?"<>|\x00-\x1f]{1,30}',name),'窗口名须为1～30字，不能含路径符号。')
        need(name.casefold() not in names,'所选窗口名称不能重复。');names.add(name.casefold())
        baseline=page_map[ident]['model'];need(spec['revision']==baseline['revision'],'窗口版本不匹配，请刷新。')
        model=apply_edits(baseline,spec['patches'])
        for node in model['components']:
            if node['kind']=='navigation':node['target_name']=renamed.get(node['target_name'],node['target_name'])
        need(isinstance(spec['assets'],dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in spec['assets'].items()),'图片清单无效。')
        assets={k:base64.b64decode(v,validate=True) for k,v in spec['assets'].items()}
        collection,report=compile_model(model,assets)
        # compile_model resolves actual CArchive classes and compares every object payload.
        need(Reader(collection).count()==len(model['components']),'窗口控件数量不一致。')
        window_id=manifest['window_id_seed']+list(page_map).index(ident)
        from canvas_profile import dimensions,details as canvas_details
        width,height=dimensions(model['width'],model['height'])
        ws=settings.clone(window_id,name)
        for index,value in ((6,width),(7,height),(19,width),(20,height)):
            need(ws.properties[index].vt==3,'窗口尺寸相关字段类型不符')
            ws.properties[index].value=value
        serialized=ws.to_bytes()
        parsed=WindowSettings.parse(serialized)
        need(parsed.properties[0].value==window_id and parsed.properties[1].value==name,'窗口名称回读不一致。')
        need([parsed.properties[i].value for i in (6,7,19,20)]==[width,height,width,height],'窗口画布/初始显示尺寸回读不一致')
        parsed.properties[0].value=settings.properties[0].value;parsed.properties[1].value=settings.properties[1].value
        for index in (6,7,19,20):parsed.properties[index].value=settings.properties[index].value
        need(parsed.to_bytes()==settings.to_bytes(),'窗口修改影响了非预期字段。')
        frame=prefix+collection+serialized+suffix;frames.append(frame)
        report.update(page_id=ident,window_name=name,window_id=window_id,window_bytes=len(frame),editor=model['editor'],canvas=[width,height],canvas_profile=canvas_details(width,height))
        reports.append(report);exports.append({'id':ident,'name':name,'model':model,'patches':spec['patches'],'assets':assets})
    blob=struct.pack('<I',len(frames))+b''.join(struct.pack('<I',len(f))+f for f in frames)+remainder
    reader=Reader(blob);need(reader.u32()==len(frames),'窗口包数量回读失败。')
    for frame in frames:need(reader.take(reader.u32())==frame,'窗口边界回读失败。')
    need(reader.take(len(remainder))==remainder and reader.pos==len(blob),'窗口包尾部回读失败。')
    need(len(blob)<=16*1024*1024,'窗口包超过本次工具支持大小。')
    return blob,{'status':'memory_roundtrip_pass','format':'MCGS_WND_USER_PRO1','window_count':len(frames),
        'count':sum(p['count'] for p in reports),'pages':reports,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),
        'new_variables':0,'native_paste':'not_checked','native_configuration_check':'not_checked',
        'native_reopen':'not_checked','runtime':'not_checked'},exports
