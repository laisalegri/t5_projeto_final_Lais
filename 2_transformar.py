"""
2_transformar.py  |  Fase 2: transformação (Raw -> Silver)

O que este script faz:
  1. Lê cada tabela Raw (tudo texto) em blocos, com pd.read_sql.
  2. Converte os campos com funções específicas:
       texto_para_decimal:  "1272,97"    -> 1272.97
       texto_para_data:     "17/09/2024" -> data 2024-09-17
     Campo vazio vira NaN/NaT no Pandas e é gravado como NULL no banco.
  3. Calcula duas colunas novas em silver_viagem:
       valor_total  = diárias + passagens + outros gastos - devolução
       duracao_dias = (data_fim - data_inicio) + 1   (conta o dia de início e o de fim)
  4. Grava nas tabelas Silver. A silver_viagem (mãe) é carregada PRIMEIRO, porque
     as outras três têm FOREIGN KEY apontando para ela.

Pode ser executado várias vezes: as tabelas Silver são esvaziadas antes da carga.
Tudo é confirmado de uma vez só (commit no fim); se algo falhar, o rollback()
desfaz tudo e as tabelas Silver ficam como estavam.

Como executar:  python 2_transformar.py   (depois do 1_extrair.py)
"""

import warnings

import pandas as pd
from psycopg2.extras import execute_values

from banco import conectar
from config import TAMANHO_BLOCO

# Ignora o aviso do Pandas sobre o uso do psycopg2
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")


# ---------------------------------------------------------------------------
# Funções de conversão
# ---------------------------------------------------------------------------

def limpar_texto(coluna):
    """Tira os espaços das pontas. Texto vazio vira NaN (NULL no banco)."""

    # Remove espaços antes e depois do texto
    coluna = coluna.str.strip()

    # Transforma textos vazios em valores ausentes
    return coluna.where(coluna != "")


def texto_para_decimal(coluna):
    """'1272,97' -> 1272.97. No CSV o decimal é a vírgula. Texto vazio vira NaN."""

    # Troca a vírgula pelo ponto para converter em número
    coluna = coluna.str.strip().str.replace(",", ".")

    return pd.to_numeric(
        coluna,
        errors="coerce"  # O que não virar número será NaN
    )


def texto_para_data(coluna):
    """'17/09/2024' -> data. O formato indica dia/mês/ano."""

    # Converte o texto para data
    return pd.to_datetime(
        coluna.str.strip(),
        format="%d/%m/%Y",
        errors="coerce"  # Datas inválidas viram NaT
    )


# ---------------------------------------------------------------------------
# Configuração das tabelas
# ---------------------------------------------------------------------------

# Define de qual tabela vêm os dados, para qual vão e quais colunas tratar
# A tabela de viagem vem primeiro porque é a tabela mãe das outras
TABELAS = [
    {
        # Tabela de origem (Raw)
        "raw": "raw_viagem",

        # Tabela de destino (Silver)
        "silver": "silver_viagem",

        # Colunas que serão tratadas como texto
        "textos": ["id_viagem", "num_proposta", "situacao", "viagem_urgente", "cod_orgao_superior",
                   "nome_orgao_superior", "nome_viajante", "cargo", "destinos", "motivo"],

        # Colunas que serão convertidas para decimal
        "valores": ["valor_diarias", "valor_passagens", "valor_devolucao", "valor_outros_gastos"],

        # Colunas que serão convertidas para data
        "datas": ["data_inicio", "data_fim"],

        # Colunas que serão convertidas para inteiros
        "inteiros": [],
    },
    {
        "raw": "raw_pagamento",
        "silver": "silver_pagamento",
        "textos": ["id_viagem", "num_proposta", "nome_orgao_pagador", "nome_ug_pagadora", "tipo_pagamento"],
        "valores": ["valor"],
        "datas": [],
        "inteiros": [],
    },
    {
        "raw": "raw_passagem",
        "silver": "silver_passagem",
        "textos": ["id_viagem", "meio_transporte", "pais_origem_ida", "uf_origem_ida", "cidade_origem_ida",
                   "pais_destino_ida", "uf_destino_ida", "cidade_destino_ida"],
        "valores": ["valor_passagem", "taxa_servico"],
        "datas": ["data_emissao"],
        "inteiros": [],
    },
    {
        "raw": "raw_trecho",
        "silver": "silver_trecho",
        "textos": ["id_viagem", "origem_uf", "origem_cidade", "destino_uf", "destino_cidade", "meio_transporte"],
        "valores": ["numero_diarias"],
        "datas": ["origem_data", "destino_data"],
        "inteiros": ["sequencia_trecho"],
    },
]


# ---------------------------------------------------------------------------
# Transformação dos dados
# ---------------------------------------------------------------------------

