// Phase 3: outbound Excel payload and its applied revisions on a compact DOM fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const started = performance.now();
const root = path.resolve(__dirname, '..');
let blocks = [];
function booking(id, room, dates = []) {
    const attrs = { 'data-day': 'Mo', 'data-col-index': room === '1.01' ? '0' : '1',
        'data-block-id': id, 'data-lesson-type': 'rental', 'data-rental-dates': JSON.stringify(dates),
        'data-source-layer': 'individual', 'data-block-metadata': JSON.stringify({ notes: 'ä & <>' }) };
    return { getAttribute: key => attrs[key] ?? null, style: { display: 'none' },
        lines: ['Vermietung', '', '', room, '10:00-11:00'], innerHTML: '' };
}
const container = {
    getAttribute: () => 'Villa', querySelectorAll: () => blocks,
    querySelector: () => ({
        querySelector: () => ({ getBoundingClientRect: () => ({ height: 45 }) }),
        querySelectorAll: () => [{ innerText: 'Mo 1.01' }, { innerText: 'Mo 1.02' }],
    }),
};
const context = vm.createContext({
    console: { log() {}, warn() {}, error() {} }, setTimeout() {}, clearTimeout() {},
    document: { readyState: 'loading', body: { classList: { toggle() {} } }, addEventListener() {}, removeEventListener() {}, getElementById: () => null,
        querySelectorAll: selector => selector === '.schedule-container' ? [container] : [], },
    getComputedStyle: block => ({ display: block.style.display, backgroundColor: '#abcdef' }),
    readBlockContentLines: block => block.lines,
});
context.window = context;
for (const name of ['static/base_sync_ui.js', 'js_modules/export_to_excel.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'gear_xls', name), 'utf8'), context, { filename: name });
}
const baseUi = context.SchedGenBaseSyncUI;
assert.equal(baseUi.getAppliedBaseRevision(), undefined);
baseUi.applyBaseScheduleData({ base_revision: null, published_base_available: false });
assert.equal(baseUi.getAppliedBaseRevision(), null);
baseUi.setBaseRevision('server-observed-newer');
assert.equal(baseUi.getAppliedBaseRevision(), null, 'observing a revision must not label the old DOM with it');
// The getter above is exercised directly; export uses a populated base fixture below.
let appliedBase = 'base-applied', dirtyBase = false, searchPrepared = 0;
context.SchedGenBaseSyncUI = { getAppliedBaseRevision: () => appliedBase, hasUnpublishedGroupChanges: () => dirtyBase };
context.ScheduleSearch = { prepareForSerialization() { searchPrepared++; } };

async function sendExport(data, freshBlocks, rejectRefresh = false) {
    const posts = [];
    let done = 0, alerts = 0;
    context.alert = () => alerts++;
    context.showExportProgress = context.hideExportProgress = context.checkServerAndAdvise = () => {};
    context.checkServerAvailability = callback => callback(true);
    context.refreshIndividualLayer = received => {
        assert.deepEqual(JSON.parse(JSON.stringify(received)), data);
        if (rejectRefresh) return Promise.reject(new Error('failed'));
        return Promise.resolve().then(() => { blocks = freshBlocks; });
    };
    context.XMLHttpRequest = class {
        open(method, url) { this.method = method; this.url = url; }
        setRequestHeader() {}
        send(body) {
            if (this.method === 'GET') {
                this.status = 200; this.responseText = JSON.stringify(data); this.onload();
            } else {
                const form = new URLSearchParams(body);
                posts.push({ records: JSON.parse(form.get('schedule_data')), sync: form.has('schedule_sync') ? JSON.parse(form.get('schedule_sync')) : null });
                this.onerror(); // Stop after outbound serialization, without real network/download.
            }
        }
    };
    context.exportScheduleToExcel(() => done++);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(done, 1);
    return { posts, alerts };
}

(async () => {
    blocks = [booking('obsolete', '1.01')];
    const fresh = [booking('00017', '1.01'), booking('other-room', '1.02', ['2026-09-28', '2026-10-05'])];
    let result = await sendExport({ blocks: [], last_modified: 'individual-applied', base_revision: 'server-unapplied' }, fresh);
    assert.equal(result.posts.length, 1);
    assert.deepEqual(result.posts[0].sync, { format_version: 1, source_base_revision: 'base-applied', source_individual_revision: 'individual-applied', snapshot_scope: 'full' });
    assert.deepEqual(result.posts[0].records.map(row => row.block_id), ['00017', 'other-room']);
    for (const row of result.posts[0].records) {
        assert.equal(row.lesson_type, 'rental'); assert.equal(row.teacher, ''); assert.equal(row.students, '');
        assert.equal(JSON.parse(row.block_metadata_json).notes, 'ä & <>');
    }
    assert.deepEqual(JSON.parse(result.posts[0].records[1].rental_dates_json), ['2026-09-28', '2026-10-05']);
    assert(searchPrepared > 0, 'existing search serialization preparation was called');
    appliedBase = null;
    result = await sendExport({ blocks: [], last_modified: null }, fresh);
    assert.equal(result.posts[0].sync.source_base_revision, '');
    assert.equal(result.posts[0].sync.source_individual_revision, '');
    result = await sendExport({ blocks: [] }, fresh);
    assert.equal(result.posts[0].sync, null, 'unknown provenance must remain unknown');
    dirtyBase = true;
    result = await sendExport({ blocks: [], last_modified: 'revision' }, fresh);
    assert.equal(result.posts[0].sync.snapshot_scope, 'full', 'local edits do not turn a complete export into a partial one');
    dirtyBase = false;
    result = await sendExport({ blocks: [], last_modified: 'revision' }, [booking('same', '1.01'), booking('same', '1.02')]);
    assert.equal(result.posts.length, 0); assert.equal(result.alerts, 1);
    result = await sendExport({ blocks: [], last_modified: 'revision' }, fresh, true);
    assert.equal(result.posts.length, 0); assert.equal(result.alerts, 1);
    console.log(`Rental Excel payload, hidden rows, identity and applied provenance passed in ${((performance.now() - started) / 1000).toFixed(3)} s`);
})().catch(error => { console.error(error); process.exitCode = 1; });
