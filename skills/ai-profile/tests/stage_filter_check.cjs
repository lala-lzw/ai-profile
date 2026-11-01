// Exercise generated viewer behavior without a browser or changing source cells.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class CanvasContext {
  constructor() { this.paths = []; this.texts = []; this.path = []; }
  clearRect() { this.paths = []; this.texts = []; }
  beginPath() { this.path = []; }
  moveTo(x, y) { this.path.push(['move', x, y]); }
  lineTo(x, y) { this.path.push(['line', x, y]); }
  stroke() { this.paths.push({ color: this.strokeStyle, points: this.path.slice() }); }
  fillText(text) { this.texts.push(String(text)); }
  setTransform() {} rect() {} clip() {} save() {} restore() {}
  setLineDash() {} fillRect() {} arc() {} fill() {}
}
class Element {
  constructor(tag = 'div') {
    Object.assign(this, { tag, children: [], style: {}, dataset: {}, attrs: {}, listeners: {},
      value: '', checked: false, textContent: '', clientWidth: 1000, clientHeight: 274,
      offsetWidth: 400, offsetHeight: 180,
      classList: { toggle() {}, add() {}, remove() {} } });
    this.context = new CanvasContext();
  }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  setAttribute(name, value) { this.attrs[name] = value; }
  click() { if (!this.disabled) this.listeners.click?.({}); }
  getContext() { return this.context; }
  setPointerCapture() {} hasPointerCapture() { return false; }
  scrollIntoView() {}
}

