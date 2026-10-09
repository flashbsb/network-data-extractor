/**
 * Network Data Extractor - Admin Portal Client Adapter
 * Transparently bridges between live REST API (/api/v1/) and offline/GitHub Pages Mock Sandbox.
 */

class AdminAPIAdapter {
    constructor() {
        this.isDemoMode = (
            window.location.protocol === 'file:' ||
            window.location.hostname.includes('github.io') ||
            window.location.search.includes('mode=demo')
        );
        this.csrfToken = '';
        this.currentUser = null;
        this.mockSession = null;
        
        // Initial mock state for GitHub Pages showcase
        this._initMockState();
    }

    _initMockState() {
        if (!this.isDemoMode) return;
        
        // Persistent or in-memory demo mock data
        const savedMock = sessionStorage.getItem('ndx_demo_admin_user');
        if (savedMock) {
            try { this.mockSession = JSON.parse(savedMock); } catch (e) {}
        }
    }

    async getAuthStatus() {
        if (this.isDemoMode) {
            return {
                authenticated: !!this.mockSession,
                user: this.mockSession ? {
                    username: this.mockSession.username,
                    role: this.mockSession.role,
                    is_default_password: !!this.mockSession.is_default_password
                } : null
            };
        }

        try {
            const res = await fetch('/api/v1/auth/me');
            if (res.ok) {
                const data = await res.json();
                this.currentUser = data;
                this.csrfToken = data.csrf_token || '';
                return { authenticated: true, user: data };
            }
            return { authenticated: false, user: null };
        } catch (e) {
            // If fetch fails (e.g. static server), gracefully fallback to demo mode
            this.isDemoMode = true;
            return this.getAuthStatus();
        }
    }

    async login(username, password) {
        if (this.isDemoMode) {
            // Showcase simulation
            if ((username === 'admin' && (password === 'admin' || password === 'demo')) || username.length >= 3) {
                const isDefault = (username === 'admin' && password === 'admin');
                this.mockSession = {
                    username: username || 'admin',
                    role: username === 'admin' ? 'SuperAdmin' : 'Operator',
                    description: 'Public Showcase Session',
                    is_default_password: isDefault
                };
                sessionStorage.setItem('ndx_demo_admin_user', JSON.stringify(this.mockSession));
                return {
                    success: true,
                    username: this.mockSession.username,
                    role: this.mockSession.role,
                    is_default_password: isDefault
                };
            }
            return { success: false, message: 'Invalid demo credentials. Use admin / demo' };
        }

        try {
            const res = await fetch('/api/v1/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.csrfToken = data.csrf_token;
                this.currentUser = data;
                return {
                    success: true,
                    username: data.username,
                    role: data.role,
                    is_default_password: data.is_default_password
                };
            }
            return { success: false, message: data.message || 'Authentication failed' };
        } catch (e) {
            return { success: false, message: `Connection error: ${e.message}` };
        }
    }

    async logout() {
        if (this.isDemoMode) {
            this.mockSession = null;
            sessionStorage.removeItem('ndx_demo_admin_user');
            return { success: true };
        }

        try {
            await fetch('/api/v1/auth/logout', { method: 'POST' });
        } catch (e) {}
        this.currentUser = null;
        this.csrfToken = '';
        return { success: true };
    }

    async getSystemSummary() {
        if (this.isDemoMode) {
            return {
                total_runs: 10,
                latest_run: { id: "20261008_153513", formatted_date: "2026-10-08 15:35:13", node_count: 30 },
                oldest_run: { id: "20260908_153813", formatted_date: "2026-09-08 15:38:13", node_count: 30 },
                active_elements_count: 30,
                storage: {
                    disk_mb: 28.4,
                    database_mb: 6.2,
                    total_mb: 34.6
                },
                cron: {
                    status: "HEALTHY",
                    log_file: "cron_execution.log",
                    last_run_timestamp: "2026-10-08 15:35:13",
                    hours_since_last_run: 1.2,
                    is_delayed: false,
                    last_lines: [
                        "[INFO] [2026-10-08 15:30:00] Iniciando execucao da cron",
                        "[INFO] Filtro em uso: in:RTAC;RTED;RTOC;RTIC;RTPR;RTRR;SWAC;SWAG",
                        "[INFO] [2026-10-08 15:35:13] Execucao concluida com sucesso."
                    ]
                }
            };
        }

        const res = await fetch('/api/v1/summary');
        if (!res.ok) throw new Error('Failed to load system summary');
        return await res.json();
    }

    async listRuns() {
        if (this.isDemoMode) {
            return [
                { id: "20261008_153513", formatted_date: "2026-10-08 15:35:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20261005_124213", formatted_date: "2026-10-05 12:42:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20261002_134913", formatted_date: "2026-10-02 13:49:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260928_145613", formatted_date: "2026-09-28 14:56:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260925_130313", formatted_date: "2026-09-25 13:03:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260922_141013", formatted_date: "2026-09-22 14:10:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260918_151713", formatted_date: "2026-09-18 15:17:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260915_132413", formatted_date: "2026-09-15 13:24:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260912_143113", formatted_date: "2026-09-12 14:31:13", node_count: 30, has_ping: true, has_topology: true },
                { id: "20260908_153813", formatted_date: "2026-09-08 15:38:13", node_count: 30, has_ping: true, has_topology: true }
            ];
        }

        const res = await fetch('/api/v1/runs');
        if (!res.ok) throw new Error('Failed to load runs list');
        const data = await res.json();
        return data.runs || [];
    }