def transformar(bloco, tabela):
    """Converte um bloco da Raw e calcula informações adicionais sobre as viagens."""

    # Trata cada grupo de colunas conforme o tipo de dado
    for coluna in tabela["textos"]:
        bloco[coluna] = limpar_texto(bloco[coluna])

    for coluna in tabela["valores"]:
        bloco[coluna] = texto_para_decimal(bloco[coluna])

    for coluna in tabela["datas"]:
        bloco[coluna] = texto_para_data(bloco[coluna])

    for coluna in tabela["inteiros"]:
        # Converte para número e trata valores inválidos
        bloco[coluna] = pd.to_numeric(bloco[coluna], errors="coerce")

    # Cria duas colunas calculadas somente para a tabela de viagens
    if tabela["silver"] == "silver_viagem":

        # Calcula o valor total, descontando as devoluções
        bloco["valor_total"] = (
            bloco["valor_diarias"].fillna(0)  # Valores vazios são considerados zero
            + bloco["valor_passagens"].fillna(0)
            + bloco["valor_outros_gastos"].fillna(0)
            - bloco["valor_devolucao"].fillna(0)
        ).round(2)  # Mantém duas casas decimais

        # Calcula a duração da viagem, contando o dia de início
        bloco["duracao_dias"] = (bloco["data_fim"] - bloco["data_inicio"]).dt.days + 1

    # Troca NaN e NaT por None, que será gravado como NULL no banco
    return bloco.astype(object).where(pd.notna(bloco), None)


# ---------------------------------------------------------------------------
# Carga da camada Silver
# ---------------------------------------------------------------------------

def carregar_silver(conexao, tabela):
    """Lê a Raw em blocos, transforma e grava na Silver."""

    # Junta os nomes das colunas que serão lidas da Raw
    colunas = tabela["textos"] + tabela["valores"] + tabela["datas"] + tabela["inteiros"]

    # Lê os dados em blocos para economizar memória
    blocos = pd.read_sql(
        f"SELECT {', '.join(colunas)} FROM {tabela['raw']}", conexao, chunksize=TAMANHO_BLOCO
    )

    cursor = conexao.cursor()
    total = 0

    for bloco in blocos:
        # Limpa e converte os dados antes de inserir
        bloco = transformar(bloco, tabela)

        # Prepara as linhas para a inserção no banco
        linhas = list(bloco.itertuples(index=False, name=None))

        # Insere várias linhas de uma vez
        execute_values(
            cursor,
            f"INSERT INTO {tabela['silver']} ({', '.join(bloco.columns)}) VALUES %s",
            linhas,
        )

        # Conta e mostra quantas linhas já foram gravadas
        total += len(linhas)
        print(f"   {total} linhas gravadas")

    return total


# ---------------------------------------------------------------------------
# Conferência dos dados
# ---------------------------------------------------------------------------

def conferir(conexao):
    """Compara alguns dados da Raw com a Silver para verificar a carga."""

    cursor = conexao.cursor()

    def um_valor(sql):
        # Executa a consulta e retorna o primeiro valor encontrado
        cursor.execute(sql)
        return cursor.fetchone()[0]

    conferencias = []

    # Compara a quantidade de linhas de cada tabela
    for tabela in TABELAS:
        conferencias.append((
            f"linhas {tabela['raw']} x {tabela['silver']}",
            um_valor(f"SELECT COUNT(*) FROM {tabela['raw']}"),
            um_valor(f"SELECT COUNT(*) FROM {tabela['silver']}"),
        ))

    # Confere se as datas vazias da Raw viraram NULL na Silver
    conferencias.append((
        "datas de emissão vazias (Raw) x NULL (Silver)",
        um_valor("SELECT COUNT(*) FROM raw_passagem WHERE data_emissao = ''"),
        um_valor("SELECT COUNT(*) FROM silver_passagem WHERE data_emissao IS NULL"),
    ))

    # Confere se a soma dos pagamentos continua igual após a conversão
    conferencias.append((
        "soma dos pagamentos Raw x Silver",
        um_valor("SELECT SUM(REPLACE(NULLIF(valor, ''), ',', '.')::NUMERIC) FROM raw_pagamento"),
        um_valor("SELECT SUM(valor) FROM silver_pagamento"),
    ))

    # Mostra se cada conferência passou ou encontrou diferença
    print("\nConferência Raw x Silver:")
    for descricao, origem, destino in conferencias:
        situacao = "OK" if origem == destino else "DIFERENTE!"
        print(f"   {descricao:<48} {origem} x {destino}  {situacao}")


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

conexao = None

try:
    # Conecta ao banco de dados
    conexao = conectar()
    cursor = conexao.cursor()

    # Limpa as tabelas Silver antes de carregar novamente
    # As tabelas são esvaziadas juntas por causa das chaves estrangeiras
    cursor.execute(
        "TRUNCATE silver_pagamento, silver_passagem, silver_trecho, silver_viagem RESTART IDENTITY"
    )

    # Transforma e carrega cada tabela na ordem configurada
    for tabela in TABELAS:
        print(f"\nTransformando {tabela['raw']} -> {tabela['silver']}...")
        carregar_silver(conexao, tabela)

    # Confirma as alterações e verifica se os dados estão corretos
    conexao.commit()
    conferir(conexao)

except Exception as erro:
    if conexao:
        # Desfaz as alterações que ainda não foram confirmadas
        conexao.rollback()

    print(f"\nERRO na transformação: {type(erro).__name__}: {erro}")

finally:
    if conexao:
        # Fecha a conexão ao terminar
        conexao.close()
