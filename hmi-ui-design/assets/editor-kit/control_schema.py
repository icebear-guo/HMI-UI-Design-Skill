"""Shared, bounded properties for the first twelve editor kinds."""
import math,re
EXTRA={'navigation','alarm_strip','alarm_browser','gauge','percentage_fill','realtime_trend'}
FIELDS={
 'navigation':{'text','font','target_name'},
 'alarm_strip':{'background_color'},
 'alarm_browser':{'alarm_mode'},
 'gauge':{'show_background','needle_color','needle_width','needle_margin'},
 'percentage_fill':{'max','fill_color','text_color','background_color','hide_text'},
 'realtime_trend':{'x_major','y_major','time_minutes','y_max','curve_color'},
}
def check(n):
    k=n['kind']
    def need(ok,msg):
        if not ok:raise ValueError(n['id']+'：'+msg)
    def color(key,nullable=False):need(nullable and n.get(key) is None or bool(re.fullmatch(r'#[0-9a-fA-F]{6}',str(n.get(key)))),'颜色无效：'+key)
    if k=='bit_switch':need(n.get('action','preserve') in ('preserve','momentary','toggle'),'动作只支持保留、按1松0和取反')
    elif k=='navigation':
        need(isinstance(n.get('text'),str) and 0<len(n['text'])<=32 and not any(c in n['text'] for c in '\0\r\n'),'按钮文字需1～32字')
        need(isinstance(n.get('target_name'),str) and 0<len(n['target_name'])<=30,'请选择真实目标窗口')
        need(set(n.get('states',{}))=={'s0','s1'},'导航需两态源图')
    elif k=='alarm_strip':color('background_color')
    elif k=='alarm_browser':need(n.get('alarm_mode') in ('realtime','history'),'报警模式无效')
    elif k=='gauge':
        need(type(n.get('show_background')) is bool,'背景显隐需明确')
        color('needle_color')
        need(type(n.get('needle_width')) is int and 1<=n['needle_width']<=20,'指针宽度需1～20')
        need(type(n.get('needle_margin')) is int and 0<=n['needle_margin']<=60,'指针边距需0～60')
        need(n.get('min')==0 and n.get('max')==120,'本轮仪表沿用已验证0～120量程')
    elif k=='percentage_fill':
        need(n.get('min')==0 and type(n.get('max')) is int and n['max'] in (100,200,1000),'本轮填充支持0～100/200/1000')
        color('fill_color');color('text_color',True);color('background_color',True)
        need(type(n.get('hide_text')) is bool,'文字显隐需明确')
        l,t,r,b=n['rect'];need(r-l!=b-t,'本轮填充使用明确横向或竖向矩形')
    elif k=='realtime_trend':
        for name in ('x_major','y_major'):need(type(n.get(name)) is int and 1<=n[name]<=12,'刻线数需1～12')
        need(n.get('time_minutes') in (10,15,20) and n.get('y_max') in (100,200,300),'本轮趋势支持10/15/20分钟，上限100/200/300')
        color('curve_color')
    if k in ('gauge','percentage_fill','realtime_trend'):
        need(n.get('binding',{}).get('kind')==2,'需已有数值变量绑定')
    return n
