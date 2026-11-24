// Initial fetch on load
let refreshInterval;

document.addEventListener('DOMContentLoaded', () => {
    startGlobalLiveClock();

    // Auto refresh every 5 seconds for Real-Time feel
    refreshInterval = setInterval(() => {
        if (!authToken) return;
        const dashboardView = document.getElementById('dashboard-view');
        if (dashboardView && dashboardView.classList.contains('active')) {
            fetchAttendance();
        }
    }, 5000);
});

// Dipanggil checkAuthState() setelah token valid (saat load maupun setelah login),
// supaya dropdown master data & daftar mesin terisi meski user baru login.
function loadSessionData() {
    fetchMasterData();
    preloadDevices();
}

// Pre-fetch Devices for Edit Modal
window.allDevices = [];
async function preloadDevices() {
    if (!authToken) return;
    try {
        const response = await fetch('/devices/', { headers: getReqHeaders() });
        if (response.ok) {
            window.allDevices = await response.json();
        }
    } catch (e) {
        console.error("Failed to preload devices", e);
    }
}

// Modify initial load
document.addEventListener('DOMContentLoaded', () => {
    checkAuthState();
    // Add logout button to sidebar nav
    const navLinks = document.querySelector('.nav-links');
    const logoutLi = document.createElement('li');
    logoutLi.className = 'nav-item';
    // Inline style to guarantee visibility on dark sidebar
    logoutLi.style.cssText = 'margin-top: auto; color: #fca5a5; border: 1px solid rgba(239,68,68,0.3); background: rgba(239,68,68,0.08); border-radius: 8px;';
    logoutLi.onmouseenter = () => { logoutLi.style.background = 'rgba(239,68,68,0.2)'; logoutLi.style.color = '#fecaca'; };
    logoutLi.onmouseleave = () => { logoutLi.style.background = 'rgba(239,68,68,0.08)'; logoutLi.style.color = '#fca5a5'; };
    logoutLi.onclick = handleLogout;
    logoutLi.innerHTML = '<i data-lucide="log-out" style="width:18px;height:18px;color:#fca5a5;"></i> Keluar';

    const passwordLi = document.createElement('li');
    passwordLi.className = 'nav-item';
    passwordLi.style.marginTop = 'auto';
    passwordLi.tabIndex = 0;
    passwordLi.setAttribute('role', 'button');
    passwordLi.onclick = showChangePasswordModal;
    passwordLi.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showChangePasswordModal(); } };
    passwordLi.innerHTML = '<i data-lucide="key"></i> <span>Ubah password</span>';
    navLinks.appendChild(passwordLi);
    logoutLi.style.marginTop = '0.4rem';
    navLinks.appendChild(logoutLi);
    lucide.createIcons();
});


