import csv
import json
import os
import urllib.request
from datetime import datetime, timedelta

def run():
    print("Iniciando geração de insights com Gemini API...")
    
    csv_file = "dados_dashboard.csv"
    if not os.path.exists(csv_file):
        print(f"Erro: Arquivo {csv_file} não encontrado.")
        return

    # 1. Carregar dados do CSV
    rows = []
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            for r in reader:
                rows.append(r)
    except Exception as e:
        print(f"Erro ao ler CSV: {e}")
        return

    try:
        idx_pdv = header.index("Ponto de Venda")
        idx_date = header.index("Data")
        idx_midia = header.index("Origem / mídia da sessão")
        idx_campanha = header.index("Campanha da sessão")
        idx_sess = header.index("Sessões")
        idx_trans = header.index("Transações")
        idx_rec = header.index("Receita")
        idx_canal = header.index("Origem Agrupada")
    except Exception as e:
        print(f"Erro ao encontrar cabeçalhos no CSV: {e}")
        return

    parsed_rows = []
    for r in rows:
        try:
            parsed_rows.append({
                "pdv": r[idx_pdv].strip(),
                "date": r[idx_date].strip(),
                "midia": r[idx_midia].strip(),
                "campanha": r[idx_campanha].strip(),
                "sess": int(r[idx_sess].replace(".", "").replace(",", "").strip() or 0),
                "trans": int(r[idx_trans].replace(".", "").replace(",", "").strip() or 0),
                "rec": float(r[idx_rec].replace(".", "").replace(",", ".").replace("R$", "").replace(" ", "").strip() or 0),
                "canal": r[idx_canal].strip()
            })
        except Exception as e:
            continue

    if not parsed_rows:
        print("Nenhuma linha de dados válida encontrada.")
        return

    # 2. Filtrar dados (últimos 30 dias com base na última data disponível)
    dates = sorted(list(set([r["date"] for r in parsed_rows])))
    if not dates:
        print("Nenhuma data encontrada.")
        return

    max_date_str = dates[-1]
    max_date = datetime.strptime(max_date_str, "%Y-%m-%d")
    min_date = max_date - timedelta(days=30)
    min_date_str = min_date.strftime("%Y-%m-%d")

    filtered_rows = [r for r in parsed_rows if r["date"] >= min_date_str]
    total_rec = sum(r["rec"] for r in filtered_rows)

    # Filtrar para CRM
    crm_rows = [r for r in filtered_rows if r["canal"].upper() == "CRM"]
    crm_rec = sum(r["rec"] for r in crm_rows)
    crm_share = (crm_rec / total_rec * 100) if total_rec > 0 else 0

    # Mídia campeã
    midia_rec = {}
    for r in crm_rows:
        midia_rec[r["midia"]] = midia_rec.get(r["midia"], 0) + r["rec"]

    if midia_rec:
        top_midia = max(midia_rec, key=midia_rec.get)
        top_midia_rec = midia_rec[top_midia]
        top_midia_pct = (top_midia_rec / crm_rec * 100) if crm_rec > 0 else 0
    else:
        top_midia = "Nenhuma"
        top_midia_rec = 0
        top_midia_pct = 0

    # Automático vs Manual
    def is_automated(r):
        txt = f"{r['campanha']} {r['midia']}".lower()
        return "architect" in txt or "architecht" in txt

    auto_rows = [r for r in crm_rows if is_automated(r)]
    manual_rows = [r for r in crm_rows if not is_automated(r)]

    auto_rec = sum(r["rec"] for r in auto_rows)
    auto_sess = sum(r["sess"] for r in auto_rows)
    auto_trans = sum(r["trans"] for r in auto_rows)
    auto_pct = (auto_rec / crm_rec * 100) if crm_rec > 0 else 0
    auto_conv = (auto_trans / auto_sess * 100) if auto_sess > 0 else 0

    manual_rec = sum(r["rec"] for r in manual_rows)
    manual_sess = sum(r["sess"] for r in manual_rows)
    manual_trans = sum(r["trans"] for r in manual_rows)
    manual_pct = (manual_rec / crm_rec * 100) if crm_rec > 0 else 0
    manual_conv = (manual_trans / manual_sess * 100) if manual_sess > 0 else 0

    # App vs Site no CRM
    app_rows = [r for r in crm_rows if r["pdv"] == "App"]
    site_rows = [r for r in crm_rows if r["pdv"] == "Site"]

    app_rec = sum(r["rec"] for r in app_rows)
    app_sess = sum(r["sess"] for r in app_rows)
    app_trans = sum(r["trans"] for r in app_rows)
    app_pct = (app_rec / crm_rec * 100) if crm_rec > 0 else 0
    app_conv = (app_trans / app_sess * 100) if app_sess > 0 else 0

    site_rec = sum(r["rec"] for r in site_rows)
    site_sess = sum(r["sess"] for r in site_rows)
    site_trans = sum(r["trans"] for r in site_rows)
    site_pct = (site_rec / crm_rec * 100) if crm_rec > 0 else 0
    site_conv = (site_trans / site_sess * 100) if site_sess > 0 else 0

    # Dia de pico
    date_rec = {}
    for r in crm_rows:
        date_rec[r["date"]] = date_rec.get(r["date"], 0) + r["rec"]

    if date_rec:
        best_day = max(date_rec, key=date_rec.get)
        best_day_rec = date_rec[best_day]
        best_day_fmt = "/".join(best_day.split("-")[::-1])
    else:
        best_day_fmt = "—"
        best_day_rec = 0

    data_ini_fmt = "/".join(min_date_str.split("-")[::-1])
    data_fim_fmt = "/".join(max_date_str.split("-")[::-1])

    # 3. Montar Prompt do Gemini
    prompt = f"""
Você é um Diretor Executivo de CRM, Growth Marketing e Negócios Sênior com mais de 15 anos de experiência no mercado de transporte/turismo e e-commerce de passagens de ônibus.
Sua missão é analisar os resultados de CRM consolidado do Grupo Guanabara (período de {data_ini_fmt} a {data_fim_fmt}) e produzir 5 "Highlights de CRM e Negócios" estratégicos para o dashboard.

Aqui estão os dados analíticos reais consolidados do período para a sua análise:
- Faturamento Total de CRM: R$ {crm_rec:,.2f}
- Faturamento Global da Empresa (Guanabara): R$ {total_rec:,.2f}
- Participação (Share) do CRM na receita da empresa: {crm_share:.2f}%
- Mídia Campeã do CRM: "{top_midia}" com receita de R$ {top_midia_rec:,.2f} (representando {top_midia_pct:.2f}% do faturamento CRM)
- Desempenho de Disparos Automáticos (Jornadas do Architect):
  * Receita: R$ {auto_rec:,.2f} ({auto_pct:.2f}% do CRM)
  * Sessões: {auto_sess:,}
  * Transações: {auto_trans:,}
  * Taxa de Conversão: {auto_conv:.2f}%
- Desempenho de Disparos Manuais (Campanhas em Lote):
  * Receita: R$ {manual_rec:,.2f} ({manual_pct:.2f}% do CRM)
  * Sessões: {manual_sess:,}
  * Transações: {manual_trans:,}
  * Taxa de Conversão: {manual_conv:.2f}%
- Penetração de Canais (Site vs App no CRM):
  * App CRM: Receita de R$ {app_rec:,.2f} ({app_pct:.2f}% do CRM), Conversão de {app_conv:.2f}%
  * Site CRM: Receita de R$ {site_rec:,.2f} ({site_pct:.2f}% do CRM), Conversão de {site_conv:.2f}%
- Pico de Vendas Concentrado: Dia {best_day_fmt} com faturamento de R$ {best_day_rec:,.2f}

Instruções editoriais e de estilo:
- Adote um tom de voz executivo, corporativo, estratégico e altamente experiente. Use jargões de CRM e negócios (LTV, CAC, RFM, Réguas de Relacionamento, conversão incremental, engajamento in-app, mobile first, elasticidade).
- Cada highlight deve ter uma tese técnica de negócios baseada nos números apresentados. O número deve abrir o card de forma impactante e a descrição deve explicar o significado técnico/estratégico por trás do número em até 3 linhas de texto fluido.
- Produza exatamente 5 cards HTML com a seguinte estrutura:

<div class="highlight-card" style="border-left: 3px solid [COR];">
  <div class="highlight-card-title">[EMOJI] [TÍTULO DO HIGH-LEVEL INSIGHT]</div>
  <div class="highlight-card-num" style="color: [COR];">[NÚMERO GRANDE IMPACTANTE]</div>
  <div class="highlight-card-desc">[ANÁLISE ESTRATÉGICA DO EXECUTIVO DE CRM COM ATÉ 3 LINHAS]</div>
</div>

Cores e emojis sugeridos para as bordas e títulos:
- Card 1: 📈 Retenção & LTV (cor: var(--accent)) -> Foco na receita total de CRM e penetração de mercado.
- Card 2: ⚡ Eficiência de Mídia (cor: var(--site)) -> Foco no canal campeão e concentração de vendas.
- Card 3: 🤖 Escala & Automação (cor: var(--crm)) -> Foco nas réguas automáticas vs disparos em massa.
- Card 4: 📱 UX & Mobile First (cor: var(--app)) -> Foco na preferência do App vs Site.
- Card 5: 📅 Elasticidade da Base (cor: var(--outros)) -> Foco no dia de pico e sazonalidade.

Substitua [COR] pelas variáveis CSS indicadas para cada card (ex: var(--accent), var(--site), etc.).
Retorne apenas os 5 blocos de HTML diretamente. Não inclua blocos de markdown como ```html ou qualquer outro texto explicativo.
"""

    # 4. Fazer chamada ao Gemini API
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY não configurado nas variáveis de ambiente. Pulando geração por IA.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers, 
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
        generated_html = res_data["candidates"][0]["content"]["parts"][0]["text"]
        
        if "```html" in generated_html:
            generated_html = generated_html.split("```html")[1].split("```")[0]
        elif "```" in generated_html:
            generated_html = generated_html.split("```")[1].split("```")[0]
            
        generated_html = generated_html.strip()
        
        output_html_file = "insights_crm.html"
        with open(output_html_file, "w", encoding="utf-8") as f:
            f.write(generated_html)
            
        print(f"Insights do Gemini gerados com sucesso e salvos em {output_html_file}!")
    except Exception as e:
        print(f"Erro ao chamar a API do Gemini: {e}")

if __name__ == "__main__":
    run()
