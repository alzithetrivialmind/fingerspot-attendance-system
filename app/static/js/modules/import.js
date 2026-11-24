// ==========================================
// IMPORT DATA FUNCTIONS (Attendance & Employees)
// ==========================================

let importSelectedFile = null;

function handleImportFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    importSelectedFile = file;

    // Update UI
    const area = document.getElementById('import-upload-area');
    if (area) area.style.display = 'none';
    
    const fileInfo = document.getElementById('import-selected-file');
    if (fileInfo) fileInfo.style.display = 'flex';

    const fnEl = document.getElementById('import-filename');
    if (fnEl) fnEl.textContent = file.name;

    const fsEl = document.getElementById('import-filesize');
    if (fsEl) fsEl.textContent = (file.size / 1024).toFixed(1) + ' KB';

    const btn = document.getElementById('btn-submit-import');
    if (btn) btn.disabled = false;

    const resultEl = document.getElementById('import-result-message');
    if (resultEl) {
        resultEl.style.display = 'none';
        resultEl.textContent = '';
    }
}

async function submitImportData() {
    if (!importSelectedFile) {
        showToast('Pilih file Excel atau CSV terlebih dahulu.', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-import');
    const progressContainer = document.getElementById('import-progress-container');
    const progressText = document.getElementById('import-progress-text');
    const resultEl = document.getElementById('import-result-message');

    // Show progress, disable button
    btn.disabled = true;
    progressContainer.style.display = 'block';
    if (progressText) progressText.textContent = 'Mengunggah dan memproses file...';
    resultEl.style.display = 'none';

    try {
        const formData = new FormData();
        formData.append('file', importSelectedFile);

        const response = await fetch('/attendance/import', {
            method: 'POST',
            headers: getReqHeaders(),
            body: formData
        });

        const data = await response.json();
        progressContainer.style.display = 'none';

        if (response.ok) {
            const successCount = data.total_processed ?? 0;
            const newCount = data.new_records ?? 0;
            const errorCount = data.errors ?? 0;
            const warnings = data.warnings || [];
            let msg = `Import selesai: ${successCount} baris diproses, ${newCount} scan baru disimpan (sisanya sudah ada).`;
            if (warnings.length > 0) {
                msg = 'PERHATIAN: ' + warnings.join('\n') + '\n\n' + msg;
            }
            if (errorCount > 0) {
                msg += `\n${errorCount} baris gagal.`;
                if (data.error_details && data.error_details.length > 0) {
                    msg += '\n\n10 error pertama:\n' + data.error_details.join('\n');
                }
            }
            resultEl.style.display = 'block';
            resultEl.style.background = warnings.length > 0 ? '#fdf1f0' : 'var(--primary-light)';
            resultEl.style.border = 'none';
            resultEl.style.color = warnings.length > 0 ? 'var(--signal)' : 'var(--ink)';
            resultEl.style.whiteSpace = 'pre-wrap';
            resultEl.textContent = msg;

            // Refresh attendance view table if loaded
            if (typeof loadPaginatedAttendance === 'function') {
                loadPaginatedAttendance(1);
            }
        } else {
            throw new Error(data.detail || 'Terjadi kesalahan saat import.');
        }
    } catch (err) {
        progressContainer.style.display = 'none';
        resultEl.style.display = 'block';
        resultEl.style.background = '#fdf1f0';
        resultEl.style.border = 'none';
        resultEl.style.color = 'var(--signal)';
        resultEl.textContent = 'Import gagal: ' + err.message;
    } finally {
        btn.disabled = false;
    }
}

// ==============================
// Import Tab Switching
// ==============================

function switchImportTab(tab) {
    const attTab = document.getElementById('import-attendance-tab');
    const empTab = document.getElementById('import-employees-tab');
    const attBtn = document.getElementById('tab-import-attendance');
    const empBtn = document.getElementById('tab-import-employees');

    attTab.style.display = tab === 'attendance' ? 'block' : 'none';
    empTab.style.display = tab === 'attendance' ? 'none' : 'block';
    attBtn.classList.toggle('active', tab === 'attendance');
    empBtn.classList.toggle('active', tab !== 'attendance');
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

// ==============================
// Import Employees (Settings)
// ==============================

let importEmpSelectedFile = null;

function handleImportEmpFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    importEmpSelectedFile = file;

    document.getElementById('import-emp-filename').textContent = file.name;
    const sizeKb = (file.size / 1024).toFixed(1);
    document.getElementById('import-emp-filesize').textContent = sizeKb + ' KB';
    document.getElementById('import-emp-selected-file').style.display = 'flex';

    document.getElementById('btn-submit-import-emp').disabled = false;

    const resultEl = document.getElementById('import-emp-result-message');
    resultEl.style.display = 'none';
    resultEl.textContent = '';
}

async function submitImportEmployees() {
    if (!importEmpSelectedFile) {
        showToast('Pilih file Excel atau CSV terlebih dahulu.', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-import-emp');
    const progressContainer = document.getElementById('import-emp-progress-container');
    const progressText = document.getElementById('import-emp-progress-text');
    const resultEl = document.getElementById('import-emp-result-message');

    btn.disabled = true;
    progressContainer.style.display = 'block';
    progressText.textContent = 'Mengunggah dan memproses file...';
    resultEl.style.display = 'none';

    try {
        const formData = new FormData();
        formData.append('file', importEmpSelectedFile);

        const response = await fetch('/employees/import', {
            method: 'POST',
            headers: getReqHeaders(),
            body: formData
        });

        const data = await response.json();
        progressContainer.style.display = 'none';

        if (response.ok) {
            let msg = 'Import selesai.';
            if (data.created > 0) msg += ` ${data.created} karyawan baru ditambahkan.`;
            if (data.updated > 0) msg += ` ${data.updated} karyawan diperbarui.`;
            if (data.errors > 0) {
                msg += ` ${data.errors} baris gagal.`;
                if (data.error_details && data.error_details.length > 0) {
                    msg += '\n\nDetail:\n' + data.error_details.join('\n');
                }
            }
            resultEl.style.display = 'block';
            resultEl.style.background = 'var(--primary-light)';
            resultEl.style.border = 'none';
            resultEl.style.color = 'var(--ink)';
            resultEl.style.whiteSpace = 'pre-wrap';
            resultEl.textContent = msg;
        } else {
            throw new Error(data.detail || 'Terjadi kesalahan saat import.');
        }
    } catch (err) {
        progressContainer.style.display = 'none';
        resultEl.style.display = 'block';
        resultEl.style.background = '#fdf1f0';
        resultEl.style.border = 'none';
        resultEl.style.color = 'var(--signal)';
        resultEl.textContent = 'Import gagal: ' + err.message;
    } finally {
        btn.disabled = false;
    }
}
