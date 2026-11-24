function escapeHtml(val) {
    return String(val ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// Tanggal lokal format YYYY-MM-DD. Jangan pakai toISOString(): itu UTC, sehingga dini hari
// menghasilkan tanggal kemarin.
function localDateStr(d) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// Auth State
let authToken = localStorage.getItem('token');
let currentUser = null;

function isTokenValid(token) {
    const payload = token ? parseJwt(token) : null;
    return !!(payload && payload.exp * 1000 > Date.now());
}

// Buang token kedaluwarsa sebelum modul lain memakainya saat halaman dimuat (cegah rentetan 401).
if (authToken && !isTokenValid(authToken)) {
    authToken = null;
    localStorage.removeItem('token');
}

// Server menolak token sesi aktif (kedaluwarsa / JWT secret berubah) -> logout sekali.
// Polling berikutnya berhenti sendiri karena authToken sudah null.
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
    const response = await nativeFetch(input, init);
    if (response.status === 401 && authToken) {
        const sentAuth = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined)).get('Authorization');
        if (sentAuth === `Bearer ${authToken}`) {
            handleLogout();
            if (typeof showToast === 'function') showToast('Sesi berakhir. Silakan login ulang.', 'error');
        }
    }
    return response;
};

// Headers config getter
function getReqHeaders() {
    const headers = {
        "accept": "application/json"
    };
    if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
    }
    return headers;
}

// Format date helper
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('id-ID', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatDateOnly(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('id-ID', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric'
    });
}

function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

