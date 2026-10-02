// A small DOM fixture exercises the actual phase-1 handlers without a browser server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const started = performance.now();
const root = path.resolve(__dirname, '..');

function decode(html) {
    return html.replace(/<[^>]*>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
}
class Element {
    constructor(tag = 'div') {
        this.tagName = tag; this.nodeType = 1; this.attrs = {}; this.children = [];
        this.style = { setProperty(k, v) { this[k] = v; } }; this.events = {};
        this.html = ''; this.text = ''; this.className = '';
        this.classList = {
            contains: c => this.className.split(/\s+/).includes(c),
            add: c => { if (!this.classList.contains(c)) this.className += ' ' + c; },
            remove: c => { this.className = this.className.split(/\s+/).filter(x => x !== c).join(' '); },
            toggle: (c, on) => on ? this.classList.add(c) : this.classList.remove(c),
        };
    }
    get id() { return this.attrs.id; } set id(v) { this.attrs.id = v; }
    get innerHTML() { return this.html; } set innerHTML(v) { this.html = v; }
    get innerText() { return this.textContent; }
    get textContent() { return this.text || decode(this.html); } set textContent(v) { this.text = v; }
    get firstChild() { return this.children[0]; }
    get value() { return this.val !== undefined ? this.val : (this.tagName === 'select' && this.children[0] ? this.children[0].value : ''); }
    set value(v) { this.val = v; if (this.tagName === 'option') this.attrs.value = String(v); }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    getAttribute(k) { return this.attrs[k] ?? null; }
    removeAttribute(k) { delete this.attrs[k]; }
    appendChild(node) { node.parentNode = node.parentElement = this; this.children.push(node); return node; }
    insertBefore(node, before) { this.appendChild(node); if (before) { this.children.pop(); this.children.splice(this.children.indexOf(before), 0, node); } }
    removeChild(node) { this.children.splice(this.children.indexOf(node), 1); node.parentNode = node.parentElement = null; }
    remove() { this.parentNode?.removeChild(this); }
    matches(selector) {
        return selector.split(',').some(s => {
            s = s.trim();
            const attrs = [...s.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g)];
            if (attrs.some(([, k, v]) => v === undefined ? this.getAttribute(k) === null : this.getAttribute(k) !== v)) return false;
            s = s.replace(/\[[^\]]+\]/g, '');
            if (s.includes(' ')) s = s.split(/\s+/).at(-1);
            const id = s.match(/#([\w-]+)/)?.[1];
            if (id && this.id !== id) return false;
            if ([...s.matchAll(/\.([\w-]+)/g)].some(([, c]) => !this.classList.contains(c))) return false;
            const tag = s.match(/^([\w-]+)/)?.[1];
            return !tag || this.tagName === tag;
        });
    }
    querySelectorAll(selector) {
        return this.children.filter(c => c.nodeType === 1).flatMap(c => [c, ...c.querySelectorAll('*')])
            .filter(c => c.matches(selector));
    }
    querySelector(selector) {
        if (selector === 'strong' && /<strong>/.test(this.html)) {
            return { textContent: decode(this.html.match(/<strong>(.*?)<\/strong>/s)[1]) };
        }
        return this.querySelectorAll(selector)[0] || null;
    }
    closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) || null; }
    addEventListener(name, fn) { (this.events[name] ||= []).push(fn); }
    click() { (this.events.click || []).forEach(fn => fn({ preventDefault() {}, stopPropagation() {} })); }
    getBoundingClientRect() { return { height: 45, top: 0, bottom: 100, left: 0 }; }
}
const document = {
    body: new Element('body'), head: new Element('head'), readyState: 'loading',
    createElement: tag => new Element(tag), createTextNode: text => ({ nodeType: 3, textContent: text }),
    addEventListener() {}, removeEventListener() {},
    querySelectorAll: s => document.body.querySelectorAll(s),
    querySelector: s => document.body.querySelector(s),
    getElementById: id => document.body.querySelector('#' + id) || document.head.querySelector('#' + id),
};
const requests = [];
let saved = null;
const alerts = [];
const context = vm.createContext({
    document, console, setTimeout, clearTimeout, Date,
    alert: m => alerts.push(m), confirm: () => true,
    gridStart: 540, timeInterval: 5,
    findMatchingColumnInBuilding: () => 0,
    fetch: async (url, options) => {
        const payload = options.body ? JSON.parse(options.body) : undefined;
        requests.push({ url, method: options.method, payload });
        if (options.method === 'POST') saved = { ...payload, id: 'rental-stable' };
        if (options.method === 'PUT') saved = { ...saved, ...payload };
        if (options.method === 'DELETE') saved = null;
        const data = { ok: true, block: saved, individual_revision: String(requests.length) };
        return { ok: true, status: 200, text: async () => JSON.stringify(data) };
    },
});
context.window = context;
context.USER_ROLE = 'organizer';
context.getComputedStyle = element => ({ display: element.style.display || 'block', backgroundColor: element.style.backgroundColor || '#abcdef' });
function load(relative, exports = {}) {
    let code = fs.readFileSync(path.join(root, 'gear_xls', relative), 'utf8');
    if (Object.keys(exports).length) {
        const assignments = Object.entries(exports).map(([key, value]) => `window.${key} = { ${value.join(', ')} };`).join('\n');
        const marker = '  if (document.readyState === "loading") {';
        assert(code.includes(marker));
        code = code.replace(marker, assignments + '\n' + marker);
    }
    vm.runInContext(code, context, { filename: relative });
}
load('js_modules/block_content_sync.js');
// Load the actual normalization helper without replacing the existing placement stubs.
vm.runInContext(fs.readFileSync(path.join(root, 'gear_xls/js_modules/column_helpers.js'), 'utf8')
    .split('function getHeaderLocalColumnIndex')[0], context);
