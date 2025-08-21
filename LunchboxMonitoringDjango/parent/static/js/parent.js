/**
 * Parent Portal JavaScript
 * Handles client-side interactions for the parent portal
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Handle notification toggles
    const notificationToggles = document.querySelectorAll('.notification-toggle');
    notificationToggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const notificationId = this.dataset.notificationId;
            const isRead = this.checked;
            
            // Send AJAX request to update notification status
            fetch(`/parent/notifications/${notificationId}/toggle/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    is_read: isRead
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    updateUnreadCount();
                } else {
                    this.checked = !isRead; // Revert on error
                    showToast('Error updating notification', 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                this.checked = !isRead; // Revert on error
                showToast('An error occurred', 'danger');
            });
        });
    });

    // Handle form submissions with AJAX
    const ajaxForms = document.querySelectorAll('form.ajax-form');
    ajaxForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const submitButton = this.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.innerHTML;
            
            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
            
            fetch(this.action, {
                method: this.method,
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showToast(data.message || 'Changes saved successfully', 'success');
                    if (data.redirect) {
                        setTimeout(() => {
                            window.location.href = data.redirect;
                        }, 1500);
                    }
                } else {
                    showToast(data.message || 'An error occurred', 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('An error occurred while saving', 'danger');
            })
            .finally(() => {
                // Reset button state
                submitButton.disabled = false;
                submitButton.innerHTML = originalButtonText;
            });
        });
    });

    // Initialize charts if on dashboard
    if (document.getElementById('temperatureChart')) {
        initializeTemperatureChart();
    }

    // Initialize real-time updates if on dashboard
    if (document.getElementById('realtime-updates')) {
        initializeRealtimeUpdates();
    }
});

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of toast (success, danger, warning, info)
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;
    
    const toastId = 'toast-' + Date.now();
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastEl = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastEl, { autohide: true, delay: 5000 });
    toast.show();
    
    // Remove toast after it's hidden
    toastEl.addEventListener('hidden.bs.toast', function() {
        toastEl.remove();
    });
}

/**
 * Get cookie by name
 * @param {string} name - The name of the cookie
 * @returns {string} The cookie value
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Update the unread notification count in the navbar
 */
function updateUnreadCount() {
    fetch('/parent/notifications/unread-count/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        const badge = document.querySelector('.notification-badge');
        if (badge) {
            if (data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    })
    .catch(error => console.error('Error updating unread count:', error));
}

/**
 * Initialize temperature chart using Chart.js
 */
function initializeTemperatureChart() {
    const ctx = document.getElementById('temperatureChart').getContext('2d');
    
    // Sample data - replace with actual data from your backend
    const labels = [];
    const data = [];
    
    // Generate sample data for the last 24 hours
    const now = new Date();
    for (let i = 23; i >= 0; i--) {
        const time = new Date(now);
        time.setHours(now.getHours() - i);
        labels.push(time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        
        // Random temperature between 15°C and 30°C for demo
        data.push(Math.random() * 15 + 15);
    }
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Temperature (°C)',
                data: data,
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.3,
                fill: true,
                backgroundColor: 'rgba(75, 192, 192, 0.1)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y.toFixed(1) + '°C';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                },
                x: {
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            }
        }
    });
}

/**
 * Initialize real-time updates using WebSockets or polling
 */
function initializeRealtimeUpdates() {
    // Check if WebSockets are supported
    if (typeof WebSocket !== 'undefined' || typeof MozWebSocket !== 'undefined') {
        setupWebSocket();
    } else {
        // Fallback to polling
        setupPolling();
    }
}

/**
 * Set up WebSocket connection for real-time updates
 */
function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    const wsUri = protocol + window.location.host + '/ws/parent/';
    
    try {
        const socket = new WebSocket(wsUri);
        
        socket.onopen = function(e) {
            console.log('WebSocket connection established');
        };
        
        socket.onmessage = function(e) {
            const data = JSON.parse(e.data);
            handleRealtimeUpdate(data);
        };
        
        socket.onclose = function(e) {
            console.log('WebSocket connection closed. Attempting to reconnect...');
            // Attempt to reconnect after a delay
            setTimeout(setupWebSocket, 5000);
        };
        
        socket.onerror = function(err) {
            console.error('WebSocket error:', err);
            // Fall back to polling on error
            setupPolling();
        };
    } catch (err) {
        console.error('Error setting up WebSocket:', err);
        // Fall back to polling on error
        setupPolling();
    }
}

/**
 * Set up polling for real-time updates
 */
function setupPolling() {
    // Poll every 30 seconds
    setInterval(fetchUpdates, 30000);
    
    // Initial fetch
    fetchUpdates();
}

/**
 * Fetch updates from the server
 */
function fetchUpdates() {
    fetch('/parent/api/updates/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            handleRealtimeUpdate(data);
        }
    })
    .catch(error => console.error('Error fetching updates:', error));
}

/**
 * Handle real-time update data
 * @param {Object} data - The update data from the server
 */
function handleRealtimeUpdate(data) {
    // Update notification count
    if (data.unread_count !== undefined) {
        updateUnreadCount();
    }
    
    // Show new notification
    if (data.notification) {
        showToast(data.notification.message, data.notification.type || 'info');
    }
    
    // Refresh dashboard data if needed
    if (data.refresh_dashboard) {
        window.location.reload();
    }
}
