// FundMate Web App JavaScript

// Change date filter
function changeDateFilter(date) {
    const params = new URLSearchParams(window.location.search);
    params.set('date', date);
    window.location.search = params.toString();
}

// Check date status and run pipeline if missing
async function runDateIfMissing() {
    const inputEl = document.getElementById('date-input') || document.getElementById('date-select');
    if (!inputEl) return;
    const date = inputEl.value;
    if (!date) return;

    const statusEl = document.getElementById('date-status');
    try {
        const res = await fetch(`/api/date-status?date=${date}`);
        const data = await res.json();
        if (res.ok && data.exists) {
            changeDateFilter(date);
            return;
        }
        const confirmed = confirm(`No processed data for ${date}. Run pipeline with TC now?`);
        if (!confirmed) return;

        const runRes = await fetch(`/api/run-date?date=${date}&use_tc=true`, { method: 'POST' });
        const runData = await runRes.json();
        if (!runRes.ok || !runData.job_id) {
            showNotification(runData.error || 'Failed to start job', 'error');
            return;
        }
        showNotification(`Started job ${runData.job_id} for ${date}`, 'info');
        pollJob(runData.job_id, date);
    } catch (e) {
        if (statusEl) statusEl.textContent = 'Error checking date';
        showNotification(e.message, 'error');
    }
}

async function pollJob(jobId, targetDate) {
    const statusEl = document.getElementById('date-status');
    const check = async () => {
        const res = await fetch(`/api/jobs/${jobId}`);
        const data = await res.json();
        if (!res.ok) {
            if (statusEl) statusEl.textContent = 'Job not found';
            showNotification('Job not found', 'error');
            return;
        }
        if (statusEl) statusEl.textContent = `${data.status}: ${data.message || ''}`;
        if (data.status === 'completed') {
            showNotification('Date ready, reloading...', 'success');
            changeDateFilter(targetDate);
            return;
        }
        if (data.status === 'failed' || data.status === 'partial') {
            showNotification(data.error || 'Job failed', 'error');
            return;
        }
        setTimeout(check, 3000);
    };
    check();
}

// Format currency
function formatCurrency(value, currency = 'USD') {
    const symbols = {
        'USD': '$',
        'HKD': 'HK$',
        'CNY': '¥'
    };

    const symbol = symbols[currency] || currency + ' ';
    return symbol + parseFloat(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Format number
function formatNumber(value) {
    return parseFloat(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Format percentage
function formatPercent(value) {
    return parseFloat(value).toFixed(2) + '%';
}

// Show loading indicator
function showLoading() {
    const loader = document.createElement('div');
    loader.id = 'global-loader';
    loader.innerHTML = `
        <div style="
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        ">
            <div style="
                background: white;
                padding: 2rem;
                border-radius: 0.5rem;
                text-align: center;
            ">
                <div class="spinner"></div>
                <p style="margin-top: 1rem; font-weight: 600;">Loading...</p>
            </div>
        </div>
    `;
    document.body.appendChild(loader);
}

// Hide loading indicator
function hideLoading() {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.remove();
    }
}

// Copy text to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Copied to clipboard!', 'success');
    }).catch(err => {
        showNotification('Failed to copy', 'error');
    });
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#2563eb'};
        color: white;
        border-radius: 0.5rem;
        box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }

    .spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #f3f4f6;
        border-top: 4px solid #2563eb;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);

// API helpers
async function fetchAPI(endpoint) {
    try {
        showLoading();
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        hideLoading();
        return data;
    } catch (error) {
        hideLoading();
        showNotification('Failed to fetch data: ' + error.message, 'error');
        throw error;
    }
}

// Initialize tooltips
function initTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(element => {
        element.addEventListener('mouseenter', (e) => {
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = element.getAttribute('data-tooltip');
            tooltip.style.cssText = `
                position: absolute;
                background: #1e293b;
                color: white;
                padding: 0.5rem 0.75rem;
                border-radius: 0.25rem;
                font-size: 0.875rem;
                z-index: 1000;
                pointer-events: none;
                white-space: nowrap;
            `;

            document.body.appendChild(tooltip);

            const rect = element.getBoundingClientRect();
            tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';
            tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';

            element.addEventListener('mouseleave', () => {
                tooltip.remove();
            }, { once: true });
        });
    });
}

function setupDatePicker() {
    if (typeof flatpickr === 'undefined') return;
    const input = document.getElementById('date-input');
    if (!input) return;
    flatpickr(input, {
        dateFormat: 'Y-m-d',
        defaultDate: input.value || undefined,
        minDate: '2025-01-01',
        allowInput: true,
        disableMobile: true,
        position: 'below',
        onChange: (selectedDates, dateStr) => {
            input.value = dateStr;
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    setupDatePicker();
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initTooltips();

    // Add smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K for search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.focus();
        }
    }

    // Escape to clear search
    if (e.key === 'Escape') {
        const searchInput = document.getElementById('search-input');
        if (searchInput && searchInput.value) {
            searchInput.value = '';
            searchInput.dispatchEvent(new Event('keyup'));
        }
    }
});

// Export functions
window.FundMate = {
    formatCurrency,
    formatNumber,
    formatPercent,
    showLoading,
    hideLoading,
    copyToClipboard,
    showNotification,
    fetchAPI
};
