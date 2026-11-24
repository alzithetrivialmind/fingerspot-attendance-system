// activity_log.js
// Halaman Log aktivitas: jejak audit siapa melakukan apa dan kapan (GET /activity-logs)

let currentLogPage = 1;
let activityLogUsersLoaded = false;

// Kode aksi backend -> [label, warna badge]
const ACTIVITY_LABELS = {
    LOGIN: ['Login', 'neutral'],
    LOGIN_FAILED: ['Login gagal', 'danger'],
    CHANGE_PASSWORD: ['Ganti password', 'gold'],
    CHANGE_PASSWORD_FAILED: ['Ganti password gagal', 'danger'],
    CREATE_EMPLOYEE: ['Tambah karyawan', 'success'],
    UPDATE_EMPLOYEE: ['Ubah karyawan', 'gold'],
    UPDATE_EMPLOYEE_PHOTO: ['Ubah foto karyawan', 'gold'],
    DELETE_EMPLOYEE: ['Hapus karyawan', 'danger'],
    BULK_DELETE_EMPLOYEES: ['Hapus karyawan massal', 'danger'],
    BULK_UPDATE_EMPLOYEE_STATUS: ['Ubah status massal', 'gold'],
    IMPORT_EMPLOYEES: ['Import karyawan', 'success'],
    PULL_ATTENDANCE: ['Tarik scan dari cloud', 'success'],
    IMPORT_ATTENDANCE: ['Import scan', 'success'],
    EXPORT_DATA: ['Unduh data', 'info'],
    CREATE_MASTER_DATA: ['Tambah master data', 'success'],
    UPDATE_MASTER_DATA: ['Ubah master data', 'gold'],
    DELETE_MASTER_DATA: ['Hapus master data', 'danger'],
    CREATE_DEVICE: ['Tambah mesin', 'success'],
    DELETE_DEVICE: ['Hapus mesin', 'danger'],
    FETCH_DEVICE_USERS: ['Tarik karyawan dari mesin', 'neutral'],
    SET_DEVICE_TIME: ['Setel jam mesin', 'gold'],
    RESTART_DEVICE: ['Restart mesin', 'gold'],
    SYNC_DEVICE_USERS: ['Simpan karyawan dari mesin', 'gold'],
    PUSH_EMPLOYEES: ['Kirim karyawan ke mesin', 'gold'],
    RETRY_DEVICE_SYNC: ['Kirim ulang sinkron gagal', 'gold'],
    CREATE_USER: ['Tambah pengguna', 'success'],
    UPDATE_USER: ['Ubah pengguna', 'gold'],
    DELETE_USER: ['Hapus pengguna', 'danger'],
    BACKUP_AUTO: ['Backup otomatis', 'neutral'],
    BACKUP_MANUAL: ['Backup manual', 'success'],
    RESTORE_DATABASE: ['Restore database', 'danger'],
};

function initActivityLog() {
    if (!activityLogUsersLoaded) loadActivityLogUsers();
    return loadActivityLogs(1);
}

async function loadActivityLogUsers() {
    try {
        const res = await fetch('/activity-logs/users', { headers: getReqHeaders() });
        if (!res.ok) return;
        const users = await res.json();
        const sel = document.getElementById('log_filter_user');
        sel.innerHTML = '<option value="">Semua pengguna</option>' +
            users.map(u => `<option value="${escapeHtml(u)}">${escapeHtml(u)}</option>`).join('');
        activityLogUsersLoaded = true;
    } catch (e) {
        console.error('Gagal memuat daftar pengguna log', e);
    }
}

function resetActivityLogFilters() {
    ['log_filter_search', 'log_filter_start', 'log_filter_end', 'log_filter_user', 'log_filter_category']
        .forEach(id => { document.getElementById(id).value = ''; });
    return loadActivityLogs(1);
}

function formatLogTime(ts) {
    const d = new Date(ts);
    return d.toLocaleString('id-ID', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}

async function loadActivityLogs(page = 1) {
    currentLogPage = Math.max(page, 1);
    const tbody = document.getElementById('activity-log-tbody');
    tbody.innerHTML = '<tr><td colspan="4" class="loading">Memuat log...</td></tr>';

    const params = new URLSearchParams({
        page: currentLogPage,
        limit: document.getElementById('log_limit_select').value || 50
    });
    const filters = {
        search: 'log_filter_search', from_date: 'log_filter_start', to_date: 'log_filter_end',
        username: 'log_filter_user', category: 'log_filter_category'
    };
    Object.entries(filters).forEach(([key, id]) => {
        const val = document.getElementById(id).value.trim();
        if (val) params.append(key, val);
    });

    let result;
    try {
        const res = await fetch('/activity-logs/?' + params.toString(), { headers: getReqHeaders() });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        result = await res.json();
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="4" style="color: var(--danger); text-align: center;">Gagal memuat log: ${escapeHtml(error.message)}</td></tr>`;
        return;
    }

    if (result.data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">Tidak ada aktivitas yang cocok dengan filter ini.</td></tr>';
    } else {
        tbody.innerHTML = result.data.map(log => {
            const [label, tone] = ACTIVITY_LABELS[log.action] || [log.action, 'neutral'];
            return `<tr>
                <td class="num" style="white-space: nowrap;">${escapeHtml(formatLogTime(log.timestamp))}</td>
                <td style="font-weight: 600;">${escapeHtml(log.username)}</td>
                <td><span class="badge badge-${tone}">${escapeHtml(label)}</span></td>
                <td style="white-space: normal; word-break: break-word;">${escapeHtml(log.details || '-')}</td>
            </tr>`;
        }).join('');
    }

    const startIdx = result.total > 0 ? ((result.page - 1) * result.limit) + 1 : 0;
    const endIdx = Math.min(result.page * result.limit, result.total);
    document.getElementById('log_pagination_info').innerText = `${startIdx}–${endIdx} dari ${result.total} aktivitas`;
    document.getElementById('log_page_display').innerText = `Halaman ${result.page} dari ${result.total_pages || 1}`;
    document.getElementById('log_prev_btn').disabled = result.page <= 1;
    document.getElementById('log_next_btn').disabled = result.page >= result.total_pages;
}
