// Employees Module - Server-Side Paginated with Bulk Selection, Search, Filter & Scroll
let currentEmpPage = 1;
window.currentEmployees = [];
window.allEmployeesData = [];
window.selectedEmpIds = new Set();
window.applyEmployeeFilters = function() { loadPaginatedEmployees(1); };

async function fetchEmployees() {
    await loadPaginatedEmployees(1);
}

async function loadPaginatedEmployees(page = 1) {
    currentEmpPage = page;
    const tbody = document.getElementById('employees-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="11" class="loading">Memuat data karyawan...</td></tr>';
    }

    // Get filter values
    const searchVal = document.getElementById('filter_search')?.value.trim() || '';
    const deptVal = document.getElementById('filter_department')?.value || '';
    const posVal = document.getElementById('filter_position')?.value || '';
    const compVal = document.getElementById('filter_company')?.value || '';
    const limit = document.getElementById('emp_limit_select')?.value || '50';

    const params = new URLSearchParams({
        page: page,
        limit: limit
    });

    if (searchVal) params.append('search', searchVal);
    if (deptVal) params.append('department_id', deptVal);
    if (posVal) params.append('position_id', posVal);
    if (compVal) params.append('company_id', compVal);

    try {
        const response = await fetch(`/employees/?${params.toString()}`, { headers: getReqHeaders() });
        if (!response.ok) throw new Error('Failed to fetch employees');

        const result = await response.json();
        window.currentEmployees = result.data || [];
        
        renderEmployees(result.data || []);
        updateEmployeePagination(result);

    } catch (error) {
        console.error(error);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="11" style="color: var(--danger); text-align: center;">Gagal memuat data karyawan: ${escapeHtml(error.message)}</td></tr>`;
        }
    }
}

function renderEmployees(data) {
    const tbody = document.getElementById('employees-tbody');
    if (!tbody) return;

    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: var(--text-secondary);">Tidak ada karyawan yang cocok dengan filter ini.</td></tr>';
        updateBulkActionBar();
        return;
    }

    tbody.innerHTML = data.map(emp => {
        const isChecked = window.selectedEmpIds.has(emp.id);
        const rowBgStyle = isChecked ? 'background: #f0fdf4;' : '';

        return `
        <tr id="emp-row-${emp.id}" style="${rowBgStyle}">
            <td style="text-align: center;">
                <input type="checkbox" class="emp-row-checkbox" value="${emp.id}" ${isChecked ? 'checked' : ''} onchange="toggleEmployeeSelect(${emp.id}, this)" aria-label="Pilih ${escapeHtml(emp.full_name || emp.pin)}" style="accent-color: var(--primary); width: 16px; height: 16px; cursor: pointer;">
            </td>
            <td style="font-weight: 500;">${escapeHtml(emp.full_name || 'Tanpa nama')}</td>
            <td class="num">${escapeHtml(emp.pin)}</td>
            <td class="num text-muted">${escapeHtml(emp.nik || '-')}</td>
            <td>${formatDateOnly(emp.contract_start_date)}</td>
            <td>${formatDateOnly(emp.contract_end_date)}</td>
            <td>${escapeHtml(emp.department_name || '-')}</td>
            <td>${escapeHtml(emp.position_name || '-')}</td>
            <td>${escapeHtml(emp.company_name || '-')}</td>
            <td>${emp.is_active ? 'Aktif' : '<span style="color: var(--signal);">Nonaktif</span>'}</td>
            <td style="white-space: nowrap; text-align: right;">
                <button class="btn btn-secondary btn-sm" onclick="showEditEmployeeModal(${emp.id})">Ubah</button>
                <button class="btn btn-ghost btn-sm" style="color: var(--signal);" onclick="confirmDeleteEmployeeById(${emp.id})">Hapus</button>
            </td>
        </tr>
    `;
    }).join('');
    
    updateBulkActionBar();

    if (window.lucide) {
        lucide.createIcons();
    }
}

// Bulk Selection Management
function toggleEmployeeSelect(empId, checkbox) {
    if (checkbox.checked) {
        window.selectedEmpIds.add(empId);
    } else {
        window.selectedEmpIds.delete(empId);
    }

    const row = document.getElementById(`emp-row-${empId}`);
    if (row) {
        row.style.background = checkbox.checked ? '#f0fdf4' : '';
    }

    updateBulkActionBar();
}

function toggleSelectAllEmployees(masterCheckbox) {
    const isChecked = masterCheckbox.checked;
    const currentList = window.currentEmployees || [];

    currentList.forEach(emp => {
        if (isChecked) {
            window.selectedEmpIds.add(emp.id);
        } else {
            window.selectedEmpIds.delete(emp.id);
        }

        const row = document.getElementById(`emp-row-${emp.id}`);
        if (row) {
            row.style.background = isChecked ? '#f0fdf4' : '';
        }
    });

    document.querySelectorAll('.emp-row-checkbox').forEach(cb => {
        cb.checked = isChecked;
    });

    updateBulkActionBar();
}

function deselectAllEmployees() {
    window.selectedEmpIds.clear();
    const master = document.getElementById('emp_select_all');
    if (master) {
        master.checked = false;
        master.indeterminate = false;
    }

    document.querySelectorAll('.emp-row-checkbox').forEach(cb => {
        cb.checked = false;
    });

    document.querySelectorAll('#employees-tbody tr').forEach(tr => {
        tr.style.background = '';
    });

    updateBulkActionBar();
}

function updateBulkActionBar() {
    const count = window.selectedEmpIds.size;
    const actionBar = document.getElementById('bulk-action-bar');
    const badge = document.getElementById('bulk-selected-badge');
    const master = document.getElementById('emp_select_all');

    if (badge) {
        badge.innerText = `${count} karyawan dipilih`;
    }

    if (actionBar) {
        actionBar.style.display = count > 0 ? 'flex' : 'none';
    }

    // Sync master checkbox state with current page
    if (master && window.currentEmployees.length > 0) {
        const pageEmpIds = window.currentEmployees.map(e => e.id);
        const selectedOnPage = pageEmpIds.filter(id => window.selectedEmpIds.has(id));

        if (selectedOnPage.length === 0) {
            master.checked = false;
            master.indeterminate = false;
        } else if (selectedOnPage.length === pageEmpIds.length) {
            master.checked = true;
            master.indeterminate = false;
        } else {
            master.checked = false;
            master.indeterminate = true;
        }
    }
}

// Bulk Action: Status Active / Inactive
async function executeBulkStatus(isActive) {
    if (window.selectedEmpIds.size === 0) {
        alert("Pilih setidaknya satu karyawan terlebih dahulu.");
        return;
    }

    const count = window.selectedEmpIds.size;
    const statusLabel = isActive ? 'Aktif' : 'Nonaktif';
    const confirmMsg = `Yakin ingin mengubah status ${count} karyawan terpilih menjadi ${statusLabel.toUpperCase()}?`
        + (isActive ? '\n\nMereka akan dikirim kembali ke semua mesin.' : `\n\n${DEACTIVATE_DEVICE_WARNING}`);

    if (!confirm(confirmMsg)) return;

    try {
        const response = await fetch('/employees/bulk-status', {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                employee_ids: Array.from(window.selectedEmpIds),
                is_active: isActive
            })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || 'Gagal mengubah status karyawan secara massal');
        }

        alert(data.message || `Berhasil mengubah status ${count} karyawan menjadi ${statusLabel}.`);
        deselectAllEmployees();
        loadPaginatedEmployees(currentEmpPage);
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Bulk Action: Delete
function showBulkDeleteModal() {
    if (window.selectedEmpIds.size === 0) {
        alert("Pilih setidaknya satu karyawan terlebih dahulu.");
        return;
    }

    const modal = document.getElementById('bulk-delete-employee-modal');
    const countEl = document.getElementById('bulk-delete-count');
    if (countEl) countEl.innerText = `${window.selectedEmpIds.size} Karyawan`;

    const btn = document.getElementById('btn-confirm-bulk-delete');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Hapus karyawan terpilih';
    }

    if (modal) {
        modal.style.display = 'flex';
        if (window.lucide) lucide.createIcons();
    }
}

function hideBulkDeleteModal() {
    const modal = document.getElementById('bulk-delete-employee-modal');
    if (modal) modal.style.display = 'none';
}

async function executeBulkDelete() {
    if (window.selectedEmpIds.size === 0) return;

    const btn = document.getElementById('btn-confirm-bulk-delete');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Menghapus...';
    }

    try {
        const response = await fetch('/employees/bulk-delete', {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                employee_ids: Array.from(window.selectedEmpIds)
            })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(response.status === 403
                ? 'Hanya Administrator yang bisa menghapus karyawan. Untuk karyawan yang keluar, gunakan Nonaktifkan.'
                : (data.detail || 'Gagal menghapus karyawan terpilih'));
        }

        hideBulkDeleteModal();
        alert(data.message || 'Karyawan terpilih dihapus.');
        deselectAllEmployees();
        loadPaginatedEmployees(currentEmpPage);
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Hapus karyawan terpilih';
        }
    }
}

function updateEmployeePagination(result) {
    const totalPages = result.total_pages || 1;
    const startIdx = result.total > 0 ? ((result.page - 1) * result.limit) + 1 : 0;
    const endIdx = Math.min(result.page * result.limit, result.total);

    const infoEl = document.getElementById('emp_pagination_info');
    if (infoEl) {
        infoEl.innerText = `${startIdx}–${endIdx} dari ${result.total} karyawan`;
    }

    const pageDisplay = document.getElementById('emp_page_display');
    if (pageDisplay) {
        pageDisplay.innerText = `Halaman ${result.page} dari ${totalPages}`;
    }

    const prevBtn = document.getElementById('emp_prev_btn');
    if (prevBtn) {
        prevBtn.disabled = result.page <= 1;
    }

    const nextBtn = document.getElementById('emp_next_btn');
    if (nextBtn) {
        nextBtn.disabled = result.page >= totalPages;
    }
}

function changeEmpPage(delta) {
    loadPaginatedEmployees(currentEmpPage + delta);
}

function exportEmployees() {
    const searchVal = document.getElementById('filter_search')?.value.trim() || '';
    const deptVal = document.getElementById('filter_department')?.value || '';
    const posVal = document.getElementById('filter_position')?.value || '';
    const compVal = document.getElementById('filter_company')?.value || '';

    const params = new URLSearchParams();
    if (searchVal) params.append('search', searchVal);
    if (deptVal) params.append('department_id', deptVal);
    if (posVal) params.append('position_id', posVal);
    if (compVal) params.append('company_id', compVal);

    const queryStr = params.toString() ? `?${params.toString()}` : '';
    return downloadCSV(`/employees/export${queryStr}`, 'data_karyawan.xlsx');
}

// Master Data Fetching
async function fetchMasterData() {
    try {
        const [depRes, posRes, compRes] = await Promise.all([
            fetch('/master-data/departments', { headers: getReqHeaders() }),
            fetch('/master-data/positions', { headers: getReqHeaders() }),
            fetch('/master-data/companies', { headers: getReqHeaders() })
        ]);

        if (depRes.ok) {
            const deps = await depRes.json();
            populateDropdown('edit_employee_department', deps);
            populateFilterDropdown('filter_department', deps, 'Semua departemen');
        }
        if (posRes.ok) {
            const pos = await posRes.json();
            populateDropdown('edit_employee_position', pos);
            populateFilterDropdown('filter_position', pos, 'Semua jabatan');
        }
        if (compRes.ok) {
            const comps = await compRes.json();
            populateDropdown('edit_employee_company', comps);
            populateFilterDropdown('filter_company', comps, 'Semua perusahaan');
        }
    } catch (error) {
        console.error("Failed to load master data", error);
    }
}

function populateDropdown(selectId, data) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    const firstOption = select.options[0];
    select.innerHTML = '';
    if (firstOption) {
        select.appendChild(firstOption);
    }
    
    data.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.name;
        select.appendChild(option);
    });
}

function populateFilterDropdown(selectId, data, allLabel) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = `<option value="">${allLabel}</option>`;
    
    data.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.name;
        select.appendChild(option);
    });
}

// Add Employee Modal Logic
async function submitAddEmployee(event) {
    event.preventDefault();
    
    const selectedDevices = Array.from(document.querySelectorAll('.add-device-checkbox:checked')).map(cb => parseInt(cb.value));

    const payload = {
        full_name: document.getElementById('add_employee_name').value.trim(),
        pin: document.getElementById('add_employee_pin').value,
        nik: document.getElementById('add_employee_nik').value || null,
        is_active: true,
        contract_start_date: document.getElementById('add_employee_contract_start').value || null,
        contract_end_date: document.getElementById('add_employee_contract_end').value || null,
        department_id: document.getElementById('add_employee_department').value ? parseInt(document.getElementById('add_employee_department').value) : null,
        position_id: document.getElementById('add_employee_position').value ? parseInt(document.getElementById('add_employee_position').value) : null,
        company_id: document.getElementById('add_employee_company').value ? parseInt(document.getElementById('add_employee_company').value) : null,
        device_access_ids: selectedDevices
    };

    try {
        const response = await fetch('/employees/', {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed to add employee');
        }
        
        document.getElementById('add-employee-modal').style.display = 'none';
        document.getElementById('add-employee-form').reset();
        loadPaginatedEmployees(1);
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Initialize Add modal on open
document.addEventListener('DOMContentLoaded', () => {
    const addBtn = document.querySelector(`button[onclick="document.getElementById('add-employee-modal').style.display='block'"]`);
    if (addBtn) {
        addBtn.onclick = () => {
            const deviceContainer = document.getElementById('add_employee_devices');
            if (deviceContainer) {
                if (!window.allDevices || window.allDevices.length === 0) {
                     deviceContainer.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.875rem;">Belum ada mesin.</span>';
                } else {
                     deviceContainer.innerHTML = window.allDevices.map(d => `
                         <label style="display: flex; align-items: center; gap: 0.5rem; color: #334155; font-size: 0.875rem; cursor: pointer; padding: 0.2rem 0;">
                             <input type="checkbox" class="add-device-checkbox" value="${d.id}" style="accent-color: var(--primary); width: 15px; height: 15px;">
                             ${escapeHtml(d.name)} (${escapeHtml(d.cloud_id)})
                         </label>
                     `).join('');
                }
            }
            
            const editDept = document.getElementById('edit_employee_department');
            const editPos = document.getElementById('edit_employee_position');
            const editComp = document.getElementById('edit_employee_company');

            if (editDept) document.getElementById('add_employee_department').innerHTML = editDept.innerHTML;
            if (editPos) document.getElementById('add_employee_position').innerHTML = editPos.innerHTML;
            if (editComp) document.getElementById('add_employee_company').innerHTML = editComp.innerHTML;
            
            document.getElementById('add-employee-modal').style.display = 'flex';
        };
    }
});

// Edit Employee Modal Logic
function showEditEmployeeModal(employeeId) {
    const emp = (window.currentEmployees || []).find(e => e.id === employeeId);
    if (!emp) return;

    document.getElementById('edit_employee_id').value = emp.id;
    document.getElementById('edit_employee_name').value = emp.full_name || '';
    document.getElementById('edit_employee_nik').value = emp.nik || '';
    document.getElementById('edit_employee_status').value = emp.is_active ? 'true' : 'false';
    document.getElementById('edit_employee_contract_start').value = emp.contract_start_date ? emp.contract_start_date : '';
    document.getElementById('edit_employee_contract_end').value = emp.contract_end_date ? emp.contract_end_date : '';
    document.getElementById('edit_employee_department').value = emp.department_id || '';
    document.getElementById('edit_employee_position').value = emp.position_id || '';
    document.getElementById('edit_employee_company').value = emp.company_id || '';

    const deviceContainer = document.getElementById('edit_employee_devices');
    if (deviceContainer) {
        const accesses = emp.device_accesses || [];
        const employeeDeviceIds = accesses
            .filter(d => d.sync_status !== 'PENDING_REMOVE' && d.failed_action !== 'PENDING_REMOVE')
            .map(d => d.device_id);
        window.editEmployeeWasActive = emp.is_active;
        if (!window.allDevices || window.allDevices.length === 0) {
             deviceContainer.innerHTML = '<span style="color: var(--text-secondary); font-size: 0.875rem;">Belum ada mesin.</span>';
        } else {
             deviceContainer.innerHTML = window.allDevices.map(d => `
                 <label style="display: flex; align-items: center; gap: 0.5rem; color: #334155; font-size: 0.875rem; cursor: pointer; padding: 0.2rem 0;">
                     <input type="checkbox" class="edit-device-checkbox" value="${d.id}" ${employeeDeviceIds.includes(d.id) ? 'checked' : ''} style="accent-color: var(--primary); width: 15px; height: 15px;">
                     ${escapeHtml(d.name)} (${escapeHtml(d.cloud_id)})
                     ${deviceSyncLabel(accesses.find(a => a.device_id === d.id))}
                 </label>
             `).join('');
        }
    }

    document.getElementById('edit-employee-modal').style.display = 'flex';
}

function deviceSyncLabel(access) {
    if (!access) return '';
    const labels = {
        SYNCED: ['terkonfirmasi', 'var(--text-secondary)'],
        PENDING_ADD: ['antre kirim', 'var(--text-secondary)'],
        PENDING_REMOVE: ['antre hapus', 'var(--text-secondary)'],
        FAILED: ['gagal, simpan untuk coba lagi', 'var(--signal)'],
    };
    const [text, color] = labels[access.sync_status] || [access.sync_status, 'var(--text-secondary)'];
    return `<span style="color: ${color}; font-size: 0.8rem;" title="${escapeHtml(access.last_error || '')}">${escapeHtml(text)}</span>`;
}

function hideEditEmployeeModal() {
    document.getElementById('edit-employee-modal').style.display = 'none';
    document.getElementById('edit-employee-form').reset();
}

async function submitEditEmployee(event) {
    event.preventDefault();
    const id = document.getElementById('edit_employee_id').value;
    
    const selectedDevices = Array.from(document.querySelectorAll('.edit-device-checkbox:checked')).map(cb => parseInt(cb.value));

    const nowActive = document.getElementById('edit_employee_status').value === 'true';
    if (window.editEmployeeWasActive && !nowActive && !confirm(DEACTIVATE_DEVICE_WARNING)) return;

    const payload = {
        full_name: document.getElementById('edit_employee_name').value.trim(),
        nik: document.getElementById('edit_employee_nik').value || null,
        is_active: document.getElementById('edit_employee_status').value === 'true',
        contract_start_date: document.getElementById('edit_employee_contract_start').value || null,
        contract_end_date: document.getElementById('edit_employee_contract_end').value || null,
        department_id: document.getElementById('edit_employee_department').value ? parseInt(document.getElementById('edit_employee_department').value) : null,
        position_id: document.getElementById('edit_employee_position').value ? parseInt(document.getElementById('edit_employee_position').value) : null,
        company_id: document.getElementById('edit_employee_company').value ? parseInt(document.getElementById('edit_employee_company').value) : null,
        device_access_ids: selectedDevices
    };

    try {
        const response = await fetch(`/employees/${id}`, {
            method: 'PUT',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed to update employee');
        }
        
        hideEditEmployeeModal();
        loadPaginatedEmployees(currentEmpPage);
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

const DEACTIVATE_DEVICE_WARNING = 'Karyawan yang dinonaktifkan akan dihapus dari semua mesin dan tidak bisa scan lagi. '
    + 'Salinan sidik jarinya disimpan dulu agar bisa dikembalikan saat diaktifkan lagi.';

function confirmDeleteEmployeeById(id) {
    const emp = (window.currentEmployees || []).find(e => e.id === id);
    if (emp) confirmDeleteEmployee(emp.id, emp.full_name || '', emp.pin);
}

function confirmDeleteEmployee(id, name, pin) {
    const modal = document.getElementById('delete-employee-modal');
    if (!modal) {
        if (confirm(`YAKIN HAPUS TOTAL KARYAWAN?\n\nNama: ${name}\nPIN: ${pin}\n\nPerhatian: data karyawan terhapus permanen dan PIN-nya ikut dihapus dari semua mesin, termasuk sidik jarinya.`)) {
            executeDirectDelete(id);
        }
        return;
    }
    
    document.getElementById('delete-emp-id').value = id;
    document.getElementById('delete-emp-name').textContent = name || '-';
    document.getElementById('delete-emp-pin').textContent = pin || '-';
    
    const btn = document.getElementById('btn-confirm-delete-emp');
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Hapus karyawan';
    }
    
    modal.style.display = 'flex';
    if (window.lucide) {
        lucide.createIcons();
    }
}

function hideDeleteEmployeeModal() {
    const modal = document.getElementById('delete-employee-modal');
    if (modal) modal.style.display = 'none';
}

async function executeDeleteEmployee() {
    const id = document.getElementById('delete-emp-id').value;
    if (!id) return;

    const btn = document.getElementById('btn-confirm-delete-emp');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-spinner" aria-hidden="true"></span> Menghapus...';
    }

    try {
        const response = await fetch(`/employees/${id}`, {
            method: 'DELETE',
            headers: getReqHeaders()
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(response.status === 403
                ? 'Hanya Administrator yang bisa menghapus karyawan. Untuk karyawan yang keluar, gunakan Nonaktifkan.'
                : (data.detail || 'Gagal menghapus karyawan'));
        }

        hideDeleteEmployeeModal();
        alert(data.message || 'Karyawan dihapus.');
        window.selectedEmpIds.delete(parseInt(id));
        loadPaginatedEmployees(currentEmpPage);
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Hapus karyawan';
        }
    }
}
