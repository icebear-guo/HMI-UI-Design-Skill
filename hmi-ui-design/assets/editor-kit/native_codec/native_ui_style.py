"""Verified Pro codecs for button caption mirrors and transparent numeric input.

Memory only. These functions do not compile, run or write an MCP database.
"""
import copy
import re
import struct
import native_support
from mcs_button_control import ButtonArchive
from mcs_input_text import InputRecord
from 原生界面样式 import CommonEnvelope, set_font, fonts


def colorref(rgb):
    if not isinstance(rgb, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', rgb):
        raise ValueError('Expected #RRGGBB')
    return int.from_bytes(bytes.fromhex(rgb[1:]) + b'\0', 'little')


def button_summary(record):
    a = ButtonArchive.parse(record)
    p = a.metadata.properties
    return {'s0': {'caption': p.caption.value, 'colorref': p.words[5], 'alignment': p.words[12:14], 'fonts': fonts(p.font)},
            's1': {'caption': a.caption.value, 'colorref': a.caption_words[1], 'alignment': a.alignment, 'fonts': fonts(a.font)},
            'press_script': p.press_script.value, 'release_script': a.release_script.value}


def style_button(record, states):
    if set(states) != {'s0', 's1'}:
        raise ValueError('Provide explicit styles for both button states')
    a = ButtonArchive.parse(record)
    p = a.metadata.properties
    # This helper edits text only; image gates, same-property policy and actions
    # belong to the caller's complete factory plan and are not silently changed.
    for state, style in states.items():
        if set(style) != {'caption', 'font', 'color', 'horizontal', 'vertical'}:
            raise ValueError('Button style needs caption/font/color/horizontal/vertical; unknown fields refused')
        if style['horizontal'] not in ('left', 'center') or style['vertical'] not in ('top', 'center'):
            raise ValueError('Only native left/center and top/center alignment enums are calibrated')
        font = style['font']
        if set(font) != {'family', 'size_px', 'weight'}:
            raise ValueError('Font requires family/size_px/weight')
        align = [0 if style['horizontal'] == 'left' else 1, 0 if style['vertical'] == 'top' else 1]
        kwargs = dict(height=font['size_px'], family=font['family'], weight=font['weight'])
        if state == 's0':
            p.caption.value = style['caption']
            p.words[5] = colorref(style['color'])
            p.words[12:14] = align
            p.font = set_font(p.font, **kwargs)
        else:
            a.caption.value = style['caption']
            a.caption_words[1] = colorref(style['color'])
            a.alignment = align
            a.font = set_font(a.font, **kwargs)
    result = a.to_record()
    if ButtonArchive.parse(result).to_bytes() != result.payload:
        raise ValueError('Button style roundtrip failed')
    actual = button_summary(result)
    for state, style in states.items():
        summary = actual[state]
        if summary['caption'] != style['caption'] or summary['colorref'] != colorref(style['color']):
            raise ValueError('Button caption/color mirror readback failed')
        if not all(f['family'] == style['font']['family'] and f['height_raw'] == -style['font']['size_px'] and
                   f['weight'] == style['font']['weight'] for f in summary['fonts']):
            raise ValueError('Button font readback failed')
    return result


def transparent_input(record, font, alignment='center'):
    if alignment != 'center':
        raise ValueError('Transparent input helper currently calibrates center alignment only')
    if set(font) != {'family', 'size_px', 'weight', 'color'}:
        raise ValueError('Font requires family/size_px/weight/color; unknown fields refused')
    a = InputRecord.parse(record)
    a.properties[0] = colorref(font['color'])
    a.properties[2] = 0
    a.properties[3] = 1
    a.disable_images()
    a.font = set_font(a.font, height=font['size_px'], family=font['family'], weight=font['weight'])
    result = copy.deepcopy(record)
    result.payload = a.to_bytes()
    env = CommonEnvelope.parse(result)
    prefix = bytearray(a.common.before_name)
    struct.pack_into('<H', prefix, env.pen_offset, 0)
    struct.pack_into('<H', prefix, env.brush_offset, 0)
    a.common.before_name = bytes(prefix)
    result.payload = a.to_bytes()
    b = InputRecord.parse(result)
    env = CommonEnvelope.parse(result)
    if (b.properties[0] != colorref(font['color']) or b.properties[2:4] != [0, 1] or
            struct.unpack_from('<H', env.prefix, env.pen_offset)[0] or
            struct.unpack_from('<H', env.prefix, env.brush_offset)[0]):
        raise ValueError('Transparent input primary style readback failed')
    if b.to_bytes() != result.payload:
        raise ValueError('Transparent input roundtrip failed')
    return result


def bind_local_momentary(record, variable, press_value=1, release_value=0):
    """Explicit local HMI request only. No invented PLC interlocks or feedback."""
    if not isinstance(variable, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,31}', variable):
        raise ValueError('A resolved local variable name is required')
    if type(press_value) not in (int, float) or type(release_value) not in (int, float):
        raise ValueError('Momentary values must be numeric')
    if not all(__import__('math').isfinite(v) for v in (press_value,release_value)):
        raise ValueError('Non-finite command value')
    a = ButtonArchive.parse(record)
    p = a.metadata.properties
    p.clear_actions()
    a.action_texts.clear_values()
    a.action_ids.clear_values(0xffffffff)
    a.action_modes.clear_values(0)
    p.press_script.value = f'{variable} = {press_value:g}'
    a.release_script.value = f'{variable} = {release_value:g}'
    p.press_compiled.value = b''
    a.release_compiled.value = b''
    result = a.to_record()
    if ButtonArchive.parse(result).to_bytes() != result.payload:
        raise ValueError('Momentary source script roundtrip failed')
    return result
