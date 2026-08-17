import boto3
import time
import os
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

# Configurações da AWS Athena
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-2")
DATABASE = os.getenv("ATHENA_DATABASE", "smartbus_brasil")
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
OUTPUT_FILE = "dados_athena.csv"

# Query SQL fornecida pelo usuário
SQL_QUERY = """
WITH perfis_d_pessoa_deduplicados AS (
    -- Prepara e de-duplica os dados cadastrais da D_Pessoa
    SELECT 
        id_pessoa,
        nome_pessoa,
        email,
        telefone,
        aceitacomunicacao,
        cadastro_origem,
        pdv_aquisicao,
        total_viagens AS total_viagens_historico,
        viagens_ultimos_30d,
        viagens_ultimos_90d,
        viagens_ultimos_180d,
        viagens_ultimos_365d,
        TRY_CAST(REGEXP_REPLACE(id_pessoa, '[^0-9]', '') AS BIGINT) AS clean_doc_num,
        ROW_NUMBER() OVER (
            PARTITION BY TRY_CAST(REGEXP_REPLACE(id_pessoa, '[^0-9]', '') AS BIGINT)
            ORDER BY 
                CASE WHEN aceitacomunicacao IN (0, 1) THEN 0 ELSE 1 END ASC,
                data_atualizacao DESC,
                total_viagens DESC
        ) AS rn
    FROM 
        D_Pessoa
    WHERE 
        id_pessoa <> 'SEMREGISTRO'
        AND (
            (id_pessoa_documento = 'CPF' AND LENGTH(REGEXP_REPLACE(id_pessoa, '[^0-9]', '')) = 11)
            OR 
            (id_pessoa_documento = 'IDCLIENTE' AND LENGTH(REGEXP_REPLACE(id_pessoa, '[^0-9]', '')) >= 5)
        )
)
SELECT 
    -- 1. DIMENSÕES TEMPORAIS (Para filtros Diários e Mês a Mês no Dashboard)
    CAST(b.datasaidatrecho AS DATE) AS data_viagem,
    DATE_FORMAT(CAST(b.datasaidatrecho AS DATE), '%Y-%m') AS ano_mes_viagem,
    EXTRACT(MONTH FROM b.datasaidatrecho) AS numero_mes_viagem,
    CASE EXTRACT(MONTH FROM b.datasaidatrecho)
        WHEN 1 THEN '01 - Janeiro'
        WHEN 2 THEN '02 - Fevereiro'
        WHEN 3 THEN '03 - Março'
        WHEN 4 THEN '04 - Abril'
        WHEN 5 THEN '05 - Maio'
        WHEN 6 THEN '06 - Junho'
        WHEN 7 THEN '07 - Julho'
        WHEN 8 THEN '08 - Agosto'
        WHEN 9 THEN '09 - Setembro'
        WHEN 10 THEN '10 - Outubro'
        WHEN 11 THEN '11 - Novembro'
        WHEN 12 THEN '12 - Dezembro'
    END AS mes_nome_viagem,
    EXTRACT(DAY FROM b.datasaidatrecho) AS dia_do_mes,
    CASE EXTRACT(DAY_OF_WEEK FROM b.datasaidatrecho)
        WHEN 1 THEN '1. Domingo'
        WHEN 2 THEN '2. Segunda-feira'
        WHEN 3 THEN '3. Terça-feira'
        WHEN 4 THEN '4. Quarta-feira'
        WHEN 5 THEN '5. Quinta-feira'
        WHEN 6 THEN '6. Sexta-feira'
        WHEN 7 THEN '7. Sábado'
    END AS dia_da_semana_viagem,
    
    -- Dados de Compra e Antecedência
    CAST(b.dataemissao AS DATE) AS data_compra,
    DATE_DIFF('day', CAST(b.dataemissao AS DATE), CAST(b.datasaidatrecho AS DATE)) AS antecedencia_dias,
    CASE 
        WHEN DATE_DIFF('day', CAST(b.dataemissao AS DATE), CAST(b.datasaidatrecho AS DATE)) = 0 THEN '1. No mesmo dia'
        WHEN DATE_DIFF('day', CAST(b.dataemissao AS DATE), CAST(b.datasaidatrecho AS DATE)) BETWEEN 1 AND 3 THEN '2. 1 a 3 dias'
        WHEN DATE_DIFF('day', CAST(b.dataemissao AS DATE), CAST(b.datasaidatrecho AS DATE)) BETWEEN 4 AND 7 THEN '3. 4 a 7 dias (1 semana)'
        WHEN DATE_DIFF('day', CAST(b.dataemissao AS DATE), CAST(b.datasaidatrecho AS DATE)) BETWEEN 8 AND 15 THEN '4. 8 a 15 dias (2 semanas)'
        ELSE '5. > 15 dias (Planejador)'
    END AS faixa_antecedencia_compra,

    -- 2. DADOS DO CLIENTE (D_PESSOA)
    COALESCE(p.id_pessoa, CONCAT('DOC_', CAST(COALESCE(
        TRY_CAST(REGEXP_REPLACE(CASE WHEN b.cpf LIKE '%.0' THEN SUBSTR(b.cpf, 1, LENGTH(b.cpf) - 2) ELSE b.cpf END, '[^0-9]', '') AS BIGINT),
        TRY_CAST(b.idpassageiro AS BIGINT)
    ) AS VARCHAR))) AS id_pessoa,
    COALESCE(p.nome_pessoa, b.passageiro, b.nomecliente) AS nome_cliente,
    COALESCE(p.email, b.emailpassageiro, b.emailcliente) AS email,
    COALESCE(p.telefone, b.telefonepassageiro, b.telefonecliente) AS telefone,
    CASE COALESCE(p.aceitacomunicacao, -1)
        WHEN 1 THEN 'Opt-in (Aceita)'
        WHEN 0 THEN 'Opt-out (Não aceita)'
        ELSE 'Não Informado'
    END AS status_optin,
    
    -- 3. VIAÇÃO E OPERAÇÃO
    COALESCE(emp.nome, 'Viação Não Identificada') AS viacao,
    CONCAT(loc_orig.cidade, ' (', loc_orig.uf, ') x ', loc_dest.cidade, ' (', loc_dest.uf, ')') AS rota_completa,
    loc_orig.cidade AS cidade_origem,
    loc_orig.uf AS uf_origem,
    CASE 
        WHEN loc_orig.uf IN ('MA', 'PI', 'CE', 'RN', 'PB', 'PE', 'AL', 'SE', 'BA') THEN 'Nordeste'
        WHEN loc_orig.uf IN ('SP', 'RJ', 'MG', 'ES') THEN 'Sudeste'
        WHEN loc_orig.uf IN ('MT', 'MS', 'GO', 'DF') THEN 'Centro-Oeste'
        WHEN loc_orig.uf IN ('PR', 'RS', 'SC') THEN 'Sul'
        WHEN loc_orig.uf IN ('AC', 'AM', 'AP', 'PA', 'RO', 'RR', 'TO') THEN 'Norte'
        ELSE 'Outros / Não Identificado'
    END AS regiao_origem,
    
    loc_dest.cidade AS cidade_destino,
    loc_dest.uf AS uf_destino,
    CASE 
        WHEN loc_dest.uf IN ('MA', 'PI', 'CE', 'RN', 'PB', 'PE', 'AL', 'SE', 'BA') THEN 'Nordeste'
        WHEN loc_dest.uf IN ('SP', 'RJ', 'MG', 'ES') THEN 'Sudeste'
        WHEN loc_dest.uf IN ('MT', 'MS', 'GO', 'DF') THEN 'Centro-Oeste'
        WHEN loc_dest.uf IN ('PR', 'RS', 'SC') THEN 'Sul'
        WHEN loc_dest.uf IN ('AC', 'AM', 'AP', 'PA', 'RO', 'RR', 'TO') THEN 'Norte'
        ELSE 'Outros / Não Identificado'
    END AS regiao_destino,
    
    CASE 
        WHEN loc_orig.uf IS NOT NULL AND loc_dest.uf IS NOT NULL AND loc_orig.uf <> loc_dest.uf THEN 'Interestadual'
        WHEN loc_orig.uf IS NOT NULL AND loc_dest.uf IS NOT NULL AND loc_orig.uf = loc_dest.uf THEN 'Estadual (Intermunicipal)'
        ELSE 'Não Identificado'
    END AS tipo_rota_interestadual_ou_estadual,

    -- 4. CANAL DE ORIGEM E VENDA
    COALESCE(b.nomesite, p.cadastro_origem, 'Não Informado') AS canal_venda,
    p.cadastro_origem AS canal_origem_cadastro,

    -- 5. MÉTRICAS FINANCEIRAS DO BILHETE
    b.idbilhete,
    b.localizador,
    COALESCE(b.total, b.valor, 0.0) AS valor_passagem,
    COALESCE(b.tarifaliquida, 0.0) AS tarifa_liquida,
    
    -- 6. MÉTRICAS DE RECÊNCIA E HISTÓRICO DO CLIENTE
    p.total_viagens_historico,
    p.viagens_ultimos_30d,
    p.viagens_ultimos_90d,
    p.viagens_ultimos_180d,
    p.viagens_ultimos_365d

FROM 
    smartbus_brasil.tblbilhete b
LEFT JOIN smartbus_brasil.tblempresa emp ON CAST(b.idempresa AS BIGINT) = emp.idempresa
LEFT JOIN smartbus_brasil.tbllocalidade loc_orig ON CAST(b.idorigem AS BIGINT) = loc_orig.idlocalidade
LEFT JOIN smartbus_brasil.tbllocalidade loc_dest ON CAST(b.iddestino AS BIGINT) = loc_dest.idlocalidade
LEFT JOIN perfis_d_pessoa_deduplicados p ON 
    COALESCE(
        TRY_CAST(REGEXP_REPLACE(CASE WHEN b.cpf LIKE '%.0' THEN SUBSTR(b.cpf, 1, LENGTH(b.cpf) - 2) ELSE b.cpf END, '[^0-9]', '') AS BIGINT),
        TRY_CAST(b.idpassageiro AS BIGINT)
    ) = p.clean_doc_num AND p.rn = 1
WHERE 
    b.cancelado = 0 
    AND b._cdc_deleted = 0
    AND b.dt_etl >= DATE '2026-01-01'
    AND CAST(b.datasaidatrecho AS DATE) BETWEEN DATE '2026-01-01' AND DATE '2026-12-31'
"""

