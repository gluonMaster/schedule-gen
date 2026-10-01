// Phase 2: actual JS conflict/export/report handlers on one compact shared case table.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const started = performance.now();
const root = path.resolve(__dirname, '..');
const table = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/rental_conflicts_cases.fixture'), 'utf8'));
const record = updates => ({ ...table.defaults, ...updates });
let blocks = [];
const elements = {};
function block(data, i = 0) {
    const attrs = {
        'data-day': data.day, 'data-building': data.building, 'data-room': data.room,
        'data-lesson-type': data.lesson_type, 'data-rental-dates': JSON.stringify(data.rental_dates),
        'data-trial-dates': JSON.stringify(data.trial_dates), 'data-col-index': String(i),
        'data-block-id': 'booking-' + i,
    };
    const minutes = t => Number(t.slice(0, 2)) * 60 + Number(t.slice(3));
    const start = minutes(data.start_time), end = minutes(data.end_time);
    if (start % 5 === 0 && end % 5 === 0 && start >= 540) {
        // As generated blocks: a 09:00 grid of 5-minute rows, from which the exporter derives payload times.
        attrs['data-start-row'] = String((start - 540) / 5);
        attrs['data-row-span'] = String((end - start) / 5);
    }
    const classes = new Set();
    return {
        attrs, lines: [data.subject, data.teacher, data.students, data.room, data.start_time + '-' + data.end_time],
        innerHTML: '', style: {}, getAttribute: k => attrs[k] ?? null,
        classList: { add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c) },
    };
}
const container = {
    getAttribute: () => 'Villa',
    querySelector: () => ({
        querySelector: () => ({ getBoundingClientRect: () => ({ height: 45 }) }),
        querySelectorAll: () => blocks.map(b => ({ innerText: b.attrs['data-day'] + ' ' + b.attrs['data-room'] })),
    }),
    querySelectorAll: () => blocks,
};
const document = {
    readyState: 'loading', addEventListener() {}, removeEventListener() {},
    createElement: () => ({ style: {}, appendChild() {} }),
    head: { appendChild: node => { elements[node.id] = node; } },
    getElementById: id => elements[id] || null,
    querySelectorAll: selector => selector === '.activity-block' ? blocks : selector === '.schedule-container' ? [container] : [],
};
class LocalDate extends Date {
    constructor(...args) { super(...(args.length ? args : [table.calculation_date + 'T12:00:00'])); }
}
const context = vm.createContext({
    document, console: { log() {}, warn() {}, error() {} }, Date: LocalDate,
    setTimeout() {}, clearTimeout() {},
    getComputedStyle: b => ({ display: b.style.display || 'block', backgroundColor: '#abcdef' }),
    readBlockContentLines: b => b.lines,
});
context.window = context;
function load(relative) {
    vm.runInContext(fs.readFileSync(path.join(root, 'gear_xls', relative), 'utf8'), context, { filename: relative });
}
load('js_modules/column_helpers.js');
load('js_modules/block_utils.js');
load('js_modules/conflict_detector.js');
const integrationOnly = process.argv.includes('--integration-only');
if (!integrationOnly) {
for (const item of table.cases) {
    const records = [record(item.first), record(item.second)];
    const fromRecords = context.ConflictDetector.findConflicts(records, table.calculation_date);
    assert.equal(fromRecords[0]?.type ?? null, item.conflict, item.name + ': snapshot');
    // Exercise JSON metadata payloads too, with no arrays available.
    const serialized = records.map(r => {
        const result = { ...r, rental_dates_json: JSON.stringify(r.rental_dates), trial_dates_json: JSON.stringify(r.trial_dates) };
        delete result.rental_dates; delete result.trial_dates;
        return result;
    });
    assert.equal(context.ConflictDetector.findConflicts(serialized, table.calculation_date)[0]?.type ?? null, item.conflict, item.name + ': JSON dates');
    blocks = records.map(block);
    const fromDom = context.ConflictDetector.findConflicts(undefined, table.calculation_date);
    assert.equal(fromDom[0]?.type ?? null, item.conflict, item.name + ': DOM');
    context.ConflictDetector.highlightConflicts();
    assert.equal(blocks[0].classList.contains('conflict-block'), !!item.conflict, item.name + ': highlight');
}
// Highlighting follows visible blocks; snapshot validation always includes hidden rows.
blocks = [block(record(), 0), block(record(), 1)];
blocks[1].style.display = 'none';
assert.equal(context.ConflictDetector.hasConflicts(), false);
}
load('js_modules/export_to_excel.js');
// schedule.html runs all modules in one closure where block_utils' minutesToTime ({hour, minute}) is declared
// after the exporter's, so real payload times are objects; reproduce that order for the export checks below.
load('js_modules/block_utils.js');
if (!integrationOnly) {
assert.equal(JSON.stringify(context.collectScheduleData()[0].start_time), '{"hour":10,"minute":0}');
assert.equal(context.collectScheduleData().length, 1);
assert.equal(context.collectScheduleData({ includeHidden: true }).length, 2);
assert.equal(context.ConflictDetector.hasConflicts(context.collectScheduleData({ includeHidden: true })), true);
}

