import os
import sys
import glob
import argparse
import subprocess

# ANSI Colors for terminal output
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_RESET = '\033[0m'

def main():
    parser = argparse.ArgumentParser(description="Synchronize and batch generate missing network topologies.")
    parser.add_argument("--outbase", required=True, help="Base output directory (e.g., ../d-network-data-extractor/infos/bb)")
    
    # Topology Generator paths
    parser.add_argument("--topology-generator-path", default="../network-topology-generator/network-topology-generator.py", help="Path to network-topology-generator.py")
    parser.add_argument("--topo-config", default="../network-topology-generator/config/config.json", help="Path to topology config.json")
    parser.add_argument("--topo-elements", default="../d-network-topology-generator/config/elements.csv", help="Path to topology elements.csv")
    parser.add_argument("--topo-locations", default="../d-network-topology-generator/config/locations.csv", help="Path to topology locations.csv")
    
    # Optional parameters
    parser.add_argument("--filter", "-f", default="in:RTAC;RTED;RTOC;RTIC;RTRR;RTPR", help="Filter parameter for the topology generator")
    parser.add_argument("--theme", "-t", default="cog", help="Theme parameter for the topology generator")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the execution without generating anything")

    args = parser.parse_args()

    outbase = os.path.abspath(args.outbase)
    
    # Validations
    if not os.path.isdir(outbase):
        print(f"{C_RED}[!] Error: outbase directory does not exist: {outbase}{C_RESET}")
        sys.exit(1)
        
    if not os.path.isfile(args.topology_generator_path):
        print(f"{C_RED}[!] Error: Generator script not found at {args.topology_generator_path}{C_RESET}")
        sys.exit(1)

    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}           NETWORK TOPOLOGY BATCH SYNCHRONIZER              {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"[*] Scanning outbase: {outbase}")
    if args.dry_run:
        print(f"[*] {C_YELLOW}Mode: DRY-RUN (Simulation only){C_RESET}")
        
    run_dirs = sorted(glob.glob(os.path.join(outbase, "20*_*")), reverse=True)
    
    if not run_dirs:
        print(f"{C_YELLOW}[!] No timestamped run directories found in outbase.{C_RESET}")
        return

    generated_count = 0
    skipped_count = 0
    missing_data_count = 0

    for run_dir in run_dirs:
        if not os.path.isdir(run_dir):
            continue
            
        ts_id = os.path.basename(run_dir)
        
        # Check source connections
        conn_dir = os.path.join(run_dir, "connections")
        sum_csv = os.path.join(conn_dir, "topology.connections.SUM.csv")
        base_csv = os.path.join(conn_dir, "topology.connections.csv")
        
        if not (os.path.isfile(sum_csv) and os.path.isfile(base_csv)):
            missing_data_count += 1
            continue
            
        # Check destination topology
        dest_topo_dir = os.path.join(outbase, "topology", ts_id)
        
        # We consider it generated if the directory exists and has files (e.g. index.html or diagrams)
        has_topology = False
        if os.path.isdir(dest_topo_dir) and len(os.listdir(dest_topo_dir)) > 0:
            has_topology = True
            
        if has_topology:
            skipped_count += 1
            print(f"  [+] {C_GREEN}Skip{C_RESET}: Topology already exists for {ts_id}")
        else:
            print(f"  [-] {C_YELLOW}Pending{C_RESET}: Topology missing for {ts_id}. Generating...")
            
            cmd = [
                sys.executable, args.topology_generator_path,
                "-t", args.theme,
                "-c", os.path.abspath(args.topo_config),
                "-e", os.path.abspath(args.topo_elements),
                "-s", os.path.abspath(args.topo_locations),
                "-w", dest_topo_dir,
            ]
            
            if args.filter:
                cmd.extend(["-f", args.filter])
                
            cmd.extend([sum_csv, base_csv])
            
            if args.dry_run:
                print(f"      {C_CYAN}CMD: {' '.join(cmd)}{C_RESET}")
            else:
                try:
                    rc = subprocess.run(cmd)
                    if rc.returncode == 0:
                        print(f"      {C_GREEN}└─> Success! Generated at: {dest_topo_dir}{C_RESET}")
                        generated_count += 1
                    else:
                        print(f"      {C_RED}└─> Failed with return code: {rc.returncode}{C_RESET}")
                except Exception as e:
                    print(f"      {C_RED}└─> Error executing command: {e}{C_RESET}")

    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"[*] Summary:")
    print(f"    - Processed Runs: {len(run_dirs)}")
    print(f"    - Already Synced: {C_GREEN}{skipped_count}{C_RESET}")
    print(f"    - Generated Now : {C_YELLOW}{generated_count}{C_RESET}")
    print(f"    - Missing Data  : {missing_data_count} (ignored)")
    print(f"{C_CYAN}============================================================{C_RESET}\n")

if __name__ == "__main__":
    main()
