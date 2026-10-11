# Projeto Final Módulo 1 - Pipeline ETL — Viagens a Serviço (Portal da Transparência)

Projeto avaliativo do curso **Análise de Dados com Python (SENAI / LAB365)** — Módulo 1, Semana 13.

Um pipeline de dados em **Python + PostgreSQL** que baixa os dados abertos de *Viagens a Serviço* do Governo Federal, guarda o dado bruto sem alterar nada, limpa e organiza esse dado e responde perguntas de negócio com tabelas e gráficos.

---

## 📌 O problema que este projeto resolve

O Portal da Transparência publica os gastos com viagens a serviço, mas o dado chega bruto:

- Quatro arquivos CSV grandes (**quase 1,9 milhão de linhas**);
- Texto com acentos em codificação antiga (`latin-1`);
- Vírgula como separador decimal (`1272,97`);
- Datas escritas como `17/09/2024`;
- Campos vazios e nomes de coluna com pequenos defeitos.

Para transformar isso em informação confiável, o projeto constrói o caminho completo: **extrair → guardar o original → limpar e tipar → agregar → responder perguntas**, de forma que possa ser executado quantas vezes for preciso sem duplicar nem quebrar nada.

---

## 🛠️ Técnicas e tecnologias

| Camada | Tecnologia / Técnica |
|---|---|
| Linguagem | Python 3 |
| Banco de dados | PostgreSQL |
| Conexão | `psycopg2` (com `execute_values` para inserção em lote) |
| Manipulação de dados | `pandas` (leitura em blocos com `chunksize`) |
| Download | `requests` + `zipfile` (streaming, sem carregar tudo na memória) |
| Configuração | Arquivo `.env` lido manualmente (sem biblioteca externa) |
| Visualização | `matplotlib` |

**Conceitos aplicados:**

- Arquitetura **medalhão** (Raw → Silver → Gold);
- Processamento em **blocos** para não estourar a memória;
- **Idempotência** (rodar várias vezes não duplica dados);
- **Transações** com `commit` / `rollback`;
- **Chaves estrangeiras** e **constraints** (`CHECK`, `UNIQUE`, `NOT NULL`);
- Conversão explícita de tipos (`texto_para_decimal`, `texto_para_data`).

---

## 📂 Estrutura do repositório

```
.
├── .env.example            # Modelo do arquivo de credenciais (copiar para .env)
├── .gitignore              # Ignora .env, data/ e outros arquivos locais
├── 0_criar_banco.sql       # Cria o banco e as tabelas Raw, Silver e Gold
├── 1_extrair.py            # Fase 1: download e carga da camada Raw
├── 2_transformar.py        # Fase 2: transformação Raw → Silver
├── banco.py                # Funções de conexão e execução no PostgreSQL
├── config.py               # Configurações, caminhos e mapeamento dos CSVs
├── requirements.txt        # Dependências do projeto
└── README.md               # Este arquivo
```

---

## ✅ Pré-requisitos

- **Python 3.10+** instalado;
- **PostgreSQL** instalado e rodando localmente (ou acessível pela rede);
- Acesso ao arquivo `.zip` no Google Drive (o ID já está em `config.py`);
- Pacotes Python listados em `requirements.txt`.

Instalação das dependências:

```bash
pip install -r requirements.txt
```

---

## ▶️ Como executar

### 1. Configurar as credenciais

Copie o arquivo de exemplo e preencha com os seus dados:

```bash
cp .env.example .env
```

