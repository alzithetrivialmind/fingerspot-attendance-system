// backup.js
// Menu Pengaturan > Backup & restore (super admin): daftar backup, backup manual, unduh, restore

const BACKUP_KIND_TONE = {
    harian: 'neutral', mingguan: 'info', bulanan: 'success', manual: 'gold', 'sebelum-restore': 'danger'
};

function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatBackupTime(iso) {
    return new Date(iso).toLocaleString('id-ID', {
        weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

async function loadBackups() {
    const tbody = document.getElementById('backup-tbody');
    const status = document.getElementById('backup-status-text');
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Memuat backup...</td></tr>';

    let data;
    try {
        const res = await fetch('/backups/', { headers: getReqHeaders() });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        data = await res.json();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" style="color: var(--danger); text-align: center;">Gagal memuat backup: ${escapeHtml(e.message)}</td></tr>`;
        return;
    }

    const runBtn = document.getElementById('btn-run-backup');
    runBtn.disabled = !data.tools_available;
    status.textContent = data.tools_available
        ? `Backup otomatis berjalan tiap hari setelah pukul ${String(data.backup_hour).padStart(2, '0')}.00.`
        : 'pg_dump belum terpasang di server, backup belum aktif. Rebuild image aplikasi (docker compose up -d --build).';

    const files = data.groups.flatMap(g => g.files.map(f => ({ ...f, label: g.label })));
    if (files.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-secondary);">Belum ada backup.</td></tr>';
        return;
    }
    tbody.innerHTML = files.map(f => `<tr>
        <td><span class="badge badge-${BACKUP_KIND_TONE[f.kind] || 'neutral'}">${escapeHtml(f.label)}</span></td>
        <td class="num" style="white-space: nowrap;">${escapeHtml(formatBackupTime(f.created_at))}</td>
        <td class="num">${formatBytes(f.size)}</td>
        <td style="word-break: break-all; font-size: 0.8rem; color: var(--text-secondary);">${escapeHtml(f.name)}</td>
        <td style="white-space: nowrap; text-align: right;">
            <button class="btn btn-ghost btn-sm" data-viewer-ok onclick="downloadBackup('${f.kind}', '${f.name}')">Unduh</button>
            <button class="btn btn-danger-soft btn-sm" onclick="showRestoreModal('${f.kind}', '${f.name}', '${f.created_at}')">Restore</button>
        </td>
    </tr>`).join('');
}

async function runManualBackup() {
    const btn = document.getElementById('btn-run-backup');
    btn.disabled = true;
    btn.textContent = 'Membuat backup...';
    try {
        const res = await fetch('/backups/run', { method: 'POST', headers: getReqHeaders() });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || res.statusText);
        showToast(`Backup dibuat: ${body.name} (${formatBytes(body.size)})`, 'success');
    } catch (e) {
        showToast('Backup gagal: ' + e.message, 'error', 8000);
    } finally {
        btn.textContent = 'Backup sekarang';
        await loadBackups();
    }
}

function downloadBackup(kind, name) {
    return downloadCSV(`/backups/${encodeURIComponent(kind)}/${encodeURIComponent(name)}/download`, name);
}

function showRestoreModal(kind, name, createdAt) {
    document.getElementById('restore-backup-kind').value = kind;
    document.getElementById('restore-backup-name').textContent = name;
    document.getElementById('restore-backup-time').textContent = formatBackupTime(createdAt);
    document.getElementById('restore-confirm-input').value = '';
    document.getElementById('btn-confirm-restore').disabled = true;
    document.getElementById('restore-backup-modal').style.display = 'flex';
    document.getElementById('restore-confirm-input').focus();
}

function hideRestoreModal() {
    document.getElementById('restore-backup-modal').style.display = 'none';
}

async function executeRestore() {
    const btn = document.getElementById('btn-confirm-restore');
    const name = document.getElementById('restore-backup-name').textContent;
    const payload = {
        kind: document.getElementById('restore-backup-kind').value,
        name,
        confirm: document.getElementById('restore-confirm-input').value.trim()
    };
    btn.disabled = true;
    btn.textContent = 'Memulihkan...';
    try {
        const res = await fetch('/backups/restore', {
            method: 'POST',
            headers: { ...getReqHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || res.statusText);
        hideRestoreModal();
        showToast(`Database dipulihkan dari ${name}. Kondisi sebelumnya disimpan sebagai ${body.safety_backup}.`, 'success', 10000);
        await loadBackups();
    } catch (e) {
        showToast('Restore gagal: ' + e.message, 'error', 10000);
    } finally {
        btn.textContent = 'Restore';
    }
}
