import pandas as pd
import glob
import re
import os
import argparse
import json

# Default prefixes if settings fail to load
IGNORE_VIRTUAL_PREFIXES = ("Bundle", "PW", "NULL", "Null", "Loopback", "Tunnel")
NEIGHBOR_PREFIXES = ["CONEXAO_COM_", "PEERING_", "TRUNK_"]
DEVICE_NAME_PREFIXES = ["RT", "SW", "SM", "PTT", "DW"]
SPEED_COLORS = {
    "1000000": {"width": 1, "color": "#800080"},
    "10000000": {"width": 2, "color": "#0085DA"},
    "100000000": {"width": 3, "color": "#006400"},
    "default": {"width": 4, "color": "#800080"}
}

def load_settings(custom_path=None):
    global IGNORE_VIRTUAL_PREFIXES, NEIGHBOR_PREFIXES, DEVICE_NAME_PREFIXES, SPEED_COLORS
    config_path = custom_path if custom_path else "config/settings.json"
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                json_config = json.load(f)
                topology_cfg = json_config.get("topology", {})
                IGNORE_VIRTUAL_PREFIXES = tuple(topology_cfg.get("ignore_virtual_prefixes", IGNORE_VIRTUAL_PREFIXES))
                NEIGHBOR_PREFIXES = topology_cfg.get("neighbor_regex_prefixes", NEIGHBOR_PREFIXES)
                DEVICE_NAME_PREFIXES = topology_cfg.get("device_name_prefixes", DEVICE_NAME_PREFIXES)
                SPEED_COLORS = topology_cfg.get("speed_colors", SPEED_COLORS)
        except:
            pass

def parse_neighbor(description):
    """
    Smart Analyzer: Hunts anywhere in the description string for a known device 
    naming convention (e.g. SWAC-ARPO2-01) based on settings.json prefixes.
    """
    if pd.isna(description):
        return None
        
    # Build regex like: ((?:RT|SW|SM|PTT|DW)[A-Za-z0-9]+-[A-Za-z0-9-]+)
    dev_group = "|".join(DEVICE_NAME_PREFIXES)
    pattern = rf'((?:{dev_group})[A-Za-z0-9]+-[A-Za-z0-9-]+)'
    
    match = re.search(pattern, str(description), re.IGNORECASE)
    if match:
        neighbor = match.group(1).upper()
        # Clean up suffix artifacts just in case
        neighbor = re.sub(r'_(?:IPV4|IPV6)$', '', neighbor)
        return neighbor
        
    return None

def is_virtual(interface_name):
    """
    Checks if the interface is virtual to be ignored.
    """
    if pd.isna(interface_name):
        return False
    name = str(interface_name).strip()
    return name.startswith(IGNORE_VIRTUAL_PREFIXES)

def extract_capacity(bandwidth_kbit, interface_name=""):
    """
    Returns (label, speed_in_kbit) for sorting and display.
    """
    try:
        if bandwidth_kbit == 'Unknown' or not bandwidth_kbit:
            bw = 0
        else:
            bw = int(bandwidth_kbit)
    except:
        bw = 0
        
    # Fallback to interface name inference if BW is 0 or missing
    if bw == 0 and interface_name:
        if_name = interface_name.lower()
        if '100g' in if_name or 'hundredgig' in if_name:
            bw = 100000000
        elif '40g' in if_name or 'fortygig' in if_name:
            bw = 40000000
        elif '25g' in if_name or 'twentyfivegig' in if_name:
            bw = 25000000
        elif '10g' in if_name or 'tengig' in if_name or 'xge' in if_name:
            bw = 10000000
        elif 'giga' in if_name or 'gigabit' in if_name or 'ge' in if_name or 'eth' in if_name:
            bw = 1000000
            
    if bw == 1000000:
        return "1G", bw
    elif bw == 10000000:
        return "10G", bw
    elif bw == 100000000:
        return "100G", bw
    elif bw >= 1000000:
        return f"{int(bw/1000000)}G", bw
    else:
        return f"{int(bw/1000)}M", bw

def get_style(bw_kbit):
    """
    Returns edge width and color based on bandwidth.
    """
    try:
        bw = str(int(bw_kbit))
    except (ValueError, TypeError):
        bw = "0"
        
    style = SPEED_COLORS.get(bw, SPEED_COLORS.get("default", {"width": 4, "color": "#800080"}))
    return style.get("width", 4), style.get("color", "#800080")

