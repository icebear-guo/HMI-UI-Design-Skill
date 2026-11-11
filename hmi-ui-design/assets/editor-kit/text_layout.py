"""Shared logical-pixel text sizing for project builds, editing and native copy.

No screen-DPI multiplier, font shrinking, neighbour movement or native writes.
The C/B margins are tested candidates, not a reverse-engineered MCGS inset.
"""
import copy, ctypes, math, os
from decimal import Decimal, ROUND_HALF_UP, localcontext
from functools import lru_cache

REVISION = 'gdi-text-layout/1.0'
KINDS = {'label', 'numeric_input', 'numeric_output'}
PROFILES = {
    'mcgs351-c': {'width_extra': 16, 'height_extra': 8},
    'mcgs351-b': {'width_extra': 8, 'height_extra': 4},
}
DEFAULT_PROFILE = 'mcgs351-c'
EVIDENCE = {
    'mcgs_version': '3.5.1.6963', 'family': '微软雅黑',
    'weights': [400, 700], 'tested_sizes_px': [12, 13, 14, 16, 18, 24, 28],
    'tested_size_weight_pairs': [[s,w] for s in [12,14,16,18,24,28] for w in [400,700]] + [[13,400]],
    'windows_scaling': '200%', 'screen_resolution': [2560, 1600],
    'scope': 'finite static-label and numeric samples; other fonts/sizes/DPI remain unverified',
}

class LayoutError(ValueError):
    pass

def options(model, node):
    base = model.get('text_layout', {})
    own = node.get('text_layout', {})
    for value in (base, own):
        if not isinstance(value, dict) or set(value) - {'profile'}:
            raise LayoutError('文字尺寸设置只支持 profile')
    profile = own.get('profile', base.get('profile', DEFAULT_PROFILE))
    if profile not in PROFILES:
        raise LayoutError('未知文字余量方案：' + str(profile))
    return profile, PROFILES[profile]

@lru_cache(maxsize=8192)
def measure(text, family, size_px, weight):
    """MM_TEXT advances and line extent using the exact requested LOGFONT."""
    if os.name != 'nt':
        raise LayoutError('精确字体测量需要Windows GDI；未使用估算替代')
    if not isinstance(text, str) or any(c in text for c in '\0\r\n'):
        raise LayoutError('本轮字体测量只支持单行文字')
    if not family or len(family.encode('utf-16-le')) // 2 > 31:
        raise LayoutError('字体名称无效或超过LOGFONT长度')
    from ctypes import wintypes as W
    class LOGFONT(ctypes.Structure):
        _fields_ = [('height', W.LONG), ('width', W.LONG), ('escapement', W.LONG),
                   ('orientation', W.LONG), ('weight', W.LONG), ('italic', W.BYTE),
                   ('underline', W.BYTE), ('strikeout', W.BYTE), ('charset', W.BYTE),
                   ('outprecision', W.BYTE), ('clipprecision', W.BYTE), ('quality', W.BYTE),
                   ('pitchfamily', W.BYTE), ('face', W.WCHAR * 32)]
    class SIZE(ctypes.Structure):
        _fields_ = [('cx', W.LONG), ('cy', W.LONG)]
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [W.HDC]; gdi.CreateCompatibleDC.restype = W.HDC
    gdi.CreateFontIndirectW.argtypes = [ctypes.POINTER(LOGFONT)]; gdi.CreateFontIndirectW.restype = W.HFONT
    gdi.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]; gdi.SelectObject.restype = W.HGDIOBJ
    gdi.GetTextExtentPoint32W.argtypes = [W.HDC, W.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)]
    gdi.GetTextFaceW.argtypes = [W.HDC, ctypes.c_int, W.LPWSTR]
    gdi.GetGlyphIndicesW.argtypes = [W.HDC, W.LPCWSTR, ctypes.c_int, ctypes.POINTER(W.WORD), W.DWORD]
    gdi.GetGlyphIndicesW.restype = W.DWORD
    gdi.DeleteObject.argtypes = [W.HGDIOBJ]; gdi.DeleteDC.argtypes = [W.HDC]
    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        raise LayoutError('无法创建字体测量DC')
    font = None; old = None
    try:
        lf = LOGFONT(); lf.height = -size_px; lf.weight = weight
        lf.charset = 134; lf.quality = 1; lf.pitchfamily = 2; lf.face = family
        font = gdi.CreateFontIndirectW(ctypes.byref(lf))
        if not font:
            raise LayoutError('无法加载字体：' + family)
        old = gdi.SelectObject(dc, font)
        actual = ctypes.create_unicode_buffer(64)
        if not gdi.GetTextFaceW(dc, 64, actual):
            raise LayoutError('无法核实实际字体')
        aliases = {'microsoft yahei': '微软雅黑', '微软雅黑': '微软雅黑'}
        normalize = lambda s: aliases.get(s.casefold(), s.casefold())
        if normalize(actual.value) != normalize(family):
            raise LayoutError('缺少指定字体：' + family + '；系统替换为 ' + actual.value)
        units = len(text.encode('utf-16-le')) // 2
        if units:
            glyphs = (W.WORD * units)()
            status = gdi.GetGlyphIndicesW(dc, text, units, glyphs, 1)
            if status == 0xffffffff or 0xffff in glyphs:
                raise LayoutError('指定字体缺少文字中的字形，需换字体后测量：' + text)
        extent = SIZE()
        if not gdi.GetTextExtentPoint32W(dc, text or ' ', units or 1, ctypes.byref(extent)):
            raise LayoutError('字体尺寸测量失败')
        return (extent.cx if text else 0), extent.cy, actual.value
    finally:
        if old: gdi.SelectObject(dc, old)
        if font: gdi.DeleteObject(font)
        gdi.DeleteDC(dc)

