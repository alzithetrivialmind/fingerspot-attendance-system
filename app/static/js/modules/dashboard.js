// Dashboard State
let currentDashboardLogs = [];

// Format Indonesian Date
function updateDashboardDateDisplay() {
    try {
        const now = new Date();
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        const dateStr = now.toLocaleDateString('id-ID', options);
        const dateText = document.getElementById('dashboard-date-text');
        if (dateText) dateText.innerText = dateStr;
        if (typeof updateUserGreeting === 'function') updateUserGreeting();
    } catch (e) {
        console.error(e);
    }
}

// Fetch Attendance Data & Calculate KPI Stats
async function fetchAttendance() {
    updateDashboardDateDisplay();
    const tbody = document.getElementById('attendance-tbody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="loading">Memuat data absensi...</td></tr>';

    try {
        const todayStr = localDateStr(new Date());
        const startDt = todayStr + 'T00:00:00';
        const endDt = todayStr + 'T23:59:59';
        
        const [attRes, empRes] = await Promise.all([
            fetch(`/attendance/?from_date=${startDt}&to_date=${endDt}&limit=5000`, { headers: getReqHeaders() }),
            fetch(`/employees/?limit=1&is_active=true`, { headers: getReqHeaders() })
        ]);

        let data = [];
        let totalEmpCount = 0;

        if (attRes.ok) {
            const result = await attRes.json();
            data = result.data || [];
        }

        if (empRes.ok) {
            const empResult = await empRes.json();
            totalEmpCount = empResult.total || (empResult.items || []).length || (empResult.data || []).length || 0;
        }


        currentDashboardLogs = data;
        renderDashboardStats(data, totalEmpCount);
        renderDashboardTable(data);
    } catch (error) {
        console.error(error);
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="color: var(--danger); text-align: center;">Gagal memuat data: ${escapeHtml(error.message)}</td></tr>`;
    }
}

// Calculate and Render KPI Cards
function renderDashboardStats(logs, totalEmp) {
    const totalScans = logs.length;
    
    // Unique employees present today
    const uniquePins = new Set();

    logs.forEach(log => uniquePins.add(String(log.employee_pin)));

    const presentCount = uniquePins.size;
    const baseTotal = Math.max(totalEmp || 0, presentCount, 1);
    const absentCount = Math.max(0, (totalEmp || 0) - presentCount);

    const setText = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };
    setText('stat-ontime-today', presentCount);
    setText('stat-absent-today', absentCount);
    setText('stat-total-emp', totalEmp || presentCount);
    setText('stat-total-scans', totalScans);

    // Bar: yang sudah scan dari total karyawan aktif; sisanya (belum scan) = latar
    const pct = n => `${(n / baseTotal) * 100}%`;
    const ontimeSeg = document.getElementById('tally-ontime');
    if (ontimeSeg) ontimeSeg.style.width = pct(presentCount);
    const bar = document.getElementById('tally-bar');
    if (bar) bar.setAttribute('aria-label', `${presentCount} sudah scan, ${absentCount} belum scan dari ${totalEmp} karyawan aktif`);
}

// Render Table Rows
function renderDashboardTable(data) {
    const tbody = document.getElementById('attendance-tbody');
    if (!tbody) return;

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-secondary); padding: 2rem;">Belum ada scan hari ini. Data muncul otomatis begitu karyawan scan di mesin.</td></tr>';
        return;
    }

    const firstScanAt = {};
    data.forEach(item => {
        const t = new Date(item.scan_time).getTime();
        const pin = String(item.employee_pin);
        if (!(pin in firstScanAt) || t < firstScanAt[pin]) firstScanAt[pin] = t;
    });
    const SOURCE_LABEL = { REALTIME: 'Langsung', PULLED: 'Tarik API', IMPORTED: 'Import file' };

    tbody.innerHTML = data.map(item => {
        const scanDate = new Date(item.scan_time);
        const isFirst = firstScanAt[String(item.employee_pin)] === scanDate.getTime();
        const status = isFirst
            ? '<span class="badge badge-success">Scan pertama</span>'
            : '<span class="text-muted">Scan lanjutan</span>';

        return `
            <tr>
                <td style="font-weight: 500;">${escapeHtml(item.employee_name || 'Tanpa nama')}</td>
                <td class="num">${escapeHtml(item.employee_pin)}</td>
                <td class="num">${scanDate.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</td>
                <td>${escapeHtml(item.device_sn || '-')} <span class="text-muted">· ${SOURCE_LABEL[item.source] || escapeHtml(item.source || '-')}</span></td>
                <td>${status}</td>
                <td class="num text-muted">${item.verify_mode ?? '-'}</td>
            </tr>
        `;
    }).join('');

    if (window.lucide) lucide.createIcons();
}

// Search Filter in Dashboard Table
function filterDashboardTable() {
    const query = (document.getElementById('dashboard-search-input')?.value || '').toLowerCase().trim();
    if (!query) {
        renderDashboardTable(currentDashboardLogs);
        return;
    }
    const filtered = currentDashboardLogs.filter(item => {
        const name = (item.employee_name || '').toLowerCase();
        const pin = String(item.employee_pin || '').toLowerCase();
        return name.includes(query) || pin.includes(query);
    });
    renderDashboardTable(filtered);
}


