async function fetchCurrentUserProfile() {
    if (!authToken) return;
    try {
        const res = await fetch('/auth/me', { headers: getReqHeaders() });
        if (res.ok) {
            const data = await res.json();
            if (data) {
                if (!currentUser) currentUser = {};
                currentUser.id = data.id;
                currentUser.username = data.username;
                currentUser.full_name = data.full_name;
                currentUser.role = data.role;
                if (data.full_name) {
                    localStorage.setItem('user_full_name', data.full_name);
                } else if (data.username) {
                    localStorage.setItem('user_full_name', data.username);
                }
                updateUserGreeting();
            }
        }
    } catch (e) {
        console.error('Failed to fetch user profile:', e);
    }
}

function updateUserGreeting() {
    const greetingEl = document.getElementById('dashboard-user-greeting');
    if (!greetingEl) return;
    
    const storedFullName = localStorage.getItem('user_full_name');
    if (currentUser && currentUser.full_name) {
        greetingEl.textContent = currentUser.full_name;
    } else if (storedFullName) {
        greetingEl.textContent = storedFullName;
    } else if (currentUser) {
        greetingEl.textContent = currentUser.sub || currentUser.username || 'User';
    } else {
        greetingEl.textContent = 'User';
    }
}

function checkAuthState() {
    if (authToken) {
        currentUser = parseJwt(authToken);
        if (currentUser && currentUser.exp * 1000 > Date.now() && currentUser.role) {
            // Akun monitor hanya untuk layar monitor
            if (currentUser.role === 'monitor') {
                location.replace('/monitor');
                return;
            }
            document.getElementById('login-container').style.display = 'none';
            document.getElementById('app-container').style.display = 'flex';
            applyRolePermissions();
            updateUserGreeting();
            fetchCurrentUserProfile();
            loadSessionData();
            // Default view if on login screen
            const activeView = document.querySelector('.view-section.active');
            if (activeView && activeView.id === 'dashboard-view' && !restoreLocation()) {
                const firstNavItem = document.querySelector('.nav-item');
                if (firstNavItem) firstNavItem.click();
            }
            return;
        } else {
            handleLogout();
        }
    }
    document.getElementById('login-container').style.display = 'flex';
    document.getElementById('app-container').style.display = 'none';
}

function applyRolePermissions() {
    if (!currentUser) return;
    const role = (currentUser.role || '').toLowerCase();
    const isSuperAdmin = role === 'super admin';
    const isAdmin = isSuperAdmin || role === 'administrator';
    const isOperator = isAdmin || role === 'operator';

    const show = (el, visible, display) => { if (el) el.style.display = visible ? display : 'none'; };
    const nav = view => document.querySelector(`li.nav-item[onclick="switchView('${view}')"]`);
    const card = id => document.querySelector(`div[onclick="toggleSettingsSubmenu('${id}')"]`);

    show(nav('activity-log'), isOperator, 'flex');
    show(nav('settings'), isOperator, 'flex');
    show(card('devices-submenu'), isOperator, 'flex');
    show(card('import-data-submenu'), isOperator, 'flex');
    show(card('master-data-submenu'), isAdmin, 'flex');
    show(card('users-submenu'), isSuperAdmin, 'flex');
    show(card('backup-submenu'), isSuperAdmin, 'flex');

    // Tombol pengelolaan perangkat keras hanya untuk administrator ke atas
    show(document.querySelector('button[onclick="showAddDeviceModal()"]'), isAdmin, 'inline-flex');
    document.querySelectorAll('.admin-only-btn').forEach(btn => show(btn, isAdmin, 'inline-flex'));

    // View-only: sembunyikan semua tombol yang mengubah data (ditolak juga oleh server)
    document.body.classList.toggle('role-view-only', !isOperator);
}

async function handleLogin(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type="submit"]');
    const err = document.getElementById('login-error');
    err.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Masuk...';

    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    try {
        const params = new URLSearchParams();
        params.append('username', username);
        params.append('password', password);

        const response = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: params
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Gagal masuk');
        }

        const data = await response.json();
        authToken = data.access_token;
        localStorage.setItem('token', authToken);
        checkAuthState();
    } catch (error) {
        err.textContent = error.message;
        err.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Masuk';
    }
}