def number(value):
    return type(value) in (int, float) and math.isfinite(value)

def fixed(value, digits):
    with localcontext() as context:
        context.prec = 40
        return format(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), 'f')

def numeric_samples(model, node):
    """Actual endpoints plus conservative digit envelopes, never write values."""
    digits = node['digits']; low = node.get('min'); high = node.get('max')
    initial = model.get('preview_initial', {}).get(node['binding']['name'], 0)
    actual = [initial] if number(initial) else [0]
    bounded = number(low) and number(high) and low < high
    if bounded:
        actual = [v for v in actual if low <= v <= high] + [low, high]
        if low <= 0 <= high: actual.append(0)
    strings = list(dict.fromkeys(fixed(v, digits) for v in actual))
    integer_digits = max(len(s.lstrip('-').split('.')[0]) for s in strings)
    signed = low < 0 if bounded else any(v < 0 for v in actual)
    # These envelopes may exceed the variable's range. They bound glyph width
    # only, and are never added to preview initials, bindings or native scripts.
    envelopes = [('-' if signed else '') + d * integer_digits + ('.' + d * digits if digits else '') for d in '0123456789']
    return strings, envelopes, integer_digits, signed, bounded

def requirement(model, node):
    font = node['font']; profile, margins = options(model, node)
    sample = lambda text: measure(text, font['family'], font['size_px'], font['weight'])
    warnings = []
    if node['kind'] == 'label':
        strings = [node['text']]; envelopes = []
        measurements = [sample(s) for s in strings]
        width = max(m[0] for m in measurements)
    else:
        strings, envelopes, integer_digits, signed, bounded = numeric_samples(model, node)
        measurements = [sample(s) for s in strings + envelopes]
        digit_advance = max(sample(d)[0] for d in '0123456789')
        envelope_width = (integer_digits + node['digits']) * digit_advance
        if node['digits']: envelope_width += sample('.')[0]
        if signed: envelope_width += sample('-')[0]
        width = max(envelope_width, *(m[0] for m in measurements))
        if not bounded: warnings.append('未声明数值范围，只核对初值；动态宽度覆盖未完成')
    height = max(m[1] for m in measurements)
    calibrated = (font['family'] in ('微软雅黑', 'Microsoft YaHei') and [font['size_px'],font['weight']] in EVIDENCE['tested_size_weight_pairs'])
    if not calibrated: warnings.append('字体或字号超出本轮原厂样本；实测有效，MCGS显示待验')
    return {'profile': profile, 'required_size': [width + margins['width_extra'], height + margins['height_extra']],
            'gdi_extent': [width, height], 'actual_face': measurements[0][2],
            'samples': strings, 'width_envelopes': envelopes, 'warnings': warnings,
            'native_evidence_scope': 'tested_sample_profile' if calibrated else 'unverified_font_or_size'}

def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]

def overlaps(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])