Edite o `.env`:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=sua_senha_aqui
POSTGRES_DATABASE=transparencia
```

> ⚠️ O arquivo `.env` está no `.gitignore` e **não deve** ser enviado ao Git.

### 2. Criar o banco e as tabelas

No **pgAdmin** ou **psql**:

1. Conecte-se ao PostgreSQL e execute a **Parte 1** do `0_criar_banco.sql` (criação do banco `transparencia`).
2. Conecte-se ao banco `transparencia` e execute a **Parte 2** (criação das tabelas Raw e Silver).

### 3. Executar o pipeline

Na ordem:

```bash
python 1_extrair.py       # Baixa os CSVs e carrega a camada Raw
python 2_transformar.py   # Limpa, tipa e carrega a camada Silver
```

Os scripts são **idempotentes**: podem ser rodados várias vezes sem duplicar registros.

---

## 🧠 Decisões de modelagem e de negócio

### Camada Raw — o dado como veio

- Todas as colunas são `VARCHAR`, sem tratamento;
- Os CSVs são lidos com `dtype=str` e `keep_default_na=False`, para que campos vazios continuem vazios (e não virem `NaN`);
- Cada tabela é esvaziada com `TRUNCATE` antes da carga — assim, rodar de novo nunca duplica;
- A leitura é feita em **blocos de 50.000 linhas** (`TAMANHO_BLOCO`), o que evita estourar a memória.

### Camada Silver — dado limpo e tipado

- `silver_viagem` é a **tabela mãe** e é carregada **primeiro**, pois as outras três têm `FOREIGN KEY` apontando para ela;
- Conversões:
  - `texto_para_decimal`: `"1272,97"` → `1272.97`;
  - `texto_para_data`: `"17/09/2024"` → `2024-09-17`;
- Campos vazios viram `NULL` no banco;
- Duas colunas calculadas em Python:
  - `valor_total = diárias + passagens + outros gastos − devolução`;
  - `duracao_dias = (data_fim − data_inicio) + 1` (conta o dia de início e o de fim);
- `CONSTRAINTS` para garantir integridade:
  - `CHECK (valor_diarias >= 0)`;
  - `CHECK (valor >= 0)` em pagamentos;
  - `CHECK (valor_passagem >= 0)` e `CHECK (taxa_servico >= 0)` em passagens;
  - `CHECK (numero_diarias >= 0)` e `UNIQUE (id_viagem, sequencia_trecho)` em trechos.

### Idempotência e segurança

- Todas as tabelas são esvaziadas antes da carga (`TRUNCATE ... RESTART IDENTITY`);
- Em caso de erro, o `rollback()` desfaz o que ainda não foi confirmado;
- Ao final de cada carga, um bloco de **conferência** compara:
  - linhas do CSV × linhas da tabela Raw;
  - linhas Raw × linhas Silver;
  - soma dos pagamentos antes × depois da conversão.

---

## 📊 Resultado da execução

Ao final do `1_extrair.py`, é impressa uma conferência como esta:

```
Conferência (linhas lidas do CSV x linhas na tabela Raw):
   raw_viagem          xxxxxx x   xxxxxx   OK
   raw_pagamento       xxxxxx x   xxxxxx   OK
   raw_passagem        xxxxxx x   xxxxxx   OK
   raw_trecho          xxxxxx x   xxxxxx   OK
```

Ao final do `2_transformar.py`:

```
Conferência Raw x Silver:
   linhas raw_viagem x silver_viagem                        xxxxxx x xxxxxx   OK
   linhas raw_pagamento x silver_pagamento                  xxxxxx x xxxxxx   OK
   linhas raw_passagem x silver_passagem                    xxxxxx x xxxxxx   OK
   linhas raw_trecho x silver_trecho                        xxxxxx x xxxxxx   OK
   datas de emissão vazias (Raw) x NULL (Silver)            xxxx x xxxx       OK
   soma dos pagamentos Raw x Silver                         xxxxxx.xx x xxxxxx.xx   OK
```

Com a camada Silver pronta, é possível responder perguntas de negócio como:

- Quais órgãos gastaram mais com viagens?
- Qual o valor total gasto por mês?
- Quais os destinos mais frequentes?
- Qual a duração média das viagens?

---

## 📌 Próximos passos

- Construir a camada **Gold** com views agregadas (`vw_gold_pagamento_resumo`, `vw_gold_trecho_resumo`);
- Gerar gráficos com `matplotlib` a partir das consultas da Gold;
- Documentar os insights obtidos com os dados de 2025.