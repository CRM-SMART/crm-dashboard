import os
import csv
from datetime import datetime, timedelta
import json
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest
)

# Se rodar localmente, ele tenta usar o arquivo JSON. 
# No GitHub Actions, ele criará o JSON a partir de um Secret antes de rodar.
CREDENTIAL_PATH = "agente-guanabara-16ba36a165a7.json"
if os.path.exists(CREDENTIAL_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH

PROPERTY_IDS = {
    "Site": "256859064",
    "App": "326912205"
}

def format_date(ga_date):
    # GA4 date is YYYYMMDD
    return f"{ga_date[6:8]}/{ga_date[4:6]}/{ga_date[0:4]}"

def run():
    print("Iniciando extração do GA4...")
    try:
        client = BetaAnalyticsDataClient()
    except Exception as e:
        print("Erro ao inicializar o cliente do GA4. Verifique suas credenciais.")
        print(e)
        return

    # Coletamos desde o inicio de 2025 até 'today'
    start_date = "2025-01-01"
    end_date = "today"

    csv_rows = []
    # Cabeçalho esperado pelo Dashboard
    headers = [
        "Ponto de Venda", "Data", "Origem / mídia da sessão", 
        "Campanha da sessão", "Sessões", "Transações", "Receita",
        "Origem Agrupada"
    ]
    csv_rows.append(headers)

    for prop_name, prop_id in PROPERTY_IDS.items():
        print(f"Buscando dados em: {prop_name} ({prop_id})...")
        
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
                Metric(name="totalRevenue")
            ],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        )
        
        try:
            response = client.run_report(request)
            for row in response.rows:
                date_val = format_date(row.dimension_values[0].value)
                source_medium = row.dimension_values[1].value
                campaign = row.dimension_values[2].value
                
                sessions = int(row.metric_values[0].value)
                transactions = int(row.metric_values[1].value)
                revenue = float(row.metric_values[2].value)
                
                # Ignora linhas com zero em tudo pra manter o CSV leve
                if sessions == 0 and transactions == 0 and revenue == 0:
                    continue

                                               sm_lower = source_medium.lower()
                is_crm = (('insider' in sm_lower and 'insite' not in sm_lower) or 
                          'firebase' in sm_lower or 
                          'pushnews' in sm_lower)
                
                origem_agrupada = "CRM" if is_crm else "Outros Canais"

                csv_rows.append([
                    prop_name,
                    date_val,
                    source_medium,
                    campaign,
                    sessions,
                    transactions,
                    revenue,
                    origem_agrupada
                ])
                
            print(f"Sucesso: Extraídas {len(response.rows)} linhas de {prop_name}.")
            
        except Exception as e:
            print(f"Erro na extração de {prop_name}: {e}")

    # Salva o arquivo CSV
    output_file = "dados_dashboard.csv"
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(csv_rows)
        print(f"\nExtração concluída! Arquivo {output_file} gerado com sucesso.")
    except Exception as e:
        print(f"Erro ao salvar CSV: {e}")

if __name__ == "__main__":
    run()
