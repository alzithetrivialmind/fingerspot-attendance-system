// Posisi halaman disimpan di URL (#view/sub) agar refresh tetap di halaman yang sama
const SETTINGS_SUBMENUS = ['master-data-submenu', 'devices-submenu', 'import-data-submenu', 'users-submenu', 'backup-submenu'];

function saveLocation(view, sub) {
    try {
        history.replaceState(null, '', sub ? `#${view}/${sub}` : `#${view}`);
    } catch (e) { /* posisi hanya kemudahan, halaman tetap jalan tanpanya */ }
}

function openSubLocation(view) {
    if (view === 'settings') {
        return SETTINGS_SUBMENUS.find(id => document.getElementById(id)?.style.display === 'block');
    }
    return undefined;
}

// Dipanggil setelah hak akses diterapkan. Halaman yang tidak boleh dibuka role ini diabaikan.
function restoreLocation() {
    const match = location.hash.match(/^#([a-z-]+)(?:\/([a-z-]+))?$/);
    if (!match) return false;
    const [, view, sub] = match;
    const nav = document.querySelector(`li.nav-item[onclick="switchView('${view}')"]`);
    if (!nav || nav.style.display === 'none') return false;
    nav.click();

    if (view === 'settings' && SETTINGS_SUBMENUS.includes(sub)) {
        const card = document.querySelector(`div[onclick="toggleSettingsSubmenu('${sub}')"]`);
        if (card && card.style.display !== 'none') toggleSettingsSubmenu(sub);
    }
    saveLocation(view, openSubLocation(view));
    return true;
}

// Switch view logic
function switchView(viewId) {
    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    event.currentTarget.classList.add('active');

    // Update view visibility
    document.querySelectorAll('.view-section').forEach(section => {
        section.classList.remove('active');
        section.style.display = 'none';
    });
    const target = document.getElementById(`${viewId}-view`);
    if (target) {
        target.classList.add('active');
        target.style.display = 'block';
    }

    // Trigger data fetch based on view
    if (viewId === 'dashboard') {
        fetchAttendance();
    } else if (viewId === 'employees') {
        fetchEmployees();
    } else if (viewId === 'devices') {
        fetchDevices();
    } else if (viewId === 'pull-attendance') {
        initAttendanceFilters();
        loadPaginatedAttendance(1);
        loadDevicesForPull();
    } else if (viewId === 'activity-log') {
        initActivityLog();
    }
    saveLocation(viewId, openSubLocation(viewId));
}

// Toggle Settings Submenu
function toggleSettingsSubmenu(menuId) {
    const main = document.getElementById('settings-main-menu');
    const masterDataSubmenu = document.getElementById('master-data-submenu');
    const devicesSubmenu = document.getElementById('devices-submenu');
    const importDataSubmenu = document.getElementById('import-data-submenu');
    const usersSubmenu = document.getElementById('users-submenu');
    const backupSubmenu = document.getElementById('backup-submenu');

    if (menuId !== 'main' && !document.getElementById(menuId)) {
        alert("Menu tidak ditemukan. Silakan lakukan Hard Refresh (tekan Ctrl + F5) agar perubahan terbaru termuat.");
        return;
    }

    saveLocation('settings', menuId === 'main' ? '' : menuId);

    // Hide all first
    if(main) main.style.display = 'none';
    if(masterDataSubmenu) masterDataSubmenu.style.display = 'none';
    if(devicesSubmenu) devicesSubmenu.style.display = 'none';
    if(importDataSubmenu) importDataSubmenu.style.display = 'none';
    if(usersSubmenu) usersSubmenu.style.display = 'none';
    if(backupSubmenu) backupSubmenu.style.display = 'none';

    if (menuId === 'main') {
        main.style.display = 'grid';
    } else if (menuId === 'master-data-submenu') {
        masterDataSubmenu.style.display = 'block';
        loadMasterDataLists();
    } else if (menuId === 'devices-submenu') {
        devicesSubmenu.style.display = 'block';
        fetchDevices();
    } else if (menuId === 'users-submenu') {
        usersSubmenu.style.display = 'block';
        fetchUsers();
    } else if (menuId === 'backup-submenu') {
        backupSubmenu.style.display = 'block';
        loadBackups();
    } else if (menuId === 'import-data-submenu') {
        importDataSubmenu.style.display = 'block';
        // Reset state when opening import panel
        importSelectedFile = null;
        document.getElementById('import-selected-file').style.display = 'none';
        document.getElementById('import-result-message').style.display = 'none';
        document.getElementById('btn-submit-import').disabled = true;
        const fileInput = document.getElementById('import_file_input');
        if (fileInput) fileInput.value = '';
    }
}

// Global Live Clock & Date Synchronizer across all modules
function startGlobalLiveClock() {
    function tick() {
        const now = new Date();
        const dateOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        const dateStr = now.toLocaleDateString('id-ID', dateOptions);
        
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        const timeStr = `${hours}:${minutes}:${seconds}`;

        // Update all date elements
        document.querySelectorAll('#sidebar-live-date, #dashboard-date-text, .global-date-text').forEach(el => {
            if (el.textContent !== dateStr) el.textContent = dateStr;
        });

        // Update all time elements
        document.querySelectorAll('#sidebar-live-time, #dashboard-live-time, .global-time-text').forEach(el => {
            el.textContent = timeStr;
        });
    }

    tick();
    setInterval(tick, 1000);
}


// ---------------------------------------------------------------------------
// Notifikasi singkat (toast) — pengganti alert untuk hasil aksi
// ---------------------------------------------------------------------------
function showToast(message, type = 'info', timeout = 4500) {
    let stack = document.getElementById('toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.id = 'toast-stack';
        stack.setAttribute('role', 'status');
        stack.setAttribute('aria-live', 'polite');
        document.body.appendChild(stack);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    stack.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('toast-leave');
        setTimeout(() => toast.remove(), 250);
    }, timeout);
}

