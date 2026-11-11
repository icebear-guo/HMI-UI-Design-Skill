"""Repeatable numeric adapters for the measured 3.5 native branches, memory only.

Use an independently rendered plate behind a transparent numeric core. The
supported core layout is centered with zero padding; output units are external
native labels. Refuse other layouts before editing, not after bulk production.
"""
import copy
import struct
import native_support
from mcs_window_archive import Reader, write_cstring
from mcs_input_text import InputRecord, InputMetadata, LabelRecord, unit_slot
from 原生界面样式 import CommonEnvelope, set_font, fonts
from native_ui_style import transparent_input, colorref
from native_capabilities import profile

LAYOUT = profile()['numeric_core_layout']


def preflight(c):
    issues = []
    if c.get('numeric_layout') != LAYOUT:
        issues.append('numeric core requires center/center and zero padding; position the core inside an independent layout plate')
    if c.get('appearance') != profile()['numeric_core_appearance']:
        issues.append('numeric core uses transparent fill, no native border and no native image; plate is a separate component')
    b = c.get('binding') or {}
    if c.get('native_type') == '0x5008' and b.get('unit') and b.get('unit_owner') != 'external':
        issues.append('numeric output unit requires an independent native label; internal output-unit rendering is not calibrated')
    if not c.get('font') or not {'family', 'size_px', 'weight', 'color'} <= c['font'].keys():
        issues.append('numeric font must specify family/size_px/weight/color')
    return issues


def _checked(c):
    issues = preflight(c)
    if issues:
        raise ValueError('Numeric adaptation blocked before write: ' + '; '.join(issues))


def style_summary(record):
    env = CommonEnvelope.parse(record)
    label = LabelRecord.parse(env.project_without_animations())
    return {'fonts': fonts(label.font), 'colorref': label.colour,
            'mirror_colorref': label.appearance_prefix[0], 'horizontal': label.style,
            'mirror_horizontal': label.appearance_prefix[1], 'unit': label.unit,
            'image_enabled': bool(label.appearance_suffix[3]),
            'pen_enabled': bool(struct.unpack_from('<H', env.prefix, env.pen_offset)[0]),
            'brush_enabled': bool(struct.unpack_from('<H', env.prefix, env.brush_offset)[0])}


def output(record, c):
    _checked(c)
    env = CommonEnvelope.parse(record)
    if len(env.animations) != 1 or env.animations[0]['class_name'] != 'CAniOutput':
        raise ValueError('One CAniOutput animation required')
    if env.metadata.value != bytes(12):
        raise ValueError('Numeric output event metadata outside calibrated empty-event branch')
    raw = env.prefix[env.animation_start:env.animation_end]
    r = Reader(raw)
    if r.count() != 1 or r.u16() != 0xffff or r.u16() != 0:
        raise ValueError('Unsupported output animation header')
    if r.take(r.u16()) != b'CAniOutput':
        raise ValueError('Unknown output class')
    r.take(4)
    begin = r.pos
    r.cstring()
    end = r.pos
    r.cstring(); r.cstring()
    field_pos = r.pos
    fields = [r.u32() for _ in range(4)]
    if r.pos != len(raw):
        raise ValueError('Unexpected output animation tail')
    fields[:2] = [1, int(c['binding']['decimal_places'])]
    replacement = raw[:begin] + write_cstring(c['binding']['name']) + raw[end:field_pos] + struct.pack('<4I', *fields)
    env.prefix = env.prefix[:env.animation_start] + replacement + env.prefix[env.animation_end:]
    # Reparse after the variable-length expression changes animation boundaries.
    env = CommonEnvelope.parse(env.to_record())
    projected = env.project_without_animations()
    label = LabelRecord.parse(projected)
    label.common.name = c['object_name']; label.common.set_rect(c['bounds'])
    label.unit = ''
    label.colour = label.appearance_prefix[0] = colorref(c['font']['color'])
    label.style = label.appearance_prefix[1] = 1
    label.font = set_font(label.font, height=c['font']['size_px'], family=c['font']['family'], weight=c['font']['weight'])
    label.appearance_suffix[3] = 0; label.background_picture = b''
    projected.payload = label.to_bytes()
    pe = CommonEnvelope.parse(projected); prefix = bytearray(pe.prefix)
    struct.pack_into('<H', prefix, pe.pen_offset, 0); struct.pack_into('<H', prefix, pe.brush_offset, 0)
    pe.prefix = bytes(prefix)
    result = env.restore_projected(pe.to_record())
    actual = CommonEnvelope.parse(result)
    if actual.animations[0]['expression'] != c['binding']['name'] or actual.animations[0]['fields'][:2] != fields[:2]:
        raise ValueError('Numeric output mode/binding readback failed')
    s = style_summary(result)
    if s['colorref'] != colorref(c['font']['color']) or s['mirror_colorref'] != s['colorref'] or any(s[k] for k in ('pen_enabled', 'brush_enabled', 'image_enabled')):
        raise ValueError('Numeric output appearance readback failed')
    if not all(f['family'] == c['font']['family'] and f['height_raw'] == -c['font']['size_px'] and f['weight'] == c['font']['weight'] for f in s['fonts']):
        raise ValueError('Numeric output font readback failed')
    return result


def input(record, c, variable):
    _checked(c)
    b = c['binding']
    if variable['name'] != b['name'] or variable['kind'] != 2:
        raise ValueError('Resolved numeric variable required')
    a = InputRecord.parse(record)
    a.common.name = c['object_name']; a.common.set_rect(c['bounds'])
    a.variable = b['name']; a.properties[5] = variable['id']; a.properties[6] = variable['kind']
    a.expression_cache = b''
    a.min_raw = struct.pack('<f', b['min']); a.max_raw = struct.pack('<f', b['max'])
    a.set_unit(b.get('unit') or '', bool(b.get('unit')) and b.get('unit_owner') == 'internal')
    a.set_decimal_format()
    meta = InputMetadata.parse(a.common.metadata, a.appearance)
    for primary in (True, False):
        raw = bytearray(meta.properties.value if primary else a.appearance)
        _, end, _ = unit_slot(raw, 20)
        struct.pack_into('<i', raw, end + 12, int(b['decimal_places']))
        if primary: meta.properties.value = bytes(raw)
        else: a.appearance = bytes(raw)
    meta.normalize_counts(); a.common.metadata = meta.to_bytes()
    result = copy.deepcopy(record); result.payload = a.to_bytes()
    font = {k: c['font'][k] for k in ('family', 'size_px', 'weight', 'color')}
    result = transparent_input(result, font)
    actual = InputRecord.parse(result)
    if actual.variable != b['name'] or actual.variable_id != variable['id'] or actual.variable_type != variable['kind']:
        raise ValueError('Numeric input binding readback failed')
    return result