def grow_rect(rect, width, height):
    # Preserve the centre to within half a design pixel; no shrinking.
    w = max(rect[2] - rect[0], width); h = max(rect[3] - rect[1], height)
    left = math.floor((rect[0] + rect[2] - w) / 2)
    top = math.floor((rect[1] + rect[3] - h) / 2)
    return [left, top, left + w, top + h]

def layout_model(model, policy='check', component_ids=None):
    if policy not in ('check', 'grow'): raise LayoutError('文字尺寸策略支持check/grow')
    result = copy.deepcopy(model); old = {n['id']: n['rect'][:] for n in model['components']}
    ids = None if component_ids is None else set(component_ids)
    rows = []; errors = []; changes = []; checked = set()
    def error(ident, code, message, **extra):
        errors.append({'id': ident, 'code': code, 'message': message, **extra})
    for node in result['components']:
        if node['kind'] not in KINDS or ids is not None and node['id'] not in ids: continue
        ident = node['id']; checked.add(ident)
        try:
            req = requirement(model, node)
        except (LayoutError, OSError, KeyError, TypeError, ValueError) as exc:
            error(ident, 'measurement_unavailable', str(exc)); continue
        rect = node['rect']; w, h = req['required_size']
        small = rect[2] - rect[0] < w or rect[3] - rect[1] < h
        row = {'id': ident, 'kind': node['kind'], 'rect_before': rect[:], **req}
        if small and policy == 'check':
            error(ident, 'text_box_too_small', f'需要至少 {w}×{h}，当前 {rect[2]-rect[0]}×{rect[3]-rect[1]}；请应用文字适配或调整布局')
        if small and policy == 'grow':
            node['rect'] = grow_rect(rect, w, h)
            changes.append({'id': ident, 'before': rect[:], 'after': node['rect'][:]})
        row['rect_after'] = node['rect'][:]; rows.append(row)
        if not contains([0, 0, model['width'], model['height']], node['rect']):
            error(ident, 'canvas_overflow', '文字扩框超出画布；需移动控件或调整布局', rect=node['rect'])
    changed_ids = {c['id'] for c in changes}
    # Only newly introduced collisions block automatic expansion. Existing
    # intentional overlays are not reinterpreted as business-layout errors.
    for i, node in enumerate(result['components']):
        for other in result['components'][i+1:]:
            if not ({node['id'], other['id']} & changed_ids): continue
            if not overlaps(node['rect'], other['rect']): continue
            if node['kind'] == 'picture' or other['kind'] == 'picture':
                picture, text = (node, other) if node['kind'] == 'picture' else (other, node)
                if text['kind'] not in KINDS: continue
                if contains(old[picture['id']], old[text['id']]) and not contains(picture['rect'], text['rect']):
                    error(text['id'], 'container_escape', '扩框超出原来承载文字的底图', other_id=picture['id'])
                continue
            if not overlaps(old[node['id']], old[other['id']]):
                error(node['id'], 'new_collision', '文字扩框与邻近控件重叠；请调整布局', other_id=other['id'])
    existing_overlaps=[]
    peers=[n for n in model['components'] if n.get('font')]
    for i,node in enumerate(peers):
        for other in peers[i+1:]:
            if (node['id'] in checked or other['id'] in checked) and overlaps(node['rect'],other['rect']):
                existing_overlaps.append({'id':node['id'],'other_id':other['id'],'code':'existing_text_overlap','message':'原布局已有文字控件重叠，需结合实际内容判断；未自动移动'})
    report = {'schema': REVISION, 'policy': policy, 'status': 'fail' if errors else 'pass',
              'profile_default': model.get('text_layout', {}).get('profile', DEFAULT_PROFILE),
              'checked': len(checked), 'changed': changes, 'errors': errors, 'items': rows,
              'existing_overlap_warnings': existing_overlaps,
              'evidence': EVIDENCE, 'not_covered_kinds': sorted({n['kind'] for n in model['components'] if n.get('font') and n['kind'] not in KINDS}),
              'native_application_for_this_model': 'not_run'}
    result['text_layout_report'] = report
    return result, report

def require_fit(model, component_ids=None):
    _, report = layout_model(model, 'check', component_ids)
    if report['errors']:
        raise LayoutError('文字尺寸检查未通过：' + '；'.join(e['id'] + '：' + e['message'] for e in report['errors'][:4]))
    return report
