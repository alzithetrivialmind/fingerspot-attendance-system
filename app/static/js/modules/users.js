function handleLogout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('token');
    document.getElementById('login-container').style.display = 'flex';
    document.getElementById('app-container').style.display = 'none';
}

// User Management
async function fetchUsers() {
    const tbody = document.getElementById('users-tbody');
    tbody.innerHTML = '<tr><td colspan="4" class="loading">Memuat pengguna...</td></tr>';
    try {
        const response = await fetch('/users/', { headers: getReqHeaders() });
        if (!response.ok) throw new Error('Failed to fetch users');
        const data = await response.json();
        
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">Belum ada pengguna</td></tr>';
            return;
        }

        const ROLE_LABEL = { 'monitor': 'Monitor', 'view-only': 'Hanya lihat', 'operator': 'Operator', 'administrator': 'Administrator', 'super admin': 'Super admin' };
        window.__userRows = data;
        tbody.innerHTML = data.map(user => `
            <tr>
                <td style="font-weight: 500;">${escapeHtml(user.username)}${user.full_name ? `<div class="section-sub">${escapeHtml(user.full_name)}</div>` : ''}</td>
                <td>${escapeHtml(ROLE_LABEL[user.role] || user.role)}</td>
                <td>${user.is_active ? 'Aktif' : '<span style="color: var(--signal);">Nonaktif</span>'}</td>
                <td style="text-align: right; white-space: nowrap;">
                    <button class="btn btn-secondary btn-sm" onclick="showEditUserModal(window.__userRows.find(u => u.id === ${user.id}))">Ubah</button>
                    ${user.username !== currentUser.sub ? `<button class="btn btn-ghost btn-sm" style="color: var(--signal);" onclick="deleteUser(${user.id})">Hapus</button>` : ''}
                </td>
            </tr>
        `).join('');
    } catch (error) {
        console.error(error);
        tbody.innerHTML = `<tr><td colspan="4" style="color: var(--danger); text-align: center;">Gagal memuat daftar pengguna</td></tr>`;
    }
}

function showAddUserModal() {
    document.getElementById('user-modal-title').textContent = 'Tambah pengguna';
    document.getElementById('user-form').reset();
    document.getElementById('user_id').value = '';
    
    const pwInput = document.getElementById('user_password');
    pwInput.required = true;
    pwInput.placeholder = 'Minimal 8 karakter';
    
    const reqMarker = document.getElementById('user_password_required_marker');
    if (reqMarker) reqMarker.style.display = 'inline';
    
    const hint = document.getElementById('user_password_hint');
    if (hint) hint.textContent = 'Wajib diisi (minimal 8 karakter).';
    
    document.getElementById('user-modal').style.display = 'flex';
}

function showEditUserModal(user) {
    document.getElementById('user-modal-title').textContent = 'Ubah pengguna';
    document.getElementById('user-form').reset();
    document.getElementById('user_id').value = user.id;
    document.getElementById('user_username').value = user.username;
    
    const fnInput = document.getElementById('user_fullname');
    if (fnInput) fnInput.value = user.full_name || '';
    
    document.getElementById('user_role').value = user.role;
    document.getElementById('user_is_active').checked = user.is_active;
    
    const pwInput = document.getElementById('user_password');
    pwInput.required = false;
    pwInput.placeholder = 'Kosongkan jika tidak ingin mengubah password';
    
    const reqMarker = document.getElementById('user_password_required_marker');
    if (reqMarker) reqMarker.style.display = 'none';
    
    const hint = document.getElementById('user_password_hint');
    if (hint) hint.textContent = 'Kosongkan jika tidak ingin mengganti password.';
    
    document.getElementById('user-modal').style.display = 'flex';
}

function hideUserModal() {
    document.getElementById('user-modal').style.display = 'none';
}

async function submitUserForm(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Menyimpan...';

    const userId = document.getElementById('user_id').value;
    const isEdit = !!userId;

    const username = document.getElementById('user_username').value.trim();
    const fullNameInput = document.getElementById('user_fullname');
    const fullName = fullNameInput ? fullNameInput.value.trim() : null;
    const role = document.getElementById('user_role').value;
    const isActive = document.getElementById('user_is_active').checked;
    const pw = document.getElementById('user_password').value;

    if (!username || username.length < 3) {
        alert('Username minimal 3 karakter.');
        btn.disabled = false;
        btn.textContent = 'Simpan pengguna';
        return;
    }

    if (!isEdit && (!pw || pw.length < 8)) {
        alert('Password wajib diisi minimal 8 karakter untuk user baru.');
        btn.disabled = false;
        btn.textContent = 'Simpan pengguna';
        return;
    }

    const payload = {
        username: username,
        full_name: fullName || null,
        role: role,
        is_active: isActive
    };
    
    if (pw) {
        payload.password = pw;
    }

    try {
        const url = isEdit ? '/users/' + userId : '/users/';
        const method = isEdit ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { ...getReqHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({ detail: 'Terjadi kesalahan pada server' }));
            let errorMsg = 'Gagal menyimpan data user';
            if (typeof data.detail === 'string') {
                errorMsg = data.detail;
            } else if (Array.isArray(data.detail)) {
                errorMsg = data.detail.map(err => {
                    const field = err.loc ? err.loc[err.loc.length - 1] : '';
                    return `${field ? field + ': ' : ''}${err.msg}`;
                }).join('\n');
            }
            throw new Error(errorMsg);
        }

        hideUserModal();
        fetchUsers();
        if (currentUser && (currentUser.username === username || currentUser.sub === username)) {
            currentUser.full_name = fullName;
            if (fullName) {
                localStorage.setItem('user_full_name', fullName);
            }
            if (typeof updateUserGreeting === 'function') updateUserGreeting();
        }
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Simpan pengguna';
    }
}

async function deleteUser(id) {
    if (!confirm('Hapus pengguna ini? Ia tidak akan bisa masuk lagi.')) return;
    try {
        const response = await fetch('/users/' + id, {
            method: 'DELETE',
            headers: getReqHeaders()
        });
        if (!response.ok) throw new Error('Failed to delete user');
        fetchUsers();
    } catch (error) {
        alert(error.message);
    }
}



// Ubah password akun sendiri (semua role)
function showChangePasswordModal() {
    document.getElementById('change-password-form').reset();
    document.getElementById('cp-error').style.display = 'none';
    document.getElementById('change-password-username').textContent = currentUser?.sub || '-';
    document.getElementById('change-password-modal').style.display = 'flex';
    document.getElementById('cp-current').focus();
}

function hideChangePasswordModal() {
    document.getElementById('change-password-modal').style.display = 'none';
}

async function submitChangePassword(event) {
    event.preventDefault();
    const err = document.getElementById('cp-error');
    const showError = msg => { err.textContent = msg; err.style.display = 'block'; };
    const current = document.getElementById('cp-current').value;
    const next = document.getElementById('cp-new').value;
    if (next !== document.getElementById('cp-confirm').value) return showError('Ulangi password baru tidak sama.');
    if (next === current) return showError('Password baru harus berbeda dari password lama.');
    try {
        const res = await fetch('/auth/change-password', {
            method: 'POST',
            headers: { ...getReqHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: current, new_password: next })
        });
        const body = await res.json();
        if (!res.ok) {
            const detail = Array.isArray(body.detail) ? 'Password baru minimal 8 karakter.' : body.detail;
            throw new Error(detail || res.statusText);
        }
        hideChangePasswordModal();
        showToast('Password berhasil diganti. Gunakan password baru saat login berikutnya.', 'success', 7000);
    } catch (e) {
        showError(e.message);
    }
}
