# -*- coding: utf-8 -*-
"""
Topology Native Interactive Graph Engine (Phases 3 & 4)
======================================================
Generates client-side pure HTML5 Canvas interactive graph visualizer (topology_graph.js).
Features:
  - Concentric Orbital, Organic (Force-Directed), and Site-Grouped layouts
  - Viewport culling & Level of Detail (LOD) for scaling to 6,500 elements
  - Phase 4 Topological Drift Analyzer (snapshot diffing, node/edge addition & removal highlights)
  - Smooth pan, zoom, drag & drop, hover highlights, and selection
  - Tier filtering, search-and-focus, physics freeze/resume
  - 100% offline, zero CORS (compatible with file:/// and http://)
  - Zero external libraries or CDNs required
"""

import os


def get_topology_graph_js() -> str:
    """Returns standalone JavaScript module for high-performance canvas topology."""
    return """/* Native Interactive Topology Graph Engine (Phases 3 & 4)
 * High-performance 2D Canvas graph renderer with Concentric Orbital,
 * Force-Directed, Clustered layouts, and Topological Drift Comparator.
 * Zero CORS / Pure Offline / Scalable up to 6,500 elements.
 */
(function() {
    'use strict';

    /**
     * High-performance Binary Min-Heap Priority Queue for Dijkstra.
     * Enqueue and Dequeue operations operate in O(log N).
     */
    class MinHeapPriorityQueue {
        constructor() {
            this.heap = [];
        }
        enqueue(element, priority) {
            this.heap.push({ element, priority });
            this.bubbleUp(this.heap.length - 1);
        }
        dequeue() {
            if (this.heap.length === 0) return null;
            const min = this.heap[0];
            const end = this.heap.pop();
            if (this.heap.length > 0) {
                this.heap[0] = end;
                this.sinkDown(0);
            }
            return min;
        }
        isEmpty() {
            return this.heap.length === 0;
        }
        bubbleUp(n) {
            const item = this.heap[n];
            while (n > 0) {
                const pIdx = (n - 1) >> 1;
                const parent = this.heap[pIdx];
                if (item.priority >= parent.priority) break;
                this.heap[n] = parent;
                n = pIdx;
            }
            this.heap[n] = item;
        }
        sinkDown(n) {
            const length = this.heap.length;
            const item = this.heap[n];
            while (true) {
                const leftChildIdx = (n << 1) + 1;
                const rightChildIdx = leftChildIdx + 1;
                let swapIdx = null;

                if (leftChildIdx < length) {
                    if (this.heap[leftChildIdx].priority < item.priority) {
                        swapIdx = leftChildIdx;
                    }
                }
                if (rightChildIdx < length) {
                    const rightPriority = this.heap[rightChildIdx].priority;
                    const compPriority = (swapIdx === null) ? item.priority : this.heap[leftChildIdx].priority;
                    if (rightPriority < compPriority) {
                        swapIdx = rightChildIdx;
                    }
                }
                if (swapIdx === null) break;
                this.heap[n] = this.heap[swapIdx];
                n = swapIdx;
            }
            this.heap[n] = item;
        }
    }

    class NetworkTopologyGraph {
        constructor(canvasContainerId, options = {}) {
            this.container = document.getElementById(canvasContainerId);
            if (!this.container) {
                console.error("Canvas container not found:", canvasContainerId);
                return;
            }

            this.canvas = document.createElement('canvas');
            this.canvas.className = 'topology-canvas';
            this.canvas.style.width = '100%';
            this.canvas.style.height = '100%';
            this.canvas.style.display = 'block';
            this.canvas.style.cursor = 'grab';
            this.container.appendChild(this.canvas);

            this.ctx = this.canvas.getContext('2d', { alpha: false });
            this.dpr = window.devicePixelRatio || 1;

            // Graph State
            this.nodes = [];
            this.edges = [];
            this.nodeMap = new Map();
            this.activeType = 'summary'; // 'summary' or 'detailed'
            this.activeLayout = 'concentric'; // 'concentric', 'organic', 'site'
            this.activeTiers = new Set(['core', 'core_agg', 'edge', 'metro', 'peering', 'router_reflector', 'other']);
            this.searchQuery = '';
            
            // Phase 4 Drift State
            this.isDriftMode = false;
            this.driftStats = null;
            this.driftDatasetA = null;
            this.driftDatasetB = null;

            // Camera / Viewport Transform
            this.camera = { x: 0, y: 0, zoom: 0.85 };
            this.targetCamera = { x: 0, y: 0, zoom: 0.85 };
            
            // Physics Engine
            this.physicsEnabled = true;
            this.physicsFrozen = false;
            this.energy = 1.0;
            this.damping = 0.82;
            this.repulsion = 450;
            this.springLength = 110;
            this.springK = 0.05;
            this.simulationSteps = 0;
            this.maxSimulationSteps = 120; // Auto-freeze threshold for performance

            // Interaction State
            this.draggedNode = null;
            this.isPanning = false;
            this.panStart = { x: 0, y: 0 };
            this.hoveredNode = null;
            this.hoveredEdge = null;
            this.selectedNode = null;
            this.connectedNodeIds = new Set();
            this.connectedEdgeIds = new Set();
            this.telemetryMode = 'speed'; // 'speed', 'latency', 'loss'

            // Phase 3 & 4: Path Tracing State
            this.pingLookup = {};
            this.activePaths = [];
            this.activePathIdx = 0;
            this.activePath = null;
            this.activePathNodeIds = new Set();
            this.activePathEdgeIds = new Set();
            this.activePathPairKeys = new Set();
            this.pathTraceStartNode = null;
            this.pathTraceEndNode = null;
            this.onPathChanged = null;
            this.onPathCleared = null;

            // Resize Observer
            this.resize();
            window.addEventListener('resize', () => this.resize());

            // Bind Event Handlers
            this.setupEvents();
            
            // Animation Loop
            this.animating = true;
            this.renderLoop = this.renderLoop.bind(this);
            requestAnimationFrame(this.renderLoop);
        }

        resize() {
            const rect = this.container.getBoundingClientRect();
            this.width = Math.max(rect.width, 300);
            this.height = Math.max(rect.height, 300);
            
            this.canvas.width = Math.floor(this.width * this.dpr);
            this.canvas.height = Math.floor(this.height * this.dpr);
            this.ctx.setTransform(1, 0, 0, 1, 0, 0);
            this.ctx.scale(this.dpr, this.dpr);
        }

        setData(dataset, type = 'summary') {
            if (!dataset) return;
            this.isDriftMode = false;
            this.driftStats = null;
            this.rawDataset = dataset;
            this.activeType = typeof type === 'string' ? type : 'summary';

            const allNodes = Array.isArray(dataset) ? dataset : (dataset.nodes || []);
            const summaryEdges = Array.isArray(type) ? type : (dataset.summary_edges || dataset.edges_summary || []);
            const detailedEdges = dataset.detailed_edges || dataset.edges_detail || [];

            this.nodeMap.clear();
            this.nodes = allNodes.map((n, idx) => {
                const nodeObj = {
                    ...n,
                    idx: idx,
                    x: (Math.random() - 0.5) * 600,
                    y: (Math.random() - 0.5) * 600,
                    vx: 0,
                    vy: 0,
                    radius: this.getNodeRadius(n.tier),
                    degree: 0,
                    visible: true,
                    pinned: false,
                    drift: 'none'
                };
                this.nodeMap.set(n.id, nodeObj);
                return nodeObj;
            });

            const sourceEdges = (type === 'detailed' && detailedEdges.length > 0) ? detailedEdges : summaryEdges;
            this.edges = [];

            sourceEdges.forEach((e, idx) => {
                const sId = e.source || e.from;
                const tId = e.target || e.to;
                const src = this.nodeMap.get(sId);
                const tgt = this.nodeMap.get(tId);
                if (src && tgt) {
                    src.degree = (src.degree || 0) + 1;
                    tgt.degree = (tgt.degree || 0) + 1;
                    this.edges.push({
                        ...e,
                        id: e.id || ('edge_' + idx),
                        source: src.id,
                        target: tgt.id,
                        from: src.id,
                        to: tgt.id,
                        sourceNode: src,
                        targetNode: tgt,
                        local_int: e.local_int || e.from_intf || '',
                        remote_int: e.remote_int || e.to_intf || '',
                        visible: true,
                        drift: 'none'
                    });
                }
            });

            // Auto-scale radius slightly by degree for visual hierarchy
            this.nodes.forEach(n => {
                n.radius = Math.max(n.radius, Math.min(n.radius + Math.sqrt(n.degree || 0) * 1.5, 30));
            });

            this.selectedNode = null;
            this.hoveredNode = null;
            this.connectedNodeIds.clear();
            this.connectedEdgeIds.clear();
            this.pingLookup = dataset.ping_lookup || {};
            this.clearActivePath();

            this.applyLayout(this.activeLayout, true);
        }

        /* Phase 4: Topological Drift Calculation */
        setDriftData(datasetA, datasetB, type = 'summary') {
            if (!datasetA || !datasetB) return null;
            this.isDriftMode = true;
            this.driftDatasetA = datasetA;
            this.driftDatasetB = datasetB;
            this.activeType = type;
            this.pingLookup = (datasetB && datasetB.ping_lookup) || (datasetA && datasetA.ping_lookup) || {};
            this.clearActivePath();

            const nodesAMap = new Map((datasetA.nodes || []).map(n => [n.id, n]));
            const nodesBMap = new Map((datasetB.nodes || []).map(n => [n.id, n]));

            const edgesA = (type === 'detailed' && datasetA.detailed_edges && datasetA.detailed_edges.length > 0) ? datasetA.detailed_edges : (datasetA.summary_edges || []);
            const edgesB = (type === 'detailed' && datasetB.detailed_edges && datasetB.detailed_edges.length > 0) ? datasetB.detailed_edges : (datasetB.summary_edges || []);

            // Identify node drifts
            const allNodeIds = new Set([...nodesAMap.keys(), ...nodesBMap.keys()]);
            this.nodeMap.clear();
            let nodesAdded = 0, nodesRemoved = 0, nodesUnchanged = 0;

            this.nodes = Array.from(allNodeIds).map((id, idx) => {
                const inA = nodesAMap.has(id);
                const inB = nodesBMap.has(id);
                const rawNode = inB ? nodesBMap.get(id) : nodesAMap.get(id);

                let drift = 'unchanged';
                if (!inA && inB) { drift = 'added'; nodesAdded++; }
                else if (inA && !inB) { drift = 'removed'; nodesRemoved++; }
                else { nodesUnchanged++; }

                const nodeObj = {
                    ...rawNode,
                    idx: idx,
                    x: (Math.random() - 0.5) * 600,
                    y: (Math.random() - 0.5) * 600,
                    vx: 0,
                    vy: 0,
                    radius: this.getNodeRadius(rawNode.tier),
                    degree: 0,
                    visible: true,
                    pinned: false,
                    drift: drift
                };
                this.nodeMap.set(id, nodeObj);
                return nodeObj;
            });

            // Edge key helper
            const edgeKey = (e) => {
                const s = e.source || e.from || '';
                const t = e.target || e.to || '';
                const lInt = e.local_int || e.from_intf || '';
                const rInt = e.remote_int || e.to_intf || '';
                if (type === 'detailed') {
                    return `${s}:${lInt} <-> ${t}:${rInt}`;
                }
                return s < t ? `${s}:::${t}` : `${t}:::${s}`;
            };

            const edgesAMap = new Map();
            edgesA.forEach(e => edgesAMap.set(edgeKey(e), e));

            const edgesBMap = new Map();
            edgesB.forEach(e => edgesBMap.set(edgeKey(e), e));

            const allEdgeKeys = new Set([...edgesAMap.keys(), ...edgesBMap.keys()]);
            this.edges = [];
            let edgesAdded = 0, edgesRemoved = 0, edgesUnchanged = 0;

            let edgeIdx = 0;
            allEdgeKeys.forEach(k => {
                const inA = edgesAMap.has(k);
                const inB = edgesBMap.has(k);
                const rawEdge = inB ? edgesBMap.get(k) : edgesAMap.get(k);

                let drift = 'unchanged';
                if (!inA && inB) { drift = 'added'; edgesAdded++; }
                else if (inA && !inB) { drift = 'removed'; edgesRemoved++; }
                else { edgesUnchanged++; }

                const sId = rawEdge.source || rawEdge.from;
                const tId = rawEdge.target || rawEdge.to;
                const src = this.nodeMap.get(sId);
                const tgt = this.nodeMap.get(tId);

                if (src && tgt) {
                    src.degree = (src.degree || 0) + 1;
                    tgt.degree = (tgt.degree || 0) + 1;
                    this.edges.push({
                        ...rawEdge,
                        id: rawEdge.id || ('drift_edge_' + (edgeIdx++)),
                        source: src.id,
                        target: tgt.id,
                        from: src.id,
                        to: tgt.id,
                        sourceNode: src,
                        targetNode: tgt,
                        local_int: rawEdge.local_int || rawEdge.from_intf || '',
                        remote_int: rawEdge.remote_int || rawEdge.to_intf || '',
                        visible: true,
                        drift: drift
                    });
                }
            });

            this.driftStats = {
                nodes_added: nodesAdded,
                nodes_removed: nodesRemoved,
                nodes_unchanged: nodesUnchanged,
                edges_added: edgesAdded,
                edges_removed: edgesRemoved,
                edges_unchanged: edgesUnchanged
            };

            this.selectedNode = null;
            this.hoveredNode = null;
            this.connectedNodeIds.clear();
            this.connectedEdgeIds.clear();

            this.applyLayout(this.activeLayout, true);
            return this.driftStats;
        }

        getNodeRadius(tier) {
            switch(tier) {
                case 'core': return 22;
                case 'core_agg': return 19;
                case 'edge': return 16;
                case 'peering': return 17;
                case 'router_reflector': return 18;
                case 'metro': return 13;
                default: return 12;
            }
        }

        applyLayout(layoutName = 'concentric', resetCamera = false) {
            this.activeLayout = layoutName;
            this.simulationSteps = 0;
            this.physicsFrozen = false;

            const visibleNodes = this.nodes.filter(n => this.activeTiers.has(n.tier));

            if (layoutName === 'concentric') {
                this.applyConcentricLayout(visibleNodes);
            } else if (layoutName === 'site') {
                this.applySiteLayout(visibleNodes);
            } else {
                this.applyOrganicLayout(visibleNodes);
            }

            if (resetCamera) {
                this.fitToScreen();
            }
        }

        applyConcentricLayout(nodes) {
            const tiersOrder = ['core', 'router_reflector', 'core_agg', 'edge', 'peering', 'metro', 'other'];
            const groups = {};
            tiersOrder.forEach(t => groups[t] = []);

            nodes.forEach(n => {
                if (groups[n.tier]) groups[n.tier].push(n);
                else (groups['other'] = groups['other'] || []).push(n);
            });

            const ringRadii = {
                core: 90,
                router_reflector: 170,
                core_agg: 260,
                edge: 390,
                peering: 520,
                metro: 680,
                other: 840
            };

            tiersOrder.forEach(tier => {
                const tierNodes = groups[tier] || [];
                const count = tierNodes.length;
                if (count === 0) return;

                let r = ringRadii[tier] || 700;
                if (count > 25) {
                    r = Math.max(r, count * 14 / Math.PI);
                }

                if (tier === 'core' && count === 1) {
                    tierNodes[0].x = 0;
                    tierNodes[0].y = 0;
                    tierNodes[0].vx = 0;
                    tierNodes[0].vy = 0;
                    return;
                }

                tierNodes.forEach((node, i) => {
                    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
                    node.x = Math.cos(angle) * r;
                    node.y = Math.sin(angle) * r;
                    node.vx = 0;
                    node.vy = 0;
                });
            });

            this.physicsFrozen = true;
            this.energy = 0;
        }

        applyOrganicLayout(nodes) {
            const count = nodes.length;
            const spread = Math.max(300, Math.sqrt(count) * 60);

            nodes.forEach(n => {
                n.x = (Math.random() - 0.5) * spread;
                n.y = (Math.random() - 0.5) * spread;
                n.vx = 0;
                n.vy = 0;
            });

            this.physicsFrozen = false;
            this.simulationSteps = 0;
            this.energy = 1.0;
        }

        applySiteLayout(nodes) {
            const siteMap = new Map();
            nodes.forEach(n => {
                const s = n.site || 'OTHER';
                if (!siteMap.has(s)) siteMap.set(s, []);
                siteMap.get(s).push(n);
            });

            const siteCount = siteMap.size;
            const siteRadius = Math.max(400, Math.sqrt(siteCount) * 160);
            let siteIdx = 0;

            siteMap.forEach((siteNodes, site) => {
                const sAngle = (2 * Math.PI * siteIdx) / siteCount;
                const sx = Math.cos(sAngle) * siteRadius;
                const sy = Math.sin(sAngle) * siteRadius;

                const internalCount = siteNodes.length;
                const internalR = Math.min(80, Math.sqrt(internalCount) * 22);

                siteNodes.forEach((node, i) => {
                    if (internalCount === 1) {
                        node.x = sx;
                        node.y = sy;
                    } else {
                        const inAngle = (2 * Math.PI * i) / internalCount;
                        node.x = sx + Math.cos(inAngle) * internalR;
                        node.y = sy + Math.sin(inAngle) * internalR;
                    }
                    node.vx = 0;
                    node.vy = 0;
                });
                siteIdx++;
            });

            this.physicsFrozen = true;
            this.energy = 0;
        }

        stepPhysics() {
            if (this.physicsFrozen || !this.physicsEnabled) return;

            const visibleNodes = this.nodes.filter(n => this.activeTiers.has(n.tier) && !n.pinned);
            const count = visibleNodes.length;
            if (count === 0) return;

            this.simulationSteps++;
            if (this.simulationSteps > this.maxSimulationSteps || (count > 350 && this.simulationSteps > 60)) {
                this.physicsFrozen = true;
                this.energy = 0;
                this.notifyPhysicsState();
                return;
            }

            const kRep = this.repulsion * 100;
            for (let i = 0; i < count; i++) {
                const n1 = visibleNodes[i];
                for (let j = i + 1; j < count; j++) {
                    const n2 = visibleNodes[j];
                    const dx = n2.x - n1.x;
                    const dy = n2.y - n1.y;
                    const distSq = dx * dx + dy * dy + 100;
                    const dist = Math.sqrt(distSq);

                    if (dist < 400) {
                        const force = kRep / distSq;
                        const fx = (dx / dist) * force;
                        const fy = (dy / dist) * force;

                        n1.vx -= fx;
                        n1.vy -= fy;
                        n2.vx += fx;
                        n2.vy += fy;
                    }
                }
            }

            const visibleEdges = this.edges.filter(e => 
                this.activeTiers.has(e.sourceNode.tier) && 
                this.activeTiers.has(e.targetNode.tier)
            );

            for (let i = 0; i < visibleEdges.length; i++) {
                const e = visibleEdges[i];
                const n1 = e.sourceNode;
                const n2 = e.targetNode;
                const dx = n2.x - n1.x;
                const dy = n2.y - n1.y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;

                const force = (dist - this.springLength) * this.springK;
                const fx = (dx / dist) * force;
                const fy = (dy / dist) * force;

                if (!n1.pinned) { n1.vx += fx; n1.vy += fy; }
                if (!n2.pinned) { n2.vx += fx; n2.vy += fy; }
            }

            let totalEnergy = 0;
            for (let i = 0; i < count; i++) {
                const n = visibleNodes[i];
                if (n === this.draggedNode) continue;

                n.vx -= n.x * 0.003;
                n.vy -= n.y * 0.003;

                n.vx *= this.damping;
                n.vy *= this.damping;

                n.x += n.vx;
                n.y += n.vy;

                totalEnergy += Math.abs(n.vx) + Math.abs(n.vy);
            }

            this.energy = totalEnergy / count;
            if (this.energy < 0.05) {
                this.physicsFrozen = true;
                this.notifyPhysicsState();
            }
        }

        togglePhysics() {
            this.physicsFrozen = !this.physicsFrozen;
            if (!this.physicsFrozen) {
                this.simulationSteps = 0;
                this.energy = 1.0;
            }
            this.notifyPhysicsState();
        }

        notifyPhysicsState() {
            const btn = document.getElementById('freezePhysicsBtn');
            if (btn) {
                if (this.physicsFrozen) {
                    btn.innerHTML = '▶️ Physics: Frozen';
                    btn.classList.add('frozen');
                } else {
                    btn.innerHTML = '⏸️ Physics: Running';
                    btn.classList.remove('frozen');
                }
            }
        }

        fitToScreen() {
            const visibleNodes = this.nodes.filter(n => this.activeTiers.has(n.tier));
            if (visibleNodes.length === 0) return;

            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            visibleNodes.forEach(n => {
                if (n.x < minX) minX = n.x;
                if (n.x > maxX) maxX = n.x;
                if (n.y < minY) minY = n.y;
                if (n.y > maxY) maxY = n.y;
            });

            const pad = 120;
            const w = Math.max(maxX - minX + pad * 2, 200);
            const h = Math.max(maxY - minY + pad * 2, 200);

            const scaleX = this.width / w;
            const scaleY = this.height / h;
            const zoom = Math.min(Math.max(Math.min(scaleX, scaleY), 0.2), 1.6);

            this.targetCamera.x = this.width / 2 - ((minX + maxX) / 2) * zoom;
            this.targetCamera.y = this.height / 2 - ((minY + maxY) / 2) * zoom;
            this.targetCamera.zoom = zoom;

            this.camera.x = this.targetCamera.x;
            this.camera.y = this.targetCamera.y;
            this.camera.zoom = this.targetCamera.zoom;
        }

        focusNode(node) {
            if (!node) return;
            this.selectNode(node);
            this.targetCamera.x = this.width / 2 - node.x * 1.2;
            this.targetCamera.y = this.height / 2 - node.y * 1.2;
            this.targetCamera.zoom = 1.2;
        }

        focusHop(uId, vId) {
            const u = this.nodeMap.get(uId);
            const v = this.nodeMap.get(vId);
            if (!u || !v) return;
            const midX = (u.x + v.x) / 2;
            const midY = (u.y + v.y) / 2;
            this.targetCamera.x = this.width / 2 - midX * 1.25;
            this.targetCamera.y = this.height / 2 - midY * 1.25;
            this.targetCamera.zoom = 1.25;
        }

        selectNode(node) {
            this.selectedNode = node;
            this.connectedNodeIds.clear();
            this.connectedEdgeIds.clear();

            if (node) {
                this.connectedNodeIds.add(node.id);
                this.edges.forEach(e => {
                    const s = e.source || (e.sourceNode ? e.sourceNode.id : e.from);
                    const t = e.target || (e.targetNode ? e.targetNode.id : e.to);
                    if (s === node.id || t === node.id) {
                        this.connectedEdgeIds.add(e.id);
                        this.connectedNodeIds.add(s);
                        this.connectedNodeIds.add(t);
                    }
                });
            }

            if (typeof this.onNodeSelected === 'function') {
                this.onNodeSelected(node);
            }
        }

        setFilterTier(tier, isEnabled) {
            if (isEnabled) this.activeTiers.add(tier);
            else this.activeTiers.delete(tier);

            if (this.activeLayout === 'concentric') {
                this.applyConcentricLayout(this.nodes.filter(n => this.activeTiers.has(n.tier)));
            } else if (this.activeLayout === 'site') {
                this.applySiteLayout(this.nodes.filter(n => this.activeTiers.has(n.tier)));
            } else {
                this.simulationSteps = 0;
                this.physicsFrozen = false;
            }
        }

        evaluateBooleanFilter(node, query) {
            if (!query || !query.trim()) return true;

            const tokenize = (str) => {
                const tokens = [];
                let i = 0;
                while (i < str.length) {
                    const c = str[i];
                    if (/\\s/.test(c)) { i++; continue; }
                    if (c === '(' || c === ')') { tokens.push({ type: c }); i++; continue; }
                    if (c === '&' || c === ';') { tokens.push({ type: 'AND' }); i++; continue; }
                    if (c === '|' || c === ',') { tokens.push({ type: 'OR' }); i++; continue; }
                    if (c === '!' || c === '-') { tokens.push({ type: 'NOT' }); i++; continue; }
                    if (c === '"' || c === "'") {
                        const quote = c;
                        i++;
                        let val = '';
                        while (i < str.length && str[i] !== quote) { val += str[i]; i++; }
                        if (i < str.length) i++;
                        tokens.push({ type: 'TERM', value: val });
                        continue;
                    }
                    let val = '';
                    while (i < str.length && !/[\\s()&;|,!-]/.test(str[i])) { val += str[i]; i++; }
                    if (val) {
                        const up = val.toUpperCase();
                        if (up === 'AND') tokens.push({ type: 'AND' });
                        else if (up === 'OR') tokens.push({ type: 'OR' });
                        else if (up === 'NOT') tokens.push({ type: 'NOT' });
                        else tokens.push({ type: 'TERM', value: val });
                    }
                }
                return tokens;
            };

            const insertImplicitAnd = (tokens) => {
                const res = [];
                for (let i = 0; i < tokens.length; i++) {
                    res.push(tokens[i]);
                    if (i < tokens.length - 1) {
                        const curr = tokens[i];
                        const next = tokens[i+1];
                        const currIsOperand = (curr.type === 'TERM' || curr.type === ')');
                        const nextIsOperand = (next.type === 'TERM' || next.type === '(' || next.type === 'NOT');
                        if (currIsOperand && nextIsOperand) {
                            res.push({ type: 'AND' });
                        }
                    }
                }
                return res;
            };

            const matchTerm = (targetNode, term) => {
                if (!term) return true;
                const colonIdx = term.indexOf(':');
                if (colonIdx > 0) {
                    const field = term.substring(0, colonIdx).toLowerCase();
                    const val = term.substring(colonIdx + 1).toLowerCase();
                    if (field === 'tier') return (targetNode.tier || '').toLowerCase() === val || (targetNode.tier || '').toLowerCase().includes(val);
                    if (field === 'site') return (targetNode.site || '').toLowerCase().includes(val);
                    if (field === 'vendor') return (targetNode.vendor || '').toLowerCase().includes(val);
                    if (field === 'model') return (targetNode.model || '').toLowerCase().includes(val);
                    if (field === 'status') return (targetNode.status || '').toLowerCase().includes(val);
                    if (field === 'id' || field === 'name' || field === 'host') return (targetNode.id || '').toLowerCase().includes(val);
                }
                const lowerTerm = term.toLowerCase();
                const idMatch = (targetNode.id || '').toLowerCase().includes(lowerTerm);
                const siteMatch = (targetNode.site || '').toLowerCase().includes(lowerTerm);
                const modelMatch = (targetNode.model || '').toLowerCase().includes(lowerTerm);
                const vendorMatch = (targetNode.vendor || '').toLowerCase().includes(lowerTerm);
                const tierMatch = (targetNode.tier || '').toLowerCase().includes(lowerTerm);
                return idMatch || siteMatch || modelMatch || vendorMatch || tierMatch;
            };

            const tokens = insertImplicitAnd(tokenize(query));
            if (tokens.length === 0) return true;

            let pos = 0;

            const parseOr = () => {
                let left = parseAnd();
                while (pos < tokens.length && tokens[pos].type === 'OR') {
                    pos++;
                    const right = parseAnd();
                    left = left || right;
                }
                return left;
            };

            const parseAnd = () => {
                let left = parseUnary();
                while (pos < tokens.length && tokens[pos].type === 'AND') {
                    pos++;
                    const right = parseUnary();
                    left = left && right;
                }
                return left;
            };

            const parseUnary = () => {
                if (pos < tokens.length && tokens[pos].type === 'NOT') {
                    pos++;
                    return !parseUnary();
                }
                return parsePrimary();
            };

            const parsePrimary = () => {
                if (pos >= tokens.length) return true;
                const tok = tokens[pos];
                if (tok.type === '(') {
                    pos++;
                    const val = parseOr();
                    if (pos < tokens.length && tokens[pos].type === ')') pos++;
                    return val;
                }
                if (tok.type === 'TERM') {
                    pos++;
                    return matchTerm(node, tok.value);
                }
                pos++;
                return true;
            };

            try {
                return parseOr();
            } catch (e) {
                return (node.id || '').toLowerCase().includes(query.toLowerCase());
            }
        }

        setSearchQuery(q) {
            this.searchQuery = (q || '').trim();
            if (!this.searchQuery) {
                this.searchMatchingNodes = [];
                this.searchMatchIndex = -1;
                if (typeof this.onSearchMatchesChanged === 'function') {
                    this.onSearchMatchesChanged(0, -1);
                }
                return;
            }

            // Collect all matching nodes
            this.searchMatchingNodes = this.nodes.filter(n => {
                return this.activeTiers.has(n.tier) && this.evaluateBooleanFilter(n, this.searchQuery);
            });

            this.searchMatchIndex = this.searchMatchingNodes.length > 0 ? 0 : -1;

            if (this.searchMatchingNodes.length > 0) {
                if (this.searchMatchingNodes.length === 1) {
                    this.focusNode(this.searchMatchingNodes[0]);
                } else {
                    this.fitNodesBoundingBox(this.searchMatchingNodes);
                }
            }

            if (typeof this.onSearchMatchesChanged === 'function') {
                this.onSearchMatchesChanged(this.searchMatchingNodes.length, this.searchMatchIndex);
            }
        }

        nextSearchMatch() {
            if (!this.searchMatchingNodes || this.searchMatchingNodes.length === 0) return;
            this.searchMatchIndex = (this.searchMatchIndex + 1) % this.searchMatchingNodes.length;
            const n = this.searchMatchingNodes[this.searchMatchIndex];
            this.focusNode(n);
            if (typeof this.onSearchMatchesChanged === 'function') {
                this.onSearchMatchesChanged(this.searchMatchingNodes.length, this.searchMatchIndex);
            }
        }

        prevSearchMatch() {
            if (!this.searchMatchingNodes || this.searchMatchingNodes.length === 0) return;
            this.searchMatchIndex = (this.searchMatchIndex - 1 + this.searchMatchingNodes.length) % this.searchMatchingNodes.length;
            const n = this.searchMatchingNodes[this.searchMatchIndex];
            this.focusNode(n);
            if (typeof this.onSearchMatchesChanged === 'function') {
                this.onSearchMatchesChanged(this.searchMatchingNodes.length, this.searchMatchIndex);
            }
        }

        fitNodesBoundingBox(nodes, padding = 120) {
            if (!nodes || nodes.length === 0) return;
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            nodes.forEach(n => {
                if (n.x < minX) minX = n.x;
                if (n.x > maxX) maxX = n.x;
                if (n.y < minY) minY = n.y;
                if (n.y > maxY) maxY = n.y;
            });

            const boxW = Math.max(maxX - minX, 100);
            const boxH = Math.max(maxY - minY, 100);
            const centerX = (minX + maxX) / 2;
            const centerY = (minY + maxY) / 2;

            const availW = Math.max(this.width - padding * 2, 200);
            const availH = Math.max(this.height - padding * 2, 200);

            let zoom = Math.min(availW / boxW, availH / boxH);
            zoom = Math.max(0.35, Math.min(zoom, 1.6));

            this.targetCamera.x = this.width / 2 - centerX * zoom;
            this.targetCamera.y = this.height / 2 - centerY * zoom;
            this.targetCamera.zoom = zoom;
        }

        screenToWorld(sx, sy) {
            return {
                x: (sx - this.camera.x) / this.camera.zoom,
                y: (sy - this.camera.y) / this.camera.zoom
            };
        }

        worldToScreen(wx, wy) {
            return {
                x: wx * this.camera.zoom + this.camera.x,
                y: wy * this.camera.zoom + this.camera.y
            };
        }

        getNodeAt(sx, sy) {
            const world = this.screenToWorld(sx, sy);
            const hitMargin = 8 / this.camera.zoom;

            for (let i = this.nodes.length - 1; i >= 0; i--) {
                const n = this.nodes[i];
                if (!this.activeTiers.has(n.tier)) continue;

                const dx = n.x - world.x;
                const dy = n.y - world.y;
                const hitRadius = n.radius + hitMargin;

                if (dx * dx + dy * dy <= hitRadius * hitRadius) {
                    return n;
                }
            }
            return null;
        }

        getEdgeAt(sx, sy) {
            const world = this.screenToWorld(sx, sy);
            const hitMargin = 8 / this.camera.zoom;

            for (let i = this.edges.length - 1; i >= 0; i--) {
                const e = this.edges[i];
                const n1 = e.sourceNode;
                const n2 = e.targetNode;
                if (!n1 || !n2) continue;
                if (!this.activeTiers.has(n1.tier) || !this.activeTiers.has(n2.tier)) continue;

                const dx = n2.x - n1.x;
                const dy = n2.y - n1.y;
                const lenSq = dx * dx + dy * dy;
                if (lenSq === 0) continue;

                const t = Math.max(0, Math.min(1, ((world.x - n1.x) * dx + (world.y - n1.y) * dy) / lenSq));
                const projX = n1.x + t * dx;
                const projY = n1.y + t * dy;
                const distSq = (world.x - projX) * (world.x - projX) + (world.y - projY) * (world.y - projY);

                if (distSq <= hitMargin * hitMargin) {
                    return e;
                }
            }
            return null;
        }

        setTelemetryMode(mode) {
            this.telemetryMode = mode;
            this.render();
        }

        setupEvents() {
            let mouseDownPos = { x: 0, y: 0 };

            this.canvas.addEventListener('mousedown', (e) => {
                const rect = this.canvas.getBoundingClientRect();
                const sx = e.clientX - rect.left;
                const sy = e.clientY - rect.top;
                mouseDownPos = { x: sx, y: sy };

                const clickedNode = this.getNodeAt(sx, sy);
                if (clickedNode) {
                    this.draggedNode = clickedNode;
                    this.draggedNode.pinned = true;
                    this.canvas.style.cursor = 'grabbing';
                } else {
                    this.isPanning = true;
                    this.panStart = { x: sx - this.camera.x, y: sy - this.camera.y };
                    this.canvas.style.cursor = 'grabbing';
                }
            });

            window.addEventListener('mousemove', (e) => {
                const rect = this.canvas.getBoundingClientRect();
                const sx = e.clientX - rect.left;
                const sy = e.clientY - rect.top;

                if (this.draggedNode) {
                    const world = this.screenToWorld(sx, sy);
                    this.draggedNode.x = world.x;
                    this.draggedNode.y = world.y;
                    this.draggedNode.vx = 0;
                    this.draggedNode.vy = 0;
                } else if (this.isPanning) {
                    this.camera.x = sx - this.panStart.x;
                    this.camera.y = sy - this.panStart.y;
                    this.targetCamera.x = this.camera.x;
                    this.targetCamera.y = this.camera.y;
                } else {
                    const node = this.getNodeAt(sx, sy);
                    const edge = !node ? this.getEdgeAt(sx, sy) : null;
                    if (node !== this.hoveredNode || edge !== this.hoveredEdge) {
                        this.hoveredNode = node;
                        this.hoveredEdge = edge;
                        this.canvas.style.cursor = (node || edge) ? 'pointer' : 'grab';
                        this.updateTooltip(node, edge, e.clientX, e.clientY);
                    } else if (node || edge) {
                        this.updateTooltip(node, edge, e.clientX, e.clientY);
                    } else {
                        this.updateTooltip(null, null, 0, 0);
                    }
                }
            });

            window.addEventListener('mouseup', (e) => {
                const rect = this.canvas.getBoundingClientRect();
                const sx = e.clientX - rect.left;
                const sy = e.clientY - rect.top;
                const distMoved = Math.hypot(sx - mouseDownPos.x, sy - mouseDownPos.y);

                if (this.draggedNode) {
                    this.draggedNode.pinned = false;
                    this.draggedNode = null;
                }
                this.isPanning = false;
                this.canvas.style.cursor = 'grab';

                if (distMoved < 5) {
                    const node = this.getNodeAt(sx, sy);
                    this.selectNode(node);
                }
            });

            this.canvas.addEventListener('wheel', (e) => {
                e.preventDefault();
                const rect = this.canvas.getBoundingClientRect();
                const sx = e.clientX - rect.left;
                const sy = e.clientY - rect.top;

                const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
                const newZoom = Math.min(Math.max(this.camera.zoom * zoomFactor, 0.15), 3.5);

                this.camera.x = sx - (sx - this.camera.x) * (newZoom / this.camera.zoom);
                this.camera.y = sy - (sy - this.camera.y) * (newZoom / this.camera.zoom);
                this.camera.zoom = newZoom;

                this.targetCamera.x = this.camera.x;
                this.targetCamera.y = this.camera.y;
                this.targetCamera.zoom = this.camera.zoom;
            }, { passive: false });

            this.canvas.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                const rect = this.canvas.getBoundingClientRect();
                const sx = e.clientX - rect.left;
                const sy = e.clientY - rect.top;
                const node = this.getNodeAt(sx, sy);
                if (node && typeof this.onNodeContextMenu === 'function') {
                    this.onNodeContextMenu(node, e.clientX, e.clientY);
                }
            });
        }

        updateTooltip(node, edge, screenX, screenY) {
            let tip = document.getElementById('topo-canvas-tooltip');
            if (!node && !edge) {
                if (tip) tip.style.display = 'none';
                return;
            }

            if (!tip) {
                tip = document.createElement('div');
                tip.id = 'topo-canvas-tooltip';
                tip.className = 'topo-tooltip';
                document.body.appendChild(tip);
            }

            if (node) {
                const meta = window.TopologyTheme ? window.TopologyTheme.getMeta(node.tier) : { label: node.tier };
                let driftHtml = '';
                if (this.isDriftMode) {
                    if (node.drift === 'added') driftHtml = '<span class="tooltip-badge" style="background:#059669; color:#fff;">+ NEW</span>';
                    else if (node.drift === 'removed') driftHtml = '<span class="tooltip-badge" style="background:#dc2626; color:#fff;">- REMOVED</span>';
                    else driftHtml = '<span class="tooltip-badge" style="background:#475569; color:#fff;">UNCHANGED</span>';
                }

                tip.innerHTML = `
                    <div class="tooltip-title">${node.id}</div>
                    <div class="tooltip-meta">
                        <span class="tooltip-badge badge-${node.tier}">${meta.shortLabel || node.tier}</span>
                        <span class="tooltip-site">Site: ${node.site || 'N/A'}</span>
                        ${driftHtml}
                    </div>
                    <div class="tooltip-stats">Degree: ${node.degree || 0} links</div>
                `;
            } else if (edge) {
                const p = edge.ping;
                const pInfo = p ? `
                    <div style="margin-top:6px; padding-top:6px; border-top:1px solid rgba(255,255,255,0.1); font-size:0.75rem;">
                        <span class="tooltip-badge" style="background:${p.status === 'critical' ? '#ef4444' : (p.status === 'warning' ? '#f59e0b' : '#10b981')}; color:#fff; font-weight:700;">● ${p.status.toUpperCase()}</span>
                        <span style="margin-left:8px; color:#fff;">RTT: <b>${p.rtt_avg_ms} ms</b></span>
                        <span style="margin-left:8px; color:var(--text-dim, #94a3b8);">Loss: <b>${p.loss_pct}%</b></span>
                    </div>
                ` : `
                    <div style="margin-top:4px; font-size:0.72rem; color:var(--text-dim, #94a3b8);">No direct ping telemetry recorded</div>
                `;

                const labelText = edge.label || (edge.capacity_gbps ? edge.capacity_gbps + 'G' : 'Link');
                tip.innerHTML = `
                    <div class="tooltip-title">${edge.source} ↔ ${edge.target}</div>
                    <div class="tooltip-meta">
                        <span class="tooltip-badge" style="background:#0284c7; color:#fff;">${labelText}</span>
                        <span class="tooltip-site">${edge.local_int || '-'} ⇄ ${edge.remote_int || '-'}</span>
                    </div>
                    ${pInfo}
                `;
            }

            tip.style.left = (screenX + 14) + 'px';
            tip.style.top = (screenY + 14) + 'px';
            tip.style.display = 'block';
        }

        renderLoop() {
            this.camera.x += (this.targetCamera.x - this.camera.x) * 0.15;
            this.camera.y += (this.targetCamera.y - this.camera.y) * 0.15;
            this.camera.zoom += (this.targetCamera.zoom - this.camera.zoom) * 0.15;

            this.stepPhysics();
            this.render();

            if (this.animating) {
                requestAnimationFrame(this.renderLoop);
            }
        }

        render() {
            const ctx = this.ctx;
            const w = this.width;
            const h = this.height;
            const cam = this.camera;

            const themeName = window.TopologyTheme ? window.TopologyTheme.getCurrentThemeName() : 'dark';
            const theme = window.TopologyTheme ? window.TopologyTheme.getTheme(themeName) : { canvasBg: '#020617', text: '#fff', gridLine: 'rgba(255,255,255,0.05)' };

            // 1. Clear background
            ctx.fillStyle = theme.canvasBg;
            ctx.fillRect(0, 0, w, h);

            ctx.save();
            ctx.translate(cam.x, cam.y);
            ctx.scale(cam.zoom, cam.zoom);

            // 2. Background Grid / Orbital concentric guide rings
            if (this.activeLayout === 'concentric') {
                this.drawOrbitalGuides(ctx, theme);
            } else {
                this.drawBackgroundGrid(ctx, theme);
            }

            // Visible Viewport Bounds for Culling
            const cullMargin = 100;
            const minX = -cam.x / cam.zoom - cullMargin;
            const maxX = (w - cam.x) / cam.zoom + cullMargin;
            const minY = -cam.y / cam.zoom - cullMargin;
            const maxY = (h - cam.y) / cam.zoom + cullMargin;

            // 3. Render Edges
            this.renderEdges(ctx, minX, maxX, minY, maxY, theme, themeName);

            // 4. Render Nodes
            this.renderNodes(ctx, minX, maxX, minY, maxY, theme, themeName);

            ctx.restore();

            // 5. HUD Status Overlay
            this.renderCanvasHUD(ctx, w, h, theme);
        }

        drawOrbitalGuides(ctx, theme) {
            const radii = [90, 170, 260, 390, 520, 680, 840];
            const labels = ['CORE (1)', 'BGP-RR', 'CORE-AGG (2)', 'EDGE / PE (3)', 'PEERING', 'METRO (4)', 'OTHER'];

            ctx.save();
            radii.forEach((r, i) => {
                ctx.beginPath();
                ctx.arc(0, 0, r, 0, Math.PI * 2);
                ctx.strokeStyle = theme.gridLine || 'rgba(255,255,255,0.06)';
                ctx.lineWidth = 1;
                ctx.setLineDash([4, 4]);
                ctx.stroke();

                if (this.camera.zoom >= 0.45 && labels[i]) {
                    ctx.font = '10px Outfit, sans-serif';
                    ctx.fillStyle = theme.textDim || '#94a3b8';
                    ctx.textAlign = 'center';
                    ctx.fillText(labels[i], 0, -r - 4);
                }
            });
            ctx.restore();
        }

        drawBackgroundGrid(ctx, theme) {
            if (this.camera.zoom < 0.35) return;
            const step = 80;
            const cam = this.camera;
            const startX = Math.floor((-cam.x / cam.zoom) / step) * step;
            const endX = Math.ceil(((this.width - cam.x) / cam.zoom) / step) * step;
            const startY = Math.floor((-cam.y / cam.zoom) / step) * step;
            const endY = Math.ceil(((this.height - cam.y) / cam.zoom) / step) * step;

            ctx.save();
            ctx.fillStyle = theme.gridLine || 'rgba(255,255,255,0.05)';
            for (let x = startX; x <= endX; x += step) {
                for (let y = startY; y <= endY; y += step) {
                    ctx.fillRect(x - 1, y - 1, 2, 2);
                }
            }
            ctx.restore();
        }

        renderEdges(ctx, minX, maxX, minY, maxY, theme, themeName) {
            const isHighlightMode = (this.selectedNode !== null || this.hoveredNode !== null);
            const activeNode = this.hoveredNode || this.selectedNode;

            ctx.save();
            for (let i = 0; i < this.edges.length; i++) {
                const e = this.edges[i];
                const n1 = e.sourceNode;
                const n2 = e.targetNode;

                if (!this.activeTiers.has(n1.tier) || !this.activeTiers.has(n2.tier)) continue;

                if ((n1.x < minX && n2.x < minX) || (n1.x > maxX && n2.x > maxX) ||
                    (n1.y < minY && n2.y < minY) || (n1.y > maxY && n2.y > maxY)) {
                    continue;
                }

                const isConnected = isHighlightMode && (
                    n1.id === activeNode.id || n2.id === activeNode.id
                );

                // Phase 4: Drift edge styling
                if (this.isDriftMode) {
                    if (e.drift === 'added') {
                        ctx.strokeStyle = '#10b981'; // Emerald Green
                        ctx.lineWidth = isConnected ? 3.5 : 2.5;
                        ctx.setLineDash([]);
                        ctx.globalAlpha = 1.0;
                    } else if (e.drift === 'removed') {
                        ctx.strokeStyle = '#ef4444'; // Red Carmine
                        ctx.lineWidth = isConnected ? 3.0 : 2.0;
                        ctx.setLineDash([4, 4]);
                        ctx.globalAlpha = 0.85;
                    } else {
                        ctx.strokeStyle = theme.border || 'rgba(148, 163, 184, 0.2)';
                        ctx.lineWidth = 1.0;
                        ctx.setLineDash([]);
                        ctx.globalAlpha = isHighlightMode ? (isConnected ? 0.9 : 0.05) : 0.12;
                    }
                    ctx.beginPath();
                    ctx.moveTo(n1.x, n1.y);
                    ctx.lineTo(n2.x, n2.y);
                    ctx.stroke();
                    ctx.setLineDash([]);
                    continue;
                }

                const speed = e.capacity_str || e.bandwidth || '10G';
                const isPathMode = (this.activePath !== null && this.activePathEdgeIds && this.activePathEdgeIds.size > 0);
                const isPathEdge = isPathMode && (
                    this.activePathEdgeIds.has(e.id) ||
                    (this.activePathPairKeys && (this.activePathPairKeys.has(`${n1.id}:::${n2.id}`) || this.activePathPairKeys.has(`${n2.id}:::${n1.id}`)))
                );

                const hasSearchFilter = (this.searchMatchingNodes && this.searchMatchingNodes.length > 0);
                const isN1Match = hasSearchFilter && this.searchMatchingNodes.some(m => m.id === n1.id);
                const isN2Match = hasSearchFilter && this.searchMatchingNodes.some(m => m.id === n2.id);
                const isSearchEdge = isN1Match && isN2Match;
                const isPartialSearchEdge = isN1Match || isN2Match;

                if (isPathMode) {
                    ctx.globalAlpha = isPathEdge ? 1.0 : 0.06;
                } else if (hasSearchFilter) {
                    ctx.globalAlpha = isSearchEdge ? 0.95 : (isPartialSearchEdge ? 0.25 : 0.04);
                } else if (isHighlightMode && !isConnected) {
                    ctx.globalAlpha = 0.08;
                } else if (isConnected) {
                    ctx.globalAlpha = 1.0;
                } else {
                    ctx.globalAlpha = 0.55;
                }

                let edgeColor = '#38bdf8';
                let edgeWidth = isConnected ? 2.5 : (speed === '100G' ? 2.0 : 1.2);
                let edgeDash = [];

                if (isPathEdge) {
                    edgeColor = '#38bdf8'; // Active Path Neon Route Beam
                    edgeWidth = 3.6;
                } else if (this.telemetryMode === 'latency') {
                    if (e.ping && e.ping.rtt_avg_ms !== undefined) {
                        const rtt = e.ping.rtt_avg_ms;
                        if (rtt <= 10.0) edgeColor = '#10b981'; // Emerald (<10ms)
                        else if (rtt <= 30.0) edgeColor = '#0ea5e9'; // Sky Blue (10-30ms)
                        else if (rtt <= 60.0) edgeColor = '#f59e0b'; // Amber (30-60ms)
                        else edgeColor = '#ef4444'; // Red (>60ms)
                        edgeWidth = isConnected ? 3.0 : 1.8;
                    } else {
                        edgeColor = '#64748b'; // Slate (No Ping Telemetry)
                        edgeDash = [3, 3];
                        edgeWidth = 1.0;
                    }
                } else if (this.telemetryMode === 'loss') {
                    if (e.ping && e.ping.loss_pct !== undefined) {
                        const loss = e.ping.loss_pct;
                        if (loss === 0.0) edgeColor = '#10b981'; // Clean (0%)
                        else if (loss < 10.0) edgeColor = '#f59e0b'; // Degraded (>0%)
                        else edgeColor = '#ef4444'; // Critical Loss (>=10%)
                        edgeWidth = isConnected ? 3.0 : (loss > 0 ? 2.2 : 1.6);
                    } else {
                        edgeColor = '#64748b'; // Slate (No Ping Telemetry)
                        edgeDash = [3, 3];
                        edgeWidth = 1.0;
                    }
                } else {
                    edgeColor = window.TopologyTheme ? window.TopologyTheme.getLinkColor(speed, themeName) : '#38bdf8';
                }

                ctx.beginPath();
                ctx.moveTo(n1.x, n1.y);
                ctx.lineTo(n2.x, n2.y);
                ctx.strokeStyle = (isConnected && !isPathEdge) ? '#ffffff' : edgeColor;
                ctx.lineWidth = edgeWidth;
                if (edgeDash.length > 0) ctx.setLineDash(edgeDash);
                ctx.stroke();
                if (edgeDash.length > 0) ctx.setLineDash([]);

                if (isPathEdge) {
                    // Pulsating directional particle along active route
                    const animPhase = ((Date.now() / 1200) + (i * 0.18)) % 1;
                    const pX = n1.x + (n2.x - n1.x) * animPhase;
                    const pY = n1.y + (n2.y - n1.y) * animPhase;
                    ctx.save();
                    ctx.beginPath();
                    ctx.arc(pX, pY, 3.2, 0, Math.PI * 2);
                    ctx.fillStyle = '#ffffff';
                    ctx.shadowColor = '#38bdf8';
                    ctx.shadowBlur = 8;
                    ctx.fill();
                    ctx.restore();
                }

                if ((isConnected || isPathEdge) && this.camera.zoom >= 0.75 && e.local_int) {
                    const midX = (n1.x + n2.x) / 2;
                    const midY = (n1.y + n2.y) / 2;
                    ctx.font = '9px monospace';
                    ctx.fillStyle = theme.text || '#fff';
                    ctx.textAlign = 'center';
                    let midLabel = `${e.local_int} ↔ ${e.remote_int || ''}`;
                    if (this.telemetryMode === 'latency' && e.ping) {
                        midLabel += ` (${e.ping.rtt_avg_ms}ms)`;
                    } else if (this.telemetryMode === 'loss' && e.ping) {
                        midLabel += ` (${e.ping.loss_pct}% loss)`;
                    }
                    ctx.fillText(midLabel, midX, midY - 4);
                }
            }
            ctx.restore();
        }

        renderNodes(ctx, minX, maxX, minY, maxY, theme, themeName) {
            const isHighlightMode = (this.selectedNode !== null || this.hoveredNode !== null);
            const activeNode = this.hoveredNode || this.selectedNode;
            const hasSearchFilter = (this.searchMatchingNodes && this.searchMatchingNodes.length > 0);
            const searchSet = hasSearchFilter ? new Set(this.searchMatchingNodes.map(m => m.id)) : null;
            const currentCycleNode = (hasSearchFilter && this.searchMatchIndex >= 0 && this.searchMatchingNodes[this.searchMatchIndex]) ? this.searchMatchingNodes[this.searchMatchIndex] : null;

            for (let i = 0; i < this.nodes.length; i++) {
                const n = this.nodes[i];
                if (!this.activeTiers.has(n.tier)) continue;

                if (n.x < minX || n.x > maxX || n.y < minY || n.y > maxY) continue;

                const isSelected = (this.selectedNode && this.selectedNode.id === n.id);
                const isHovered = (this.hoveredNode && this.hoveredNode.id === n.id);
                const isNeighbor = isHighlightMode && this.connectedNodeIds.has(n.id);
                const isSearchMatch = searchSet ? searchSet.has(n.id) : false;
                const isCurrentCycleMatch = currentCycleNode && (currentCycleNode.id === n.id);

                // Phase 3 & 4: Path Tracing node classification
                const isPathMode = (this.activePath !== null && this.activePathNodeIds && this.activePathNodeIds.size > 0);
                const isPathNode = isPathMode && this.activePathNodeIds.has(n.id);
                const isPathStart = isPathMode && (n.id === this.pathTraceStartNode);
                const isPathEnd = isPathMode && (n.id === this.pathTraceEndNode);

                // Transparency logic
                if (isPathMode) {
                    ctx.globalAlpha = isPathNode ? 1.0 : 0.08;
                } else if (hasSearchFilter) {
                    ctx.globalAlpha = isSearchMatch ? 1.0 : 0.10;
                } else if (this.isDriftMode) {
                    if (n.drift === 'added') {
                        ctx.globalAlpha = 1.0;
                    } else if (n.drift === 'removed') {
                        ctx.globalAlpha = 0.8;
                    } else {
                        ctx.globalAlpha = isHighlightMode ? (isSelected || isHovered || isNeighbor || isSearchMatch ? 1.0 : 0.08) : 0.22;
                    }
                } else if (isHighlightMode && !isNeighbor && !isSelected && !isHovered) {
                    ctx.globalAlpha = 0.15;
                } else {
                    ctx.globalAlpha = 1.0;
                }

                // Draw Node Shape & Vector Icons
                if (window.TopologyTheme && typeof window.TopologyTheme.drawCanvasNode === 'function') {
                    window.TopologyTheme.drawCanvasNode(ctx, n.x, n.y, n.radius, n.tier, themeName, isSelected, isHovered);
                } else {
                    ctx.beginPath();
                    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
                    ctx.fillStyle = '#38bdf8';
                    ctx.fill();
                }

                // Phase 4: Drift visual rings
                if (this.isDriftMode) {
                    if (n.drift === 'added') {
                        ctx.beginPath();
                        ctx.arc(n.x, n.y, n.radius + 6, 0, Math.PI * 2);
                        ctx.strokeStyle = '#10b981';
                        ctx.lineWidth = 3.0;
                        ctx.stroke();
                    } else if (n.drift === 'removed') {
                        ctx.beginPath();
                        ctx.arc(n.x, n.y, n.radius + 5, 0, Math.PI * 2);
                        ctx.setLineDash([4, 4]);
                        ctx.strokeStyle = '#ef4444';
                        ctx.lineWidth = 2.5;
                        ctx.stroke();
                        ctx.setLineDash([]);
                    }
                }

                // Path Trace Start / End Markers & Route Halos
                if (isPathStart) {
                    ctx.beginPath();
                    ctx.arc(n.x, n.y, n.radius + 8, 0, Math.PI * 2);
                    ctx.strokeStyle = '#10b981'; // Emerald Origin Halo
                    ctx.lineWidth = 3.5;
                    ctx.stroke();
                } else if (isPathEnd) {
                    ctx.beginPath();
                    ctx.arc(n.x, n.y, n.radius + 8, 0, Math.PI * 2);
                    ctx.strokeStyle = '#0284c7'; // Sky/Cyan Target Halo
                    ctx.lineWidth = 3.5;
                    ctx.stroke();
                } else if (isPathNode) {
                    ctx.beginPath();
                    ctx.arc(n.x, n.y, n.radius + 5, 0, Math.PI * 2);
                    ctx.strokeStyle = '#38bdf8'; // Route Hop Halo
                    ctx.lineWidth = 2.0;
                    ctx.stroke();
                }

                // Search highlight glow
                if (isSearchMatch) {
                    ctx.save();
                    ctx.beginPath();
                    ctx.arc(n.x, n.y, n.radius + 6, 0, Math.PI * 2);
                    ctx.strokeStyle = isCurrentCycleMatch ? '#38bdf8' : '#10b981';
                    ctx.lineWidth = isCurrentCycleMatch ? 3.5 : 2.5;
                    if (!isCurrentCycleMatch) {
                        ctx.setLineDash([4, 3]);
                    }
                    ctx.stroke();
                    ctx.restore();
                }

                // Render Labels (LOD: Level of Detail)
                if (this.camera.zoom >= 0.5 || isSelected || isHovered || isNeighbor || isSearchMatch || isPathNode || (this.isDriftMode && n.drift !== 'unchanged')) {
                    ctx.save();
                    ctx.font = (n.tier === 'core' ? 'bold 11px' : '10px') + ' Inter, sans-serif';
                    ctx.textAlign = 'center';
                    
                    const labelY = n.y + n.radius + 13;
                    let displayLabel = n.id;
                    if (this.isDriftMode) {
                        if (n.drift === 'added') displayLabel += ' [+NEW]';
                        else if (n.drift === 'removed') displayLabel += ' [-REMOVED]';
                    }

                    const textWidth = ctx.measureText(displayLabel).width;

                    ctx.fillStyle = theme.hudBg || 'rgba(15,23,42,0.85)';
                    ctx.fillRect(n.x - textWidth / 2 - 4, labelY - 10, textWidth + 8, 14);

                    if (this.isDriftMode && n.drift === 'added') {
                        ctx.fillStyle = '#10b981';
                    } else if (this.isDriftMode && n.drift === 'removed') {
                        ctx.fillStyle = '#ef4444';
                    } else {
                        ctx.fillStyle = isSelected ? '#38bdf8' : (theme.text || '#ffffff');
                    }
                    ctx.fillText(displayLabel, n.x, labelY);
                    ctx.restore();
                }
            }
        }

        renderCanvasHUD(ctx, w, h, theme) {
            ctx.save();
            ctx.font = '11px monospace';
            ctx.textAlign = 'left';

            const visibleCount = this.nodes.filter(n => this.activeTiers.has(n.tier)).length;
            const zoomPercent = Math.round(this.camera.zoom * 100);

            // Phase 4: Drift HUD status
            if (this.isDriftMode && this.driftStats) {
                const s = this.driftStats;
                const driftBanner = `⚖️ DRIFT: +${s.nodes_added}/-${s.nodes_removed} Nodes | +${s.edges_added}/-${s.edges_removed} Links | ${s.nodes_unchanged} Stable`;
                
                ctx.fillStyle = 'rgba(2, 6, 23, 0.85)';
                const bannerW = ctx.measureText(driftBanner).width + 24;
                ctx.fillRect(15, 12, bannerW, 26);
                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 1;
                ctx.strokeRect(15, 12, bannerW, 26);

                ctx.fillStyle = '#38bdf8';
                ctx.fillText(driftBanner, 27, 29);
            }

            // Phase 2 Telemetry Overlay Legend Badge
            if (this.telemetryMode !== 'speed') {
                let legendText = '';
                if (this.telemetryMode === 'latency') {
                    legendText = '⏱️ RTT: ≤10ms Optimal | ≤30ms Good | ≤60ms Fair | >60ms High | ╌ No Data';
                } else if (this.telemetryMode === 'loss') {
                    legendText = '📉 LOSS: 0% Clean | 0.1-10% Degraded | >10% Critical | ╌ No Data';
                }
                ctx.save();
                ctx.font = '10px monospace';
                ctx.textAlign = 'right';
                const textW = ctx.measureText(legendText).width;
                ctx.fillStyle = 'rgba(2, 6, 23, 0.85)';
                ctx.fillRect(w - textW - 30, 12, textW + 20, 24);
                ctx.strokeStyle = (this.telemetryMode === 'loss') ? '#f59e0b' : '#38bdf8';
                ctx.lineWidth = 1;
                ctx.strokeRect(w - textW - 30, 12, textW + 20, 24);
                ctx.fillStyle = (this.telemetryMode === 'loss') ? '#fcd34d' : '#38bdf8';
                ctx.fillText(legendText, w - 20, 28);
                ctx.restore();
            }

            const statusText = `Nodes: ${visibleCount}/${this.nodes.length} | Edges: ${this.edges.length} | Zoom: ${zoomPercent}% | Physics: ${this.physicsFrozen ? 'Frozen (60fps)' : 'Stabilizing...'}`;

            ctx.fillStyle = 'rgba(2, 6, 23, 0.7)';
            ctx.fillRect(15, h - 35, ctx.measureText(statusText).width + 20, 24);

            ctx.fillStyle = theme.textDim || '#94a3b8';
            ctx.fillText(statusText, 25, h - 19);
            ctx.restore();
        }

        /* Phase 5: Client-Side Draw.io Exporter */
        generateDrawioXml(title = "Network Topology") {
            const visibleNodes = this.nodes.filter(n => this.activeTiers.has(n.tier));
            if (visibleNodes.length === 0) return "";

            // Calculate bounding box and scale to page coordinates
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            visibleNodes.forEach(n => {
                if (n.x < minX) minX = n.x;
                if (n.x > maxX) maxX = n.x;
                if (n.y < minY) minY = n.y;
                if (n.y > maxY) maxY = n.y;
            });

            const margin = 150;
            const widthSpan = maxX - minX;
            const heightSpan = maxY - minY;
            const scale = (widthSpan > 3000 || heightSpan > 3000) ? 0.8 : 1.0;

            const pageWidth = Math.max(2400, Math.round(widthSpan * scale + margin * 2));
            const pageHeight = Math.max(2400, Math.round(heightSpan * scale + margin * 2));

            const escapeXml = (str) => {
                if (!str) return "";
                return String(str)
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&apos;");
            };

            const nowIso = new Date().toISOString();
            let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`;
            xml += `<mxfile host="Electron" modified="${nowIso}" agent="Mozilla/5.0" version="21.0.0" type="device">\n`;
            xml += `  <diagram id="diag_native_export" name="${escapeXml(title)}">\n`;
            xml += `    <mxGraphModel dx="1600" dy="1200" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="${pageWidth}" pageHeight="${pageHeight}" background="#ffffff" math="0" shadow="0">\n`;
            xml += `      <root>\n`;
            xml += `        <mxCell id="0"/>\n`;
            xml += `        <mxCell id="1" parent="0"/>\n`;

            // Tier styling definitions
            const tierStyles = {
                'core': { prIcon: 'router', fill: '#036897', stroke: '#FFFFFF' },
                'core_agg': { prIcon: 'router', fill: '#0385BE', stroke: '#FFFFFF' },
                'edge': { prIcon: 'router', fill: '#0284c7', stroke: '#FFFFFF' },
                'peering': { prIcon: 'router', fill: '#E98C2F', stroke: '#FFFFFF' },
                'router_reflector': { prIcon: 'router', fill: '#0d9488', stroke: '#FFFFFF' },
                'metro': { prIcon: 'l2_switch', fill: '#228122', stroke: '#FFFFFF' },
                'other': { prIcon: 'router', fill: '#64748b', stroke: '#FFFFFF' }
            };

            // Render Nodes
            const visibleNodeSet = new Set(visibleNodes.map(n => n.id));
            visibleNodes.forEach(n => {
                const drawioX = Math.round((n.x - minX) * scale + margin);
                const drawioY = Math.round((n.y - minY) * scale + margin);

                const tStyle = tierStyles[n.tier] || tierStyles['other'];
                let fill = tStyle.fill;
                let stroke = tStyle.stroke;
                let strokeWidth = 1;
                let dashed = 0;

                if (this.isDriftMode && n.drift) {
                    if (n.drift === 'added') {
                        fill = '#10b981';
                        stroke = '#059669';
                        strokeWidth = 2;
                    } else if (n.drift === 'removed') {
                        fill = '#ef4444';
                        stroke = '#b91c1c';
                        strokeWidth = 2;
                        dashed = 1;
                    }
                }

                const siteLabel = n.site ? `&lt;br&gt;&lt;span style=&quot;font-size:9px;font-weight:normal;opacity:0.8;&quot;&gt;${escapeXml(n.site)}&lt;/span&gt;` : '';
                const driftTag = (this.isDriftMode && n.drift && n.drift !== 'unchanged') ? (n.drift === 'added' ? ' [+NEW]' : ' [-REMOVED]') : '';
                const cellValue = `${escapeXml(n.id)}${driftTag}${siteLabel}`;

                let shapeStyle = `shape=mxgraph.cisco19.rect;prIcon=${tStyle.prIcon};fillColor=${fill};strokeColor=${stroke};strokeWidth=${strokeWidth};verticalLabelPosition=bottom;verticalAlign=top;align=center;fontSize=11;fontStyle=1;fontColor=#0f172a;html=1;`;
                if (dashed) shapeStyle += `dashed=1;`;

                xml += `        <mxCell id="${escapeXml(n.id)}" value="${cellValue}" style="${shapeStyle}" vertex="1" parent="1">\n`;
                xml += `          <mxGeometry x="${drawioX}" y="${drawioY}" width="50" height="50" as="geometry"/>\n`;
                xml += `        </mxCell>\n`;
            });

            // Render Edges
            const visibleEdges = this.edges.filter(e => {
                const sId = typeof e.source === 'object' ? e.source.id : e.source;
                const tId = typeof e.target === 'object' ? e.target.id : e.target;
                return visibleNodeSet.has(sId) && visibleNodeSet.has(tId);
            });

            visibleEdges.forEach((e, idx) => {
                const sId = typeof e.source === 'object' ? e.source.id : e.source;
                const tId = typeof e.target === 'object' ? e.target.id : e.target;

                let strokeColor = '#64748b';
                let strokeWidth = 1;
                let dashed = 0;

                if (e.bandwidth_mbps >= 100000) {
                    strokeColor = '#10b981';
                    strokeWidth = 3;
                } else if (e.bandwidth_mbps >= 40000) {
                    strokeColor = '#10b981';
                    strokeWidth = 3;
                } else if (e.bandwidth_mbps >= 10000) {
                    strokeColor = '#0085da';
                    strokeWidth = 2;
                }

                if (this.isDriftMode && e.drift) {
                    if (e.drift === 'added') {
                        strokeColor = '#10b981';
                        strokeWidth = 3;
                    } else if (e.drift === 'removed') {
                        strokeColor = '#ef4444';
                        strokeWidth = 2;
                        dashed = 1;
                    } else {
                        strokeColor = '#94a3b8';
                        strokeWidth = 1;
                    }
                }

                let edgeValue = '';
                if (this.activeType === 'detailed') {
                    const lInt = e.local_int || '';
                    const rInt = e.remote_int || '';
                    const spd = e.speed || (e.bandwidth_mbps ? (e.bandwidth_mbps + 'M') : '');
                    edgeValue = `${lInt} ↔ ${rInt}${spd ? ' (' + spd + ')' : ''}`;
                } else {
                    edgeValue = e.capacity_str || (e.bandwidth_mbps ? (e.bandwidth_mbps >= 1000 ? (e.bandwidth_mbps / 1000) + 'G' : e.bandwidth_mbps + 'M') : '');
                }

                let edgeStyle = `edgeStyle=none;rounded=0;curved=0;html=1;endArrow=none;endFill=0;strokeColor=${strokeColor};strokeWidth=${strokeWidth};fontSize=9;`;
                if (dashed) edgeStyle += `dashed=1;`;

                xml += `        <mxCell id="edge_${idx}" value="${escapeXml(edgeValue)}" style="${edgeStyle}" edge="1" parent="1" source="${escapeXml(sId)}" target="${escapeXml(tId)}">\n`;
                xml += `          <mxGeometry relative="1" as="geometry"/>\n`;
                xml += `        </mxCell>\n`;
            });

            xml += `      </root>\n`;
            xml += `    </mxGraphModel>\n`;
            xml += `  </diagram>\n`;
            xml += `</mxfile>\n`;
            return xml;
        }

        exportToDrawio(suggestedFilename = "topology_export.drawio") {
            const xml = this.generateDrawioXml("Network Topology Export");
            if (!xml) {
                alert("No visible nodes to export.");
                return;
            }

            const blob = new Blob([xml], { type: "application/vnd.jgraph.mxfile;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = suggestedFilename.endsWith('.drawio') ? suggestedFilename : (suggestedFilename + '.drawio');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        /* ====================================================================
         * Phase 3 & 4: Path Tracing & Yen's K=3 Disjoint Routing Engine
         * ==================================================================== */

        buildAdjacencyGraph() {
            const adj = new Map();
            for (let i = 0; i < this.edges.length; i++) {
                const e = this.edges[i];
                const u = e.source || e.from;
                const v = e.target || e.to;
                if (!u || !v) continue;

                if (!adj.has(u)) adj.set(u, []);
                if (!adj.has(v)) adj.set(v, []);

                const pingObj = e.ping || (this.pingLookup ? (this.pingLookup[`${u}|${v}`] || this.pingLookup[`${v}|${u}`]) : null);

                adj.get(u).push({
                    node: v,
                    edge: e,
                    bandwidth: e.bandwidth || e.speed || e.capacity_str || '',
                    capacity_gbps: e.capacity_gbps || 0,
                    dashed: (e.drift === 'removed' || e.dashed === 1 || e.dashed === '1') ? 1 : 0,
                    ping: pingObj
                });
                adj.get(v).push({
                    node: u,
                    edge: e,
                    bandwidth: e.bandwidth || e.speed || e.capacity_str || '',
                    capacity_gbps: e.capacity_gbps || 0,
                    dashed: (e.drift === 'removed' || e.dashed === 1 || e.dashed === '1') ? 1 : 0,
                    ping: pingObj
                });
            }
            return adj;
        }

        parseBandwidth(bw) {
            if (!bw) return 0;
            if (typeof bw === 'number') {
                return bw > 1000000 ? Math.floor(bw / 1000) : bw;
            }
            const s = bw.toString().trim().toUpperCase();
            if (s.endsWith('G') || s.endsWith('GB') || s.endsWith('GBPS')) {
                return (parseFloat(s) || 0) * 1000000;
            }
            if (s.endsWith('M') || s.endsWith('MB') || s.endsWith('MBPS')) {
                return (parseFloat(s) || 0) * 1000;
            }
            if (s.endsWith('K') || s.endsWith('KB') || s.endsWith('KBPS')) {
                return parseFloat(s) || 0;
            }
            const val = parseFloat(s) || 0;
            return val > 1000000 ? Math.floor(val / 1000) : val;
        }

        getDeviceRank(nodeId) {
            if (!nodeId) return 0;
            const node = this.nodeMap.get(nodeId);
            if (node && node.tier) {
                const tier = String(node.tier).toLowerCase();
                if (tier === 'metro') return 1;
                if (tier === 'edge') return 2;
                if (tier === 'core_agg') return 3;
                if (tier === 'core') return 4;
                if (tier === 'peering') return 5;
                if (tier === 'router_reflector') return 6;
            }
            const nameUpper = String(nodeId).trim().toUpperCase();
            if (nameUpper.startsWith('SWAC') || nameUpper.startsWith('SWAG')) return 1;
            if (nameUpper.startsWith('RTAC') || nameUpper.startsWith('RTED')) return 2;
            if (nameUpper.startsWith('RTOC')) return 3;
            if (nameUpper.startsWith('RTIC')) return 4;
            if (nameUpper.startsWith('RTPR')) return 5;
            if (nameUpper.startsWith('RTRR')) return 6;
            return 0;
        }

        serializeState(node, hasDecreased, lastRank) {
            return `${node}|${hasDecreased ? 1 : 0}|${lastRank}`;
        }

        deserializeState(stateKey) {
            const lastPipe = stateKey.lastIndexOf('|');
            const secondLastPipe = stateKey.lastIndexOf('|', lastPipe - 1);
            const node = stateKey.substring(0, secondLastPipe);
            const hasDecreased = stateKey.substring(secondLastPipe + 1, lastPipe) === '1';
            const lastRank = parseInt(stateKey.substring(lastPipe + 1), 10);
            return { node, hasDecreased, lastRank };
        }

        calculateDijkstra(graph, startNode, endNode, disabledEdges = new Set()) {
            const distances = new Map();
            const prev = new Map();
            const pq = new MinHeapPriorityQueue();

            const rankStart = this.getDeviceRank(startNode);
            const startStateKey = this.serializeState(startNode, false, rankStart > 0 ? rankStart : -1);

            distances.set(startStateKey, 0);
            pq.enqueue(startStateKey, 0);

            let minEndCost = Infinity;
            let bestEndStateKey = null;

            while (!pq.isEmpty()) {
                const item = pq.dequeue();
                if (!item) break;
                const { element: uStateKey, priority: dist } = item;

                const { node: u, hasDecreased, lastRank } = this.deserializeState(uStateKey);

                if (u === endNode) {
                    if (dist < minEndCost) {
                        minEndCost = dist;
                        bestEndStateKey = uStateKey;
                    }
                    break;
                }

                const currentKnownDist = distances.get(uStateKey);
                if (currentKnownDist !== undefined && dist > currentKnownDist) continue;

                const neighbors = graph.get(u) || [];
                for (let i = 0; i < neighbors.length; i++) {
                    const edgeItem = neighbors[i];
                    const v = edgeItem.node;

                    // Check if edge is disabled (Yen's K-path simulation)
                    const edgeKey1 = `${u}|${v}`;
                    const edgeKey2 = `${v}|${u}`;
                    if (disabledEdges.has(edgeKey1) || disabledEdges.has(edgeKey2)) continue;

                    let weight = 1.0; // Base hop cost

                    // Status penalty (removed drift or dashed)
                    if (edgeItem.dashed === 1) {
                        weight += 10000.0;
                    }

                    // Capacity penalty (favor higher bandwidth links)
                    const bwKbps = this.parseBandwidth(edgeItem.bandwidth);
                    if (bwKbps > 0) {
                        weight += (100000000.0 / bwKbps); // 100G = 1, 10G = 10, 1G = 100
                    } else {
                        weight += 1000.0;
                    }

                    // Telemetry Penalty (Ping metrics)
                    const p = edgeItem.ping;
                    if (p) {
                        if (p.is_unreachable || p.loss_pct === 100.0) {
                            weight += 10000.0;
                        } else {
                            weight += (p.rtt_avg_ms || p.avg || 0);
                            weight += (p.loss_pct || 0) * 50.0;
                        }
                    }

                    // Hierarchy & Valley-Free Routing Constraints
                    const rankU = this.getDeviceRank(u);
                    const rankV = this.getDeviceRank(v);

                    // 1. Metro-to-Metro Transit Penalty
                    if (u !== startNode && v !== endNode && rankU === 1 && rankV === 1) {
                        weight += 50000.0;
                    }

                    // 2. Valley-Free Constraint (No going down then up)
                    let nextHasDecreased = hasDecreased;
                    let nextLastRank = lastRank;

                    if (rankV > 0) {
                        if (lastRank !== -1) {
                            if (rankV < lastRank) {
                                nextHasDecreased = true;
                            } else if (rankV > lastRank) {
                                if (hasDecreased) {
                                    weight += 1000000.0; // Valley violation penalty
                                }
                            }
                        }
                        nextLastRank = rankV;
                    }

                    // 3. Level-Skipping Penalty (Shortcut penalty)
                    if (rankU > 0 && rankV > 0) {
                        const diff = Math.abs(rankU - rankV);
                        if (diff > 1) {
                            weight += 5000.0 * (diff - 1);
                        }
                    }

                    // 4. Peering & Router Reflector Transit Penalty
                    if (u !== startNode && (rankU === 5 || rankU === 6)) {
                        weight += 1000000.0;
                    }
                    if (v !== endNode && (rankV === 5 || rankV === 6)) {
                        weight += 1000000.0;
                    }

                    const vStateKey = this.serializeState(v, nextHasDecreased, nextLastRank);
                    const altDist = dist + weight;
                    const existingDist = distances.get(vStateKey);

                    if (existingDist === undefined || altDist < existingDist) {
                        distances.set(vStateKey, altDist);
                        prev.set(vStateKey, uStateKey);
                        pq.enqueue(vStateKey, altDist);
                    }
                }
            }

            const path = [];
            let curr = bestEndStateKey;
            while (curr) {
                const { node } = this.deserializeState(curr);
                path.unshift(node);
                curr = prev.get(curr);
            }

            if (path.length > 1 && path[0] === startNode) {
                return { path, cost: minEndCost };
            }
            return null;
        }

        enrichPath(rawResult, graph) {
            if (!rawResult || !rawResult.path) return null;
            const pathNodes = rawResult.path;
            const hops = pathNodes.length - 1;
            const hopDetails = [];
            let cumulativeRtt = 0;
            let hasPingData = false;
            let worstLoss = 0;
            let bottleneckBwGbps = Infinity;
            let bottleneckInterface = '';
            const edgeIds = [];

            for (let i = 0; i < hops; i++) {
                const u = pathNodes[i];
                const v = pathNodes[i + 1];
                const neighbors = graph.get(u) || [];
                let matchedEdge = null;
                for (let j = 0; j < neighbors.length; j++) {
                    if (neighbors[j].node === v) {
                        matchedEdge = neighbors[j];
                        break;
                    }
                }

                let hopRtt = null;
                let hopLoss = null;
                let hopBwStr = matchedEdge ? (matchedEdge.edge.capacity_str || matchedEdge.edge.speed || '10G') : '10G';
                let localInt = matchedEdge ? (matchedEdge.edge.source === u ? matchedEdge.edge.local_int : matchedEdge.edge.remote_int) : '';
                let remoteInt = matchedEdge ? (matchedEdge.edge.source === u ? matchedEdge.edge.remote_int : matchedEdge.edge.local_int) : '';
                let edgeId = matchedEdge ? matchedEdge.edge.id : `${u}::${v}`;
                edgeIds.push(edgeId);

                if (matchedEdge && matchedEdge.ping) {
                    const p = matchedEdge.ping;
                    hopRtt = p.rtt_avg_ms !== undefined ? p.rtt_avg_ms : (p.avg !== undefined ? p.avg : null);
                    hopLoss = p.loss_pct !== undefined ? p.loss_pct : 0.0;
                    if (hopRtt !== null) {
                        cumulativeRtt += hopRtt;
                        hasPingData = true;
                    }
                    if (hopLoss !== null && hopLoss > worstLoss) {
                        worstLoss = hopLoss;
                    }
                }

                let capGbps = matchedEdge ? matchedEdge.capacity_gbps : 0;
                if (!capGbps && matchedEdge) {
                    const bwKbps = this.parseBandwidth(matchedEdge.bandwidth);
                    capGbps = bwKbps / 1000000;
                }
                if (capGbps > 0 && capGbps < bottleneckBwGbps) {
                    bottleneckBwGbps = capGbps;
                    bottleneckInterface = `${localInt || remoteInt || 'port'} (${u})`;
                }

                hopDetails.push({
                    from: u,
                    to: v,
                    edgeId: edgeId,
                    localInt: localInt || '',
                    remoteInt: remoteInt || '',
                    bandwidth: hopBwStr,
                    rtt: hopRtt,
                    loss: hopLoss
                });
            }

            if (bottleneckBwGbps === Infinity) bottleneckBwGbps = 10.0;

            return {
                path: pathNodes,
                hops: hops,
                cost: rawResult.cost,
                edgeIds: edgeIds,
                cumulativeRtt: hasPingData ? Number(cumulativeRtt.toFixed(2)) : null,
                worstLoss: worstLoss,
                bottleneckBwGbps: bottleneckBwGbps,
                bottleneckInterface: bottleneckInterface,
                bottleneckStr: `${bottleneckBwGbps} Gbps`,
                hopDetails: hopDetails
            };
        }

        calculateTopKPaths(startNode, endNode, k = 3) {
            if (!startNode || !endNode || startNode === endNode) return [];
            const graph = this.buildAdjacencyGraph();
            if (!graph.has(startNode) || !graph.has(endNode)) return [];

            const paths = [];
            const primary = this.calculateDijkstra(graph, startNode, endNode, new Set());
            if (!primary) return [];

            paths.push(this.enrichPath(primary, graph));

            const disabledEdges = new Set();
            for (let i = 1; i < k; i++) {
                const prevPath = paths[i - 1].path;
                if (prevPath.length < 3) break;

                const midIdx = Math.floor(prevPath.length / 2);
                const uMid = prevPath[midIdx - 1];
                const vMid = prevPath[midIdx];
                disabledEdges.add(`${uMid}|${vMid}`);
                disabledEdges.add(`${vMid}|${uMid}`);

                let altPath = this.calculateDijkstra(graph, startNode, endNode, disabledEdges);
                if (altPath && !paths.some(p => p.path.join('->') === altPath.path.join('->'))) {
                    paths.push(this.enrichPath(altPath, graph));
                } else {
                    let foundAlt = false;
                    for (let j = 1; j < prevPath.length; j++) {
                        const uJ = prevPath[j - 1];
                        const vJ = prevPath[j];
                        const k1 = `${uJ}|${vJ}`;
                        const k2 = `${vJ}|${uJ}`;
                        if (disabledEdges.has(k1)) continue;
                        disabledEdges.add(k1);
                        disabledEdges.add(k2);
                        const secondAlt = this.calculateDijkstra(graph, startNode, endNode, disabledEdges);
                        if (secondAlt && !paths.some(p => p.path.join('->') === secondAlt.path.join('->'))) {
                            paths.push(this.enrichPath(secondAlt, graph));
                            foundAlt = true;
                            break;
                        }
                    }
                    if (!foundAlt) break;
                }
            }

            paths.sort((a, b) => {
                if (a.hops !== b.hops) return a.hops - b.hops;
                const rttA = a.cumulativeRtt !== null ? a.cumulativeRtt : 999999;
                const rttB = b.cumulativeRtt !== null ? b.cumulativeRtt : 999999;
                return rttA - rttB;
            });

            this.activePaths = paths;
            this.pathTraceStartNode = startNode;
            this.pathTraceEndNode = endNode;
            return paths;
        }

        setActivePathIndex(idx) {
            if (!this.activePaths || this.activePaths.length === 0) return null;
            if (idx < 0 || idx >= this.activePaths.length) idx = 0;
            this.activePathIdx = idx;
            const selectedPath = this.activePaths[idx];
            this.setActivePath(selectedPath);
            return selectedPath;
        }

        setActivePath(pathObj) {
            if (!pathObj) {
                this.clearActivePath();
                return;
            }
            this.activePath = pathObj;
            this.activePathNodeIds = new Set(pathObj.path || []);
            this.activePathEdgeIds = new Set(pathObj.edgeIds || []);

            this.activePathPairKeys = new Set();
            for (let i = 0; i < (pathObj.path.length - 1); i++) {
                const u = pathObj.path[i];
                const v = pathObj.path[i + 1];
                this.activePathPairKeys.add(`${u}:::${v}`);
                this.activePathPairKeys.add(`${v}:::${u}`);
            }

            this.selectedNode = null;
            this.hoveredNode = null;
            this.connectedNodeIds.clear();
            this.connectedEdgeIds.clear();

            if (typeof this.onPathChanged === 'function') {
                this.onPathChanged(pathObj, this.activePathIdx);
            }
        }

        clearActivePath() {
            this.activePath = null;
            this.activePaths = [];
            this.activePathIdx = 0;
            this.activePathNodeIds.clear();
            this.activePathEdgeIds.clear();
            this.activePathPairKeys = new Set();
            this.pathTraceStartNode = null;
            this.pathTraceEndNode = null;
            if (typeof this.onPathCleared === 'function') {
                this.onPathCleared();
            }
        }

        getActivePath() {
            return this.activePath;
        }

        getActivePaths() {
            return this.activePaths;
        }
    }

    window.NetworkTopologyGraph = NetworkTopologyGraph;

})();
"""


class TopologyGraphEngine:
    """Manages creation and distribution of topology interactive graph script."""

    def __init__(self, outbase: str):
        self.outbase = os.path.abspath(outbase)
        self.topology_dir = os.path.join(self.outbase, "topology")

    def ensure_graph_js(self) -> str:
        """Writes topology_graph.js to the topology directory."""
        os.makedirs(self.topology_dir, exist_ok=True)
        target_path = os.path.join(self.topology_dir, "topology_graph.js")
        content = get_topology_graph_js()
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return target_path