load('js_modules/lesson_type_filter.js');
load('js_modules/export_to_excel.js');
load('js_modules/trial_ui.js');
load('static/auth_ui.js');
context.SchedGenAuthUI.isEditMode = () => true;
load('static/individual_ui.js', { individualTest: [
    'enhanceCreateDialog', 'bindEditFormToBlock', 'buildEditPayload', 'buildBlockPayloadFromElement',
    'interceptCreateSubmit', 'interceptEditSubmit', 'interceptDeleteBlockClick',
    'captureBlockSnapshot', 'persistChangedBlock', 'applyIndividualState',
] });
context.SchedGenIndividualUI = { enhanceCreateDialog: context.individualTest.enhanceCreateDialog };
load('static/base_sync_ui.js', { baseTest: ['collectBlocksForPublish', 'buildScheduleSnapshotFromDom', 'isGroupBlockElement', 'normalizeBlocksForSignature'] });
load('js_modules/editing_update.js');
if (process.argv.includes('--sync-only')) load('static/lock_ui.js', { lockTest: ['acquireLock'] });
let conflictSource = fs.readFileSync(path.join(root, 'gear_xls/js_modules/conflict_detector.js'), 'utf8').replace(/\r\n/g, '\n');
conflictSource = conflictSource.replace('    ensureStyles();\n\n    return {', '    window.conflictTest = { parseBlock };\n    ensureStyles();\n\n    return {');
// Read the conflict payload; highlighting belongs to phase 2.
vm.runInContext(conflictSource, context);
context.ConflictDetector = undefined;