def main():
    parser = argparse.ArgumentParser(description="Generates connections from interface CSV files.")
    parser.add_argument("--input", default=".", help="Input directory containing CSVs.")
    parser.add_argument("--output", default=".", help="Output directory for generated CSVs.")
    parser.add_argument("--settings", help="Path to settings.json")
    args = parser.parse_args()

    load_settings(args.settings)

    os.makedirs(args.output, exist_ok=True)
    files = glob.glob(os.path.join(args.input, '*interfaces_all.csv'))
    
    if not files:
        print(f"No *.interfaces_all.csv file found in {args.input}.")
        return

    print("Loading interface data...")
    df_list = []
    for f in files:
        try:
            df = pd.read_csv(f, sep=';', dtype=str)
            df_list.append(df)
        except Exception as e:
            print(f"Error reading {f}: {e}")
            
    if not df_list:
        return

    # Phase 1: Ingest All Files into a Master DataFrame
    master_df = pd.concat(df_list, ignore_index=True)
    
    connections = {} # (node_A, node_B) -> list of links
    ignored_virtual = 0

    print("Cross-referencing logic...")
    # Phase 2: Process valid physical links
    for _, row in master_df.iterrows():
        if is_virtual(row.get('interface', '')):
            ignored_virtual += 1
            continue
            
        src_element = str(row.get('element', '')).strip()
        description = row.get('description', '')
        
        neighbor = parse_neighbor(description)
        if not neighbor or not src_element:
            continue
            
        # Standardize Nodes Alphabetically to avoid A->B / B->A duplication
        node_a, node_b = sorted([src_element, neighbor])
        pair_key = (node_a, node_b)
        
        bw_kbit = row.get('bandwidth_kbit', '0')
        admin = str(row.get('admin_status', '')).lower()
        protocol = str(row.get('line_protocol', '')).lower()
        dashed = 1 if protocol != 'up' else ''
        
        label, bw_val = extract_capacity(bw_kbit, row.get('interface', ''))
        
        if pair_key not in connections:
            connections[pair_key] = []
            
        connections[pair_key].append({
            'source_port': str(row.get('interface', '')),
            'label': label,
            'bw_val': bw_val,
            'dashed': dashed,
            'admin': admin,
            'protocol': protocol
        })

    # Phase 3: Deduplication and Normalization
    detailed_rows = []
    summarized_rows = []
    
    for (node_a, node_b), links in connections.items():
        # A single physical cable might have been declared twice (once by node A, once by node B)
        # We assume that a cable of the same speed existing in both directions is just one physical link
        # Strategy: Differentiate by speed, and take the maximum symmetric count.
        
        # Count connections declared by side
        speed_counts = {}
        for link in links:
            spd = link['bw_val']
            speed_counts[spd] = speed_counts.get(spd, 0) + 1
            
        deduplicated_links = []
        # Since each side can report the link, a link reported by both is 2 entries.
        # Real physical links = CEIL(reported_entries / 2)
        for spd, count in speed_counts.items():
            real_count = (count // 2) + (count % 2)
            
            # Find a representative link object to extract styles
            rep_link = next(l for l in links if l['bw_val'] == spd)
            width, color = get_style(spd)
            
            # Create detailed rows (one for each physical cable)
            for _ in range(real_count):
                detailed_rows.append({
                    'endpoint_a': node_a,
                    'endpoint_b': node_b,
                    'connection_text': rep_link['label'],
                    'strokeWidth': width,
                    'strokeColor': color,
                    'dashed': rep_link['dashed'],
                    'fontStyle': '',
                    'fontSize': ''
                })
                
            # Summarize formatting: "2x 10G"
            deduplicated_links.append(f"{real_count}x {rep_link['label']}")

        # Create one summarized row per node pair
        if deduplicated_links:
            # e.g., "Max Width" logic for the summarized edge
            max_spd_link = max(links, key=lambda x: x['bw_val'])
            width, color = get_style(max_spd_link['bw_val'])
            
            # The line should be dashed ONLY if EVERY single link is down (dashed == 1)
            all_down = all(link.get('dashed') == 1 for link in links)
            agg_dashed = 1 if all_down else ''
            
            summarized_rows.append({
                'endpoint_a': node_a,
                'endpoint_b': node_b,
                'connection_text': " + ".join(deduplicated_links),
                'strokeWidth': width,
                'strokeColor': color,
                'dashed': agg_dashed,
                'fontStyle': '',
                'fontSize': ''
            })

    # Output detailed CSV
    df_detailed = pd.DataFrame(detailed_rows)
    cols = ['endpoint_a', 'endpoint_b', 'connection_text', 'strokeWidth', 'strokeColor', 'dashed', 'fontStyle', 'fontSize']
    output_detailed = os.path.join(args.output, 'topology.connections.csv')
    if not df_detailed.empty:
        df_detailed = df_detailed[cols]
        df_detailed.to_csv(output_detailed, sep=';', index=False)
        print(f" -> Generated: {output_detailed} ({len(df_detailed)} specific links)")

    # Output summarized CSV
    df_sum = pd.DataFrame(summarized_rows)
    output_sum = os.path.join(args.output, 'topology.connections.SUM.csv')
    if not df_sum.empty:
        df_sum = df_sum[cols]
        df_sum.to_csv(output_sum, sep=';', index=False)
        print(f" -> Generated: {output_sum} ({len(df_sum)} unified edge summaries)")

    print(f"\n--- Final Connection Summary ---")
    print(f"Completed Successfully.")
    print(f"Total resolved physical links: {len(df_detailed)}")
    print(f"Total summarized edge pairs: {len(df_sum)}")
    print(f"Total ignored virtual interfaces: {ignored_virtual}")

if __name__ == "__main__":
    main()
