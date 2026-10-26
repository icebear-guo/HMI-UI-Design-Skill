#!/usr/bin/env node
'use strict';
// Pure code simulation. No browser, rendering engine, network, or native UI is used.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class FakeElement {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.style = {}; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(x => typeof x === 'string' ? x : x.textContent).join(''); }
  append(...items) { for (const item of items) { if (typeof item !== 'string') item.parent = this; this.children.push(item); } }
  replaceChildren(...items) { for (const c of this.children) if (typeof c !== 'string') c.parent = null; this.children = []; this._text = ''; this.append(...items); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  setPointerCapture(id) { this.capturedPointer = id; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(c => c !== this); this.parent = null; } }
  focus() { FakeElement.active = this; }
  select() { this.selected = true; }
  get isConnected() { return this.tag === 'body' || Boolean(this.parent?.isConnected); }
}
function all(node) { return [node, ...node.children.flatMap(x => typeof x === 'string' ? [] : all(x))]; }
function classHas(node, value) { return (node.className || '').split(/\s+/).includes(value); }
function scripts(html) {
  return [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)].map(m => ({attributes: m[1], body: m[2]}));
}
function splitHtml(html) {
  const blocks = scripts(html);
  assert.equal(blocks.length, 2, 'Expected one JSON block and one behavior script');
  const data = blocks.filter(b => /\bid\s*=\s*["']design-data["']/i.test(b.attributes));
  assert.equal(data.length, 1, 'Missing or duplicate design-data block');
  assert.match(data[0].attributes, /\btype\s*=\s*["']application\/json["']/i);
  const behavior = blocks.find(b => b !== data[0]);
  assert.equal(behavior.attributes.trim(), '', 'External or attributed behavior scripts are not accepted');
  return {data: data[0].body, behavior: behavior.body.replace(/\r\n/g, '\n')};
}

function inspect(file) {
  const checks = [];
  function check(name, task, detail = '') {
    try { task(); checks.push({name, status: 'pass', detail}); }
    catch (error) { checks.push({name, status: 'fail', detail: error.message}); }
  }
  function notApplicable(name, detail) { checks.push({name, status: 'not_applicable', detail}); }
  try {
    const template = splitHtml(fs.readFileSync(path.join(__dirname, '../assets/delivery-viewer.template.html'), 'utf8'));
    const packed = splitHtml(fs.readFileSync(path.resolve(file), 'utf8'));
    // Compare first. A package must never supply arbitrary code to this simulator.
    assert.equal(packed.behavior, template.behavior, 'Behavior script differs from maintained template');
    checks.push({name: 'trusted_behavior_script', status: 'pass', detail: 'Exact match; only maintained script is executed'});
    const model = JSON.parse(packed.data);
    assert.ok(Array.isArray(model.pages) && model.pages.length, 'No pages to simulate');
    assert.ok(Array.isArray(model.assets) && Array.isArray(model.fonts), 'Invalid resource arrays');
    const nodes = Object.fromEntries(['navigation', 'main', 'inspector', 'design-data', 'runtime-tab', 'page-tab', 'asset-tab', 'font-tab']
      .map(id => [id, new FakeElement(id === 'design-data' ? 'script' : 'div')]));
    nodes['design-data'].textContent = JSON.stringify(model);
    const body = new FakeElement('body'); body.append(...Object.values(nodes));
    const documentEvents = {}, windowEvents = {}, timers = new Map(); let timerId = 0;
    const document = {body, hidden: false, get activeElement() { return FakeElement.active; },
      addEventListener: (event, fn) => { documentEvents[event] = fn; },
      getElementById: id => { assert.ok(nodes[id], 'Unexpected element id'); return nodes[id]; }, createElement: tag => new FakeElement(tag)};
    function Option(label, value) { const option = new FakeElement('option'); option.textContent = label; option.value = value; return option; }
    const context = vm.createContext({document, Option, window: {addEventListener: (event, fn) => { windowEvents[event] = fn; }},
      setInterval: fn => { timers.set(++timerId, fn); return timerId; }, clearInterval: id => timers.delete(id)},
      {codeGeneration: {strings: false, wasm: false}});
    const run = code => vm.runInContext(code, context, {timeout: 2000});
    const invoke = (target, eventName, event = {}) => {
      assert.equal(typeof target[eventName], 'function', `Missing ${eventName} handler`);
      context.__target = target; context.__eventName = eventName; context.__event = event;
      try { run('__target[__eventName](__event)'); }
      finally { delete context.__target; delete context.__eventName; delete context.__event; }
    };
    const stage = () => all(nodes.main).find(n => classHas(n, 'stage'));
    const menu = () => all(nodes.main).find(n => n.attributes['aria-label'] === '选择图层');
    const range = () => all(nodes.main).find(n => n.attributes['aria-label'] === '画面缩放');
    const overlays = () => stage().children.filter(n => classHas(n, 'layer'));
    const navigate = index => invoke(nodes.navigation.children[index], 'onclick');
    run(template.behavior);
    if (model.simulation) check('prototype_is_default', () => {
      assert.ok(all(nodes.main).find(n => classHas(n, 'runtime-stage')), 'New delivery should open in interactive mode');
    });
    invoke(nodes['page-tab'], 'onclick');
    check('startup', () => {
      assert.equal(nodes.navigation.children.length, model.pages.length);
      assert.equal(stage().children[0].src, model.pages[0].preview);
    }, 'Template initializes the mock document');
    if (model.pages.length > 1) check('multiple_page_navigation', () => {
      model.pages.forEach((page, i) => { navigate(i); assert.equal(stage().children[0].src, page.preview); });
    }, `${model.pages.length} supplied pages`);
    else notApplicable('multiple_page_navigation', 'Package contains one page');

    check('zoom_and_logical_rectangles', () => {
      for (let i = 0; i < model.pages.length; i++) {
        navigate(i);
        const page = model.pages[i];
        for (const percentage of [25, 100, 200]) {
          range().value = String(percentage); invoke(range(), 'oninput');
          const scale = percentage / 100;
          assert.equal(stage().style.width, page.design_size_px[0] * scale + 'px');
          assert.equal(stage().style.height, page.design_size_px[1] * scale + 'px');
          const expected = page.layers.map(layer => [layer.name, ...layer.rect_px.map(v => v * scale + 'px')]);
          const actual = overlays().map(n => [n.title, n.style.left, n.style.top, n.style.width, n.style.height]);
          assert.deepEqual(actual.map(JSON.stringify).sort(), expected.map(JSON.stringify).sort());
        }
      }
    }, '25%, 100%, 200%; style values only, no CSS layout/render test');

    check('layer_selection_and_attributes', () => {
      for (let i = 0; i < model.pages.length; i++) {
        navigate(i);
        for (const layer of model.pages[i].layers) {
          menu().value = layer.id; invoke(menu(), 'onchange');
          assert.ok(nodes.inspector.textContent.includes(layer.id + ' / ' + layer.type));
          assert.ok(nodes.inspector.textContent.includes(layer.rect_px.join(', ')));
          assert.equal(overlays().filter(n => classHas(n, 'selected')).length, 1);
        }
        const first = overlays()[0];
        invoke(first, 'onclick');
        assert.ok(nodes.inspector.textContent.includes(first.title));
      }
    }, 'Dropdown selection and overlay click handlers');

    check('original_preview_preserved', () => {
      for (let i = 0; i < model.pages.length; i++) {
        navigate(i);
        const images = all(stage()).filter(n => n.tag === 'img');
        assert.equal(images.length, 1, 'State assets must not cover the page preview');
        assert.equal(images[0].src, model.pages[i].preview);
      }
    }, 'Mock element tree contains only the original page image');

    const expectedPlates = (pageId, layerId) => { if (model.element_inventory) { const e = model.element_inventory.elements.find(e => e.page_id === pageId && e.layer_id === layerId && e.asset_role === 'control_plate' && e.delivery_mode === 'export'); return e ? e.asset_refs.map(r => model.assets.find(a => a.id === r.asset_id)) : []; } return model.assets.filter(a => a.component_id === layerId && (a.asset_role || 'control_plate') === 'control_plate'); };
    const buttons = model.pages.flatMap((page, pageIndex) => page.layers
      .filter(l => ['button', 'control'].includes(l.type.toLowerCase())).map(layer => ({pageIndex, layer})));
    if (buttons.length) check('button_pointer_and_keyboard_feedback', () => {
      for (const {pageIndex, layer} of buttons) {
        navigate(pageIndex); menu().value = layer.id; invoke(menu(), 'onchange');
        const preview = all(nodes.inspector).find(n => n.attributes['aria-label'] === '按住预览按钮交互反馈');
        assert.ok(preview, `No state preview for ${layer.id}`);
        const face = all(preview).find(n => n.tag === 'img');
        const states = expectedPlates(model.pages[pageIndex].id, layer.id);
        const s0 = states.find(a => a.state.toLowerCase() === 's0');
        const s1 = states.find(a => a.state.toLowerCase() === 's1');
        assert.ok(s0 && s1, 'Missing s0/s1 pair'); assert.equal(face.src, s0.file);
        for (const reset of ['onpointerup', 'onpointercancel', 'onlostpointercapture']) {
          invoke(preview, 'onpointerdown', {pointerId: 7}); assert.equal(face.src, s1.file);
          assert.equal(preview.capturedPointer, 7);
          invoke(preview, reset); assert.equal(face.src, s0.file);
        }
        for (const key of [' ', 'Enter']) {
          let prevented = false;
          invoke(preview, 'onkeydown', {key, preventDefault() { prevented = true; }});
          assert.equal(face.src, s1.file); assert.ok(prevented);
          invoke(preview, 'onkeyup'); assert.equal(face.src, s0.file);
        }
        invoke(preview, 'onpointerdown', {pointerId: 8});
        invoke(preview, 'onblur'); assert.equal(face.src, s0.file);
      }
    }, `${buttons.length} button instances; events are simulated, not browser input`);
    else notApplicable('button_pointer_and_keyboard_feedback', 'No button/control layers supplied');

    check('asset_panel', () => {
      invoke(nodes['asset-tab'], 'onclick');
      assert.equal(all(nodes.main).filter(n => classHas(n, 'card')).length, model.assets.length);
      const files = all(nodes.main).filter(n => n.tag === 'a').map(n => n.href).sort();
      assert.deepEqual(files, model.assets.map(a => a.file).sort());
    }, 'Card count and resource link binding; no file download');
    if (model.fonts.length) check('font_resource_panel', () => {
      invoke(nodes['font-tab'], 'onclick');
      assert.deepEqual(all(nodes.main).filter(n => n.tag === 'a').map(n => n.href).sort(), model.fonts.map(f => f.file).sort());
    }, `${model.fonts.length} declared resources; no font loading/rendering`);
    else {
      notApplicable('font_resource_panel', 'No font resources supplied');
      check('font_absence_notice', () => {
        invoke(nodes['font-tab'], 'onclick'); assert.ok(nodes.main.textContent.includes('未提供'));
      }, 'Missing fonts are disclosed');
    }
    check('return_to_pages', () => {
      invoke(nodes['page-tab'], 'onclick'); assert.ok(stage());
      assert.equal(nodes.navigation.children.length, model.pages.length);
    }, 'Page tab restores the mock page tree');
    if (!model.simulation) notApplicable('functional_prototype', 'Legacy annotation-only package; does not meet current full UI delivery');
    else {
      const role = (name, root = nodes.main) => all(root).find(n => n.attributes['data-role'] === name);
      const component = id => all(nodes.main).find(n => n.attributes['data-component'] === id);
      const wrapper = id => all(nodes.main).find(n => n.attributes['data-layer'] === id);
      const driver = id => all(nodes.inspector).find(n => n.attributes['data-variable'] === id);
      const read = id => run(`effective(${JSON.stringify(id)})`);
      const go = i => { invoke(nodes['runtime-tab'], 'onclick'); invoke(nodes.navigation.children[i], 'onclick'); };
      const reset = () => invoke(role('reset'), 'onclick');
      const keyEvent = key => ({key, preventDefault() {}});
      const instances = model.pages.flatMap((p, i) => p.layers.filter(l => l.interaction).map(l => ({i, l})));
      for (const {i, l} of instances) check('prototype_' + model.pages[i].id + '_' + l.id, () => {
        go(i); reset(); const it = l.interaction, d = model.simulation.variables.find(v => v.id === it.variable), control = component(l.id);
        if (!['gauge', 'bar'].includes(it.kind)) {
          assert.ok(control); invoke(control, 'onpointerdown', {pointerId: 11, button: 0});
          assert.equal(control.attributes['data-state'], 's1');
          if (it.kind === 'momentary') assert.equal(read(d.id), true);
          invoke(control, 'onpointerup'); assert.equal(control.attributes['data-state'], 's0');
          const s0 = expectedPlates(model.pages[i].id, l.id).find(a => a.state === 's0');
          assert.equal(all(control).find(n => n.tag === 'img').src, s0.file);
        }
        if (it.kind === 'momentary') {
          assert.equal(read(d.id), false);
          for (const event of ['onpointercancel', 'onlostpointercapture', 'onblur']) {
            invoke(control, 'onpointerdown', {pointerId: 12}); invoke(control, event); assert.equal(read(d.id), false);
          }
          for (const key of [' ', 'Enter']) { invoke(control, 'onkeydown', keyEvent(key)); assert.equal(read(d.id), true); invoke(control, 'onkeyup', keyEvent(key)); assert.equal(read(d.id), false); }
          invoke(control, 'onpointerdown', {pointerId: 12}); windowEvents.blur(); assert.equal(read(d.id), false);
          invoke(control, 'onpointerdown', {pointerId: 12}); invoke(nodes['page-tab'], 'onclick'); assert.equal(read(d.id), false);
        } else if (['toggle', 'indicator', 'io-input'].includes(it.kind)) {
          invoke(control, 'onclick'); assert.equal(read(d.id), !d.initial);
          assert.equal(control.attributes['aria-pressed'], String(!d.initial));
          invoke(control, 'onkeydown', keyEvent('Enter')); invoke(control, 'onkeyup', keyEvent('Enter')); assert.equal(read(d.id), d.initial);
          invoke(control, 'onclick'); go(i); assert.equal(read(d.id), !d.initial, 'Bindings must persist across page changes'); reset(); assert.equal(read(d.id), d.initial);
        } else if (it.kind === 'output') {
          const select = all(wrapper(l.id)).find(n => n.tag === 'select');
          for (const mode of ['on', 'off']) { select.value = mode; invoke(select, 'onchange');
            assert.equal(read(d.id), mode === 'on'); driver(d.id).checked = mode !== 'on'; invoke(driver(d.id), 'onchange'); assert.equal(read(d.id), mode === 'on'); }
          select.value = 'auto'; invoke(select, 'onchange'); assert.equal(read(d.id), true, 'Release must follow current auto value');
          invoke(control, 'onclick'); assert.equal(select.value, 'on'); invoke(control, 'onclick'); assert.equal(select.value, 'off'); invoke(control, 'onclick'); assert.equal(select.value, 'auto');
        } else if (it.kind === 'navigation') {
          invoke(control, 'onclick'); assert.equal(all(nodes.main).find(n => classHas(n, 'runtime-stage')).attributes['data-page'], it.target_page);
          assert.ok(nodes.navigation.children.find(n => classHas(n, 'active')).textContent === model.pages.find(p => p.id === it.target_page).name);
        } else if (it.kind === 'parameter') {
          const enter = () => { invoke(control, 'onclick'); const pad = role('keypad', body); assert.ok(pad); return {pad, input: all(pad).find(n => n.attributes['aria-label'] === '参数输入'), click: title => invoke(all(pad).find(n => n.tag === 'button' && n.textContent === title), 'onclick')}; };
          let k = enter();
          for (const raw of ['', 'NaN', 'Infinity', String(d.max + d.step), String(d.min - d.step), String(d.min + d.step / 2)]) {
            k.input.value = raw; k.click('确认'); assert.ok(role('keypad', body), 'Invalid input must keep keypad open'); assert.equal(read(d.id), d.initial);
          }
          k.input.value = String(d.max); k.click('确认'); assert.equal(read(d.id), d.max); assert.equal(role('keypad', body), undefined);
          k = enter(); k.input.value = String(d.min); k.click('取消'); assert.equal(read(d.id), d.max);
          k = enter(); k.click('清空'); k.click('1'); k.click('2'); k.click('退格'); assert.equal(k.input.value, '1'); k.click('-'); assert.equal(k.input.value, '-1'); invoke(k.pad, 'onkeydown', keyEvent('Escape')); assert.equal(role('keypad', body), undefined);
          k = enter(); k.input.value = String(d.min); invoke(k.pad, 'onkeydown', keyEvent('Enter')); assert.equal(read(d.id), d.min);
        } else {
          const w = wrapper(l.id), fill = all(w).find(n => classHas(n, it.kind === 'gauge' ? 'runtime-needle' : 'runtime-fill'));
          for (const [n, ratio] of [[d.min, 0], [(d.min + d.max) / 2, .5], [d.max, 1]]) { driver(d.id).value = String(n); invoke(driver(d.id), 'oninput');
            assert.equal(w.attributes['aria-valuenow'], String(n)); assert.ok(w.textContent.includes(String(n)));
            if (it.kind === 'gauge') assert.equal(fill.style.transform, 'rotate(' + (-90 + ratio * 180) + 'deg)');
            else assert.equal(it.orientation === 'vertical' ? fill.style.height : fill.style.width, ratio * 100 + '%'); }
        }
      }, `${l.interaction.kind}; trusted DOM event handlers and binding state only`);
      check('prototype_simulation_lifecycle', () => {
        go(0); reset(); const animated = model.simulation.variables.find(v => v.animate);
        if (animated) { const initial = read(animated.id); invoke(role('play'), 'onclick'); assert.equal(timers.size, 1); for (const fn of timers.values()) fn(); assert.notEqual(read(animated.id), initial);
          invoke(nodes['asset-tab'], 'onclick'); assert.equal(timers.size, 0); go(0); invoke(role('play'), 'onclick'); document.hidden = true; documentEvents.visibilitychange(); assert.equal(timers.size, 0); document.hidden = false; }
        go(0); reset(); for (const d of model.simulation.variables) assert.equal(read(d.id), d.initial); assert.equal(role('keypad', body), undefined);
      }, 'Animation ticks, state reset, tab cleanup and hidden document cleanup; no wall-clock timer/rendering');
      check('prototype_shared_numeric_binding', () => {
        for (const d of model.simulation.variables.filter(v => v.type === 'number')) {
          go(0); driver(d.id).value = String(d.max); invoke(driver(d.id), 'oninput');
          for (let i = 0; i < model.pages.length; i++) { go(i); for (const l of model.pages[i].layers.filter(l => l.interaction?.variable === d.id)) {
            assert.ok(wrapper(l.id).textContent.includes(String(d.max)), 'Bound display must refresh after navigation');
          } }
        }
      }, 'Parameter, gauge and bars keep the same value across all supplied pages');
    }
  } catch (error) { checks.push({name: 'simulation_setup', status: 'fail', detail: error.message}); }
  return {status: checks.some(c => c.status === 'fail') ? 'fail' : 'pass', backend: 'pure-js-simulation', checks,
    browser_rendering: 'not_checked', scope: 'Offline trusted-code unit simulation only; no browser, network, CSS layout, image rendering, or native UI'};
}

if (require.main === module) {
  if (process.argv.length !== 3) {
    console.log(JSON.stringify({status: 'fail', backend: 'pure-js-simulation', checks: [], error: 'Usage: node check_viewer_logic.cjs <index.html>'}));
    process.exitCode = 1;
  } else {
    const result = inspect(process.argv[2]); console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.status === 'pass' ? 0 : 1;
  }
}
module.exports = {inspect};
