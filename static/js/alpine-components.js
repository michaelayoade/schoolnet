/*  Alpine.js CSP-compatible components
 *  All inline x-data expressions are registered here as named components.
 *  Usage: <div x-data="componentName"> instead of <div x-data="{ ... }">
 */

document.addEventListener('alpine:init', function () {

    // ── Global: dark mode on <html> ───────────────────────────────────
    Alpine.data('darkModeRoot', function () {
        return {
            darkMode: localStorage.getItem('darkMode') === 'true',
            get darkClass() {
                return this.darkMode ? 'dark' : '';
            },
            init: function () {
                this.$watch('darkMode', function (val) {
                    localStorage.setItem('darkMode', val);
                });
            }
        };
    });

    // ── Toast notification system ─────────────────────────────────────
    Alpine.data('toastStore', function () {
        return {
            toasts: [],
            addToast: function (detail) {
                var id = Date.now();
                this.toasts.push({
                    id: id,
                    message: detail.message,
                    type: detail.type || 'info',
                    visible: true
                });
                var self = this;
                setTimeout(function () { self.removeToast(id); }, detail.duration || 4000);
            },
            toastClass: function (toast) {
                if (toast.type === 'success') return 'bg-green-600';
                if (toast.type === 'error') return 'bg-red-600';
                if (toast.type === 'warning') return 'bg-yellow-500';
                return 'bg-blue-600';
            },
            removeToast: function (id) {
                var self = this;
                var toast = this.toasts.find(function (t) { return t.id === id; });
                if (toast) toast.visible = false;
                setTimeout(function () {
                    self.toasts = self.toasts.filter(function (t) { return t.id !== id; });
                }, 300);
            }
        };
    });

    // ── Confirm dialog ────────────────────────────────────────────────
    Alpine.data('confirmDialog', function () {
        return {
            open: false,
            title: '',
            message: '',
            confirmLabel: 'Confirm',
            targetForm: null,
            show: function (detail) {
                this.title = detail.title || 'Are you sure?';
                this.message = detail.message || 'This action cannot be undone.';
                this.confirmLabel = detail.confirmLabel || 'Confirm';
                this.targetForm = detail.form || null;
                this.open = true;
            },
            onConfirm: function () {
                if (this.targetForm) this.targetForm.submit();
                this.open = false;
            },
            cancel: function () {
                this.targetForm = null;
                this.open = false;
            }
        };
    });

    // ── Simple toggle (sidebar, mobile nav, dropdowns) ────────────────
    Alpine.data('toggle', function () {
        return {
            open: false,
            toggle: function () { this.open = !this.open; },
            close: function () { this.open = false; }
        };
    });

    // ── Mobile nav (public) ───────────────────────────────────────────
    Alpine.data('mobileNav', function () {
        return {
            open: false,
            toggleNav: function () { this.open = !this.open; },
            close: function () { this.open = false; }
        };
    });

    // ── Sidebar toggle (admin, school, parent) ────────────────────────
    Alpine.data('sidebarLayout', function () {
        return {
            sidebarOpen: false,
            toggleSidebar: function () { this.sidebarOpen = !this.sidebarOpen; },
            closeSidebar: function () { this.sidebarOpen = false; }
        };
    });

    // ── Password visibility toggle ────────────────────────────────────
    Alpine.data('passwordToggle', function () {
        return {
            showPassword: false,
            togglePassword: function () { this.showPassword = !this.showPassword; }
        };
    });

    // ── Multi-password toggle (settings page) ─────────────────────────
    Alpine.data('passwordSettings', function () {
        return {
            showCurrent: false,
            showNew: false,
            showConfirm: false,
            toggleCurrent: function () { this.showCurrent = !this.showCurrent; },
            toggleNew: function () { this.showNew = !this.showNew; },
            toggleConfirm: function () { this.showConfirm = !this.showConfirm; }
        };
    });

    // ── Reset password form with mismatch check ───────────────────────
    Alpine.data('resetPassword', function () {
        return {
            password: '',
            confirm: '',
            get mismatch() {
                return this.confirm && this.password !== this.confirm;
            }
        };
    });

    // ── Star rating picker ────────────────────────────────────────────
    Alpine.data('starRating', function () {
        return {
            rating: 0,
            hoveredRating: 0,
            setRating: function (val) { this.rating = val; },
            hoverRating: function (val) { this.hoveredRating = val; },
            resetHover: function () { this.hoveredRating = 0; },
            isActive: function (star) {
                return (this.hoveredRating || this.rating) >= star;
            },
            starClass: function (star) {
                return this.isActive(star) ? 'text-yellow-400' : 'text-slate-300 dark:text-slate-600';
            }
        };
    });

    // ── Notification bell (admin topbar) ──────────────────────────────
    Alpine.data('notificationBell', function () {
        return {
            open: false,
            unreadCount: 0,
            notifications: [],
            ws: null,
            reconnectTimer: null,

            init: function () {
                this.fetchNotifications();
                this.connectWebSocket();
                var self = this;
                setInterval(function () { self.fetchUnreadCount(); }, 60000);
            },

            toggle: function () {
                this.open = !this.open;
                if (this.open) this.fetchNotifications();
            },

            close: function () { this.open = false; },

            fetchNotifications: function () {
                var self = this;
                var token = this.getToken();
                if (!token) return;
                fetch('/notifications/me?limit=10', {
                    headers: { 'Authorization': 'Bearer ' + token }
                }).then(function (resp) {
                    if (resp.ok) return resp.json();
                }).then(function (data) {
                    if (data) {
                        self.notifications = data.items || [];
                        self.fetchUnreadCount();
                    }
                }).catch(function (e) { console.debug('[Notifications] fetch failed:', e); });
            },

            fetchUnreadCount: function () {
                var self = this;
                var token = this.getToken();
                if (!token) return;
                fetch('/notifications/me/unread-count', {
                    headers: { 'Authorization': 'Bearer ' + token }
                }).then(function (resp) {
                    if (resp.ok) return resp.json();
                }).then(function (data) {
                    if (data) self.unreadCount = data.count;
                }).catch(function () {});
            },

            markRead: function (n) {
                if (n.is_read) return;
                var self = this;
                var token = this.getToken();
                if (!token) return;
                fetch('/notifications/me/' + n.id + '/read', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token }
                }).then(function () {
                    n.is_read = true;
                    self.unreadCount = Math.max(0, self.unreadCount - 1);
                }).catch(function () {});
            },

            markAllRead: function () {
                var self = this;
                var token = this.getToken();
                if (!token) return;
                fetch('/notifications/me/read-all', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token }
                }).then(function () {
                    self.notifications.forEach(function (n) { n.is_read = true; });
                    self.unreadCount = 0;
                }).catch(function () {});
            },

            connectWebSocket: function () {
                var self = this;
                var token = this.getToken();
                if (!token) return;
                var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                var wsUrl = protocol + '//' + window.location.host + '/ws/notifications';
                try {
                    this.ws = new WebSocket(wsUrl, token);
                    this.ws.onmessage = function (event) {
                        try {
                            var data = JSON.parse(event.data);
                            if (data.type === 'notification') {
                                self.unreadCount++;
                                self.notifications.unshift(data.notification);
                                if (self.notifications.length > 10) self.notifications.pop();
                                if (window.showToast) window.showToast(data.notification.title, 'info');
                            }
                        } catch (e) {}
                    };
                    this.ws.onclose = function () { self.scheduleReconnect(); };
                    this.ws.onerror = function () { if (self.ws) self.ws.close(); };
                } catch (e) {
                    this.scheduleReconnect();
                }
            },

            scheduleReconnect: function () {
                var self = this;
                if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
                this.reconnectTimer = setTimeout(function () { self.connectWebSocket(); }, 5000);
            },

            getToken: function () {
                var match = document.cookie.match(/(?:^|;\s*)access_token=([^;]*)/);
                return match ? match[1] : '';
            },

            hasUnread: function () {
                return this.unreadCount > 0;
            },

            unreadDisplay: function () {
                return this.unreadCount > 99 ? '99+' : String(this.unreadCount);
            },

            noNotifications: function () {
                return this.notifications.length === 0;
            },

            notificationHref: function (n) {
                return n.action_url || '#';
            },

            notificationRowClass: function (n) {
                return n.is_read ? '' : 'bg-primary-50/50 dark:bg-primary-900/10';
            },

            notificationMessage: function (n) {
                return n.message || '';
            },

            destroy: function () {
                if (this.ws) { this.ws.close(); this.ws = null; }
                if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
            }
        };
    });

    // ── Dark mode toggle button ───────────────────────────────────────
    Alpine.data('darkModeToggle', function () {
        return {
            toggleDarkMode: function () {
                this.darkMode = !this.darkMode;
            }
        };
    });

    // ── User dropdown (admin topbar) ──────────────────────────────────
    Alpine.data('userDropdown', function () {
        return {
            userOpen: false,
            toggleUser: function () { this.userOpen = !this.userOpen; },
            closeUser: function () { this.userOpen = false; }
        };
    });

    // ── Counter (index dashboard) ─────────────────────────────────────
    Alpine.data('counter', function () {
        return {
            count: 214,
            increment: function () { this.count = this.count + 1; }
        };
    });

    // ── Scroll-triggered animated counter ───────────────────────────
    Alpine.data('scrollCounter', function () {
        return {
            started: false,
            val1: 0,
            val2: 0,
            val3: 0,
            target1: 100,
            target2: 1000,
            target3: 36,
            startCounting: function () {
                if (this.started) return;
                this.started = true;
                var self = this;
                var duration = 2000;
                var steps = 60;
                var interval = duration / steps;
                var step = 0;
                var timer = setInterval(function () {
                    step++;
                    var progress = step / steps;
                    // Ease-out cubic
                    var eased = 1 - Math.pow(1 - progress, 3);
                    self.val1 = Math.round(self.target1 * eased);
                    self.val2 = Math.round(self.target2 * eased);
                    self.val3 = Math.round(self.target3 * eased);
                    if (step >= steps) {
                        clearInterval(timer);
                        self.val1 = self.target1;
                        self.val2 = self.target2;
                        self.val3 = self.target3;
                    }
                }, interval);
            }
        };
    });

    // ── Filter chip dismiss (search page) ───────────────────────────
    Alpine.data('filterChips', function () {
        return {
            dismiss: function (param) {
                var url = new URL(window.location.href);
                url.searchParams.delete(param);
                window.location.href = url.toString();
            }
        };
    });

    // ── File drop zone ────────────────────────────────────────────────
    Alpine.data('fileDrop', function () {
        return {
            dragging: false,
            fileName: '',
            onDragOver: function () { this.dragging = true; },
            onDragLeave: function () { this.dragging = false; },
            onDrop: function (event) {
                this.dragging = false;
                var files = event.dataTransfer.files;
                this.fileName = (files[0] && files[0].name) || '';
                this.$refs.fileInput.files = files;
            },
            onFileChange: function (event) {
                var files = event.target.files;
                this.fileName = (files[0] && files[0].name) || '';
            }
        };
    });

    // ── File upload with preview (branding logo) ──────────────────────
    Alpine.data('fileUploadPreview', function () {
        return {
            preview: '',
            filename: '',
            init: function () {
                if (this.$el.dataset.init) {
                    this.preview = this.$el.dataset.init;
                }
            },
            onFileChange: function (event) {
                var f = event.target.files[0];
                if (!f) return;
                this.filename = f.name;
                var self = this;
                var reader = new FileReader();
                reader.onload = function (e) { self.preview = e.target.result; };
                reader.readAsDataURL(f);
            },
            onRemove: function (event) {
                if (event.target.checked) {
                    this.preview = '';
                    this.filename = '';
                }
            }
        };
    });

    // ── Confirm action dispatcher (for forms) ─────────────────────────
    Alpine.data('confirmAction', function () {
        return {
            dispatchConfirm: function () {
                this.$dispatch('confirm-action', {
                    title: this.$el.dataset.confirmTitle || 'Are you sure?',
                    message: this.$el.dataset.confirmMessage || 'This action cannot be undone.',
                    confirmLabel: this.$el.dataset.confirmLabel || 'Confirm',
                    form: this.$el
                });
            }
        };
    });

    // ── Branding editor ───────────────────────────────────────────────
    Alpine.data('brandingEditor', function () {
        return {
            primary: '#06B6D4',
            accent: '#F97316',
            displayFont: 'Outfit',
            bodyFont: 'Plus Jakarta Sans',
            init: function () {
                if (this.$el.dataset.init) {
                    var opts = JSON.parse(this.$el.dataset.init);
                    this.primary = opts.primary || this.primary;
                    this.accent = opts.accent || this.accent;
                    this.displayFont = opts.displayFont || this.displayFont;
                    this.bodyFont = opts.bodyFont || this.bodyFont;
                }
            },
            gradientStyle: function () {
                return 'background: linear-gradient(120deg, ' + this.primary + ', ' + this.accent + ')';
            },
            displayFontStyle: function () {
                return 'font-family: ' + this.displayFont;
            },
            bodyFontStyle: function () {
                return 'font-family: ' + this.bodyFont;
            }
        };
    });

    // ── Admin sidebar with collapsible sections ───────────────────────
    Alpine.data('adminSidebar', function () {
        return {
            search: '',
            sections: {},
            init: function () {
                var keys = (this.$el.dataset.sections || '').split(',').filter(Boolean);
                var self = this;
                keys.forEach(function (k) {
                    var stored = localStorage.getItem('sidebar_' + k);
                    self.sections[k] = stored !== null ? JSON.parse(stored) : true;
                });
                this.$watch('sections', function (val) {
                    Object.keys(val).forEach(function (k) {
                        localStorage.setItem('sidebar_' + k, val[k]);
                    });
                });
            },
            toggleSection: function (key) {
                this.sections[key] = !this.sections[key];
            },
            showItem: function (label) {
                if (!this.search) return true;
                return label.toLowerCase().includes(this.search.toLowerCase());
            },
            showSection: function (key) {
                return this.sections[key] || !!this.search;
            },
            isSectionOpen: function (key) {
                return !!this.sections[key];
            },
            sectionChevronClass: function (key) {
                return this.sections[key] ? '' : '-rotate-90';
            }
        };
    });

    // ── Dynamic form builder (admission forms create/edit) ────────────
    Alpine.data('formBuilder', function () {
        return {
            fields: [],
            init: function () {
                if (this.$el.dataset.init) {
                    var parsed = JSON.parse(this.$el.dataset.init);
                    this.fields = parsed.map(function (f) {
                        return Object.assign({}, f, {
                            _optionsText: (f.options || []).join(', ')
                        });
                    });
                }
            },
            addField: function () {
                this.fields.push({
                    name: '', label: '', type: 'text',
                    required: false, options: [], _optionsText: ''
                });
            },
            removeField: function (index) {
                this.fields.splice(index, 1);
            },
            onLabelInput: function (field) {
                field.name = field.label.toLowerCase()
                    .replace(/[^a-z0-9]+/g, '_')
                    .replace(/^_|_$/g, '');
            },
            onOptionsInput: function (field) {
                field.options = field._optionsText
                    .split(',')
                    .map(function (o) { return o.trim(); })
                    .filter(function (o) { return o; });
            },
            fieldTitle: function (index) {
                return 'Field #' + (index + 1);
            },
            isSelectType: function (field) {
                return field.type === 'select';
            },
            fieldIdAttr: function (index) {
                return 'req_' + index;
            },
            fieldsJson: function () {
                return JSON.stringify(this.fields.map(function (f) {
                    var obj = { name: f.name, label: f.label, type: f.type, required: f.required };
                    if (f.type === 'select') obj.options = f.options;
                    return obj;
                }));
            }
        };
    });

    // ── Document list builder (admission forms) ───────────────────────
    Alpine.data('docList', function () {
        return {
            docs: [],
            init: function () {
                if (this.$el.dataset.init) {
                    this.docs = JSON.parse(this.$el.dataset.init);
                }
            },
            addDoc: function () { this.docs.push(''); },
            removeDoc: function (index) { this.docs.splice(index, 1); },
            docsJson: function () {
                return JSON.stringify(this.docs.filter(function (d) { return d.trim(); }));
            }
        };
    });

    // ── Ward source selector (application fill) ───────────────────────
    Alpine.data('wardSelector', function () {
        return {
            wardSource: 'manual',
            selectedWardId: '',
            wards: [],
            init: function () {
                if (this.$el.dataset.init) {
                    this.wards = JSON.parse(this.$el.dataset.init);
                }
                var self = this;
                this.$watch('selectedWardId', function (id) {
                    if (!id) return;
                    var ward = self.wards.find(function (w) { return String(w.id) === String(id); });
                    if (!ward) return;
                    var fields = {
                        'ward_first_name': ward.first_name,
                        'ward_last_name': ward.last_name,
                        'ward_dob': ward.date_of_birth,
                        'ward_gender': ward.gender
                    };
                    Object.keys(fields).forEach(function (name) {
                        var el = document.querySelector('[name="' + name + '"]');
                        if (el && fields[name]) {
                            el.value = fields[name];
                            el.dispatchEvent(new Event('input'));
                        }
                    });
                });
            },
            onSourceChange: function (event) {
                if (event.target.value === 'manual') {
                    this.selectedWardId = '';
                } else {
                    this.selectedWardId = event.target.value;
                }
            },
            wardBindValue: function () {
                return this.wardSource !== 'manual' ? this.wardSource : '';
            }
        };
    });

});