const container = document.body.appendChild(new Element());
container.className = 'schedule-container'; container.setAttribute('data-building', 'Villa');
const table = container.appendChild(new Element('table')); table.className = 'schedule-grid';
const head = table.appendChild(new Element('thead'));
const header = head.appendChild(new Element('th')); header.className = 'day-Mo'; header.textContent = 'Mo 1.01';
context.BuildingService = {
    findScheduleContainerForBuilding: () => container,
    getAvailableBuildings: () => ['Villa'], determineBuildingForBlock: () => 'Villa',
};
context.getRoomListForBuilding = () => ['1.01'];
context.extractRoomFromDayHeader = () => '1.01';
function form(id, values) {
    const f = document.body.appendChild(new Element('form')); f.id = id;
    for (const [name, value] of Object.entries(values)) {
        const label = f.appendChild(new Element('label'));
        label.appendChild(document.createTextNode(name));
        const field = label.appendChild(new Element('input')); field.id = name; field.value = value;
    }
    const row = f.appendChild(new Element()); row.className = 'button-row';
    return f;
}
const createForm = form('create-form', {
    'new-building': 'Villa', 'new-day': 'Mo', 'new-room': '1.01', 'new-subject': '',
    'new-teacher': '', 'new-students': 'Org & Contact', 'new-time': '10:00-11:00', 'color-value': '#abcdef',
});
const api = context.individualTest;
api.enhanceCreateDialog(createForm);
const type = createForm.querySelector('#new-lesson-type');
assert.equal(type.disabled, false);
// The organizer works with rentals only: no trial/auto choice in the create dialog.
assert.deepEqual(type.querySelectorAll('option').map(option => option.value), ['rental']);
assert.equal(type.value, 'rental');
assert.equal(context.SchedGenAuthUI.canMutateBlock('organizer', { getAttribute: () => 'trial' }), false);
type.value = 'rental'; type.events.change.forEach(fn => fn());
assert.equal(createForm.querySelector('#new-subject').value, 'Vermietung');
assert.equal(createForm.querySelector('#create-trial-dates-section').style.display, 'none');
assert.equal(createForm.querySelector('#create-rental-dates-section').style.display, '');

function event(target) { return { target, preventDefault() {}, stopPropagation() {}, stopImmediatePropagation() {} }; }
function current() { return container.querySelector('[data-block-id="rental-stable"]'); }
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

