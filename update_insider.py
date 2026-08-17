import os
import json
import csv
import ssl
import urllib.request
import urllib.parse
from datetime import datetime

CONFIG_FILE = "insider_config.json"
OUTPUT_FILE = "dados_insider.csv"

def get_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Arquivo {CONFIG_FILE} nao encontrado.")
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def run():
    print("Iniciando extracao de estatisticas da Insider (Sem filtros)...")
    try:
        config = get_config()
    except Exception as e:
        print(f"[-] Erro ao carregar configuracoes: {e}")
        return
        
    api_key = config.get("app_push_key")
    if not api_key:
        print("[-] Erro: app_push_key nao encontrada no arquivo de configuracoes.")
        return
        
    url = "https://mobile.useinsider.com/api/v1/notification/get_statistics"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "api_key": api_key
    }
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    try:
        print("[*] Chamando API da Insider...")
        with urllib.request.urlopen(req, context=ctx) as response:
            res_data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[-] Erro de conexao com a API da Insider: {e}")
        return
        
    campaigns = res_data.get("campaigns")
    if not campaigns:
        print("[!] Nenhuma campanha encontrada no retorno da Insider para hoje.")
        campaigns = []
        
    # Carregar dados existentes
    existing_data = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_data[row["Campanha"]] = {
                        "Data": row["Data"],
                        "Envios": int(row["Envios"] or 0),
                        "Entregas": int(row["Entregas"] or 0),
                        "Cliques": int(row["Cliques"] or 0)
                    }
        except Exception as e:
            print(f"[-] Erro ao ler {OUTPUT_FILE}: {e}")
            
    hoje_str = datetime.now().strftime('%Y-%m-%d')
    updates_count = 0
    new_count = 0
    
    for camp in campaigns:
        name = camp.get("name")
        if not name:
            continue
            
        envios = int(camp.get("delivery_count", 0))
        entregas = int(camp.get("delivery_count", 0))
        cliques = int(camp.get("session_count", 0))
        
        # LOGAR TODOS OS DISPAROS RETORNADOS PELA API SEM FILTRO DE NOME
        if name in existing_data:
            existing_data[name]["Envios"] = max(existing_data[name]["Envios"], envios)
            existing_data[name]["Entregas"] = max(existing_data[name]["Entregas"], entregas)
            existing_data[name]["Cliques"] = max(existing_data[name]["Cliques"], cliques)
            updates_count += 1
        else:
            existing_data[name] = {
                "Data": hoje_str,
                "Envios": envios,
                "Entregas": entregas,
                "Cliques": cliques
            }
            new_count += 1
            
    # Salvar de volta no CSV
    try:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Data", "Campanha", "Envios", "Entregas", "Cliques"])
            for name, metrics in sorted(existing_data.items(), key=lambda x: x[1]["Data"], reverse=True):
                writer.writerow([
                    metrics["Data"],
                    name,
                    metrics["Envios"],
                    metrics["Entregas"],
                    metrics["Cliques"]
                ])
        print(f"[+] Salvo! {new_count} novas, {updates_count} atualizadas. Total no CSV: {len(existing_data)}")
    except Exception as e:
        print(f"[-] Erro ao salvar {OUTPUT_FILE}: {e}")

if __name__ == "__main__":
    run()
