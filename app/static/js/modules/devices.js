// Fetch Devices
async function fetchDevices() {
    const tbody = document.getElementById('devices-tbody');
    tbody.innerHTML = '<tr><td colspan="6" class="loading">Memuat daftar mesin...</td></tr>';

    try {
        const response = await fetch('/devices/', { headers: getReqHeaders() });
        if (!response.ok) throw new Error('Failed to fetch devices');

        const data = await response.json();

        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">Belum ada mesin. Tambahkan mesin dengan Cloud ID dari fingerspot.io.</td></tr>';
            return;
        }

        const summaryRes = await fetch('/devices/sync-summary', { headers: getReqHeaders() });
        window.deviceSyncSummary = summaryRes.ok ? await summaryRes.json() : {};

        tbody.innerHTML = data.map(device => `
            <tr>
                <td style="font-weight: 500;">${escapeHtml(device.name)}</td>
                <td class="num">${escapeHtml(device.cloud_id)}</td>
                <td class="num text-muted">${escapeHtml(device.sn || '-')}</td>
                <td>${device.is_active ? 'Aktif' : '<span style="color: var(--signal);">Nonaktif</span>'}</td>
                <td>${renderDeviceSyncSummary(device.id)}</td>
                <td>
                    <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center;">
                        <button class="btn btn-secondary btn-sm" onclick="pullEmployeesFromDevice(${device.id})" title="Ambil daftar karyawan yang terdaftar di mesin ini">Tarik karyawan</button>
                        <button class="btn btn-secondary btn-sm" onclick="showPushEmployeesModalById(${device.id})" title="Daftarkan karyawan dari sistem ke mesin ini">Kirim karyawan</button>
                        <button class="btn btn-ghost btn-sm icon-btn" onclick="fetchDeviceInfo(${device.id})" title="Informasi mesin" aria-label="Informasi mesin ${escapeHtml(device.name)}">
                            <i data-lucide="info"></i>
                        </button>
                        <button class="btn btn-ghost btn-sm icon-btn admin-only-btn" onclick="setDeviceTime(${device.id})" title="Samakan jam mesin" aria-label="Samakan jam mesin ${escapeHtml(device.name)}">
                            <i data-lucide="clock"></i>
                        </button>
                        <button class="btn btn-ghost btn-sm icon-btn admin-only-btn" onclick="restartDevice(${device.id})" title="Restart mesin" aria-label="Restart mesin ${escapeHtml(device.name)}" style="color: var(--signal);">
                            <i data-lucide="power"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
        lucide.createIcons();
        applyRolePermissions();
    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="6" style="color: var(--danger); text-align: center;">Gagal memuat daftar mesin: ${escapeHtml(error.message)}</td></tr>`;
    }
}

function renderDeviceSyncSummary(deviceId) {
    const s = (window.deviceSyncSummary || {})[deviceId];
    if (!s) return '<span class="text-muted">Belum ada data</span>';
    let html = `<span class="num">${s.synced}</span> terkonfirmasi, <span class="num">${s.pending}</span> antre`;
    if (s.failed > 0) {
        html += `, <span class="num" style="color: var(--signal);">${s.failed}</span> gagal
            <button class="btn btn-secondary btn-sm" style="margin-left: 0.35rem;" onclick="retryFailedDeviceSync(${deviceId})">Kirim ulang</button>`;
    }
    return html;
}

async function retryFailedDeviceSync(deviceId) {
    const failures = ((window.deviceSyncSummary || {})[deviceId] || {}).failures || [];
    const lines = failures.slice(0, 5).map(f =>
        `PIN ${f.pin} ${f.name || ''}: ${f.error || 'tanpa keterangan'}`);
    if (failures.length > 5) lines.push(`... dan ${failures.length - 5} lainnya`);
    if (!confirm(`Kirim ulang ${failures.length} perintah yang gagal?\n\n${lines.join('\n')}`)) return;

    try {
        const response = await fetch(`/devices/${deviceId}/retry-failed`, { method: 'POST', headers: getReqHeaders() });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Gagal mengirim ulang');
        showToast(`${data.retried} perintah masuk antrean lagi.`, 'success');
        await fetchDevices();
    } catch (error) {
        showToast('Gagal mengirim ulang: ' + error.message, 'error');
    }
}

