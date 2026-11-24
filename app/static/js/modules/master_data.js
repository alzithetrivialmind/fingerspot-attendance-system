// Settings UI - Master Data Management
async function loadMasterDataLists() {
    try {
        const [depRes, posRes, compRes] = await Promise.all([
            fetch('/master-data/departments', { headers: getReqHeaders() }),
            fetch('/master-data/positions', { headers: getReqHeaders() }),
            fetch('/master-data/companies', { headers: getReqHeaders() })
        ]);

        if (depRes.ok) renderMasterDataList('list_departments', await depRes.json(), 'departments');
        if (posRes.ok) renderMasterDataList('list_positions', await posRes.json(), 'positions');
        if (compRes.ok) renderMasterDataList('list_companies', await compRes.json(), 'companies');
    } catch (error) {
        console.error('Failed to load master data lists', error);
    }
}

function renderMasterDataList(elementId, data, endpointPrefix) {
    const ul = document.getElementById(elementId);
    if (!ul) return;
    
    if (data.length === 0) {
        ul.innerHTML = '<li class="master-empty">Belum ada data</li>';
        return;
    }

    ul.innerHTML = data.map(item => `
        <li class="master-item" id="item_${endpointPrefix}_${item.id}">
            <span id="text_${endpointPrefix}_${item.id}" style="font-weight: 500; font-size: 0.9rem;">${escapeHtml(item.name)}</span>
            <input type="text" id="input_${endpointPrefix}_${item.id}" value="${escapeHtml(item.name)}" class="form-control" aria-label="Ubah nama" style="display: none; flex: 1; padding: 0.35rem 0.5rem; font-size: 0.85rem;">

            <div style="display: flex; gap: 0.25rem;" id="actions_${endpointPrefix}_${item.id}">
                <button class="btn btn-ghost btn-sm" onclick="enableEditMasterData('${endpointPrefix}', ${item.id})">Ubah</button>
                <button class="btn btn-ghost btn-sm" style="color: var(--signal);" onclick="deleteMasterData('${endpointPrefix}', ${item.id})">Hapus</button>
            </div>

            <div style="display: none; gap: 0.25rem;" id="save_actions_${endpointPrefix}_${item.id}">
                <button class="btn btn-primary btn-sm" onclick="updateMasterData('${endpointPrefix}', ${item.id})">Simpan</button>
                <button class="btn btn-ghost btn-sm" onclick="cancelEditMasterData('${endpointPrefix}', ${item.id})">Batal</button>
            </div>
        </li>
    `).join('');
}

function enableEditMasterData(prefix, id) {
    document.getElementById(`text_${prefix}_${id}`).style.display = 'none';
    document.getElementById(`input_${prefix}_${id}`).style.display = 'block';
    document.getElementById(`actions_${prefix}_${id}`).style.display = 'none';
    document.getElementById(`save_actions_${prefix}_${id}`).style.display = 'flex';
}

function cancelEditMasterData(prefix, id) {
    document.getElementById(`text_${prefix}_${id}`).style.display = 'block';
    document.getElementById(`input_${prefix}_${id}`).style.display = 'none';
    document.getElementById(`actions_${prefix}_${id}`).style.display = 'flex';
    document.getElementById(`save_actions_${prefix}_${id}`).style.display = 'none';
}

async function updateMasterData(prefix, id) {
    const input = document.getElementById(`input_${prefix}_${id}`);
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch(`/master-data/${prefix}/${id}`, {
            method: 'PUT',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ name: name })
        });

        if (res.ok) {
            loadMasterDataLists();
            fetchMasterData(); // Refresh the employee dropdowns globally
        } else {
            const err = await res.json();
            showToast('Gagal menyimpan: ' + (err.detail || 'kesalahan tidak diketahui'), 'error', 7000);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function addMasterData(endpointPrefix, inputId) {
    const input = document.getElementById(inputId);
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch(`/master-data/${endpointPrefix}`, {
            method: 'POST',
            headers: {
                ...getReqHeaders(),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ name: name })
        });

        if (res.ok) {
            input.value = '';
            loadMasterDataLists();
            fetchMasterData(); // Refresh the employee dropdowns globally
        } else {
            const err = await res.json();
            showToast('Gagal menambah: ' + (err.detail || 'kesalahan tidak diketahui'), 'error', 7000);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function deleteMasterData(endpointPrefix, id) {
    if (!confirm('Hapus data ini? Data yang masih dipakai karyawan tidak bisa dihapus.')) return;

    try {
        const res = await fetch(`/master-data/${endpointPrefix}/${id}`, {
            method: 'DELETE',
            headers: getReqHeaders()
        });

        if (res.ok) {
            loadMasterDataLists();
            fetchMasterData(); // Refresh the employee dropdowns globally
        } else {
            const err = await res.json();
            showToast('Gagal menghapus: ' + (err.detail || 'data mungkin masih dipakai'), 'error', 7000);
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// Call loadMasterDataLists on Settings view
document.addEventListener('DOMContentLoaded', () => {
    // When clicking the Settings nav item, make sure we show the main menu
    const settingsNav = Array.from(document.querySelectorAll('.nav-item')).find(n => (n.getAttribute('onclick') || '').includes("'settings'"));
    if (settingsNav) {
        settingsNav.addEventListener('click', () => {
            toggleSettingsSubmenu('main');
        });
    }
});

