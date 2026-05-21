import os

def generate_root_portal(outbase):
    # Ensure outbase exists
    abs_outbase = os.path.abspath(outbase)
    os.makedirs(abs_outbase, exist_ok=True)
    
    # Paths to check
    inv_path = os.path.join(abs_outbase, "inventory", "index.html")
    diff_path = os.path.join(abs_outbase, "diff", "index.html")
    ping_path = os.path.join(abs_outbase, "ping-matrix", "index.html")
    
    has_inv = os.path.isfile(inv_path)
    has_diff = os.path.isfile(diff_path)
    has_ping = os.path.isfile(ping_path)
    
    # Setup template variables
    inv_href = 'href="inventory/index.html"' if has_inv else ''
    inv_class = 'active' if has_inv else 'disabled'
    inv_status_class = 'avail' if has_inv else 'unavail'
    inv_status_text = '🟢 AVAILABLE' if has_inv else '🔴 UNAVAILABLE'
    inv_hint = '' if has_inv else '<span class="cmd-hint">Run with --inventory</span>'
    
    diff_href = 'href="diff/index.html"' if has_diff else ''
    diff_class = 'active' if has_diff else 'disabled'
    diff_status_class = 'avail' if has_diff else 'unavail'
    diff_status_text = '🟢 AVAILABLE' if has_diff else '🔴 UNAVAILABLE'
    diff_hint = '' if has_diff else '<span class="cmd-hint">Run with --diff</span>'
    
    ping_href = 'href="ping-matrix/index.html"' if has_ping else ''
    ping_class = 'active' if has_ping else 'disabled'
    ping_status_class = 'avail' if has_ping else 'unavail'
    ping_status_text = '🟢 AVAILABLE' if has_ping else '🔴 UNAVAILABLE'
    ping_hint = '' if has_ping else '<span class="cmd-hint">Run with --ping-matrix</span>'
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Network Data Extractor - Workspaces</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; font-family: 'Inter', sans-serif; background: #020617; color: #e2e8f0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .container {{ max-width: 1000px; width: 90%; margin: 40px auto; }}
        .header {{ text-align: center; margin-bottom: 50px; }}
        .header h1 {{ font-family: 'Outfit', sans-serif; font-size: 42px; font-weight: 800; margin: 0; background: linear-gradient(90deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .header p {{ font-size: 16px; color: #94a3b8; margin-top: 10px; font-weight: 500; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px; }}
        
        .card {{ 
            background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255,255,255,0.05); border-radius: 16px; padding: 30px; 
            text-decoration: none; color: inherit; display: flex; flex-direction: column; position: relative; overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .card::before {{ content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: transparent; transition: all 0.3s; }}
        
        .card.active {{ cursor: pointer; border-color: rgba(56,189,248,0.2); }}
        .card.active:hover {{ background: rgba(30, 41, 59, 0.8); transform: translateY(-5px); box-shadow: 0 15px 35px rgba(0,0,0,0.4); border-color: rgba(56,189,248,0.4); }}
        
        .card.active.inventory::before {{ background: #38bdf8; }}
        .card.active.diff::before {{ background: #f59e0b; }}
        .card.active.ping::before {{ background: #10b981; }}
        
        .card.disabled {{ opacity: 0.5; filter: grayscale(1); cursor: not-allowed; }}
        
        .icon {{ font-size: 36px; margin-bottom: 20px; display: block; }}
        .title {{ font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 700; color: #f8fafc; margin-bottom: 10px; }}
        .desc {{ font-size: 14px; color: #94a3b8; line-height: 1.6; flex-grow: 1; }}
        
        .status {{ margin-top: 25px; font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 6px; display: inline-block; width: max-content; }}
        .status.avail {{ background: rgba(16, 185, 129, 0.1); color: #10b981; border: 1px solid rgba(16,185,129,0.2); }}
        .status.unavail {{ background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.2); }}
        
        .cmd-hint {{ font-family: monospace; background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 4px; color: #fbbf24; margin-top: 10px; font-size: 11px; display: block; border: 1px solid rgba(255,255,255,0.05); }}
        
        .footer {{ margin-top: 60px; text-align: center; color: #64748b; font-size: 13px; font-weight: 500; }}
        .footer a {{ color: #38bdf8; text-decoration: none; transition: color 0.2s; }}
        .footer a:hover {{ color: #818cf8; text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌐 Network Workspaces</h1>
            <p>Master Navigation Portal for Data Extractor Analytics</p>
        </div>
        
        <div class="grid">
            <!-- INVENTORY -->
            <a {inv_href} class="card {inv_class} inventory">
                <span class="icon">📦</span>
                <div class="title">Global Inventory</div>
                <div class="desc">Accumulative dashboard containing the complete interface list, operational statuses, and physical topology spanning all execution dates.</div>
                <div class="status {inv_status_class}">{inv_status_text}</div>
                {inv_hint}
            </a>
            
            <!-- DIFF -->
            <a {diff_href} class="card {diff_class} diff">
                <span class="icon">⚖️</span>
                <div class="title">Drift Analysis</div>
                <div class="desc">Compare two snapshot collections to detect configuration drift, interface status changes, and new or removed connections.</div>
                <div class="status {diff_status_class}">{diff_status_text}</div>
                {diff_hint}
            </a>
            
            <!-- PING MATRIX -->
            <a {ping_href} class="card {ping_class} ping">
                <span class="icon">⚡</span>
                <div class="title">Ping Matrix</div>
                <div class="desc">Historical navigation portal for ICMP diagnostic runs. Visual heatmap analyzing latency, jitter, packet loss, and asymmetric routing.</div>
                <div class="status {ping_status_class}">{ping_status_text}</div>
                {ping_hint}
            </a>
        </div>
        
        <div class="footer">
            Check for updates and new versions on <a href="https://github.com/flashbsb/network-data-extractor" target="_blank">GitHub</a>
        </div>
    </div>
</body>
</html>
"""
    
    index_path = os.path.join(abs_outbase, "index.html")
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[*] Portal available at: {index_path}")
    except Exception as e:
        print(f"[!] Failed to write Root Navigation Portal: {{e}}")