def get_athena_client():
    return boto3.client('athena', region_name=REGION)

def download_s3_file(s3_uri):
    match = re.match(r"s3://([^/]+)/(.+)", s3_uri)
    if not match:
        raise ValueError(f"S3 URI inválido: {s3_uri}")
    bucket = match.group(1)
    key = match.group(2)
    
    print(f"[*] Fazendo o download do arquivo de resultados de s3://{bucket}/{key}...")
    s3_client = boto3.client('s3', region_name=REGION)
    s3_client.download_file(bucket, key, OUTPUT_FILE)
    print(f"[✔] Resultados baixados com sucesso e salvos em: {OUTPUT_FILE}!")

def execute_query():
    print("==================================================")
    print(f"        CONSULTA DE DADOS - AWS ATHENA (Ohio)    ")
    print("==================================================")
    print(f"Região: {REGION}")
    print(f"Banco de Dados: {DATABASE}")
    print(f"WorkGroup: {WORKGROUP}")
    
    client = get_athena_client()
    
    output_location = os.getenv("ATHENA_OUTPUT_LOCATION")
    if not output_location:
        print(f"[*] ATHENA_OUTPUT_LOCATION não configurado. Buscando configurações do WorkGroup '{WORKGROUP}'...")
        try:
            wg = client.get_work_group(WorkGroup=WORKGROUP)
            wg_config = wg.get('WorkGroup', {}).get('Configuration', {})
            output_location = wg_config.get('ResultConfiguration', {}).get('OutputLocation')
            if output_location:
                print(f"[+] OutputLocation recuperado do WorkGroup: {output_location}")
            else:
                print(f"[-] O WorkGroup '{WORKGROUP}' não tem um OutputLocation configurado. Por favor, forneça ATHENA_OUTPUT_LOCATION.")
        except Exception as e:
            print(f"[-] Erro ao recuperar configuração do WorkGroup: {e}")
            
    # Executar a Query
    query_params = {
        'QueryString': SQL_QUERY,
        'QueryExecutionContext': {
            'Database': DATABASE
        },
        'WorkGroup': WORKGROUP
    }
    if output_location:
        query_params['ResultConfiguration'] = {
            'OutputLocation': output_location
        }
        
    print("[*] Iniciando execução da Query no Athena...")
    try:
        response = client.start_query_execution(**query_params)
        execution_id = response['QueryExecutionId']
        print(f"[+] Query iniciada! QueryExecutionId: {execution_id}")
    except Exception as e:
        print(f"[-] Erro ao iniciar a Query: {e}")
        return
        
    # Aguardar a finalização da query
    start_time = time.time()
    while True:
        try:
            status = client.get_query_execution(QueryExecutionId=execution_id)
            state = status['QueryExecution']['Status']['State']
            elapsed = time.time() - start_time
            print(f"[*] Status: {state} ({elapsed:.1f}s decorridos)")
            
            if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                break
        except Exception as e:
            print(f"[-] Erro ao verificar status da query: {e}")
            
        time.sleep(5)
        
    if state == 'SUCCEEDED':
        s3_uri = status['QueryExecution']['ResultConfiguration']['OutputLocation']
        print(f"[+] Query executada com sucesso! Arquivo gerado em: {s3_uri}")
        try:
            download_s3_file(s3_uri)
        except Exception as e:
            print(f"[-] Erro ao fazer download do arquivo do S3: {e}")
    else:
        reason = status['QueryExecution']['Status'].get('StateChangeReason', 'Nenhuma razão informada.')
        print(f"[-] A query falhou ou foi cancelada. Status: {state}. Motivo: {reason}")

if __name__ == "__main__":
    execute_query()
