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
                    avg_latency_ms: 18.7,
                    dead_pairs: [
                        { origin: "RT-CORE-BSB-01", dest: "RT-EDGE-CBA-01", loss_pct: 100.0, avg_ms: null },
                        { origin: "RT-CORE-FOR-01", dest: "SW-METRO-NAT-02", loss_pct: 100.0, avg_ms: null }
                    ]
                },
                topology_health: {
                    total_interfaces: 68,
                    interfaces_up: 64,
                    interfaces_down: 4,
                    total_links: 37,
                    lldp_mismatches: 1,
                    lldp_mismatches_list: [
                        { Element: "RT-CORE-SPO-01", Interface: "TenGigE0/1/0/2", Actual_LLDP_Neighbor: "SW-METRO-SPO-01", remote_intf: "Port48", Mismatch_Reason: "Port speed / duplex mismatch detected", Configured_Description: "CONEXAO_METRO_SP_01" }
                    ]
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

    async getElementReliabilityAnalytics(fromDate, toDate) {
        if (this.isDemoMode) {
            // Simulated 32 nodes demo scenario with 10 historical snapshots
            return {
                from_date: fromDate || "2026-09-08",
                to_date: toDate || "2026-10-08",
                total_runs_analyzed: 10,
                runs_analyzed: [
                    "20261008_153513", "20261005_124213", "20261002_134913",
                    "20260928_145613", "20260925_130313", "20260922_141013",
                    "20260918_151713", "20260915_132413", "20260912_143113", "20260908_153813"
                ],
                catalogue_total: 32,
                summary: {
                    never_collected: 1,
                    chronic_failure: 1,
                    flapping: 2,
                    stable: 28,
                    total_monitored: 32
                },
                root_causes: {
                    timeout: 7,
                    auth_fail: 3,
                    conn_refused: 2,
                    other: 1
                },
                top_slow_culprits: [
                    { element: "RT-EDGE-RJO-02", tier: "edge", timeouts: 3, last_error: "Connection timed out after 90s (20261008_153513)" },
                    { element: "SW-METRO-CAMP-02", tier: "metro", timeouts: 2, last_error: "Read timeout waiting for prompt (20261005_124213)" },
                    { element: "DRTD-DCN-BSB-01", tier: "dcn", timeouts: 1, last_error: "Socket connect timeout (20260928_145613)" }
                ],
                elements: [
                    {
                        element: "RT-CE-REMOTE-99",
                        tier: "customer_cpe",
                        function: "Branch Office CPE",
                        in_catalogue: true,
                        total_attempts: 0,
                        success_count: 0,
                        failure_count: 0,
                        timeout_count: 0,
                        auth_count: 0,
                        status_category: "never_collected",
                        success_rate_pct: 0.0,
                        last_status: "unattempted",
                        last_run_id: null,
                        last_run_date: null,
                        last_ok_run_id: null,
                        last_ok_date: null,
                        last_error: "Never responded in any snapshot (Provisioned but unreachable)",
                        history: []
                    },
                    {
                        element: "RT-EDGE-RJO-02",
                        tier: "edge",
                        function: "Edge Distribution Router",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 0,
                        failure_count: 10,
                        timeout_count: 8,
                        auth_count: 2,
                        status_category: "chronic_failure",
                        success_rate_pct: 0.0,
                        last_status: "failed",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: null,
                        last_ok_date: null,
                        last_error: "SSH Connection timed out after 90s (20261008_153513)",
                        history: ["failed", "failed", "failed", "failed", "failed", "failed", "failed", "failed", "failed", "failed"]
                    },
                    {
                        element: "SW-METRO-CAMP-02",
                        tier: "metro",
                        function: "Metro Aggregation Switch",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 6,
                        failure_count: 4,
                        timeout_count: 3,
                        auth_count: 1,
                        status_category: "flapping",
                        success_rate_pct: 60.0,
                        last_status: "ok",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: "20261008_153513",
                        last_ok_date: "2026-10-08 15:35:13",
                        last_error: "Read timeout waiting for prompt (20261005_124213)",
                        history: ["ok", "failed", "ok", "ok", "failed", "ok", "failed", "ok", "ok", "failed"]
                    },
                    {
                        element: "DRTD-DCN-BSB-01",
                        tier: "dcn",
                        function: "DCN OAM Management Gateway",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 8,
                        failure_count: 2,
                        timeout_count: 1,
                        auth_count: 1,
                        status_category: "flapping",
                        success_rate_pct: 80.0,
                        last_status: "ok",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: "20261008_153513",
                        last_ok_date: "2026-10-08 15:35:13",
                        last_error: "Authentication rejected (20260928_145613)",
                        history: ["ok", "ok", "failed", "ok", "ok", "ok", "failed", "ok", "ok", "ok"]
                    },
                    {
                        element: "RT-CORE-BSB-01",
                        tier: "core",
                        function: "National Core Backbone",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 10,
                        failure_count: 0,
                        timeout_count: 0,
                        auth_count: 0,
                        status_category: "stable",
                        success_rate_pct: 100.0,
                        last_status: "ok",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: "20261008_153513",
                        last_ok_date: "2026-10-08 15:35:13",
                        last_error: "",
                        history: ["ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok"]
                    },
                    {
                        element: "RT-CORE-SPO-01",
                        tier: "core",
                        function: "National Core Backbone",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 10,
                        failure_count: 0,
                        timeout_count: 0,
                        auth_count: 0,
                        status_category: "stable",
                        success_rate_pct: 100.0,
                        last_status: "ok",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: "20261008_153513",
                        last_ok_date: "2026-10-08 15:35:13",
                        last_error: "",
                        history: ["ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok"]
                    },
                    {
                        element: "RT-CORE-RJO-01",
                        tier: "core",
                        function: "National Core Backbone",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 10,
                        failure_count: 0,
                        timeout_count: 0,
                        auth_count: 0,
                        status_category: "stable",
                        success_rate_pct: 100.0,
                        last_status: "ok",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: "20261008_153513",
                        last_ok_date: "2026-10-08 15:35:13",
                        last_error: "",
                        history: ["ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok"]
                    },
                    {
                        element: "RT-CORE-FOR-01",
                        tier: "core",
                        function: "National Core Backbone",
                        in_catalogue: true,
                        total_attempts: 10,
                        success_count: 10,
                        failure_count: 0,
                        timeout_count: 0,
                        auth_count: 0,
                        status_category: "stable",
                        success_rate_pct: 100.0,
                        last_status: "ok",
                        last_run_id: "20261008_153513",
                        last_run_date: "2026-10-08 15:35:13",
                        last_ok_run_id: "20261008_153513",
                        last_ok_date: "2026-10-08 15:35:13",
                        last_error: "",
                        history: ["ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok", "ok"]
                    }
                ]
            };
        }

        const params = new URLSearchParams();
        if (fromDate) params.append("from", fromDate);
        if (toDate) params.append("to", toDate);
        const qs = params.toString() ? `?${params.toString()}` : "";
        const res = await fetch(`/api/v1/analytics/element-reliability${qs}`);
        if (!res.ok) throw new Error("Failed to load element reliability analytics");
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
