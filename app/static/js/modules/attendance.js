// --- Pull Attendance Logic ---

async function loadDevicesForPull() {
    try {
        const response = await fetch('/devices/', { headers: getReqHeaders() });
        const devices = await response.json();
        
        const select = document.getElementById('pull-device-select');
        select.innerHTML = '<option value="">Pilih mesin</option>';
        
        // Add "All Devices" option
        const allOpt = document.createElement('option');
        allOpt.value = 'ALL';
        allOpt.textContent = 'Semua mesin';
        allOpt.style.fontWeight = 'bold';
        select.appendChild(allOpt);

        devices.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.cloud_id;
            opt.textContent = `${d.name} (${d.cloud_id})`;
            select.appendChild(opt);
        });
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

async function startMassPull() {
    const cloudId = document.getElementById('pull-device-select').value;
    const startDateStr = document.getElementById('pull-start-date').value;
    const endDateStr = document.getElementById('pull-end-date').value;

    if (!cloudId || !startDateStr || !endDateStr) {
        showToast("Pilih mesin dan isi rentang tanggal terlebih dahulu.", "error");
        return;
    }

    const startDate = new Date(startDateStr);
    const endDate = new Date(endDateStr);

    if (startDate > endDate) {
        showToast("Tanggal awal tidak boleh setelah tanggal akhir.", "error");
        return;
    }

    // Determine target devices
    const targetDevices = cloudId === 'ALL' 
        ? Array.from(document.getElementById('pull-device-select').options).map(o => o.value).filter(v => v && v !== 'ALL')
        : [cloudId];

    if (targetDevices.length === 0) {
        showToast("Tidak ada mesin yang bisa ditarik.", "error");
        return;
    }

    // Split into chunks of max 2 days
    const chunks = [];
    let currentStart = new Date(startDate);
    
    while (currentStart <= endDate) {
        let currentEnd = new Date(currentStart);
        currentEnd.setDate(currentStart.getDate() + 2);
        
        if (currentEnd > endDate) {
            currentEnd = new Date(endDate);
        }
        
        chunks.push({
            start: localDateStr(currentStart),
            end: localDateStr(currentEnd)
        });
        
        currentStart = new Date(currentEnd);
        currentStart.setDate(currentEnd.getDate() + 1);
    }

    // Prepare total requests list
    const fetchRequests = [];
    targetDevices.forEach(device => {
        chunks.forEach(chunk => {
            fetchRequests.push({ device, start: chunk.start, end: chunk.end });
        });
    });

    // Update UI
    const progressContainer = document.getElementById('mass-pull-progress-container');
    const progressBar = document.getElementById('mass-pull-progress-bar');
    const progressText = document.getElementById('mass-pull-progress-text');
    const progressPercentage = document.getElementById('mass-pull-progress-percentage');
    const progressStats = document.getElementById('mass-pull-stats');
    const btn = document.getElementById('btn-pull-attendance');
    
    progressContainer.style.display = 'block';
    progressText.style.color = '';
    btn.disabled = true;
    
    let totalProcessed = 0;
    const totalCount = fetchRequests.length;
    
    for (let i = 0; i < totalCount; i++) {
        const req = fetchRequests[i];
        
        progressText.innerText = `Menarik ${req.start} s/d ${req.end} dari mesin ${req.device} (${i+1} dari ${totalCount})`;
        const percentage = Math.round((i / totalCount) * 100);
        progressBar.style.width = percentage + '%';
        progressPercentage.innerText = percentage + '%';
        
        try {
            const res = await fetch('/attendance/pull', {
                method: 'POST',
                headers: {
                    ...getReqHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    cloud_id: req.device,
                    start_date: req.start,
                    end_date: req.end
                })
            });
            
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'API Error');
            }
            
            const data = await res.json();
            totalProcessed += data.total_processed || 0;
            progressStats.innerText = `Scan diproses sejauh ini: ${totalProcessed}`;
            
            // Artificial delay to prevent spamming Fingerspot API too fast
            await new Promise(r => setTimeout(r, 1000));
            
        } catch (e) {
            console.error(e);
            progressText.innerText = `Berhenti: gagal menarik ${req.start} s/d ${req.end} dari mesin ${req.device}. ${e.message}`;
            progressText.style.color = 'var(--signal)';
            showToast('Penarikan scan berhenti karena error. Lihat keterangan di panel.', 'error', 8000);
            btn.disabled = false;
            return;
        }
    }
    
    // Complete
    progressBar.style.width = '100%';
    progressPercentage.innerText = '100%';
    progressText.innerText = 'Selesai';
    progressStats.innerText = `Total scan diproses: ${totalProcessed}`;
    btn.disabled = false;
    showToast(`Penarikan scan selesai: ${totalProcessed} scan diproses.`, 'success');

    // Show results panel and fetch data (refresh it)
    loadPaginatedAttendance(1);
}