    async getRunSummary(runId) {
        if (this.isDemoMode) {
            return {
                run_id: runId,
                elements_health: {
                    total: 30,
                    counts: { ok: 30, failed: 0, timeout: 0, auth_fail: 0 },
                    elements: [
                        { element: "RT-CORE-BSB-01", status: "ok", error: "" },
                        { element: "RT-CORE-SPO-01", status: "ok", error: "" },
                        { element: "RT-CORE-RJO-01", status: "ok", error: "" },
                        { element: "RT-CORE-FOR-01", status: "ok", error: "" }
                    ]
                },
                ping_health: {
                    total: 74,
                    healthy: 72,
                    warning: 0,
                    critical: 0,
                    dead: 2,
                    avg_latency_ms: 18.7
                },
                topology_health: {
                    total_interfaces: 68,
                    interfaces_up: 64,
                    interfaces_down: 4,
                    total_links: 37,
                    lldp_mismatches: 0
                },
                has_dashboards: {
                    inventory: true,
                    diff: true,
                    topology: true,
                    ping_matrix: true
                }
            };
        }

        const res = await fetch(`/api/v1/runs/${runId}/summary`);
        if (!res.ok) throw new Error(`Failed to load summary for run ${runId}`);
        return await res.json();
    }

    async listConfigs() {
        if (this.isDemoMode) {
            return [
                { filename: "network.json", type: "json", description: "Network tier hierarchy, optic speeds & regexes", size_bytes: 4200, can_edit: true },
                { filename: "extractor.json", type: "json", description: "Threading, discovery & timeouts", size_bytes: 1400, can_edit: true },
                { filename: "ssh.json", type: "json", description: "SSH auth, banners, retries & prompt regex", size_bytes: 1200, can_edit: true },
                { filename: "ping.json", type: "json", description: "ICMP parameters, SLA thresholds & matrices", size_bytes: 1800, can_edit: true },
                { filename: "storage.json", type: "json", description: "SAL persistence mode & retention rules", size_bytes: 1600, can_edit: true },
                { filename: "commands.cfg", type: "cfg", description: "Assigned CLI collection macros", size_bytes: 850, can_edit: true },
                { filename: "commands.icmp.cfg", type: "cfg", description: "ICMP matrix origin and target pairs", size_bytes: 1240, can_edit: true }
            ];
        }

        const res = await fetch('/api/v1/configs');
        if (!res.ok) throw new Error('Failed to load configuration list');
        const data = await res.json();
        return data.configs || [];
    }

    async readConfig(filename) {
        if (this.isDemoMode) {
            const demoMockMap = {
                "network.json": '{\n  "routing_hierarchy": {\n    "core": ["RT.*CORE", "CR-.*"],\n    "aggregation": ["RT.*AGGR", "AGG-.*"]\n  }\n}',
                "commands.cfg": "# NOC Multivendor Commands\ncisco;show int status\ncisco;show lldp neighbors detail\n",
                "commands.icmp.cfg": "# ICMP Sweep Targets\nRT-CORE-BSB-01;192.0.2.1\nRT-CORE-SPO-01;192.0.2.2\n"
            };
            return {
                filename,
                content: demoMockMap[filename] || `// Mock configuration for ${filename}\n{\n  "enabled": true\n}\n`,
                is_json: filename.endsWith('.json'),
                can_edit: true
            };
        }

        const res = await fetch(`/api/v1/configs/${filename}`);
        if (!res.ok) throw new Error(`Failed to load ${filename}`);
        return await res.json();
    }

    async saveConfig(filename, content) {
        if (this.isDemoMode) {
            return { success: true, message: `[Simulated] Changes to ${filename} validated in demo sandbox` };
        }

        const res = await fetch(`/api/v1/configs/${filename}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken
            },
            body: JSON.stringify({ content })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to save configuration');
        return data;
    }

    async listUsers() {
        if (this.isDemoMode) {
            return {
                users: [
                    { username: "admin", role: "SuperAdmin", description: "Default System Administrator" },
                    { username: "noc_engineer", role: "NetOps", description: "Backbone Network Specialist" },
                    { username: "operator_shift1", role: "Operator", description: "NOC Tier 1 Duty Operator" }
                ],
                roles: ["SuperAdmin", "NetOps", "Operator", "Auditor"]
            };
        }

        const res = await fetch('/api/v1/users');
        if (!res.ok) throw new Error('Failed to load user list');
        return await res.json();
    }

    async createUser(payload) {
        if (this.isDemoMode) {
            return { success: true, message: `[Simulated] User ${payload.username} created in demo sandbox` };
        }

        const res = await fetch('/api/v1/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to create user');
        return data;
    }

    async updateUserPassword(username, newPassword) {
        if (this.isDemoMode) {
            const isDefault = (newPassword === 'admin');
            if (this.mockSession && this.mockSession.username === username) {
                this.mockSession.is_default_password = isDefault;
                sessionStorage.setItem('ndx_demo_admin_user', JSON.stringify(this.mockSession));
            }
            return { success: true, message: `[Simulated] Password updated for ${username} in demo sandbox` };
        }

        const res = await fetch(`/api/v1/users/${username}/password`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.csrfToken
            },
            body: JSON.stringify({ new_password: newPassword })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to update password');
        if (this.currentUser && this.currentUser.username === username) {
            this.currentUser.is_default_password = (newPassword === 'admin');
        }
        return data;
    }

    async deleteUser(username) {
        if (this.isDemoMode) {
            return { success: true, message: `[Simulated] User ${username} removed from demo sandbox` };
        }

        const res = await fetch(`/api/v1/users/${username}`, {
            method: 'DELETE',
            headers: { 'X-CSRF-Token': this.csrfToken }
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.message || 'Failed to delete user');
        return data;
    }
}

window.AdminAPIAdapter = AdminAPIAdapter;
