# -*- coding: utf-8 -*-
"""
Theme System Module (NDX Universal Theming)
===========================================
Provides standardized CSS Custom Properties, anti-FOUC initialization script,
accessible UI theme switcher component, and iframe synchronization for:
- Dark (Default NOC / Deep Obsidian)
- Light (Paper Clean / Enterprise Day Mode)
- HighText (WCAG AAA High Contrast / Pure Black & High Legibility)
"""

THEME_HEAD_INIT = """    <script>
        (function() {
            if (window.self !== window.top) {
                document.documentElement.classList.add('in-iframe');
            }
            try {
                var theme = localStorage.getItem('ndx_theme') || localStorage.getItem('nde_theme') || 'dark';
                document.documentElement.setAttribute('data-theme', theme);
            } catch(e) {}
        })();
    </script>"""

THEME_CSS = """
        /* Hide redundant switcher and portal link when embedded inside iframe */
        html.in-iframe .theme-switcher,
        body.in-iframe .theme-switcher,
        html.in-iframe .back-portal,
        body.in-iframe .back-portal {
            display: none !important;
        }

        /* === THEME SYSTEM DESIGN TOKENS === */
        :root, :root[data-theme="dark"] {
            --bg-dark: #020617;
            --sidebar-bg: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.4);
            --card-hover: rgba(30, 41, 59, 0.8);
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #1e293b;
            --border-light: rgba(255, 255, 255, 0.08);
            --glass: rgba(15, 23, 42, 0.7);
            --table-hover: rgba(56, 189, 248, 0.05);
            --table-stripe: rgba(255, 255, 255, 0.02);
            --hud-header-bg: rgba(15, 23, 42, 0.75);
            --stat-card-bg: #0f172a;
            --tag-up-bg: rgba(34, 197, 94, 0.15);
            --tag-up-text: #4ade80;
            --tag-down-bg: rgba(239, 68, 68, 0.15);
            --tag-down-text: #f87171;
            --switcher-bg: rgba(15, 23, 42, 0.8);
            --switcher-btn-bg: transparent;
            --switcher-btn-active: #38bdf8;
            --switcher-btn-active-text: #020617;
        }

        :root[data-theme="light"] {
            --bg-dark: #f8fafc;
            --sidebar-bg: #ffffff;
            --card-bg: #ffffff;
            --card-hover: #f1f5f9;
            --accent: #0284c7;
            --accent-hover: #0369a1;
            --text: #0f172a;
            --text-dim: #475569;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
            --border: #cbd5e1;
            --border-light: #e2e8f0;
            --glass: rgba(255, 255, 255, 0.9);
            --table-hover: rgba(2, 132, 199, 0.06);
            --table-stripe: #f8fafc;
            --hud-header-bg: rgba(255, 255, 255, 0.9);
            --stat-card-bg: #ffffff;
            --tag-up-bg: rgba(22, 163, 74, 0.12);
            --tag-up-text: #15803d;
            --tag-down-bg: rgba(220, 38, 38, 0.12);
            --tag-down-text: #b91c1c;
            --switcher-bg: #e2e8f0;
            --switcher-btn-bg: transparent;
            --switcher-btn-active: #0284c7;
            --switcher-btn-active-text: #ffffff;
        }

        :root[data-theme="hightext"] {
            --bg-dark: #000000;
            --sidebar-bg: #000000;
            --card-bg: #000000;
            --card-hover: #18181b;
            --accent: #facc15;
            --accent-hover: #eab308;
            --text: #ffffff;
            --text-dim: #fef08a;
            --success: #4ade80;
            --warning: #facc15;
            --danger: #f87171;
            --border: #ffffff;
            --border-light: #ffffff;
            --glass: #000000;
            --table-hover: #1f1f1f;
            --table-stripe: #0a0a0a;
            --hud-header-bg: #000000;
            --stat-card-bg: #000000;
            --tag-up-bg: #000000;
            --tag-up-text: #4ade80;
            --tag-down-bg: #000000;
            --tag-down-text: #f87171;
            --switcher-bg: #000000;
            --switcher-btn-bg: #000000;
            --switcher-btn-active: #facc15;
            --switcher-btn-active-text: #000000;
        }

        /* Smooth theme transitions */
        body, .main-content, .sidebar, .hud-header, .card, .metric-card, table, th, td {
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }

        /* === UNIVERSAL COMPONENT OVERRIDES: LIGHT THEME === */
        :root[data-theme="light"] body {
            background-color: var(--bg-dark);
            color: var(--text);
        }
        :root[data-theme="light"] .main-content {
            background: var(--bg-dark) !important;
            color: var(--text);
        }
        :root[data-theme="light"] .sidebar {
            background-color: var(--sidebar-bg) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .sidebar .header {
            background: var(--sidebar-bg) !important;
            border-bottom: 1px solid var(--border) !important;
        }
        :root[data-theme="light"] .sidebar-footer {
            background: var(--sidebar-bg) !important;
            border-top: 1px solid var(--border) !important;
        }
        :root[data-theme="light"] .hud-header {
            background: var(--glass) !important;
            border-bottom: 1px solid var(--border) !important;
        }
        :root[data-theme="light"] .sidebar-toggle-btn {
            background: var(--card-bg) !important;
            color: var(--text) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .back-portal {
            background: var(--card-bg) !important;
            color: var(--accent) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .back-portal:hover {
            background: var(--accent) !important;
            color: #ffffff !important;
        }
        :root[data-theme="light"] .card {
            background: var(--card-bg) !important;
            border-color: var(--border) !important;
            color: var(--text) !important;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
        }
        :root[data-theme="light"] .card .title {
            color: var(--text) !important;
        }
        :root[data-theme="light"] .card .desc {
            color: var(--text-dim) !important;
        }
        :root[data-theme="light"] .sub-btn {
            background: #f1f5f9 !important;
            color: var(--text) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .sub-btn:hover:not(.disabled) {
            background: #e2e8f0 !important;
            color: var(--accent) !important;
            border-color: var(--accent) !important;
        }
        :root[data-theme="light"] .metric-card {
            background: var(--card-bg) !important;
            border-color: var(--border) !important;
            color: var(--text) !important;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05) !important;
        }
        :root[data-theme="light"] .controls-bar,
        :root[data-theme="light"] .topo-controls,
        :root[data-theme="light"] .compare-filters,
        :root[data-theme="light"] .compare-header {
            background: var(--sidebar-bg) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .table-container,
        :root[data-theme="light"] .diff-card {
            background: var(--card-bg) !important;
            border-color: var(--border) !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05) !important;
        }
        :root[data-theme="light"] table th,
        :root[data-theme="light"] .diff-table th {
            background: #f1f5f9 !important;
            color: var(--text-dim) !important;
            border-bottom: 2px solid var(--border) !important;
        }
        :root[data-theme="light"] table td,
        :root[data-theme="light"] .diff-table td {
            color: var(--text) !important;
            border-bottom: 1px solid var(--border) !important;
        }
        :root[data-theme="light"] table tr:hover td,
        :root[data-theme="light"] .diff-table tr:hover td {
            background: rgba(2, 132, 199, 0.05) !important;
        }
        :root[data-theme="light"] .input-styled,
        :root[data-theme="light"] .control-input,
        :root[data-theme="light"] .control-select {
            background: #ffffff !important;
            color: var(--text) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .checkbox-group {
            background: #ffffff !important;
            border-color: var(--border) !important;
            color: var(--text) !important;
        }
        :root[data-theme="light"] .run-item {
            background: #f8fafc !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .run-item:hover {
            background: #f1f5f9 !important;
            border-color: var(--accent) !important;
        }
        :root[data-theme="light"] .run-item.active {
            background: rgba(2, 132, 199, 0.1) !important;
            border-color: var(--accent) !important;
        }
        :root[data-theme="light"] .run-date {
            color: var(--text) !important;
        }
        :root[data-theme="light"] .run-id {
            color: var(--text-dim) !important;
        }
        :root[data-theme="light"] .context-menu {
            background: #ffffff !important;
            border-color: var(--border) !important;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15) !important;
        }
        :root[data-theme="light"] .context-menu a {
            color: var(--text) !important;
        }
        :root[data-theme="light"] .context-menu a:hover:not(.disabled) {
            background: rgba(2, 132, 199, 0.1) !important;
            color: var(--accent) !important;
        }
        :root[data-theme="light"] .timeline-form-card {
            background: var(--card-bg) !important;
            border-color: var(--border) !important;
        }
        :root[data-theme="light"] .tab-btn {
            background: #f1f5f9;
            border-color: var(--border);
            color: var(--text-dim);
        }
        :root[data-theme="light"] .tab-btn.active {
            background: var(--accent);
            color: #ffffff !important;
            border-color: var(--accent);
        }
        :root[data-theme="light"] .conn-node {
            background: #e2e8f0 !important;
            color: var(--text) !important;
        }

        /* === UNIVERSAL COMPONENT OVERRIDES: HIGHTEXT THEME === */
        :root[data-theme="hightext"] .main-content {
            background: #000000 !important;
        }
        :root[data-theme="hightext"] .sidebar,
        :root[data-theme="hightext"] .sidebar .header,
        :root[data-theme="hightext"] .sidebar-footer {
            background: #000000 !important;
            border-color: #ffffff !important;
        }
        :root[data-theme="hightext"] .card,
        :root[data-theme="hightext"] .metric-card,
        :root[data-theme="hightext"] .table-container,
        :root[data-theme="hightext"] .diff-card {
            background: #000000 !important;
            border: 2px solid #ffffff !important;
        }
        :root[data-theme="hightext"] table th,
        :root[data-theme="hightext"] .diff-table th {
            background: #000000 !important;
            color: #facc15 !important;
            border-bottom: 2px solid #ffffff !important;
        }
        :root[data-theme="hightext"] table td,
        :root[data-theme="hightext"] .diff-table td {
            color: #ffffff !important;
            border-bottom: 1px solid #ffffff !important;
        }
        :root[data-theme="hightext"] .input-styled,
        :root[data-theme="hightext"] .checkbox-group {
            background: #000000 !important;
            color: #ffffff !important;
            border: 2px solid #ffffff !important;
        }
        :root[data-theme="hightext"] .run-item {
            background: #000000 !important;
            border: 1px solid #ffffff !important;
        }
        :root[data-theme="hightext"] .run-item.active {
            border: 2px solid #facc15 !important;
            background: #18181b !important;
        }
        :root[data-theme="hightext"] .sub-btn {
            background: #000000 !important;
            color: #ffffff !important;
            border: 1px solid #ffffff !important;
        }
        :root[data-theme="hightext"] .context-menu {
            background: #000000 !important;
            border: 2px solid #ffffff !important;
        }
        :root[data-theme="hightext"] .context-menu a {
            color: #ffffff !important;
        }

        /* Theme Switcher Pill Component */
        .theme-switcher {
            display: inline-flex;
            align-items: center;
            background: var(--switcher-bg);
            border: 1px solid var(--border);
            border-radius: 9999px;
            padding: 3px;
            gap: 2px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            z-index: 100;
        }
        .theme-btn {
            background: var(--switcher-btn-bg);
            border: none;
            color: var(--text-dim);
            padding: 5px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 4px;
            transition: all 0.2s ease;
            white-space: nowrap;
            font-family: inherit;
        }
        .theme-btn:hover {
            color: var(--text);
        }
        .theme-btn.active {
            background: var(--switcher-btn-active);
            color: var(--switcher-btn-active-text);
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
        }
"""

