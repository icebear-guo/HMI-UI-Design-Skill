"""Reusable source components and three industrial HMI layout recipes.

No site-specific variables, native donors, PNG output or whole-page artwork.
"""
import copy,html,json
STYLES={
 'blue':{'title':'清蓝 · 运行总览','page':'设备运行总览','bg':'#edf2f8','panel':'#ffffff','ink':'#24354d','muted':'#728197','accent':'#2878ed','soft':'#e6effd','header':'#173758'},
 'graphite':{'title':'石墨 · 参数控制','page':'工艺参数设置','bg':'#172229','panel':'#23343e','ink':'#eef6fa','muted':'#9eb5c0','accent':'#12bfa5','soft':'#334e55','header':'#102029'},
 'sand':{'title':'暖灰 · 报警趋势','page':'报警与趋势','bg':'#f1eee8','panel':'#ffffff','ink':'#343b43','muted':'#8a8173','accent':'#d48a29','soft':'#faf0df','header':'#3e454b'}
}
def svg_rect(w,h,color,radius=0,stroke=None):
    border=f' stroke="{stroke}" stroke-width="1"' if stroke else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{radius}" fill="{color}"{border}/></svg>'
def font(size=18,color='#24354d',weight=400):return {'family':'微软雅黑','size_px':size,'weight':weight,'color':color}

