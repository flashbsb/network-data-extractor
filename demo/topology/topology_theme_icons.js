/* Topology Vector Icons & Theme System (Phase 2)
 * Pure client-side SVG vector library and multi-theme color palettes.
 * Fully compatible with file:/// and http:// (Zero CORS).
 */
(function() {
    'use strict';

    window.TopologyTheme = window.TopologyTheme || {};

    // 1. TIER SPECIFICATION & METADATA
    const TIER_META = {
        core: {
            label: 'Core Router',
            shortLabel: 'CORE',
            rank: 1,
            description: 'Backbone ultra-high capacity transit & chassis routers'
        },
        core_agg: {
            label: 'Core Aggregation',
            shortLabel: 'C-AGG',
            rank: 2,
            description: 'Regional distribution and aggregation transit nodes'
        },
        edge: {
            label: 'Edge / PE Router',
            shortLabel: 'EDGE',
            rank: 3,
            description: 'Provider edge routers terminating customer and metro links'
        },
        metro: {
            label: 'Metro Switch',
            shortLabel: 'METRO',
            rank: 4,
            description: 'Access switches and metro ethernet aggregation fabrics'
        },
        peering: {
            label: 'Peering / IX Edge',
            shortLabel: 'PEER',
            rank: 5,
            description: 'Internet exchange points, transit gateways, and BGP peering'
        },
        router_reflector: {
            label: 'Route Reflector',
            shortLabel: 'BGP-RR',
            rank: 6,
            description: 'BGP control-plane route reflector cluster nodes'
        },
        other: {
            label: 'Generic Element',
            shortLabel: 'OTHER',
            rank: 7,
            description: 'Unclassified endpoints, servers, or legacy elements'
        }
    };

    // 2. THEME COLOR PALETTES (PURPLE BAN STRICTLY ENFORCED: No Violet, No Purple, No Magenta)
    const THEMES = {
        dark: {
            name: 'dark',
            bg: '#020617',
            canvasBg: '#090d16',
            gridLine: 'rgba(255, 255, 255, 0.04)',
            text: '#f8fafc',
            textDim: '#94a3b8',
            border: '#1e293b',
            hudBg: 'rgba(15, 23, 42, 0.85)',
            panelBg: '#0f172a',
            tiers: {
                core: {
                    primary: '#38bdf8',      // Electric Sky Blue
                    fill: 'rgba(56, 189, 248, 0.16)',
                    border: '#0284c7',
                    text: '#e0f2fe',
                    glow: 'rgba(56, 189, 248, 0.4)'
                },
                core_agg: {
                    primary: '#34d399',      // Bright Emerald
                    fill: 'rgba(52, 211, 153, 0.16)',
                    border: '#059669',
                    text: '#d1fae5',
                    glow: 'rgba(52, 211, 153, 0.4)'
                },
                edge: {
                    primary: '#fbbf24',      // Warm Amber
                    fill: 'rgba(251, 191, 36, 0.16)',
                    border: '#d97706',
                    text: '#fef3c7',
                    glow: 'rgba(251, 191, 36, 0.4)'
                },
                metro: {
                    primary: '#94a3b8',      // Slate / Steel
                    fill: 'rgba(148, 163, 184, 0.16)',
                    border: '#475569',
                    text: '#f1f5f9',
                    glow: 'rgba(148, 163, 184, 0.3)'
                },
                peering: {
                    primary: '#f43f5e',      // Crimson / Rose
                    fill: 'rgba(244, 63, 94, 0.16)',
                    border: '#e11d48',
                    text: '#ffe4e6',
                    glow: 'rgba(244, 63, 94, 0.4)'
                },
                router_reflector: {
                    primary: '#60a5fa',      // Deep Azure / Cobalt
                    fill: 'rgba(96, 165, 250, 0.16)',
                    border: '#2563eb',
                    text: '#eff6ff',
                    glow: 'rgba(96, 165, 250, 0.4)'
                },
                other: {
                    primary: '#a1a1aa',      // Neutral Zinc
                    fill: 'rgba(161, 161, 170, 0.14)',
                    border: '#52525b',
                    text: '#f4f4f5',
                    glow: 'rgba(161, 161, 170, 0.3)'
                }
            },
            links: {
                '100G': '#38bdf8',
                '40G': '#0284c7',
                '10G': '#34d399',
                '1G': '#64748b',
                'down': '#ef4444',
                'default': '#94a3b8'
            }
        },

        light: {
            name: 'light',
            bg: '#f8fafc',
            canvasBg: '#f1f5f9',
            gridLine: 'rgba(0, 0, 0, 0.05)',
            text: '#0f172a',
            textDim: '#475569',
            border: '#cbd5e1',
            hudBg: 'rgba(255, 255, 255, 0.92)',
            panelBg: '#ffffff',
            tiers: {
                core: {
                    primary: '#0284c7',      // Deep Sky
                    fill: '#e0f2fe',
                    border: '#0369a1',
                    text: '#0369a1',
                    glow: 'rgba(2, 132, 199, 0.2)'
                },
                core_agg: {
                    primary: '#059669',      // Forest Emerald
                    fill: '#d1fae5',
                    border: '#047857',
                    text: '#065f46',
                    glow: 'rgba(5, 150, 105, 0.2)'
                },
                edge: {
                    primary: '#d97706',      // Dark Amber
                    fill: '#fef3c7',
                    border: '#b45309',
                    text: '#92400e',
                    glow: 'rgba(217, 119, 6, 0.2)'
                },
                metro: {
                    primary: '#475569',      // Dark Slate
                    fill: '#f1f5f9',
                    border: '#334155',
                    text: '#1e293b',
                    glow: 'rgba(71, 85, 105, 0.2)'
                },
                peering: {
                    primary: '#e11d48',      // Ruby Crimson
                    fill: '#ffe4e6',
                    border: '#be123c',
                    text: '#9f1239',
                    glow: 'rgba(225, 29, 72, 0.2)'
                },
                router_reflector: {
                    primary: '#2563eb',      // Royal Azure
                    fill: '#eff6ff',
                    border: '#1d4ed8',
                    text: '#1e40af',
                    glow: 'rgba(37, 99, 235, 0.2)'
                },
                other: {
                    primary: '#52525b',      // Neutral Zinc
                    fill: '#f4f4f5',
                    border: '#3f3f46',
                    text: '#27272a',
                    glow: 'rgba(82, 82, 91, 0.2)'
                }
            },
            links: {
                '100G': '#0284c7',
                '40G': '#0369a1',
                '10G': '#059669',
                '1G': '#475569',
                'down': '#dc2626',
                'default': '#64748b'
            }
        },

        hightext: {
            name: 'hightext',
            bg: '#000000',
            canvasBg: '#000000',
            gridLine: 'rgba(255, 255, 255, 0.1)',
            text: '#ffffff',
            textDim: '#fef08a',
            border: '#ffffff',
            hudBg: '#000000',
            panelBg: '#000000',
            tiers: {
                core: {
                    primary: '#00e5ff',      // Cyan High Contrast
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(0, 229, 255, 0.6)'
                },
                core_agg: {
                    primary: '#00ff66',      // Neon Emerald
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(0, 255, 102, 0.6)'
                },
                edge: {
                    primary: '#ffd600',      // Vivid Yellow
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(255, 214, 0, 0.6)'
                },
                metro: {
                    primary: '#ffffff',      // Pure White
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(255, 255, 255, 0.6)'
                },
                peering: {
                    primary: '#ff1744',      // Vivid Crimson
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(255, 23, 68, 0.6)'
                },
                router_reflector: {
                    primary: '#2979ff',      // Electric Azure
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(41, 121, 255, 0.6)'
                },
                other: {
                    primary: '#e0e0e0',      // Silver White
                    fill: '#000000',
                    border: '#ffffff',
                    text: '#ffffff',
                    glow: 'rgba(224, 224, 224, 0.6)'
                }
            },
            links: {
                '100G': '#00e5ff',
                '40G': '#2979ff',
                '10G': '#00ff66',
                '1G': '#ffffff',
                'down': '#ff1744',
                'default': '#ffffff'
            }
        }
    };

    // 3. PURE SVG VECTOR ICONS (ViewBox 0 0 48 48)
    // Clean, scalable, lightweight path drawings without external dependencies
    const SVG_TEMPLATES = {
        // Core: Modular dual-ring chassis router with cross-connect arrows
        core: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <circle cx="24" cy="24" r="21" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <polygon points="24,7 39,15.5 39,32.5 24,41 9,32.5 9,15.5" fill="none" stroke="${color}" stroke-width="2"/>
                <circle cx="24" cy="24" r="6" fill="${color}"/>
                <path d="M24 10 L24 16 M24 32 L24 38 M10 24 L16 24 M32 24 L38 24" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
                <path d="M14 14 L18 18 M30 30 L34 34 M34 14 L30 18 M14 34 L18 30" stroke="${border}" stroke-width="1.5" stroke-linecap="round"/>
            </svg>`;
        },

        // Core Aggregation: Multi-layer aggregation router with inward/outward distribution conduits
        core_agg: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <rect x="5" y="7" width="38" height="34" rx="8" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <path d="M12 18 L24 24 L36 18 M12 30 L24 24 L36 30" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>
                <circle cx="24" cy="24" r="4.5" fill="${color}"/>
                <circle cx="12" cy="18" r="2.5" fill="${border}"/>
                <circle cx="36" cy="18" r="2.5" fill="${border}"/>
                <circle cx="12" cy="30" r="2.5" fill="${border}"/>
                <circle cx="36" cy="30" r="2.5" fill="${border}"/>
            </svg>`;
        },

        // Edge / PE: Border router with circular boundary shield and external egress gateway arrow
        edge: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <circle cx="24" cy="24" r="20" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <path d="M14 24 C14 18 20 14 26 14 C31 14 34 18 34 24 C34 30 28 34 22 34" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
                <polygon points="34,18 41,24 34,30" fill="${color}"/>
                <circle cx="24" cy="24" r="3.5" fill="${border}"/>
                <line x1="8" y1="24" x2="16" y2="24" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
            </svg>`;
        },

        // Metro: Access switch with port matrix indicator LEDs and dual duplex arrows
        metro: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <rect x="6" y="11" width="36" height="26" rx="5" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <line x1="6" y1="24" x2="42" y2="24" stroke="${border}" stroke-width="1.2" stroke-dasharray="2 2"/>
                <!-- Port matrix dots -->
                <rect x="11" y="15" width="4" height="4" rx="1" fill="${color}"/>
                <rect x="19" y="15" width="4" height="4" rx="1" fill="${color}"/>
                <rect x="27" y="15" width="4" height="4" rx="1" fill="${color}"/>
                <rect x="35" y="15" width="4" height="4" rx="1" fill="${color}"/>
                <rect x="11" y="29" width="4" height="4" rx="1" fill="${border}"/>
                <rect x="19" y="29" width="4" height="4" rx="1" fill="${color}"/>
                <rect x="27" y="29" width="4" height="4" rx="1" fill="${color}"/>
                <rect x="35" y="29" width="4" height="4" rx="1" fill="${border}"/>
            </svg>`;
        },

        // Peering / IX Edge: Interconnecting autonomous systems global mesh
        peering: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <circle cx="24" cy="24" r="20" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <circle cx="16" cy="18" r="4" fill="${color}"/>
                <circle cx="32" cy="18" r="4" fill="${color}"/>
                <circle cx="24" cy="32" r="5" fill="${color}"/>
                <line x1="16" y1="18" x2="32" y2="18" stroke="${border}" stroke-width="2"/>
                <line x1="16" y1="18" x2="24" y2="32" stroke="${border}" stroke-width="2"/>
                <line x1="32" y1="18" x2="24" y2="32" stroke="${border}" stroke-width="2"/>
                <circle cx="24" cy="24" r="2" fill="${border}"/>
            </svg>`;
        },

        // Route Reflector: Central transmission beacon tower radiating BGP control-plane updates
        router_reflector: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <circle cx="24" cy="24" r="20" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <!-- Central Antenna Mast -->
                <polygon points="24,10 20,38 28,38" fill="${border}"/>
                <line x1="16" y1="38" x2="32" y2="38" stroke="${border}" stroke-width="2" stroke-linecap="round"/>
                <!-- Top Beacon -->
                <circle cx="24" cy="10" r="3.5" fill="${color}"/>
                <!-- Radar Broadcast Waves -->
                <path d="M16 15 A12 12 0 0 0 12 25" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
                <path d="M32 15 A12 12 0 0 1 36 25" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
                <path d="M12 9 A19 19 0 0 0 7 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round"/>
                <path d="M36 9 A19 19 0 0 1 41 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round"/>
            </svg>`;
        },

        // Generic Element / Server / Host
        other: function(color, border, fill) {
            return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
                <rect x="7" y="9" width="34" height="30" rx="4" fill="${fill}" stroke="${border}" stroke-width="2"/>
                <line x1="7" y1="19" x2="41" y2="19" stroke="${border}" stroke-width="1.5"/>
                <line x1="7" y1="29" x2="41" y2="29" stroke="${border}" stroke-width="1.5"/>
                <circle cx="12" cy="14" r="1.8" fill="${color}"/>
                <circle cx="17" cy="14" r="1.8" fill="${color}"/>
                <circle cx="12" cy="24" r="1.8" fill="${color}"/>
                <circle cx="17" cy="24" r="1.8" fill="${border}"/>
                <circle cx="12" cy="34" r="1.8" fill="${color}"/>
                <circle cx="17" cy="34" r="1.8" fill="${color}"/>
                <line x1="26" y1="14" x2="36" y2="14" stroke="${border}" stroke-width="2" stroke-linecap="round"/>
                <line x1="26" y1="24" x2="36" y2="24" stroke="${border}" stroke-width="2" stroke-linecap="round"/>
                <line x1="26" y1="34" x2="36" y2="34" stroke="${border}" stroke-width="2" stroke-linecap="round"/>
            </svg>`;
        }
    };

    // 4. PUBLIC HELPER METHODS
    TopologyTheme.getMeta = function(tier) {
        return TIER_META[tier] || TIER_META.other;
    };

    TopologyTheme.getAllTiers = function() {
        return Object.keys(TIER_META);
    };

    TopologyTheme.getCurrentThemeName = function() {
        return document.documentElement.getAttribute('data-theme') || 'dark';
    };

    TopologyTheme.getTheme = function(themeName) {
        const name = themeName || TopologyTheme.getCurrentThemeName();
        return THEMES[name] || THEMES.dark;
    };

    TopologyTheme.getTierStyle = function(tier, themeName) {
        const theme = TopologyTheme.getTheme(themeName);
        const t = theme.tiers[tier] || theme.tiers.other;
        return t;
    };

    TopologyTheme.getSvg = function(tier, themeName) {
        const theme = TopologyTheme.getTheme(themeName);
        const tierStyle = theme.tiers[tier] || theme.tiers.other;
        const generator = SVG_TEMPLATES[tier] || SVG_TEMPLATES.other;
        return generator(tierStyle.primary, tierStyle.border, tierStyle.fill);
    };

    TopologyTheme.getSvgDataUri = function(tier, themeName) {
        const rawSvg = TopologyTheme.getSvg(tier, themeName);
        return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(rawSvg);
    };

    TopologyTheme.getLinkColor = function(speedOrStatus, themeName) {
        const theme = TopologyTheme.getTheme(themeName);
        return theme.links[speedOrStatus] || theme.links.default;
    };

    // 5. HIGH-PERFORMANCE 2D CANVAS DRAWING (Optimized for 6,500 elements)
    TopologyTheme.drawCanvasNode = function(ctx, x, y, radius, tier, themeName, isSelected, isHovered) {
        const theme = TopologyTheme.getTheme(themeName);
        const style = theme.tiers[tier] || theme.tiers.other;

        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fillStyle = style.fill;
        ctx.fill();

        ctx.lineWidth = isSelected ? 3.5 : (isHovered ? 2.5 : 1.5);
        ctx.strokeStyle = isSelected ? '#ffffff' : (isHovered ? style.primary : style.border);
        ctx.stroke();

        // Inner shape hint
        ctx.beginPath();
        if (tier === 'core') {
            ctx.arc(x, y, radius * 0.45, 0, Math.PI * 2);
            ctx.fillStyle = style.primary;
            ctx.fill();
        } else if (tier === 'core_agg') {
            ctx.rect(x - radius * 0.4, y - radius * 0.4, radius * 0.8, radius * 0.8);
            ctx.fillStyle = style.primary;
            ctx.fill();
        } else if (tier === 'edge') {
            ctx.arc(x, y, radius * 0.35, 0, Math.PI * 2);
            ctx.fillStyle = style.primary;
            ctx.fill();
        } else if (tier === 'metro') {
            ctx.rect(x - radius * 0.45, y - radius * 0.25, radius * 0.9, radius * 0.5);
            ctx.fillStyle = style.primary;
            ctx.fill();
        } else if (tier === 'peering') {
            ctx.arc(x, y, radius * 0.4, 0, Math.PI * 2);
            ctx.fillStyle = style.primary;
            ctx.fill();
        } else if (tier === 'router_reflector') {
            ctx.moveTo(x, y - radius * 0.5);
            ctx.lineTo(x + radius * 0.4, y + radius * 0.4);
            ctx.lineTo(x - radius * 0.4, y + radius * 0.4);
            ctx.closePath();
            ctx.fillStyle = style.primary;
            ctx.fill();
        } else {
            ctx.arc(x, y, radius * 0.3, 0, Math.PI * 2);
            ctx.fillStyle = style.primary;
            ctx.fill();
        }

        ctx.restore();
    };

    // Export raw templates for direct inspection
    TopologyTheme.SVG_TEMPLATES = SVG_TEMPLATES;
    TopologyTheme.TIER_META = TIER_META;
    TopologyTheme.THEMES = THEMES;

})();
