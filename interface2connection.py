import pandas as pd
import glob
import re
import os
import argparse

def get_style(bandwidth_kbit, admin_status, line_protocol):
    """
    Define o estilo visual baseado na velocidade e status.
    """
    try:
        bw = int(bandwidth_kbit)
    except:
        bw = 0
    
    # Lógica de Status (Up/Down)
    dashed = ''
    if str(line_protocol).lower() != 'up':
        dashed = 1
        
    # Lógica de Cores e Largura
    if bw == 1000000:
        return "1Gbps", 1, "#800080", dashed
    elif bw == 10000000:
        return "10Gbps", 2, "#0085DA", dashed
    elif bw == 100000000:
        return "100Gbps", 3, "#006400", dashed
    else:
        # Fallback para velocidades exóticas
        if bw >= 1000000:
            label = f"{int(bw/1000000)}Gbps"
        else:
            label = f"{int(bw/1000)}Mbps"
        return label, 4, "#800080", dashed

def parse_neighbor(description):
    """
    Tenta encontrar o vizinho (RT* ou PTT*) na descrição.
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
    Verifica se a interface é virtual para ser ignorada.
    Retorna True se deve ser ignorada.
    """
    if pd.isna(interface_name):
        return False
        
    name = str(interface_name).strip()
    
    # Lista de prefixos proibidos (Case Insensitive logic aplicada abaixo)
    # Adicionei Loopback e Tunnel por precaução, já que são virtuais clássicas.
    virtual_prefixes = ('Bundle', 'PW', 'NULL', 'Null', 'Loopback', 'Tunnel')
    
    if name.startswith(virtual_prefixes):
        return True
        
    return False

def process_file(filepath, output_dir):
    print(f"Processando arquivo: {filepath} ...")
    
    try:
        df = pd.read_csv(filepath, sep=';')
    except Exception as e:
        print(f"Erro ao ler {filepath}: {e}")
        return

    detailed_rows = []

    for _, row in df.iterrows():
        # --- NOVO FILTRO AQUI ---
        # Se for virtual, pula para o próximo
        if is_virtual(row['interface']):
            continue
            
        # Identifica vizinho
        neighbor = parse_neighbor(row['description'])
        
        if neighbor:
            # Identifica estilo
            label, width, color, dashed = get_style(row['bandwidth_kbit'], row['admin_status'], row['line_protocol'])
            
            detailed_rows.append({
                'ponta-a': row['elemento'],
                'ponta-b': neighbor,
                'textoconexao': label,
                'strokeWidth': width,
                'strokeColor': color,
                'dashed': dashed,
                'fontStyle': '',
                'fontSize': ''
            })

    if not detailed_rows:
        print(f"Nenhuma conexão física encontrada em {filepath}. (Verifique se as descrições não estão apenas nas interfaces Bundle!)")
        return

    # 1. Gerar Arquivo Detalhado (*.conexoes.csv)
    df_detailed = pd.DataFrame(detailed_rows)
    cols = ['ponta-a', 'ponta-b', 'textoconexao', 'strokeWidth', 'strokeColor', 'dashed', 'fontStyle', 'fontSize']
    df_detailed = df_detailed[cols]
    
    filename = os.path.basename(filepath)
    output_detailed = os.path.join(output_dir, filename.replace('.interfaces_all.csv', '.conexoes.csv'))
    df_detailed.to_csv(output_detailed, sep=';', index=False)
    print(f" -> Gerado: {output_detailed} ({len(df_detailed)} linhas)")

    # 2. Gerar Arquivo Sumarizado (*.conexoes.SUM.csv)
    group_cols = ['ponta-a', 'ponta-b', 'textoconexao', 'strokeWidth', 'strokeColor', 'dashed']
    df_sum = df_detailed.groupby(group_cols).size().reset_index(name='count')
    df_sum['textoconexao'] = df_sum.apply(lambda x: f"{x['count']}X {x['textoconexao']}", axis=1)
    df_sum['fontStyle'] = ''
    df_sum['fontSize'] = ''
    df_sum = df_sum[cols]
    
    output_sum = os.path.join(output_dir, filename.replace('.interfaces_all.csv', '.conexoes.SUM.csv'))
    df_sum.to_csv(output_sum, sep=';', index=False)
    print(f" -> Gerado: {output_sum} ({len(df_sum)} linhas)")

def main():
    parser = argparse.ArgumentParser(description="Gera conexões a partir de arquivos CSV de interfaces.")
    parser.add_argument("--input", default=".", help="Diretório de entrada contendo os CSVs.")
    parser.add_argument("--output", default=".", help="Diretório de saída para os CSVs gerados.")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    
    files = glob.glob(os.path.join(args.input, '*.interfaces_all.csv'))
    
    if not files:
        print(f"Nenhum arquivo *.interfaces_all.csv encontrado em {args.input}.")
        return

    for f in files:
        process_file(f, args.output)
        
    print("\nConcluído. Interfaces virtuais foram devidamente ignoradas.")

if __name__ == "__main__":
    main()