def make(style,variables,bindings,targets,revision):
    t=STYLES[style];nodes=[]
    def add(ident,kind,rect,**fields):
        n={'id':style+'_'+ident,'kind':kind,'rect':rect,'z':len(nodes)};n.update(fields);nodes.append(n);return n
    def box(ident,rect,color=None,r=8):
        return add(ident,'picture',rect,svg=svg_rect(rect[2]-rect[0],rect[3]-rect[1],color or t['panel'],r))
    def label(ident,text,rect,size=16,color=None,bold=False):return add(ident,'label',rect,text=text,font=font(size,color or t['ink'],700 if bold else 400))
    def number(ident,rect,input=False):
        return add(ident,'numeric_input' if input else 'numeric_output',rect,binding=copy.deepcopy(bindings['numeric']),digits=0,min=0,max=1000,font=font(28,t['accent'],700))
    def bit(ident,text,rect,action='momentary'):
        w,h=rect[2]-rect[0],rect[3]-rect[1]
        return add(ident,'bit_switch',rect,binding=copy.deepcopy(bindings['bit']),action=action,
            states={'s0':svg_rect(w,h,t['soft'],7),'s1':svg_rect(w,h,t['accent'],7)},captions={'s0':text,'s1':text},
            state_colors={'s0':t['ink'],'s1':'#ffffff'},font=font(17,t['ink'],700))
    def fill(ident,rect,maxi=1000):return add(ident,'percentage_fill',rect,binding=copy.deepcopy(bindings['percentage_fill']),min=0,max=maxi,fill_color=t['accent'],text_color='#d94b40',background_color='#ffffff',hide_text=False)
    def gauge(rect):return add('gauge','gauge',rect,binding=copy.deepcopy(bindings['gauge']),min=0,max=120,show_background=True,needle_color=t['accent'],needle_width=7,needle_margin=25)
    def trend(rect):return add('trend','realtime_trend',rect,binding=copy.deepcopy(bindings['realtime_trend']),x_major=6,y_major=5,time_minutes=15,y_max=200,curve_color=t['accent'])
    def alarm(ident,rect,mode):return add(ident,'alarm_browser',rect,alarm_mode=mode)
    box('background',[0,0,1024,600],t['bg'],0);box('header',[0,0,1024,66],t['header'],0)
    label('title',t['page'],[20,12,290,52],25,'#ffffff',True);label('brand','工控北极熊（抖音）',[760,20,1004,48],16,'#ffffff')
    if style=='blue':
        for i,(caption,x) in enumerate([('过程数值',20),('参数设定',268),('设备状态',516),('操作模式',764)]):
            box('kpi'+str(i),[x,84,x+240,184]);label('kpi_label'+str(i),caption,[x+12,93,x+228,121],15,t['muted'])
        number('value',[40,130,220,168]);number('setpoint',[288,130,468,168],True)
        add('lamp','lamp',[600,130,632,162],binding=copy.deepcopy(bindings['bit']),states={'s0':svg_rect(32,32,'#a7b4c2',16),'s1':svg_rect(32,32,'#12b886',16)})
        bit('switch','运行开关',[792,130,976,168],'toggle')
        box('process_card',[20,202,612,492]);label('process_label','运行监视 / 本地试验信号',[36,214,594,246],18,bold=True)
        gauge([64,260,254,450]);label('gauge_caption','过程仪表',[64,455,254,482],14,t['muted'])
        fill('level',[304,270,344,450]);label('level_caption','液位',[282,455,368,482],14,t['muted']);fill('progress',[386,332,582,364],200)
        box('commands_card',[630,202,1004,492]);label('command_label','设备操作',[650,214,984,246],18,bold=True)
        for i,text in enumerate(['启动','停止','复位','点动']):bit('command'+str(i),text,[650+(i%2)*170,270+(i//2)*88,804+(i%2)*170,326+(i//2)*88])
        add('alarm_strip','alarm_strip',[20,510,1004,550],background_color='#eaf2ff')
    elif style=='graphite':
        box('sidebar',[20,84,232,490]);label('side_title','参数分组',[34,100,218,132],19,bold=True)
        for i,text in enumerate(['基础设置','运行参数','操作控制','维护设置']):label('side'+str(i),text,[40,160+i*66,212,194+i*66],17,t['muted'])
        box('parameters',[250,84,740,490]);label('parameter_title','参数编辑与状态控制',[272,100,718,136],20,bold=True)
        for i,text in enumerate(['过程反馈','目标设定','本地请求']):
            y=166+i*86;label('parameter'+str(i),text,[274,y,470,y+42],17)
            number('parameter_value'+str(i),[496,y,706,y+42],i>0)
        bit('apply','点动请求',[280,426,478,470]);bit('mode','自动开关',[506,426,706,470],'toggle')
        box('right',[758,84,1004,490]);label('right_title','过程反馈',[774,100,988,136],19,bold=True);gauge([786,156,976,346]);fill('progress',[784,400,976,432],200)
        add('alarm_strip','alarm_strip',[20,510,1004,550],background_color='#eaf2ff')
    else:
        box('trend_card',[20,84,654,350]);label('trend_title','实时趋势 / 原生曲线',[34,94,636,126],19,bold=True);trend([38,138,636,330])
        box('signal_card',[672,84,1004,350]);label('signal_title','采样信号',[688,94,988,126],19,bold=True)
        number('signal',[700,146,974,188],True);fill('progress',[700,220,974,252],200);bit('switch','试验开关',[700,282,974,326],'toggle')
        alarm('realtime',[20,370,502,540],'realtime');alarm('history',[522,370,1004,540],'history')
    label('scope_note','试验页：同名变量共享；未连接实际设备。',[20,556,620,586],12,t['muted'])
    # Targets refer to real source-project windows. New-window ID remapping is not assumed.
    for i,target in enumerate(targets[:2]):
        text='画面：'+target['name'];rect=[650+i*178,556,816+i*178,590];w,h=rect[2]-rect[0],rect[3]-rect[1]
        add('nav'+str(i),'navigation',rect,text=text,target_name=target['name'],font=font(12,t['ink'],400),states={'s0':svg_rect(w,h,t['soft'],6),'s1':svg_rect(w,h,t['accent'],6)})
    return {'schema':'hmi-ui-editor-model/2.0-test','revision':revision,'title':t['page'],'width':1024,'height':600,
        'template':{'id':style,'library_revision':'1.0','components_independent':True},'variables':copy.deepcopy(variables),
        'preview_initial':{b['name']:False if b['kind']==1 else 60 for b in bindings.values()},'components':nodes}

def preview_html(model):
    # Standalone offline preview; uses the same model and SVG components as export.
    encoded=json.dumps(model,ensure_ascii=False).replace('<',chr(92)+'u003c')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>模板预览</title>
<style>*{box-sizing:border-box}body{margin:0;padding:24px;background:#dce3eb;font:14px 'Microsoft YaHei',sans-serif;color:#26394c}header{display:flex;gap:20px;align-items:center;max-width:1024px;margin:0 auto 16px}header a{color:#2878ed}h1{font-size:20px;margin-right:auto}.wrap{max-width:100%;overflow:auto}#canvas{width:1024px;height:600px;position:relative;margin:auto;overflow:hidden;box-shadow:0 10px 35px #172f4520}.node{position:absolute;display:flex;align-items:center;justify-content:center;overflow:hidden;white-space:nowrap}.node>svg{width:100%;height:100%}.fill{position:absolute;left:0;bottom:0}.caption{position:relative}input[type=number]{width:90px;padding:6px}.alarm{background:white;border:1px solid #bac5cf;color:#3c4650;font-size:12px}.note{max-width:1024px;margin:16px auto;color:#65778a}</style>
<header><a href="index.html">模板库</a><h1 id="title"></h1><label>模拟数值 <input id="value" type="number" value="60" min="0" max="1000"></label></header><div class="wrap"><div id="canvas"></div></div><p class="note">离线布局模板 · 各文字、底板、按钮与动态控件独立建模。修改数值可看仪表和填充示意；报警与趋势是布局预览。原生编辑和复制请使用项目会话。</p>
<script>const model=MODEL_DATA;document.title=document.querySelector('#title').textContent=model.title;const canvas=document.querySelector('#canvas');function draw(){canvas.replaceChildren();let v=Number(document.querySelector('#value').value)||0;for(const n of model.components){const e=document.createElement('div');e.className='node';const [l,t,r,b]=n.rect;Object.assign(e.style,{left:l+'px',top:t+'px',width:r-l+'px',height:b-t+'px',zIndex:n.z});if(n.font)Object.assign(e.style,{fontSize:n.font.size_px+'px',fontWeight:n.font.weight,color:n.font.color,fontFamily:n.font.family});if(n.kind==='picture')e.innerHTML=n.svg;else if(n.kind==='label')e.textContent=n.text;else if(n.kind.startsWith('numeric'))e.textContent=v.toFixed(n.digits);else if(n.kind==='bit_switch'||n.kind==='navigation'||n.kind==='lamp'){e.innerHTML=n.states.s0;const c=document.createElement('span');c.className='caption';c.textContent=n.text||n.captions?.s0||'';e.firstChild.style.position='absolute';e.append(c);}else if(n.kind==='percentage_fill'){e.style.background=n.background_color||'transparent';const f=document.createElement('div');f.className='fill';f.style.background=n.fill_color;const vertical=b-t>r-l,ratio=Math.min(1,Math.max(0,v/n.max));f.style.width=(vertical?100:ratio*100)+'%';f.style.height=(vertical?ratio*100:100)+'%';e.append(f);if(!n.hide_text){const c=document.createElement('span');c.className='caption';c.style.color=n.text_color||'transparent';c.textContent=Math.round(ratio*100)+'%';e.append(c);}}else if(n.kind==='gauge'){let marks='';for(let i=0;i<=12;i++){const a=(-135+i*22.5)*Math.PI/180;marks+=`<text x="${100+Math.sin(a)*78}" y="${100-Math.cos(a)*78}" text-anchor="middle" font-size="10" fill="#526177">${i*10}</text>`;}const a=(-135+270*Math.min(1,v/120))*Math.PI/180;e.innerHTML=`<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="95" fill="white" stroke="#637486" stroke-width="3"/>${marks}<line x1="100" y1="100" x2="${100+Math.sin(a)*64}" y2="${100-Math.cos(a)*64}" stroke="${n.needle_color}" stroke-width="6"/><circle cx="100" cy="100" r="7" fill="#64748b"/></svg>`;}else if(n.kind==='realtime_trend'){e.innerHTML=`<svg viewBox="0 0 600 200"><defs><pattern id="grid" width="60" height="40" patternUnits="userSpaceOnUse"><path d="M60 0H0V40" fill="none" stroke="#dbe3ed"/></pattern></defs><rect width="600" height="200" fill="white"/><rect width="600" height="200" fill="url(#grid)"/><path d="M0 170L60 150L120 162L180 110L240 124L300 74L360 90L420 48L480 60L540 26L600 40" fill="none" stroke="${n.curve_color}" stroke-width="3"/></svg>`;}else {e.classList.add('alarm');e.textContent=n.kind==='alarm_strip'?'报警消息区域':(n.alarm_mode==='history'?'历史报警记录':'实时报警记录');if(n.background_color)e.style.background=n.background_color;}canvas.append(e);}}document.querySelector('#value').addEventListener('input',draw);draw();</script></html>'''.replace('MODEL_DATA',encoded)