// --- Server-Side Pull Results Rendering ---
let currentAttPage = 1;

async function initAttendanceFilters() {
    try {
        // Fetch Master Data for dropdowns
        const [deptsRes, posRes, compRes] = await Promise.all([
            fetch('/master-data/departments', { headers: getReqHeaders() }),
            fetch('/master-data/positions', { headers: getReqHeaders() }),
            fetch('/master-data/companies', { headers: getReqHeaders() })
        ]);

        const depts = await deptsRes.json();
        const positions = await posRes.json();
        const companies = await compRes.json();

        document.getElementById('att_filter_dept').innerHTML = '<option value="">Semua departemen</option>' + depts.map(d => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join('');
        document.getElementById('att_filter_pos').innerHTML = '<option value="">Semua jabatan</option>' + positions.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
        document.getElementById('att_filter_comp').innerHTML = '<option value="">Semua perusahaan</option>' + companies.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
    } catch (error) {
        console.error("Failed to load master data for filters:", error);
    }
}

async function loadPaginatedAttendance(page = 1) {
    currentAttPage = page;
    const tbody = document.getElementById('pull-results-tbody');
    tbody.innerHTML = '<tr><td colspan="7" class="loading">Memuat data absensi...</td></tr>';
    
    // Get filter values
    const search = document.getElementById('att_filter_search')?.value.trim() || '';
    const startDt = document.getElementById('att_filter_start')?.value || '';
    const endDt = document.getElementById('att_filter_end')?.value || '';
    const deptId = document.getElementById('att_filter_dept')?.value || '';
    const posId = document.getElementById('att_filter_pos')?.value || '';
    const compId = document.getElementById('att_filter_comp')?.value || '';
    const source = document.getElementById('att_filter_source')?.value || '';
    const limit = document.getElementById('att_limit_select')?.value || '50';
    
    // Build query params
    const params = new URLSearchParams({
        page: page,
        limit: limit
    });
    
    if (search) params.append('search', search);
    if (startDt) params.append('from_date', startDt + 'T00:00:00');
    if (endDt) params.append('to_date', endDt + 'T23:59:59');
    if (deptId) params.append('department_id', deptId);
    if (posId) params.append('position_id', posId);
    if (compId) params.append('company_id', compId);
    if (source) params.append('source', source);

    try {
        const response = await fetch(`/attendance/?${params.toString()}`, { headers: getReqHeaders() });
        if (!response.ok) throw new Error('Failed to fetch attendance database');
        
        const result = await response.json();
        renderPaginatedResults(result);

    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="7" style="color: var(--danger); text-align: center;">Gagal memuat data absensi: ${escapeHtml(error.message)}</td></tr>`;
    }
}

function renderPaginatedResults(result) {
    const data = result.data;
    const tbody = document.getElementById('pull-results-tbody');
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-secondary);">Tidak ada scan yang cocok dengan filter ini.</td></tr>';
    } else {
        const SOURCE_LABEL = { REALTIME: 'Langsung', PULLED: 'Tarik cloud', IMPORTED: 'Import file' };
        tbody.innerHTML = data.map(item => {
            const src = (item.source || 'REALTIME').toUpperCase();
            return `
            <tr>
                <td style="font-weight: 500;">${escapeHtml(item.employee_name || '-')}</td>
                <td class="num">${escapeHtml(item.employee_pin)}</td>
                <td class="num text-muted">${escapeHtml(item.employee_nik || '-')}</td>
                <td class="num">${new Date(item.scan_time).toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}</td>
                <td class="text-muted">${escapeHtml(item.device_sn || '-')}</td>
                <td class="num text-muted">${item.verify_mode !== null ? item.verify_mode : '-'}</td>
                <td>${SOURCE_LABEL[src] || escapeHtml(src)}</td>
            </tr>
        `;
        }).join('');
    }
    
    // Update pagination controls
    const totalPages = result.total_pages;
    const startIdx = result.total > 0 ? ((result.page - 1) * result.limit) + 1 : 0;
    const endIdx = Math.min(result.page * result.limit, result.total);
    
    document.getElementById('att_pagination_info').innerText = `${startIdx}–${endIdx} dari ${result.total} scan`;
    document.getElementById('att_page_display').innerText = `Halaman ${result.page} dari ${totalPages || 1}`;
    
    document.getElementById('att_prev_btn').disabled = result.page <= 1;
    document.getElementById('att_next_btn').disabled = result.page >= totalPages;
}

function changeAttPage(delta) {
    loadPaginatedAttendance(currentAttPage + delta);
}

function exportAttendance() {
    const todayStr = localDateStr(new Date());
    const startDt = todayStr + 'T00:00:00';
    const endDt = todayStr + 'T23:59:59';
    return downloadCSV('/attendance/export?from_date=' + startDt + '&to_date=' + endDt, `absensi_${todayStr}.xlsx`);
}

function exportPaginatedAttendance() {
    let query = '?';
    
    const search = document.getElementById('att_filter_search')?.value || '';
    if (search) query += 'search=' + encodeURIComponent(search) + '&';
    
    const start = document.getElementById('att_filter_start')?.value || '';
    if (start) query += 'from_date=' + start + 'T00:00:00&';
    
    const end = document.getElementById('att_filter_end')?.value || '';
    if (end) query += 'to_date=' + end + 'T23:59:59&';
    
    const dept = document.getElementById('att_filter_dept')?.value || '';
    if (dept) query += 'department_id=' + dept + '&';
    
    const pos = document.getElementById('att_filter_pos')?.value || '';
    if (pos) query += 'position_id=' + pos + '&';
    
    const comp = document.getElementById('att_filter_comp')?.value || '';
    if (comp) query += 'company_id=' + comp + '&';

    const src = document.getElementById('att_filter_source')?.value || '';
    if (src) query += 'source=' + encodeURIComponent(src) + '&';

    return downloadCSV('/attendance/export' + query, `data_presensi_${start || 'awal'}_${end || 'akhir'}.xlsx`);
}

// Export CSV Functions
function downloadTemplate(url, filename) {
    return downloadCSV(url, filename);
}

// Unduh file dari endpoint ber-JWT. Mengembalikan Promise (dipakai tombol sibuk).
function downloadCSV(url, filename) {
    return fetch(url, { headers: getReqHeaders() })
        .then(async response => {
            if (!response.ok) {
                let detail = `HTTP ${response.status}`;
                try { detail = (await response.json()).detail || detail; } catch (e) {}
                throw new Error(detail);
            }
            return response.blob();
        })
        .then(blob => {
            const windowUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = windowUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(windowUrl);
            showToast(`File diunduh: ${filename}`, 'success');
        })
        .catch(err => showToast('Gagal mengunduh file: ' + err.message, 'error', 7000));
}