THEME_SWITCHER_HTML = """
            <div class="theme-switcher" id="themeSwitcher" role="group" aria-label="Theme Selector" title="Escolha o tema visual">
                <button type="button" class="theme-btn" data-theme-val="dark" onclick="setAppTheme('dark')" aria-label="Dark Mode">🌙 Dark</button>
                <button type="button" class="theme-btn" data-theme-val="light" onclick="setAppTheme('light')" aria-label="Light Mode">☀️ Light</button>
                <button type="button" class="theme-btn" data-theme-val="hightext" onclick="setAppTheme('hightext')" aria-label="High Contrast">⚡ HighText</button>
            </div>
"""

THEME_SCRIPT_JS = """
        if (window.self !== window.top) {
            document.documentElement.classList.add('in-iframe');
            if (document.body) document.body.classList.add('in-iframe');
        }

        function setAppTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            try {
                localStorage.setItem('ndx_theme', theme);
                localStorage.setItem('nde_theme', theme);
            } catch(e) {}
            updateThemeButtons(theme);
            
            // Broadcast to any child iframes (e.g. Draw.io or Ping Matrix viewer)
            document.querySelectorAll('iframe').forEach(frame => {
                try {
                    frame.contentWindow.postMessage(JSON.stringify({ event: 'theme_change', theme: theme }), '*');
                } catch(err) {}
            });
        }

        function updateThemeButtons(theme) {
            document.querySelectorAll('.theme-btn').forEach(btn => {
                if (btn.getAttribute('data-theme-val') === theme) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }

        // Initialize active state on load
        (function() {
            var saved = 'dark';
            try {
                saved = localStorage.getItem('ndx_theme') || localStorage.getItem('nde_theme') || 'dark';
            } catch(e) {}
            updateThemeButtons(saved);
        })();

        // Listen for storage events across tabs
        window.addEventListener('storage', function(e) {
            if ((e.key === 'ndx_theme' || e.key === 'nde_theme') && e.newValue) {
                document.documentElement.setAttribute('data-theme', e.newValue);
                updateThemeButtons(e.newValue);
            }
        });

        // Listen for postMessage from parent window (for iframes)
        window.addEventListener('message', function(e) {
            try {
                var data = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
                if (data && data.event === 'theme_change' && data.theme) {
                    document.documentElement.setAttribute('data-theme', data.theme);
                    updateThemeButtons(data.theme);
                }
            } catch(err) {}
        });
"""
