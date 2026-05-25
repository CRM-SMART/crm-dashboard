import os
import csv
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest
)

CREDENTIAL_PATH = "agente-guanabara-16ba36a165a7.json"
if os.path.exists(CREDENTIAL_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH

PROPERTY_IDS = {
    "Site": "326912205",
    "App": "256859064"
}

def is_valid_row(row):
    try:
        rev = float(row.metric_values[2].value)
        sess = int(row.metric_values[0].value)
        return rev > 0 or sess > 0
    except:
        return False

def run():
    print("Iniciando extração do GA4...")
    try:
        client = BetaAnalyticsDataClient()
    except Exception as e:
        print("Erro ao inicializar o cliente do GA4. Verifique suas credenciais.")
        print(e)
        return
        
    headers = [
        "Ponto de Venda", "Data", "Origem / mídia da sessão", 
        "Campanha da sessão", "Sessões", "Transações", "Receita",
        "Origem Agrupada"
    ]
    csv_rows = []

    for prop_name, prop_id in PROPERTY_IDS.items():
        print(f"Buscando dados em: {prop_name} ({prop_id})...")
        
        offset = 0
        limit_per_page = 100000
        
        while True:
            request = RunReportRequest(
                property=f"properties/{prop_id}",
                dimensions=[
                    Dimension(name="date"),
                    Dimension(name="sessionSourceMedium"),
                    Dimension(name="sessionCampaignName")
                ],
                metrics=[
                    Metric(name="sessions"),
                    Metric(name="transactions"),
                    Metric(name="purchaseRevenue")
                ],
                date_ranges=[DateRange(start_date="2025-01-01", end_date="today")],
                limit=limit_per_page,
                offset=offset
            )
            
            try:
                response = client.run_report(request)
                num_rows = len(response.rows)
                print(f"[{prop_name}] Bloco extraído (offset {offset}): {num_rows} linhas")
                
                for row in response.rows:
                    if not is_valid_row(row):
                        continue

                    raw_date = row.dimension_values[0].value
                    date_val = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                    
                    source_medium = row.dimension_values[1].value
                    campaign = row.dimension_values[2].value
                    sessions = row.metric_values[0].value
                    transactions = row.metric_values[1].value
                    revenue = row.metric_values[2].value
                    
                    if source_medium in ["(not set)", "", None]:
                        source_medium = "(not set)"
                    if campaign in ["(not set)", "", None]:
                        campaign = "(not set)"

                    sm_lower = source_medium.lower()
                    
                    # Definir Origem Agrupada (Tipo de Canal)
                    origem_agrupada = "Others"
                    
                    if sm_lower in ["(not set)", "", "none"]:
                        origem_agrupada = "Not Set"
                    elif "(direct) / (none)" in sm_lower:
                        origem_agrupada = "Direct"
                    elif "insider" in sm_lower and "insite" in sm_lower:
                        origem_agrupada = "Organic"
                    elif "insider" in sm_lower or "architect" in sm_lower or "email" in sm_lower or "notification" in sm_lower or "web_push" in sm_lower or "pushnews" in sm_lower or "mobile_messaging" in sm_lower or "sms" in sm_lower or "firebase" in sm_lower:
                        origem_agrupada = "CRM"
                    elif "insite" in sm_lower or "emkt" in sm_lower or "whatsapp" in sm_lower:
                        origem_agrupada = "Others"
                    elif "cpc" in sm_lower or "display" in sm_lower or "paid" in sm_lower:
                        origem_agrupada = "Paid"
                    elif "organic" in sm_lower:
                        origem_agrupada = "Organic"
                    elif "referral" in sm_lower:
                        origem_agrupada = "Referral"
                    elif "blog" in sm_lower:
                        origem_agrupada = "Blog"

                    # O nome da mídia (source_medium) será mantido o original do GA4, 
                    # para que você possa ver exatamente quais canais formaram o grupo CRM.

                    csv_rows.append([
                        prop_name, date_val, source_medium, campaign,
                        sessions, transactions, revenue, origem_agrupada
                    ])
                    
                if num_rows < limit_per_page:
                    break
                    
                offset += limit_per_page
                    
            except Exception as e:
                print(f"Erro na propriedade {prop_name}: {e}")
                break

    output_file = "dados_dashboard.csv"
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(csv_rows)
        print(f"Processo concluído! Arquivo {output_file} gerado com sucesso.")
    except Exception as e:
        print(f"Erro ao salvar CSV: {e}")

if __name__ == "__main__":
    run()
