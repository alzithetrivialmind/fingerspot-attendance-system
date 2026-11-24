// Layar monitor: tampilkan scan terbaru dari webhook mesin, besar dan jelas.
// Akses: ?key=<MONITOR_KEY> (PC monitor tetap) atau token login aplikasi utama (localStorage).

const TIMEZONE = window.APP_CONFIG.timezone;
const POLL_MS = 1500;
const OLD_AFTER_S = 20;      // scan lebih lama dari ini diredupkan: bukan orang yang sedang di depan mesin
const LATE_AFTER_S = 120;    // jeda mesin -> server sebesar ini = data antrian, bukan scan barusan
const RECENT_MAX = 10;

const params = new URLSearchParams(location.search);
const monitorKey = params.get('key') || '';
let device = params.has('device') ? params.get('device') : (safeGet('monitor_device') ?? '');
let devices = [];
let lastSeq = 0;
let feedDate = null;         // tanggal data di layar; ganti hari = layar dikosongkan
let firstLoad = true;
let current = null;
let recent = [];
let clockOffset = 0;         // jam server - jam PC
let soundOn = safeGet('monitor_sound') === '1';
let audioCtx = null;

const $ = id => document.getElementById(id);

function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* abaikan */ } }

function escapeHtml(val) {
    return String(val ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

const fmtTime = d => d.toLocaleTimeString('id-ID', { timeZone: TIMEZONE, hour12: false });
const fmtDate = d => d.toLocaleDateString('id-ID', { timeZone: TIMEZONE, weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const serverNow = () => new Date(Date.now() + clockOffset);

function authHeaders() {
    if (monitorKey) return { 'X-Monitor-Key': monitorKey };
    const token = safeGet('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
}

class AuthError extends Error {}

async function getJSON(url) {
    const res = await fetch(url, { headers: authHeaders(), cache: 'no-store' });
    if (res.status === 401) throw new AuthError();
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

// Penilaian satu scan: warna, judul pita, catatan untuk petugas.
function assess(ev) {
    if (!ev.registered) return { state: 'bad', band: 'PIN tidak terdaftar', tag: 'Tidak terdaftar',
        note: 'Mesin mencatat scan, tetapi PIN ini belum ada di sistem. Tanyakan nama dan laporkan ke admin.' };
    if (ev.lag_seconds != null && ev.lag_seconds >= LATE_AFTER_S) return { state: 'warn', band: 'Data terlambat', tag: 'Terlambat',
        note: `Scan ini baru sampai ${Math.round(ev.lag_seconds / 60)} menit setelah tap di mesin. Bukan scan orang yang sedang di depan mesin.` };
    if (ev.active === false) return { state: 'warn', band: 'Karyawan nonaktif', tag: 'Nonaktif',
        note: 'Karyawan ini berstatus nonaktif di sistem. Laporkan ke admin.' };
    if (ev.repeat) return { state: 'warn', band: 'Scan ulang', tag: 'Scan ulang',
        note: 'PIN yang sama sudah scan kurang dari 5 menit sebelumnya.' };
    return { state: 'ok', band: 'Tercatat', tag: '', note: '' };
}

function metaLine(ev) {
    if (!ev.registered) return `PIN ${ev.pin}`;
    return [ev.nik ? `NIK ${ev.nik}` : `PIN ${ev.pin}`, ev.department || ev.position, ev.company]
        .filter(Boolean).join('  ·  ');
}

function renderHero(flash) {
    const hero = $('hero');
    if (!current) {
        hero.dataset.state = 'idle';
        $('hero-band').textContent = 'Menunggu scan';
        $('hero-name').innerHTML = '&nbsp;';
        $('hero-meta').textContent = 'Belum ada scan realtime hari ini dari mesin ini.';
        $('hero-time').textContent = '--.--.--';
        $('hero-verify').textContent = '-';
        $('hero-note').hidden = true;
        return;
    }
    const a = assess(current);
    hero.dataset.state = a.state;
    $('hero-band').textContent = a.band;
    $('hero-name').textContent = current.registered ? current.name : 'Tidak dikenal';
    $('hero-meta').textContent = metaLine(current);
    $('hero-time').textContent = fmtTime(new Date(current.scan_time));
    $('hero-verify').textContent = current.verify_label || (current.verify_mode != null ? `Mode ${current.verify_mode}` : '-');
    $('hero-note').hidden = !a.note;
    $('hero-note').textContent = a.note;
    if (flash) {
        hero.classList.remove('flash');
        void hero.offsetWidth;
        hero.classList.add('flash');
    }
    tickAgo();
}

function tickAgo() {
    const hero = $('hero');
    if (!current) { $('hero-ago').textContent = '-'; hero.classList.remove('is-old'); return; }
    const s = Math.max(0, Math.round((serverNow() - new Date(current.scan_time)) / 1000));
    $('hero-ago').textContent = s < 60 ? `${s} dtk` : s < 3600 ? `${Math.floor(s / 60)} mnt` : `${Math.floor(s / 3600)} jam`;
    hero.classList.toggle('is-old', s > OLD_AFTER_S);
}

function renderRecent() {
    const ol = $('recent');
    if (!recent.length) {
        ol.innerHTML = '<li class="recent-empty">Belum ada.</li>';
        return;
    }
    ol.innerHTML = recent.map(ev => {
        const a = assess(ev);
        const cls = a.state === 'ok' ? '' : a.state;
        return `<li class="${cls}">
            <span class="t num">${escapeHtml(fmtTime(new Date(ev.scan_time)))}</span>
            <span><div class="n">${escapeHtml(ev.registered ? ev.name : `PIN ${ev.pin}`)}</div>
                  <div class="d">${escapeHtml(ev.registered ? (ev.department || ev.company || '') : 'Belum terdaftar di sistem')}</div></span>
            <span class="tag">${escapeHtml(a.tag)}</span>
        </li>`;
    }).join('');
}

function renderStatus(state, text) {
    $('mon-status').dataset.state = state;
    $('mon-status-text').textContent = text;
}

function beep(bad) {
    if (!soundOn) return;
    try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        const tones = bad ? [[330, 0], [260, 0.22]] : [[1046, 0]];
        tones.forEach(([freq, at]) => {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.frequency.value = freq;
            osc.type = bad ? 'square' : 'sine';
            const t0 = audioCtx.currentTime + at;
            gain.gain.setValueAtTime(0.25, t0);
            gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.2);
            osc.connect(gain).connect(audioCtx.destination);
            osc.start(t0);
            osc.stop(t0 + 0.2);
        });
    } catch { /* browser tanpa suara */ }
}

function resetFeed() {
    lastSeq = 0;
    firstLoad = true;
    current = null;
    recent = [];
    renderHero(false);
    renderRecent();
}

async function poll() {
    try {
        const q = new URLSearchParams({ after: lastSeq, limit: firstLoad ? RECENT_MAX + 1 : 50 });
        if (device) q.set('cloud_id', device);
        const data = await getJSON(`/monitor/feed?${q}`);
        $('overlay').hidden = true;
        clockOffset = new Date(data.server_time) - Date.now();

        // Server baru restart, atau sudah ganti hari: muat ulang dari awal (data kemarin tidak ditampilkan)
        if (data.last_seq < lastSeq || (feedDate && data.date !== feedDate)) {
            feedDate = data.date;
            resetFeed();
            return schedule(0);
        }
        feedDate = data.date;
        const events = data.events;     // terbaru di depan
        if (firstLoad) {
            current = events[0] || null;
            recent = events.slice(1);
            renderHero(false);
            renderRecent();
            firstLoad = false;
        } else if (events.length) {
            events.slice().reverse().forEach(ev => {
                if (current) recent.unshift(current);
                current = ev;
            });
            recent = recent.slice(0, RECENT_MAX);
            renderHero(true);
            renderRecent();
            beep(assess(current).state === 'bad');
        }
        lastSeq = Math.max(lastSeq, data.last_seq);

        $('t-scans').textContent = data.today.scans;
        $('t-people').textContent = data.today.people;
        $('t-unreg').textContent = data.today.unregistered;
        if (data.last_received_at) {
            renderStatus('ok', `Terhubung · data terakhir masuk ${fmtTime(new Date(data.last_received_at))}`);
        } else {
            renderStatus('stale', 'Terhubung · belum ada data realtime dari mesin hari ini');
        }
        schedule(POLL_MS);
    } catch (err) {
        if (err instanceof AuthError) {
            $('overlay-title').textContent = monitorKey ? 'Kunci monitor salah' : 'Perlu masuk';
            $('overlay-text').textContent = monitorKey
                ? 'Link monitor ini tidak berlaku lagi. Minta link baru ke admin.'
                : 'Sesi login sudah habis atau belum masuk. Masuk lagi lewat halaman utama.';
            $('overlay').hidden = false;
            renderStatus('down', 'Belum masuk');
            return schedule(5000);
        }
        renderStatus('down', 'Server tidak terhubung · mencoba lagi');
        schedule(5000);
    }
}

let pollTimer = null;
function schedule(ms) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, ms);
}

async function loadDevices() {
    try {
        devices = await getJSON('/monitor/devices');
    } catch {
        devices = [];
    }
    if (!device && devices.length === 1) device = devices[0].cloud_id;
    const sel = $('mon-device');
    sel.innerHTML = '<option value="">Semua mesin</option>' + devices.map(d =>
        `<option value="${escapeHtml(d.cloud_id)}">${escapeHtml(d.name)}</option>`).join('');
    sel.value = devices.some(d => d.cloud_id === device) ? device : '';
    device = sel.value;
    updateTitle();
}

function updateTitle() {
    const d = devices.find(x => x.cloud_id === device);
    $('mon-title').textContent = d ? `Monitor absensi · ${d.name}` : 'Monitor absensi · semua mesin';
}

function tickClock() {
    const now = serverNow();
    $('mon-time').textContent = fmtTime(now);
    $('mon-date').textContent = fmtDate(now);
    tickAgo();
}

function updateSoundBtn() {
    const btn = $('btn-sound');
    btn.setAttribute('aria-pressed', soundOn ? 'true' : 'false');
    btn.textContent = soundOn ? 'Suara aktif' : 'Aktifkan suara';
}

$('mon-device').addEventListener('change', e => {
    device = e.target.value;
    safeSet('monitor_device', device);
    updateTitle();
    resetFeed();
    schedule(0);
});

$('btn-sound').addEventListener('click', () => {
    soundOn = !soundOn;
    safeSet('monitor_sound', soundOn ? '1' : '0');
    updateSoundBtn();
    beep(false);
});

$('btn-full').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
});
document.addEventListener('fullscreenchange', () => {
    document.body.classList.toggle('is-full', !!document.fullscreenElement);
    $('btn-full').textContent = document.fullscreenElement ? 'Keluar layar penuh' : 'Layar penuh';
});

// Browser memblokir suara sebelum ada klik; klik di mana saja menyalakan audio bila suara aktif.
document.addEventListener('click', () => {
    if (soundOn && !audioCtx) {
        try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch { /* abaikan */ }
    }
}, { once: true });

$('btn-logout').addEventListener('click', () => {
    try { localStorage.removeItem('token'); localStorage.removeItem('user_full_name'); } catch { /* abaikan */ }
    location.replace('/');
});

// Login dengan akun (bukan kunci monitor): tampilkan nama akun dan tombol Keluar
async function loadUser() {
    if (monitorKey || !safeGet('token')) return;
    try {
        const me = await getJSON('/auth/me');
        $('mon-user').textContent = `Masuk sebagai ${me.full_name || me.username}`;
        $('mon-user').hidden = false;
        $('btn-logout').hidden = false;
    } catch { /* overlay login ditangani poll() */ }
}

updateSoundBtn();
renderRecent();
loadUser();
setInterval(tickClock, 1000);
tickClock();
loadDevices().then(() => poll());