async function exportScenario(initial, refreshed, proceed, refreshFailure = '') {
    blocks = initial;
    const posts = [];
    let prompts = 0, done = 0, alerts = 0;
    context.alert = () => alerts++;
    context.confirm = message => { prompts++; assert(message.includes('Vermietung')); return proceed; };
    context.checkServerAvailability = callback => callback(true);
    context.showExportProgress = () => {};
    context.hideExportProgress = () => {};
    context.refreshIndividualLayer = () => {
        if (refreshFailure === 'promise') return Promise.reject(new Error('refresh failed'));
        if (refreshFailure === 'throw') throw new Error('refresh failed');
        return Promise.resolve().then(() => { blocks = refreshed; });
    };
    context.XMLHttpRequest = class {
        open(method, url) { this.method = method; this.url = url; }
        setRequestHeader() {}
        send(body) {
            if (this.method === 'GET') {
                this.status = 200;
                this.responseText = refreshFailure === 'json' ? 'invalid' : JSON.stringify({ blocks: [] });
                this.onload();
            } else {
                posts.push(JSON.parse(new URLSearchParams(body).get('schedule_data')));
                this.onerror(); // Stop at the outbound snapshot; no real network/download.
            }
        }
    };
    context.checkServerAndAdvise = () => {};
    context.exportScheduleToExcel(() => done++);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(done, 1);
    return { prompts, posts, alerts };
}

(async () => {
    const oldConflict = [block(record(), 0), block(record(), 1)];
    const freshSingle = [block(record(), 0)];
    let result = await exportScenario(oldConflict, freshSingle, true);
    assert.equal(result.prompts, 0, 'removed stale DOM conflict must not be checked');
    assert.equal(result.posts.length, 1);
    assert.equal(result.posts[0].length, 1);
    const freshConflict = [block(record(), 0), block(record(), 1)];
    freshConflict[1].style.display = 'none';
    result = await exportScenario(freshSingle, freshConflict, false);
    assert.equal(result.prompts, 1, 'new hidden conflict must be checked after refresh');
    assert.equal(result.posts.length, 0);
    result = await exportScenario(freshSingle, freshConflict, true);
    assert.equal(result.prompts, 1);
    assert.equal(result.posts[0].length, 2, 'checked hidden row must be included in payload');
    for (const failure of ['json', 'promise', 'throw']) {
        result = await exportScenario(freshSingle, freshConflict, true, failure);
        assert.equal(result.posts.length, 0, 'failed refresh must cancel export: ' + failure);
        assert.equal(result.alerts, 1);
    }
    load('static/rooms_report.js');
    assert.equal(context.rentalScheduleLabel({ lesson_type: 'rental', rental_dates: [] }), 'Аренда еженедельно');
    const dates = ['2026-09-28', '2026-10-05'];
    const slot = { lesson_type: 'rental', rental_dates: dates, start: '10:00', end: '11:00' };
    assert.equal(context.rentalScheduleLabel(slot), 'Аренда только по датам: ' + dates.join(', '));
    context._availData = { buildings: { Villa: { rooms: ['1.01'], days: { Mo: { '1.01': [slot] } } } } };
    const note = context.renderDatedRentalNotes();
    assert(note.includes('без выбора календарной даты') && note.includes('2026-10-05') && note.includes('Villa / 1.01'));
    console.log(`Rental conflicts/dates: ${integrationOnly ? 'targeted export/report checks' : table.cases.length + ' shared cases + export/report checks'} passed in ${((performance.now() - started) / 1000).toFixed(3)} s`);
})().catch(error => { console.error(error); process.exitCode = 1; });