// Phase 4: lock acquisition resyncs first; a stale form is neither applied nor retried.
async function syncScenario() {
    let editMode = false;
    Object.assign(context.SchedGenAuthUI, {
        isEditMode: () => editMode, setEditMode: value => { editMode = !!value; },
        setNavEditorState() {}, currentUser: () => 'organizer_one', currentRole: () => 'organizer',
    });
    Object.assign(context, { setInterval: () => 1, clearInterval() {}, SCHEDULE_HTML_REVISION: 'page-1' });
    document.documentElement = new Element('html');
    context.SchedGenIndividualUI.refreshIndividualLayer = data => { api.applyIndividualState(data); return Promise.resolve(data); };
    const server = { revision: 'rev-1', room: '0.06', html: 'page-1', scheduleStatus: 200 };
    const calls = [];
    const stored = () => ({ id: 'rental-stable', building: 'Villa', day: 'Mo', room: server.room, subject: 'Vermietung',
        teacher: '', students: 'Verein', lesson_type: 'rental', start_time: '10:00', end_time: '11:00', rental_dates: [] });
    context.fetch = async (url, options = {}) => {
        const method = options.method || 'GET';
        const payload = options.body ? JSON.parse(options.body) : undefined;
        calls.push({ call: method + ' ' + url, payload, editMode });
        if (method === 'POST' && url === '/api/blocks') throw new TypeError('network down');
        let status = 200, data = { ok: true };
        if (url === '/api/lock/acquire') data = { ok: true, version: 7 };
        if (url === '/api/lock/status') data = { holder: null, version: 8 };
        if (url === '/api/schedule') {
            status = server.scheduleStatus;
            data = { base: [], individual: [stored()], base_revision: null, published_base_available: false,
                individual_revision: server.revision, schedule_html_revision: server.html };
        }
        if (method === 'PUT') {
            if (payload.expected_individual_revision !== server.revision) {
                status = 409;
                data = { ok: false, code: 'INDIVIDUAL_REVISION_CONFLICT', error: 'conflict',
                    force_individual_refresh: true, individual_revision: server.revision };
            } else {
                server.room = payload.room; server.revision = 'rev-saved';
                data = { ok: true, block: stored(), individual_revision: server.revision };
            }
        }
        return { ok: status < 400, status, text: async () => JSON.stringify(data) };
    };
    const settle = async () => { for (let i = 0; i < 10; i++) await tick(); };
    const editFields = room => ({ 'edit-building': 'Villa', 'edit-room': room, 'edit-subject': 'Vermietung',
        'edit-teacher': '', 'edit-students': 'Verein', 'edit-time': '12:00-13:00' });

    for (const [setup, message] of [[() => { server.scheduleStatus = 500; }, /синхронизировать/],
        [() => { server.scheduleStatus = 200; server.html = 'page-2'; }, /перегенерировано/]]) {
        setup(); calls.length = 0; alerts.length = 0;
        context.lockTest.acquireLock(); await settle();
        assert.equal(editMode, false);
        assert.deepEqual(calls.slice(0, 3).map(c => c.call), ['POST /api/lock/acquire', 'GET /api/schedule', 'POST /api/lock/release']);
        assert.equal(calls[2].payload.version, 7); assert.match(alerts[0], message);
    }
    Object.assign(server, { html: 'page-1', revision: 'rev-2', room: '0.08' }); calls.length = 0; alerts.length = 0;
    context.lockTest.acquireLock(); await settle();
    assert.equal(editMode, true); assert.equal(calls[1].call, 'GET /api/schedule'); assert.equal(calls[1].editMode, false);
    assert.equal(context.SchedGenLockUI.getLockVersion(), 7);
    assert(current().innerHTML.includes('0.08'));

    const stale = form('edit-form', editFields('0.06'));
    api.bindEditFormToBlock(current());
    Object.assign(server, { revision: 'rev-3', room: '0.09' });  // saved elsewhere after the form opened
    for (let attempt = 0; attempt < 2; attempt++) {
        calls.length = 0;
        api.interceptEditSubmit(event(stale)); await settle();
        assert.deepEqual(calls.map(c => c.call), ['PUT /api/blocks/rental-stable', 'GET /api/schedule']);
        assert.equal(calls[0].payload.expected_individual_revision, 'rev-2'); assert.equal(calls[0].payload.lock_version, 7);
        assert.match(alerts.at(-1), /после открытия формы/);
        assert(stale.parentNode); assert.equal(stale.querySelector('#edit-room').value, '0.06');
        assert.equal(server.room, '0.09');
    }
    stale.remove();
    const reopened = form('edit-form', editFields('0.09'));
    api.bindEditFormToBlock(current()); calls.length = 0;
    api.interceptEditSubmit(event(reopened)); await settle(); reopened.remove();
    assert.equal(calls[0].payload.expected_individual_revision, 'rev-3'); assert.equal(server.revision, 'rev-saved');

    calls.length = 0;
    api.interceptCreateSubmit(event(createForm)); await settle();
    assert.deepEqual(calls.map(c => c.call), ['POST /api/blocks']);
    assert.equal(calls[0].payload.lock_version, 7); assert.equal(calls[0].payload.expected_individual_revision, 'rev-saved');
    assert.match(alerts.at(-1), /ошибки сети/);
    console.log(`Lock resync and stale form handling passed (${((performance.now() - started) / 1000).toFixed(3)}s)`);
}

