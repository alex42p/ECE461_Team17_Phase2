/**
 * ECE461 Package Registry - Client-Side JavaScript
 * Handles authentication, API calls, and UI interactions
 */

// Global state
let authToken = null;
let currentUser = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check for stored token
    const storedToken = localStorage.getItem('authToken');
    const storedUser = localStorage.getItem('currentUser');
    
    if (storedToken && storedUser) {
        authToken = storedToken;
        currentUser = JSON.parse(storedUser);
        updateAuthUI();
    }

    // Load initial health status
    loadHealthStatus();
});

/**
 * Show alert message
 */
function showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    alertContainer.appendChild(alert);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => alert.remove(), 150);
    }, 5000);
}

/**
 * Make authenticated API request
 */
async function apiRequest(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    if (authToken) {
        headers['X-Authorization'] = `Bearer ${authToken}`;
    }

    const response = await fetch(url, {
        ...options,
        headers
    });

    if (response.status === 401) {
        // Token expired
        logout();
        showAlert('Session expired. Please login again.', 'warning');
        throw new Error('Authentication required');
    }

    return response;
}

/**
 * Toggle authentication modal
 */
function toggleAuthModal() {
    if (authToken) {
        logout();
    } else {
        const modal = new bootstrap.Modal(document.getElementById('authModal'));
        modal.show();
    }
}

/**
 * Authenticate user
 */
async function authenticate(event) {
    event.preventDefault();

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    try {
        const response = await fetch('/authenticate', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                User: { name: username, isAdmin: false },
                Secret: { password: password }
            })
        });

        const data = await response.json();

        if (response.ok) {
            authToken = data.token;
            currentUser = data.user;

            // Store in localStorage
            localStorage.setItem('authToken', authToken);
            localStorage.setItem('currentUser', JSON.stringify(currentUser));

            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('authModal'));
            modal.hide();

            // Update UI
            updateAuthUI();
            showAlert(`Welcome, ${currentUser.name}!`, 'success');

            // Reset form
            document.getElementById('auth-form').reset();
        } else {
            showAlert(data.error || 'Authentication failed', 'danger');
        }
    } catch (error) {
        showAlert('Network error. Please try again.', 'danger');
        console.error('Authentication error:', error);
    }
}

/**
 * Logout user
 */
function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    updateAuthUI();
    showAlert('Logged out successfully', 'info');
}

/**
 * Update authentication UI
 */
function updateAuthUI() {
    const authButton = document.getElementById('auth-button');
    const authButtonText = document.getElementById('auth-button-text');
    const adminNavItem = document.getElementById('admin-nav-item');
    const adminSection = document.getElementById('admin-section');

    if (authToken && currentUser) {
        authButtonText.textContent = `Logout (${currentUser.name})`;

        // Show admin section for admins
        if (currentUser.role === 'admin') {
            adminNavItem.style.display = 'block';
            adminSection.style.display = 'block';
        }
    } else {
        authButtonText.textContent = 'Login';
        adminNavItem.style.display = 'none';
        adminSection.style.display = 'none';
    }
}

/**
 * Search packages
 */
async function searchPackages(event) {
    event.preventDefault();

    const searchInput = document.getElementById('search-input').value;
    const resultsContainer = document.getElementById('search-results');

    if (!authToken) {
        showAlert('Please login to search packages', 'warning');
        return;
    }

    // Show loading
    resultsContainer.innerHTML = '<div class="spinner-container"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';

    try {
        const response = await apiRequest(`/packages/byRegex?RegEx=${encodeURIComponent(searchInput)}`);
        const data = await response.json();

        if (response.ok && data.packages) {
            if (data.packages.length === 0) {
                resultsContainer.innerHTML = '<p class="text-muted">No packages found matching your search.</p>';
            } else {
                displaySearchResults(data.packages);
            }
        } else {
            showAlert(data.error || 'Search failed', 'danger');
            resultsContainer.innerHTML = '';
        }
    } catch (error) {
        showAlert('Error searching packages', 'danger');
        console.error('Search error:', error);
        resultsContainer.innerHTML = '';
    }
}

/**
 * Display search results
 */
