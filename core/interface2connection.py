import pandas as pd
import glob
import re
import os
import argparse

def get_style(bandwidth_kbit, admin_status, line_protocol):
    """
    Defines visual style based on speed and status.
    """
    try:
        bw = int(bandwidth_kbit)
    except:
        bw = 0
    
    # Status Logic (Up/Down)
    dashed = ''
    if str(line_protocol).lower() != 'up':
        dashed = 1
        
    # Color and Width Logic
    if bw == 1000000:
        return "1Gbps", 1, "#800080", dashed
    elif bw == 10000000:
        return "10Gbps", 2, "#0085DA", dashed
    elif bw == 100000000:
        return "100Gbps", 3, "#006400", dashed
    else:
        # Fallback for exotic speeds
        if bw >= 1000000:
            label = f"{int(bw/1000000)}Gbps"
        else:
            label = f"{int(bw/1000)}Mbps"
        return label, 4, "#800080", dashed

def parse_neighbor(description):
    """
    Tries to find the neighbor (RT* or PTT*) in the description.
    """
    if pd.isna(description):
        return None
    
    match = re.search(r'(?:CONEXAO_COM_|PEERING_|TRUNK_)([A-Za-z0-9-]+(?:-[A-Za-z0-9]+)*)', description)
    
    if match:
        neighbor = match.group(1)
        neighbor = re.sub(r'_(?:IPV4|IPV6|ipv4|ipv6)$', '', neighbor)
        
        if neighbor.startswith('RT') or neighbor.startswith('PTT')  or neighbor.startswith('SW') or neighbor.startswith('SM'):
            return neighbor
            
    return None

def is_virtual(interface_name):
    """
    Checks if the interface is virtual to be ignored.
    Returns True if it should be ignored.
    """
    if pd.isna(interface_name):
        return False
        
    name = str(interface_name).strip()
    
    # List of forbidden prefixes (Case Insensitive logic applied below)
    # Added Loopback and Tunnel as a precaution, since they are classic virtuals.
    virtual_prefixes = ('Bundle', 'PW', 'NULL', 'Null', 'Loopback', 'Tunnel')
    
    if name.startswith(virtual_prefixes):
        return True
        
    return False

def process_file(filepath, output_dir):
    print(f"Processing file: {filepath} ...")
    
    try:
        df = pd.read_csv(filepath, sep=';')
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return 0, 0

    detailed_rows = []
    ignored_virtual = 0

    for _, row in df.iterrows():
        # --- NEW FILTER HERE ---
        # If it's virtual, skip to the next
        if is_virtual(row['interface']):
            ignored_virtual += 1
            continue
            
        # Identify neighbor
        neighbor = parse_neighbor(row['description'])
        
        if neighbor:
            # Identify style
            label, width, color, dashed = get_style(row['bandwidth_kbit'], row['admin_status'], row['line_protocol'])
            
            detailed_rows.append({
                'endpoint_a': row['element'],
                'endpoint_b': neighbor,
                'connection_text': label,
                'strokeWidth': width,
                'strokeColor': color,
                'dashed': dashed,
                'fontStyle': '',
                'fontSize': ''
            })

    if not detailed_rows:
        print(f"No physical connections found in {filepath}. Ignored Virtual interfaces: {ignored_virtual}")
        return 0, ignored_virtual

    # 1. Generate Detailed File (*.connections.csv)
    df_detailed = pd.DataFrame(detailed_rows)
    cols = ['endpoint_a', 'endpoint_b', 'connection_text', 'strokeWidth', 'strokeColor', 'dashed', 'fontStyle', 'fontSize']
    df_detailed = df_detailed[cols]
    
    filename = os.path.basename(filepath)
    output_detailed = os.path.join(output_dir, filename.replace('interfaces_all.csv', 'connections.csv'))
    df_detailed.to_csv(output_detailed, sep=';', index=False)
    print(f" -> Generated: {output_detailed} ({len(df_detailed)} rows)")

    # 2. Generate Summarized File (*.connections.SUM.csv)
    group_cols = ['endpoint_a', 'endpoint_b', 'connection_text', 'strokeWidth', 'strokeColor', 'dashed']
    df_sum = df_detailed.groupby(group_cols).size().reset_index(name='count')
    df_sum['connection_text'] = df_sum.apply(lambda x: f"{x['count']}X {x['connection_text']}", axis=1)
    df_sum['fontStyle'] = ''
    df_sum['fontSize'] = ''
    df_sum = df_sum[cols]
    
    output_sum = os.path.join(output_dir, filename.replace('interfaces_all.csv', 'connections.SUM.csv'))
    df_sum.to_csv(output_sum, sep=';', index=False)
    print(f" -> Generated: {output_sum} ({len(df_sum)} rows)")
    return len(df_detailed), ignored_virtual

def main():
    parser = argparse.ArgumentParser(description="Generates connections from interface CSV files.")
    parser.add_argument("--input", default=".", help="Input directory containing CSVs.")
    parser.add_argument("--output", default=".", help="Output directory for generated CSVs.")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    
    files = glob.glob(os.path.join(args.input, '*interfaces_all.csv'))
    
    if not files:
        print(f"No *.interfaces_all.csv file found in {args.input}.")
        return

    total_connections = 0
    total_virtuals = 0
    for f in files:
        conns_ok, conns_ignored = process_file(f, args.output)
        total_connections += conns_ok
        total_virtuals += conns_ignored
        
    print(f"\n--- Final Connection Summary ---")
    print(f"Completed Successfully.")
    print(f"Total resolved connections: {total_connections}")
    print(f"Total ignored virtual interfaces: {total_virtuals}")

if __name__ == "__main__":
    main()