// ---------------------------------------------------------------------------
// Tombol sibuk: selama aksi berjalan tombol dikunci, berisi spinner + teks,
// klik berulang diabaikan. Fungsi aksi harus mengembalikan Promise.
// ---------------------------------------------------------------------------
// Hanya tombol (atau tombol submit milik form) yang dikunci: fungsi yang sama juga dipanggil
// dari dropdown/menu/polling, dan elemen itu tidak boleh diganti isinya.
function busyTargetOf(evt) {
    const el = evt && evt.currentTarget;
    if (el instanceof HTMLButtonElement) return el;
    if (el instanceof HTMLFormElement) return el.querySelector('button[type="submit"], button:not([type])');
    return null;
}

function wrapBusyAction(name, label) {
    const fn = window[name];
    if (typeof fn !== 'function' || fn.__busyWrapped) return;
    const wrapped = function (...args) {
        const btn = busyTargetOf(window.event);
        // Panggilan bersarang di klik yang sama (aksi memanggil aksi lain) tetap dijalankan
        if (!btn || wrapBusyAction.running) return fn.apply(this, args);
        if (btn.dataset.busy === '1') return;

        const originalHtml = btn.innerHTML;
        btn.dataset.busy = '1';
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        btn.style.minWidth = `${btn.offsetWidth}px`;
        btn.innerHTML = `<span class="btn-spinner" aria-hidden="true"></span><span>${label}</span>`;

        const restore = () => {
            btn.dataset.busy = '';
            btn.disabled = false;
            btn.removeAttribute('aria-busy');
            btn.style.minWidth = '';
            btn.innerHTML = originalHtml;
            if (window.lucide) lucide.createIcons();
        };
        let result;
        wrapBusyAction.running = true;
        try {
            result = fn.apply(this, args);
        } catch (e) {
            restore();
            throw e;
        } finally {
            wrapBusyAction.running = false;
        }
        Promise.resolve(result).finally(restore);
        return result;
    };
    wrapped.__busyWrapped = true;
    window[name] = wrapped;
}

const BUSY_ACTIONS = {
    exportAttendance: 'Menyiapkan file...',
    exportPaginatedAttendance: 'Menyiapkan file...',
    exportEmployees: 'Menyiapkan file...',
    downloadTemplate: 'Mengunduh...',
    restartDevice: 'Mengirim perintah...',
    fetchData: 'Menghubungi mesin...',
    saveSelectedUsersToEmployees: 'Mengirim...',
    submitPushEmployeesToDevice: 'Mengirim...',
    // Form (tombol submit ikut dikunci, cegah data dobel)
    submitAddDevice: 'Menyimpan...',
    submitAddEmployee: 'Menyimpan...',
    submitEditEmployee: 'Menyimpan...',
    submitChangePassword: 'Menyimpan...',
    // Master data, pengguna
    addMasterData: 'Menyimpan...',
    updateMasterData: 'Menyimpan...',
    deleteMasterData: 'Menghapus...',
    deleteUser: 'Menghapus...',
    executeBulkStatus: 'Menyimpan...',
    // Mesin
    fetchDeviceInfo: 'Menghubungi mesin...',
    setDeviceTime: 'Mengirim perintah...',
    pullEmployeesFromDevice: 'Menghubungi mesin...',
    retryFailedDeviceSync: 'Mengirim ulang...',
    // Muat ulang / tampilkan data
    fetchAttendance: 'Memuat...',
    loadPaginatedAttendance: 'Memuat...',
    loadPaginatedEmployees: 'Memuat...',
    loadActivityLogs: 'Memuat...',
    resetActivityLogFilters: 'Memuat...',
    loadBackups: 'Memuat...',
    downloadBackup: 'Mengunduh...',
};

document.addEventListener('DOMContentLoaded', () => {
    Object.entries(BUSY_ACTIONS).forEach(([name, label]) => wrapBusyAction(name, label));
});

// ---------------------------------------------------------------------------
// Navigasi di layar kecil: sidebar jadi laci yang dibuka tombol menu
// ---------------------------------------------------------------------------
function toggleNav(open) {
    const sidebar = document.getElementById('app-sidebar');
    const btn = document.getElementById('nav-toggle');
    const backdrop = document.getElementById('nav-backdrop');
    if (!sidebar) return;
    const willOpen = typeof open === 'boolean' ? open : !sidebar.classList.contains('open');
    sidebar.classList.toggle('open', willOpen);
    if (backdrop) backdrop.hidden = !willOpen;
    if (btn) {
        btn.setAttribute('aria-expanded', String(willOpen));
        btn.setAttribute('aria-label', willOpen ? 'Tutup menu' : 'Buka menu');
    }
    if (willOpen) {
        const active = sidebar.querySelector('.nav-item.active') || sidebar.querySelector('.nav-item');
        if (active) active.focus();
    }
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        const sidebar = document.getElementById('app-sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            toggleNav(false);
            document.getElementById('nav-toggle')?.focus();
        }
    }
});

document.addEventListener('click', e => {
    // Pilih menu di laci -> tutup laci
    if (e.target.closest('#app-sidebar .nav-item') && window.matchMedia('(max-width: 768px)').matches) {
        toggleNav(false);
    }
});

window.matchMedia('(max-width: 768px)').addEventListener('change', mq => {
    if (!mq.matches) toggleNav(false);
});