function displaySearchResults(packages) {
    const resultsContainer = document.getElementById('search-results');
    
    let html = `<h3 class="h5 mb-3">Found ${packages.length} package(s)</h3>`;

    packages.forEach(pkg => {
        const netScore = pkg.scores?.net_score?.value || 0;
        const scoreClass = netScore >= 0.7 ? 'score-high' : netScore >= 0.4 ? 'score-medium' : 'score-low';

        html += `
            <div class="package-card">
                <div class="package-title">${escapeHtml(pkg.name)}</div>
                <div class="package-meta">
                    <span><i class="bi bi-tag" aria-hidden="true"></i> Version: ${escapeHtml(pkg.version)}</span>
                    <span class="ms-3"><i class="bi bi-calendar" aria-hidden="true"></i> ${new Date(pkg.created_at).toLocaleDateString()}</span>
                </div>
                <div class="mb-2">
                    <span class="score-badge ${scoreClass}">
                        Net Score: ${(netScore * 100).toFixed(0)}%
                    </span>
                </div>
                <div class="d-flex gap-2">
                    <a href="${escapeHtml(pkg.url)}" target="_blank" class="btn btn-sm btn-outline-primary">
                        <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
                        View on HuggingFace
                    </a>
                    <button class="btn btn-sm btn-outline-secondary" onclick="viewPackageDetails('${pkg.id}')">
                        <i class="bi bi-info-circle" aria-hidden="true"></i>
                        Details
                    </button>
                </div>
            </div>
        `;
    });

    resultsContainer.innerHTML = html;
}

/**
 * Upload package
 */
async function uploadPackage(event) {
    event.preventDefault();

    if (!authToken) {
        showAlert('Please login to upload packages', 'warning');
        return;
    }

    const name = document.getElementById('package-name').value;
    const version = document.getElementById('package-version').value;
    const url = document.getElementById('package-url').value;
    const isSensitive = document.getElementById('is-sensitive').checked;

    const resultsContainer = document.getElementById('upload-results');
    resultsContainer.innerHTML = '<div class="spinner-container"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Uploading and scoring...</span></div></div>';

    try {
        const response = await apiRequest('/package', {
            method: 'POST',
            body: JSON.stringify({
                name: name,
                version: version,
                url: url,
                is_sensitive: isSensitive
            })
        });

        const data = await response.json();

        if (response.ok) {
            showAlert('Package uploaded and scored successfully!', 'success');
            displayUploadResults(data);
            document.getElementById('upload-form').reset();
        } else {
            showAlert(data.error || 'Upload failed', 'danger');
            resultsContainer.innerHTML = '';
        }
    } catch (error) {
        showAlert('Error uploading package', 'danger');
        console.error('Upload error:', error);
        resultsContainer.innerHTML = '';
    }
}

/**
 * Display upload results
 */
function displayUploadResults(data) {
    const resultsContainer = document.getElementById('upload-results');
    
    const netScore = data.scores?.net_score?.value || 0;
    const scoreClass = netScore >= 0.7 ? 'success' : netScore >= 0.4 ? 'warning' : 'danger';

    let html = `
        <div class="alert alert-${scoreClass}">
            <h4 class="alert-heading">Package Uploaded Successfully!</h4>
            <p><strong>Package ID:</strong> ${escapeHtml(data.package_id)}</p>
            <p><strong>Net Score:</strong> ${(netScore * 100).toFixed(0)}%</p>
            <hr>
            <p class="mb-0">The package has been analyzed and is ready for use.</p>
        </div>
    `;

    resultsContainer.innerHTML = html;
}

/**
 * Load system health status
 */
async function loadHealthStatus() {
    const statusContainer = document.getElementById('health-status');

    try {
        const response = await fetch('/health/components');
        const data = await response.json();

        if (response.ok) {
            displayHealthStatus(data);
        } else {
            statusContainer.innerHTML = '<p class="text-danger">Failed to load health status</p>';
        }
    } catch (error) {
        statusContainer.innerHTML = '<p class="text-danger">Error loading health status</p>';
        console.error('Health check error:', error);
    }
}

/**
 * Display health status
 */