const elements = new Map();
const windowListeners = new Map();
const context = vm.createContext({
  console, Blob, URL, Uint8Array, atob,
  document: {
    body: new Element(),
    getElementById(id) {
      assert.ok(!['fps-rows', 'fps-status'].includes(id), 'FPS details must remain removed');
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement: tag => new Element(tag),
    createTextNode: text => ({ textContent: text }),
    querySelectorAll: () => [],
  },
  window: { devicePixelRatio: 1, innerWidth: 1200, innerHeight: 900,
    addEventListener(name, handler) { windowListeners.set(name, handler); } },
  ResizeObserver: class { observe() {} },
  requestAnimationFrame: callback => callback(),
  setTimeout() {},
});
const html = fs.readFileSync(process.argv[2], 'utf8');
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
const run = code => vm.runInContext(code, context);
const valuesBefore = run('JSON.stringify(report.rawColumns)');
const sourceBefore = run('report.sourceBase64');

assert.equal(run('stages.length'), 3);
assert.equal(run('activeIndices.length'), 8);
assert.equal(elements.get('stage-checks').children.length, 4);
assert.equal(run('stageTitle(stages[0])'), '未打标 / 准备');
assert.equal(run('formatElapsed(61.25)'), '01:01.3');
assert.equal(run('formatElapsed(59.99)'), '01:00.0');
assert.equal(run('elapsedAtLine(5)'), .6);
assert.equal(run('lineAtElapsed(.6)'), 5);
assert.ok(run('views[0].canvas.context.texts.some(text=>text.includes(":"))'));
assert.ok(run('views[0].canvas.context.texts.every(text=>!/^L[0-9]+$/.test(text))'));

// Zooming through actual pointer handlers must always have a visible way back.
assert.ok(run('views.length > 1'), 'exercise navigation shared by multiple charts');
assert.equal(run('rangeControls.length'), run('views.length + 1'));
assert.equal(run('rangeControls.every(({back,reset})=>back.disabled&&reset.disabled)'), true);
const canvas = run('views[0].canvas');
canvas.listeners.pointerdown({button: 0, offsetX: 260, pointerId: 1});
canvas.listeners.pointerup({offsetX: 860, pointerId: 1});
assert.deepEqual(Array.from(run('range')), [3, 8], 'pointerup must use the final position even without a pointermove');
assert.equal(elements.get('range-start').value, .2);
assert.equal(elements.get('range-end').value, 1.2);
assert.equal(run('rangeControls.every(({back,reset})=>!back.disabled&&!reset.disabled)'), true);
canvas.listeners.pointerdown({button: 0, offsetX: 812, pointerId: 1});
canvas.listeners.pointerup({offsetX: 308, pointerId: 1});
assert.deepEqual(Array.from(run('range')), [4, 7], 'reverse drag must also be reversible');
elements.get('previous-range').click();
assert.deepEqual(Array.from(run('range')), [3, 8]);
run('rangeControls.at(-1).back.click()');
assert.deepEqual(Array.from(run('range')), [2, 9], 'a different chart can restore the original view');
assert.equal(run('rangeControls.every(({back,reset})=>back.disabled&&reset.disabled)'), true);

canvas.listeners.pointerdown({button: 0, offsetX: 380, pointerId: 1});
canvas.listeners.pointerup({offsetX: 380, pointerId: 1});
assert.equal(run('times[selectedIndex]'), 4);
assert.deepEqual(Array.from(run('range')), [2, 9], 'clicking a point must not zoom');
canvas.listeners.pointerdown({button: 0, offsetX: 260, pointerId: 1});
canvas.listeners.pointercancel();
assert.equal(run('rangeHistory.length'), 0, 'cancelled drags must not change history');

elements.get('range-start').value = .6;
elements.get('range-end').value = .6;
elements.get('range-form').listeners.submit({preventDefault(){}});
assert.deepEqual(Array.from(run('range')), [5, 5]);
run('setRange(5,5);setRange(7,4);setRange(NaN,8)');
assert.equal(run('rangeHistory.length'), 1, 'unchanged or invalid ranges must not add undo steps');
const escape = {key: 'Escape', preventDefault(){ this.prevented = true; }};
windowListeners.get('keydown')({...escape, target: {closest: () => ({})}});
assert.deepEqual(Array.from(run('range')), [5, 5], 'Esc must leave an active input alone');
windowListeners.get('keydown')(escape);
assert.equal(escape.prevented, true);
assert.deepEqual(Array.from(run('range')), [2, 9], 'Esc must recover even from a single sample');
assert.equal(elements.get('range-error').textContent, '');
windowListeners.get('keydown')({key: 'Escape', preventDefault(){ assert.fail('no history to undo'); }});

run('setRange(4,6);rangeControls.at(-1).reset.click()');
assert.deepEqual(Array.from(run('range')), [2, 9]);
elements.get('previous-range').click();
assert.deepEqual(Array.from(run('range')), [4, 6], 'restoring full range can itself be undone');
canvas.listeners.dblclick();
assert.deepEqual(Array.from(run('range')), [2, 9]);

// One-click removal of prep samples also removes the prep FPS peak and flags.
elements.get('stage-marked').click();
assert.equal(run('rangeHistory.length'), 0, 'stage changes must discard ranges from the old filter');
assert.equal(elements.get('previous-range').disabled, true);
assert.equal(run('activeIndices.length'), 5);
assert.deepEqual(Array.from(run('range')), [5, 9]);
assert.equal(elements.get('range-start').value,.6);
assert.equal(elements.get('range-end').value,1.4);
assert.equal(run('selectedFpsSamples().length'), 4);
assert.equal(run('stageAtTime(3.5)'), 1, 'FPS must use real marker time, not configured row period');
assert.equal(elements.get('fps-value').textContent, '60');
assert.equal(elements.get('audit-rows').children.length, 0);
assert.ok(run('views[0].canvas.context.texts.includes("52.5")'), 'prep spike must not set GPU axis scale');
assert.ok(elements.get('fps-chart').context.texts.includes('66.0'), 'prep spike must not set FPS scale');
assert.equal(run('allStagesInput.indeterminate'), true);
assert.equal(run('stageInputs.get(stages[0].id).every(input=>!input.checked)'), true);

// Selecting two nonadjacent stages must break lines across the excluded stage.
run('setStageSelection([stages[0].id, stages[2].id])');
assert.equal(run('activeIndices.length'), 6);
const gpuPath = run('views[0].canvas.context.paths.find(path=>path.color==="#137f83")');
assert.equal(gpuPath.points.filter(point => point[0] === 'move').length, 2);
assert.equal(gpuPath.points.filter(point => point[0] === 'line').length, 4);
const fpsPath = elements.get('fps-chart').context.paths.find(path => path.color === '#137f83');
assert.equal(fpsPath.points.filter(point => point[0] === 'move').length, 2);
run('selectLine(4)');
elements.get('next-row').click();
assert.equal(run('times[selectedIndex]'), 7, 'sample navigation must skip unchecked stages');
assert.equal(run('nearestLine(5)'), 4, 'hover must not show excluded samples');

// A single checked stage narrows both plots, while range zoom keeps stage checks.
run('setStageSelection([stages[1].id])');
assert.equal(run('activeIndices.length'), 2);
assert.equal(run('selectedFpsSamples().length'), 2);
assert.equal(elements.get('fps-value').textContent, '40');
run('setRange(5,5)');
assert.equal(run('activeIndices.length'), 1);
elements.get('previous-range').click();
assert.deepEqual(Array.from(run('range')), [5, 6]);
assert.equal(run('selectedStages.size'), 1, 'undo must keep the current label filter');
run('setRange(5,5)');
run('resetRange()');
assert.equal(run('activeIndices.length'), 2);
elements.get('range-start').value=.8;
elements.get('range-end').value=.8;
elements.get('range-form').listeners.submit({preventDefault(){}});
assert.equal(run('activeIndices.length'),1);
assert.equal(run('times[activeIndices[0]]'),6);
run('resetRange()');

elements.get('stage-none').click();
assert.equal(run('activeIndices.length'), 0);
assert.equal(run('selectedIndex'), -1);
assert.equal(elements.get('fps-value').textContent, '—');
assert.equal(elements.get('source-row').value, '');
assert.equal(elements.get('next-row').disabled, true);
assert.equal(run('nearestLine(5)'), null);

run('allStagesInput.checked=true;allStagesInput.listeners.change()');
assert.equal(run('activeIndices.length'), 8);
assert.equal(run('selectedFpsSamples().length'), 6);
assert.equal(run('allStagesInput.indeterminate'), false);
assert.equal(run('JSON.stringify(report.rawColumns)'), valuesBefore);
assert.equal(run('report.sourceBase64'), sourceBefore);
console.log('Stage filtering passed: reversible pointer zoom, nested history, single sample recovery, Esc, reset, multiselect, prep exclusion, FPS time alignment, gap rendering, axes, navigation, empty selection and unchanged source data.');