function showPushEmployeesModalById(id) {
    const d = (window.allDevices || []).find(x => x.id === id);
    showPushEmployeesModal(id, d ? d.name : '');
}

// Add Device Modal
function showAddDeviceModal() {
    document.getElementById('add-device-modal').style.display = 'flex';
}

function hideAddDeviceModal() {
    document.getElementById('add-device-modal').style.display = 'none';
    document.getElementById('add-device-form').reset();
}

async function submitAddDevice(event) {
    event.preventDefault();
    const name = document.getElementById('device_name').value;
    const cloud_id = document.getElementById('device_cloud_id').value;

    try {
        const response = await fetch('/devices/', {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ name, cloud_id, is_active: true })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed to add device');
        }
        
        hideAddDeviceModal();
        fetchDevices();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Device Info Modal
function hideInfoDeviceModal() {
    document.getElementById('info-device-modal').style.display = 'none';
}

async function fetchDeviceInfo(deviceId) {
    document.getElementById('info-device-modal').style.display = 'flex';
    document.getElementById('device-info-content').innerHTML = '<p class="loading">Mengambil info mesin...</p>';
    
    try {
        const response = await fetch(`/devices/${deviceId}/info`, { headers: getReqHeaders() });
        const resData = await response.json();
        
        if (!response.ok) throw new Error(resData.detail || 'Failed to fetch device info');
        
        const data = resData.data;
        document.getElementById('device-info-content').innerHTML = `
            <div style="margin-bottom: 0.75rem;"><strong>Cloud ID:</strong> ${escapeHtml(data.cloud_id || '-')}</div>
            <div style="margin-bottom: 0.75rem;"><strong>Nama mesin:</strong> ${escapeHtml(data.device_name || '-')}</div>
            <div style="margin-bottom: 0.75rem;"><strong>Dibuat:</strong> ${escapeHtml(data.created_at || '-')}</div>
            <div style="margin-bottom: 0.75rem;"><strong>Aktivitas terakhir:</strong> ${escapeHtml(data.last_activity || '-')}</div>
            <div style="margin-bottom: 0.75rem; word-break: break-all;"><strong>URL webhook:</strong> ${escapeHtml(data.webhook_url || '-')}</div>
        `;
    } catch (error) {
        document.getElementById('device-info-content').innerHTML = `<p style="color: var(--danger);">Gagal: ${escapeHtml(error.message)}</p>`;
    }
}

// Set Time & Restart functions
async function setDeviceTime(deviceId) {
    if (!confirm(`Samakan jam mesin ini ke zona waktu ${window.APP_CONFIG.timezone}?`)) return;
    
    try {
        const response = await fetch(`/devices/${deviceId}/set-time`, {
            method: 'POST',
            headers: { ...getReqHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ timezone: window.APP_CONFIG.timezone })
        });
        const data = await response.json();
        
        if (!response.ok) throw new Error(data.detail || 'Failed to set time');
        showToast('Perintah sinkron jam terkirim. Menunggu konfirmasi mesin...', 'info');
        
        if (data.trans_id) startPollingProgress(data.trans_id, 'set_time');
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

async function restartDevice(deviceId) {
    if (!confirm('Restart mesin ini sekarang?')) return;
    
    try {
        const response = await fetch(`/devices/${deviceId}/restart`, {
            method: 'POST',
            headers: getReqHeaders()
        });
        const data = await response.json();
        
        if (!response.ok) throw new Error(data.detail || 'Failed to restart device');
        showToast('Perintah restart terkirim. Menunggu konfirmasi mesin...', 'info');
        
        if (data.trans_id) startPollingProgress(data.trans_id, 'restart');
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Progress Polling Variables
let syncPollInterval = null;

// Trigger Data Fetch per device
let currentSyncDeviceId = null;

// Panel progres proses mesin (Settings > Devices). Proses berjalan di cloud Fingerspot
// dan dikonfirmasi lewat webhook, jadi bisa lama; panel menampilkan waktu berjalan
// dan bar bergerak walau jumlah item belum diketahui.
const jobProgress = {
    timer: null,
    startedAt: 0,
    el(id) { return document.getElementById(id); },
    isRunning() { return !!syncPollInterval; },
    show(text) {
        this.el('sync-progress-container').style.display = 'block';
        this.setText(text);
        this.el('sync-progress-percentage').innerText = '';
        const bar = this.el('sync-progress-bar');
        bar.style.width = '';
        bar.classList.add('is-indeterminate');
        this.el('sync-progress-close').style.display = 'none';
        this.startedAt = Date.now();
        clearInterval(this.timer);
        const tick = () => {
            const s = Math.floor((Date.now() - this.startedAt) / 1000);
            this.el('sync-progress-elapsed').innerText = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
        };
        tick();
        this.timer = setInterval(tick, 1000);
    },
    setText(text, color = 'var(--foreground)') {
        const t = this.el('sync-progress-text');
        t.innerText = text;
        t.style.color = color;
    },
    update(processed, total, text) {
        const pct = Math.min(100, Math.round((processed / total) * 100));
        const bar = this.el('sync-progress-bar');
        bar.classList.remove('is-indeterminate');
        bar.style.width = `${pct}%`;
        this.el('sync-progress-percentage').innerText = `${pct}%`;
        this.setText(text);
    },
    end(text, ok) {
        clearInterval(this.timer);
        const bar = this.el('sync-progress-bar');
        bar.classList.remove('is-indeterminate');
        if (ok) {
            bar.style.width = '100%';
            this.el('sync-progress-percentage').innerText = '100%';
        }
        this.setText(text, ok ? 'var(--success)' : 'var(--destructive)');
        this.el('sync-progress-close').style.display = 'inline-flex';
        showToast(text, ok ? 'success' : 'error', ok ? 4500 : 8000);
    },
    hide() {
        clearInterval(this.timer);
        this.el('sync-progress-container').style.display = 'none';
    }
};

const STALL_LIMIT_MS = 3 * 60 * 1000;   // tidak ada kemajuan selama 3 menit -> dianggap gagal
const HARD_LIMIT_MS = 20 * 60 * 1000;   // batas total satu proses
const NO_REPLY_HINT = 'Mesin tidak membalas. Pastikan mesin online dan URL webhook di fingerspot.io mengarah ke server ini.';

async function fetchData(deviceId) {
    if (jobProgress.isRunning()) {
        showToast('Masih ada proses mesin yang berjalan. Tunggu sampai selesai.', 'info');
        return;
    }
    if (!confirm('Tarik seluruh data karyawan dari mesin ini? Perintah akan dikirim ke mesin fisik dan berjalan di latar belakang.')) {
        return;
    }

    currentSyncDeviceId = deviceId;
    jobProgress.show('Menghubungi mesin untuk menarik daftar PIN karyawan...');

    try {
        const response = await fetch(`/devices/${deviceId}/fetch-data`, {
            method: 'POST',
            headers: getReqHeaders()
        });
        const data = await response.json();

        if (!response.ok) throw new Error(data.detail || 'Gagal mengirim perintah ke mesin');

        if (data.trans_id) {
            jobProgress.setText('Perintah terkirim. Menunggu mesin mengirim daftar PIN...');
            startPollingProgress(data.trans_id, 'sync');
        }
    } catch (error) {
        jobProgress.end('Gagal menarik data: ' + error.message, false);
    }
}

function startPollingProgress(transId, type = 'sync') {
    if (syncPollInterval) clearInterval(syncPollInterval);

    const startedAt = Date.now();
    let lastChangeAt = Date.now();
    let lastProcessed = -1;
    const stop = () => { clearInterval(syncPollInterval); syncPollInterval = null; };

    const poll = async () => {
        const now = Date.now();
        if (now - lastChangeAt > STALL_LIMIT_MS || now - startedAt > HARD_LIMIT_MS) {
            stop();
            const msg = `Proses berhenti: ${NO_REPLY_HINT}`;
            if (type === 'set_time' || type === 'restart') showToast(msg, 'error', 8000);
            else jobProgress.end(msg, false);
            return;
        }

        let data;
        try {
            const res = await fetch(`/devices/transactions/${transId}`, { headers: getReqHeaders() });
            if (!res.ok) return;
            data = await res.json();
        } catch (e) {
            console.error('Polling error', e);
            return;
        }

        // Perintah sederhana (set waktu, restart): cukup notifikasi di akhir
        if (type === 'set_time' || type === 'restart') {
            const label = type === 'restart' ? 'Restart mesin' : 'Sinkron jam mesin';
            if (data.status === 'SUCCESS') { stop(); showToast(`${label} berhasil dikonfirmasi mesin.`, 'success'); }
            else if (data.status === 'FAILED') { stop(); showToast(`${label} gagal. Coba lagi.`, 'error', 8000); }
            return;
        }

        // Tarik daftar PIN: jumlah belum diketahui sampai mesin membalas
        if (type === 'sync') {
            if (data.status === 'SUCCESS') {
                stop();
                jobProgress.hide();
                if (data.data && data.data.pin_arr) {
                    showSyncUsersModal(data.data.pin_arr);
                } else {
                    showToast('Tidak ada karyawan di mesin ini.', 'info');
                }
            } else if (data.status === 'FAILED') {
                stop();
                jobProgress.end('Penarikan data gagal. Periksa log mesin.', false);
            }
            return;
        }

        // Tarik data per karyawan: ada jumlah item
        if (data.total_items > 0) {
            if (data.processed_items !== lastProcessed) {
                lastProcessed = data.processed_items;
                lastChangeAt = Date.now();
            }
            jobProgress.update(data.processed_items, data.total_items, `Meminta data karyawan dari mesin: ${data.processed_items} dari ${data.total_items}`);
        }
        const finished = data.status !== 'PENDING';
        if (finished && data.status === 'SUCCESS') {
            stop();
            const failed = (data.data && data.data.failed) || 0;
            const sent = data.total_items - failed;
            const msg = `${sent} permintaan terkirim${failed ? `, ${failed} gagal` : ''}. Jawaban mesin masuk bertahap.`;
            jobProgress.end(msg, failed === 0);
            fetchDevices();
        } else if (data.status === 'FAILED') {
            stop();
            jobProgress.end('Semua permintaan gagal dikirim ke fingerspot.io. Periksa mesin dan koneksi.', false);
        }
    };

    if (type === 'sync_users_progress') {
        jobProgress.show('Meminta data karyawan dari mesin...');
    }
    syncPollInterval = setInterval(poll, 2000);
    poll();
}

// Modal Logic for Sync Users
async function showSyncUsersModal(devicePins) {
    document.getElementById('sync-users-modal').style.display = 'flex';
    const listEl = document.getElementById('sync-users-list-container');
    if (listEl) listEl.innerHTML = '<p class="loading">Memeriksa status karyawan...</p>';
    
    try {
        const response = await fetch('/employees/?limit=10000', { headers: getReqHeaders() });
        const resData = await response.json();
        const employees = Array.isArray(resData) ? resData : (resData.data || resData.items || []);

        
        const existingPins = {};
        employees.forEach(emp => {
            if (emp.pin !== undefined && emp.pin !== null) {
                const pStr = String(emp.pin).trim();
                existingPins[pStr] = emp.full_name || 'No Name';
                const intVal = parseInt(pStr, 10);
                if (!isNaN(intVal)) {
                    existingPins[String(intVal)] = emp.full_name || 'No Name';
                }
            }
        });
        
        let newCount = 0;
        let existingCount = 0;
        let html = '';
        
        devicePins.forEach(rawPin => {
            const pinStr = escapeHtml(String(rawPin ?? '').trim());
            const exists = existingPins.hasOwnProperty(pinStr);
            if (exists) existingCount++;
            else newCount++;
            
            const empName = existingPins[pinStr] || '';
            const labelStr = exists ? `PIN: ${pinStr} (${escapeHtml(empName)})` : `PIN: ${pinStr} (Karyawan Baru)`;
            const colorStyle = exists ? 'color: #334155; font-weight: 500;' : 'color: #0f172a; font-weight: 600;';
            const badge = exists 
                ? '<span style="font-size: 0.725rem; background: #f1f5f9; color: #64748b; padding: 2px 8px; border-radius: 4px; margin-left: 8px;">Terdaftar</span>'
                : '<span style="font-size: 0.725rem; background: #d1fae5; color: #065f46; padding: 2px 8px; border-radius: 4px; margin-left: 8px; font-weight: 600;">Baru</span>';
            const dataNewAttr = exists ? 'data-is-new="false"' : 'data-is-new="true"';
            
            html += `
                <label style="display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0.75rem; border-radius: 6px; margin-bottom: 0.35rem; background: #ffffff; border: 1px solid var(--border); cursor: pointer; transition: background 0.15s;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='#ffffff'">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <input type="checkbox" id="sync-pin-${pinStr}" value="${pinStr}" class="sync-user-checkbox" ${dataNewAttr} onchange="updateSyncUsersSelectedCount()" style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary);">
                        <span style="${colorStyle}">${labelStr}</span>
                    </div>
                    ${badge}
                </label>`;
        });
        
        document.getElementById('sync-users-summary').innerText = `Ditemukan ${devicePins.length} PIN di mesin. ${newCount} baru, ${existingCount} sudah terdaftar di database.`;
        if (listEl) listEl.innerHTML = html;
        updateSyncUsersSelectedCount();
        
    } catch (e) {
        console.error("Error in showSyncUsersModal:", e);
        if (listEl) listEl.innerHTML = `<p style="color: var(--destructive); padding: 1rem;">Gagal memeriksa data karyawan: ${escapeHtml(e.message)}</p>`;
    }
}

function updateSyncUsersSelectedCount() {
    const count = document.querySelectorAll('.sync-user-checkbox:checked').length;
    const el = document.getElementById('sync-users-selected-count');
    if (el) el.innerText = `${count} dipilih`;
}

function selectAllNewUsers() {
    document.querySelectorAll('.sync-user-checkbox').forEach(cb => {
        if (cb.getAttribute('data-is-new') === 'true') {
            cb.checked = true;
        } else {
            cb.checked = false;
        }
    });
    updateSyncUsersSelectedCount();
}

function selectAllDeviceUsers() {
    document.querySelectorAll('.sync-user-checkbox').forEach(cb => { cb.checked = true; });
    updateSyncUsersSelectedCount();
}

function deselectAllUsers() {
    document.querySelectorAll('.sync-user-checkbox').forEach(cb => {
        cb.checked = false;
    });
    updateSyncUsersSelectedCount();
}

function hideSyncUsersModal() {
    document.getElementById('sync-users-modal').style.display = 'none';
}


async function saveSelectedUsersToEmployees() {
    const selectedPins = Array.from(document.querySelectorAll('.sync-user-checkbox:checked')).map(cb => cb.value);
    
    if (selectedPins.length === 0) {
        alert("Silakan pilih setidaknya 1 PIN karyawan untuk ditarik ke database.");
        return;
    }
    
    if (!currentSyncDeviceId) {
        alert("Tidak ada perangkat yang dipilih.");
        return;
    }
    
    hideSyncUsersModal();
    
    try {
        const response = await fetch("/devices/" + currentSyncDeviceId + "/sync-selected-users", {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ pin_arr: selectedPins })
        });
        
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Gagal memulai proses penarikan data.");
        
        startPollingProgress(data.trans_id, 'sync_users_progress');
        
    } catch (e) {
        alert("Error starting sync: " + e.message);
    }
}

function pullEmployeesFromDevice(deviceId) {
    return fetchData(deviceId);
}

// Push / Upload Employees to Device Logic
window.allPushEmployeesData = [];

async function showPushEmployeesModal(deviceId, deviceName) {
    currentSyncDeviceId = deviceId;
    const targetSub = document.getElementById('push-employees-summary');
    if (targetSub) targetSub.innerText = `Pilih karyawan dari database untuk diunggah ke mesin "${deviceName}"`;
    document.getElementById('push-employees-modal').style.display = 'flex';
    const listEl = document.getElementById('push-employees-list-container');
    if (listEl) listEl.innerHTML = '<p class="loading" style="text-align: center; color: #64748b; padding: 1.5rem;">Memuat daftar karyawan dari database...</p>';
    const searchEl = document.getElementById('push_employee_search');
    if (searchEl) searchEl.value = '';
    
    try {
        const response = await fetch('/employees/?limit=10000', { headers: getReqHeaders() });
        const resData = await response.json();
        const employees = Array.isArray(resData) ? resData : (resData.data || resData.items || []);
        // Karyawan nonaktif tidak bisa dikirim ke mesin
        const activeEmployees = employees.filter(emp => emp.is_active);
        window.allPushEmployeesData = activeEmployees;
        renderPushEmployeesList(activeEmployees);

    } catch (e) {
        if (listEl) listEl.innerHTML = `<p style="color: var(--destructive); text-align: center; padding: 1rem;">Gagal memuat data karyawan: ${escapeHtml(e.message)}</p>`;
    }

    lucide.createIcons();
}

function hidePushEmployeesModal() {
    document.getElementById('push-employees-modal').style.display = 'none';
}

const NO_TEMPLATE_HINT = 'Tarik dulu karyawan ini dari mesin tempat sidik jarinya terdaftar. Kalau dikirim sekarang, karyawan bisa tidak dikenali di mesin tujuan.';

function renderPushEmployeesList(employees) {
    const container = document.getElementById('push-employees-list-container');
    if (!container) return;
    if (!employees || employees.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #64748b; padding: 1rem;">Tidak ada karyawan ditemukan.</p>';
        updatePushSelectedCount();
        return;
    }

    container.innerHTML = employees.map(emp => `
        <label style="display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0.75rem; border-radius: 6px; margin-bottom: 0.35rem; background: #ffffff; border: 1px solid var(--border); cursor: pointer; transition: background 0.15s;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='#ffffff'">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <input type="checkbox" value="${emp.id}" class="push-emp-checkbox" data-has-template="${emp.has_device_template ? 'true' : 'false'}" onchange="updatePushSelectedCount()" style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary);">
                <div>
                    <span style="font-weight: 600; color: #0f172a;">${escapeHtml(emp.full_name || 'Tanpa Nama')}</span>
                    <span style="font-size: 0.8rem; color: #64748b; margin-left: 0.5rem;">PIN: <strong style="color: var(--primary);">${escapeHtml(emp.pin)}</strong></span>
                    ${emp.has_device_template ? '' : `<span style="font-size: 0.8rem; color: var(--signal); margin-left: 0.5rem;" title="${NO_TEMPLATE_HINT}">Belum ada sidik jari</span>`}
                </div>
            </div>
            <div style="font-size: 0.8rem; color: #64748b;">
                ${escapeHtml(emp.department_name || '-')} | ${escapeHtml(emp.position_name || '-')}
            </div>
        </label>
    `).join('');
    
    updatePushSelectedCount();
    lucide.createIcons();
}

function filterPushEmployeeList() {
    const search = (document.getElementById('push_employee_search')?.value || '').toLowerCase();
    const filtered = window.allPushEmployeesData.filter(emp => 
        (emp.full_name && emp.full_name.toLowerCase().includes(search)) ||
        (emp.pin && emp.pin.toString().includes(search)) ||
        (emp.department_name && emp.department_name.toLowerCase().includes(search))
    );
    renderPushEmployeesList(filtered);
}

function selectAllPushEmployees(checked = true) {
    document.querySelectorAll('.push-emp-checkbox').forEach(cb => {
        cb.checked = checked;
    });
    updatePushSelectedCount();
}

function deselectAllPushEmployees() {
    selectAllPushEmployees(false);
}

function updatePushSelectedCount() {
    const count = document.querySelectorAll('.push-emp-checkbox:checked').length;
    const noTemplate = document.querySelectorAll('.push-emp-checkbox:checked[data-has-template="false"]').length;
    const label = document.getElementById('push-selected-count');
    if (label) {
        label.innerText = noTemplate > 0
            ? `${count} karyawan terpilih, ${noTemplate} belum ada sidik jari`
            : `${count} karyawan terpilih`;
    }
}

async function submitPushEmployeesToDevice() {
    const selectedIds = Array.from(document.querySelectorAll('.push-emp-checkbox:checked')).map(cb => parseInt(cb.value));
    const deviceId = currentSyncDeviceId;

    if (selectedIds.length === 0) {
        alert("Silakan pilih setidaknya 1 karyawan yang akan di-upload ke mesin.");
        return;
    }

    const btn = document.getElementById('btn-submit-push-employees');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Mengirim...';
    }

    try {
        const response = await fetch(`/devices/${deviceId}/push-employees`, {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ employee_ids: selectedIds })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Gagal memulai upload data karyawan.");
        }

        hidePushEmployeesModal();
        showToast(data.message, 'success', 8000);
        fetchDevices();
    } catch (e) {
        alert("Error: " + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Kirim ke mesin';
        }
    }
}