function displayHealthStatus(data) {
    const statusContainer = document.getElementById('health-status');
    
    const statusIcons = {
        ok: 'bi-check-circle-fill text-success',
        degraded: 'bi-exclamation-triangle-fill text-warning',
        critical: 'bi-x-circle-fill text-danger',
        unknown: 'bi-question-circle-fill text-secondary'
    };

    let html = `
        <div class="health-component health-status-${data.status}">
            <div class="d-flex align-items-center mb-3">
                <i class="bi ${statusIcons[data.status]} status-icon" aria-hidden="true"></i>
                <div>
                    <h3 class="h5 mb-0">Overall Status: ${data.status.toUpperCase()}</h3>
                    <small class="text-muted">Uptime: ${data.uptime_human}</small>
                </div>
            </div>
        </div>
    `;

    if (data.components) {
        html += '<h4 class="h6 mt-4 mb-3">Components</h4>';
        data.components.forEach(component => {
            html += `
                <div class="health-component health-status-${component.status}">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${component.name}</strong>
                            <span class="badge bg-${component.status === 'ok' ? 'success' : component.status === 'degraded' ? 'warning' : 'danger'} ms-2">
                                ${component.status}
                            </span>
                        </div>
                        ${component.response_time_ms ? `<small class="text-muted">${component.response_time_ms}ms</small>` : ''}
                    </div>
                    ${component.error_message ? `<small class="text-danger">${escapeHtml(component.error_message)}</small>` : ''}
                </div>
            `;
        });
    }

    statusContainer.innerHTML = html;
}

/**
 * Load users (admin only)
 */
async function loadUsers() {
    if (!authToken || currentUser?.role !== 'admin') {
        showAlert('Admin access required', 'danger');
        return;
    }

    const usersContainer = document.getElementById('users-list');
    usersContainer.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';

    try {
        const response = await apiRequest('/users');
        const data = await response.json();

        if (response.ok && data.users) {
            displayUsers(data.users);
        } else {
            showAlert(data.error || 'Failed to load users', 'danger');
            usersContainer.innerHTML = '';
        }
    } catch (error) {
        showAlert('Error loading users', 'danger');
        console.error('Load users error:', error);
        usersContainer.innerHTML = '';
    }
}

/**
 * Display users list
 */
function displayUsers(users) {
    const usersContainer = document.getElementById('users-list');
    
    let html = '<div class="table-responsive"><table class="table table-striped"><thead><tr><th>Username</th><th>Role</th><th>Created</th><th>Actions</th></tr></thead><tbody>';

    users.forEach(user => {
        html += `
            <tr>
                <td>${escapeHtml(user.username)}</td>
                <td><span class="badge bg-primary">${escapeHtml(user.role)}</span></td>
                <td>${new Date(user.created_at).toLocaleDateString()}</td>
                <td>
                    ${user.username !== 'admin' ? `<button class="btn btn-sm btn-danger" onclick="deleteUser('${user.username}')">Delete</button>` : ''}
                </td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    usersContainer.innerHTML = html;
}

/**
 * Reset system (admin only)
 */
async function resetSystem() {
    if (!authToken || currentUser?.role !== 'admin') {
        showAlert('Admin access required', 'danger');
        return;
    }

    if (!confirm('Are you sure you want to reset the entire system? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await apiRequest('/reset', { method: 'DELETE' });
        const data = await response.json();

        if (response.ok) {
            showAlert('System reset successfully', 'success');
            // Logout user
            logout();
        } else {
            showAlert(data.error || 'Reset failed', 'danger');
        }
    } catch (error) {
        showAlert('Error resetting system', 'danger');
        console.error('Reset error:', error);
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

/**
 * View package details
 */
async function viewPackageDetails(packageId) {
    if (!authToken) {
        showAlert('Please login to view package details', 'warning');
        return;
    }

    try {
        const response = await apiRequest(`/package/${packageId}`);
        const data = await response.json();

        if (response.ok) {
            // Show details in modal or alert
            alert(JSON.stringify(data, null, 2));
        } else {
            showAlert(data.error || 'Failed to load package details', 'danger');
        }
    } catch (error) {
        showAlert('Error loading package details', 'danger');
        console.error('Package details error:', error);
    }
}