async function run() {
    if (process.argv.includes('--sync-only')) {
        await syncScenario();
        return;
    }
    if (process.argv.includes('--exchange-only')) {
        api.applyIndividualState({ individual_revision: 'snapshot-revision', individual: [{
            id: 'rental-stable', building: 'Villa', day: 'Mo', room: '1.01',
            subject: 'Other rental name', teacher: '', students: '', lesson_type: 'rental',
            start_time: '10:00', end_time: '11:00', duration: 60,
            rental_dates: ['2026-09-28', '2026-10-05'], notes: 'ä & <>', created_by: 'organizer_one',
        }] });
        const block = current();
        const extra = JSON.parse(block.getAttribute('data-block-metadata'));
        assert.deepEqual(extra, { notes: 'ä & <>', created_by: 'organizer_one' });
        block.setAttribute('data-start-row', 24);
        context.syncBlockContent(block);
        const exported = context.collectScheduleData({ includeHidden: true })[0];
        assert.equal(exported.block_id, 'rental-stable');
        assert.equal(exported.lesson_type, 'rental');
        assert.equal(exported.teacher, ''); assert.equal(exported.students, '');
        assert.deepEqual(JSON.parse(exported.rental_dates_json), ['2026-09-28', '2026-10-05']);
        assert.deepEqual(JSON.parse(exported.block_metadata_json), extra);
        console.log(`Rental metadata rendering/serialization passed (${((performance.now() - started) / 1000).toFixed(3)}s)`);
        return;
    }
    api.interceptCreateSubmit(event(createForm)); await tick();
    assert.equal(requests[0].payload.lesson_type, 'rental');
    assert.deepEqual(requests[0].payload.rental_dates, []);
    createForm.remove();
    let block = current();
    assert.equal(block.getAttribute('data-block-id'), 'rental-stable');
    assert.equal(context.SchedGenAuthUI.canMutateBlock('organizer', block), true);

    let editForm = form('edit-form', {
        'edit-building': 'Villa', 'edit-room': '1.01', 'edit-subject': 'Vermietung',
        'edit-teacher': '', 'edit-students': 'Org & Contact', 'edit-time': '10:00-11:00',
    });
    api.bindEditFormToBlock(block);
    let section = editForm.querySelector('#edit-rental-dates-section');
    section.querySelector('.rental-frequency').value = 'dates';
    const chip = section.querySelector('.trial-date-chips').appendChild(new Element('span'));
    chip.className = 'trial-date-chip'; chip.setAttribute('data-date', '2026-10-05');
    api.interceptEditSubmit(event(editForm)); await tick();
    assert.equal(saved.lesson_type, 'rental'); assert.equal(saved.id, 'rental-stable');
    assert.deepEqual(saved.rental_dates, ['2026-10-05']);
    block = current();
    assert(block.innerHTML.includes('05.10.2026'));
    editForm.remove();

    // Reopening the same ID restores dated frequency. Explicit switch clears dates only.
    editForm = form('edit-form', {
        'edit-building': 'Villa', 'edit-room': '1.01', 'edit-subject': 'Vermietung',
        'edit-teacher': '', 'edit-students': '', 'edit-time': '10:00-11:00',
    });
    api.bindEditFormToBlock(block);
    section = editForm.querySelector('#edit-rental-dates-section');
    assert.equal(section.querySelector('.rental-frequency').value, 'dates');
    section.querySelector('.rental-frequency').value = 'weekly';
    api.interceptEditSubmit(event(editForm)); await tick(); editForm.remove();
    assert.deepEqual(saved.rental_dates, []); assert.equal(saved.lesson_type, 'rental');
    block = current();
    for (const [start, span] of [[24, 12], [24, 18]]) {
        const snapshot = api.captureBlockSnapshot(block);
        block.setAttribute('data-start-row', start); block.setAttribute('data-row-span', span);
        context.syncBlockContent(block);
        api.persistChangedBlock(block, snapshot); await tick(); block = current();
        assert.equal(block.getAttribute('data-block-id'), 'rental-stable');
        assert.equal(saved.lesson_type, 'rental'); assert.deepEqual(saved.rental_dates, []);
        assert.equal(saved.teacher, ''); assert.equal(saved.students, '');
    }
    assert.equal(saved.start_time, '11:00'); assert.equal(saved.end_time, '12:30');
    assert.equal(context.SchedGenAuthUI.canMutateBlock('organizer', { getAttribute: () => 'group' }), false);
    assert.equal(context.SchedGenAuthUI.canMutateBlock('editor', { getAttribute: () => 'unknown' }), false);

    for (const [teacher, students] of [['', 'Org & Contact'], ['Contact', ''], ['', '']]) {
        block.innerHTML = `<strong>Vermietung</strong><br>${teacher}<br>${students.replace(/&/g, '&amp;')}<br>1.01<br>11:00-12:30`;
        const payload = api.buildBlockPayloadFromElement(block);
        assert.equal(payload.teacher, teacher); assert.equal(payload.students, students);
        const exported = context.collectScheduleData({ includeHidden: true })[0];
        assert.equal(exported.teacher, teacher); assert.equal(exported.students, students);
        assert.equal(exported.block_id, 'rental-stable'); assert.equal(exported.source_layer, 'individual');
        const conflict = context.conflictTest.parseBlock(block);
        assert.equal(conflict.teacher, teacher); assert.equal(conflict.students, students);
        assert.equal(conflict.room, '1.01'); assert.equal(conflict.timeRange, '11:00-12:30');
        context.openEditDialog(block, '', '', 'Villa');
        const dialog = document.querySelector('.dialog-overlay');
        assert(dialog.innerHTML.includes(`id="edit-teacher" value="${teacher}"`));
        assert(dialog.innerHTML.includes(`id="edit-students" value="${students.replace(/&/g, '&amp;')}"`));
        context.closeEditDialog();
    }
    context.applyLessonTypeFilter('non-group');
    assert.equal(block.classList.contains('lesson-type-filter-hidden'), false);
    context.applyLessonTypeFilter('all');

    // Repeated serialization excludes managed origins even when the DOM says group.
    const group = container.appendChild(new Element()); group.className = 'activity-block';
    for (const [name, value] of Object.entries({ day: 'Mo', building: 'Villa', 'col-index': '0', 'start-row': '36', 'row-span': '12', 'lesson-type': 'group' })) group.setAttribute('data-' + name, value);
    group.innerHTML = '<strong>Math</strong><br><br>G1<br>1.01<br>12:00-13:00';
    block.setAttribute('data-lesson-type', 'group');
    for (let i = 0; i < 3; i++) {
        assert.equal(context.baseTest.isGroupBlockElement(block), false);
        const publication = context.baseTest.collectBlocksForPublish();
        assert.equal(publication.length, 1); assert.equal(publication[0].subject, 'Math');
        assert.equal(publication[0].teacher, ''); assert.equal(publication[0].students, 'G1');
        const fallback = context.baseTest.buildScheduleSnapshotFromDom();
        assert.equal(fallback.find(b => b.block_id).source_layer, 'individual');
        assert.equal(context.baseTest.normalizeBlocksForSignature(fallback).length, 1);
    }
    block.setAttribute('data-lesson-type', 'rental');
    // Applying the two layers again must leave one managed ID and one group.
    for (let i = 0; i < 3; i++) {
        api.applyIndividualState({
            base: context.collectScheduleData({ includeHidden: true }).filter(b => !b.block_id),
            individual: [saved], base_revision: String(i), published_base_available: true,
            individual_revision: String(i),
        });
        block = current();
        assert.equal(container.querySelectorAll('[data-block-id="rental-stable"]').length, 1);
        assert.equal(container.querySelectorAll('.activity-block[data-lesson-type="group"]').length, 1);
    }
    // The shared date UI covers Sunday and does not turn an empty dated selection into weekly.
    const sunday = context.TrialUI.buildRentalDatesSection([]);
    assert(context.TrialUI.validateRentalDates(sunday, 'So'));
    sunday.querySelector('.rental-frequency').value = 'dates';
    assert(context.TrialUI.validateRentalDates(sunday, 'So'));
    const sundayChip = sunday.querySelector('.trial-date-chips').appendChild(new Element('span'));
    sundayChip.className = 'trial-date-chip'; sundayChip.setAttribute('data-date', '2026-10-04');
    assert.equal(context.TrialUI.validateRentalDates(sunday, 'So'), null);
    assert(context.TrialUI.validateRentalDates(sunday, 'Mo'));
    sundayChip.setAttribute('data-date', '2026-02-30');
    assert(context.TrialUI.validateRentalDates(sunday, 'Mo'));
    assert.equal(context.validateScheduleDataForExcelExport([{ day: 'So', lesson_type: 'rental', rental_dates_json: '["2026-10-04"]' }]).ok, true);
    assert.equal(context.validateScheduleDataForExcelExport([{ day: 'So', lesson_type: 'rental', rental_dates_json: '[]' }]).ok, false);
    assert.equal(context.validateScheduleDataForExcelExport([{ day: 'Mo', lesson_type: 'rental', rental_dates_json: 'broken' }]).ok, false);
    api.interceptDeleteBlockClick(event(block)); await tick();
    assert.equal(requests.at(-1).method, 'DELETE'); assert.equal(current(), null);
    assert.equal(alerts.length, 0, alerts.join('\n'));
    console.log(`Rental editor handlers passed (${((performance.now() - started) / 1000).toFixed(3)}s)`);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
