# Pipeline ETL — Viagens a Serviço (Portal da Transparência)

**Autora:** Laís Alegri · leislaa@gmail.com

Projeto avaliativo do curso **Análise de Dados com Python (SENAI / LAB365)** — Módulo 1, Semana 13.

Um pipeline de dados em **Python + PostgreSQL** que baixa os dados abertos de *Viagens a Serviço* do Governo Federal, guarda o dado bruto sem alterar nada, limpa e organiza esse dado e responde perguntas de negócio com tabelas e gráficos.

---

## 📌 O problema que este projeto resolve

O Portal da Transparência publica os gastos com viagens a serviço, mas o dado chega bruto. São quatro arquivos CSV grandes (quase 1,9 milhão de linhas), com texto em codificação antiga (`latin-1`), vírgula como separador decimal (`1272,97`), datas no formato `17/09/2024`, campos vazios e nomes de coluna com pequenos defeitos.

Para transformar isso em informação confiável, o projeto constrói o caminho completo: **extrair → guardar o original → limpar e tipar → agregar → responder perguntas**. Tudo pensado para ser executado quantas vezes for preciso, sem duplicar nem quebrar nada.

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
- **Idempotência**: rodar várias vezes não duplica dados;
- **Transações** com `commit` / `rollback`;
- **Chaves estrangeiras** e **constraints** (`CHECK`, `UNIQUE`, `NOT NULL`);
- Conversão explícita de tipos (`texto_para_decimal`, `texto_para_data`).

### 🔄 Fluxo do pipeline

```
  ┌──────────────────────────┐
  │  0_criar_banco.sql       │
  │  Cria o banco e as       │
  │  tabelas Raw e Silver    │
  └────────────┬─────────────┘
               │
               ▼
  ┌──────────────────────────┐        ┌─────────────────────┐
  │  1_extrair.py            │◄───────│  Google Drive       │
  │  Baixa o .zip e          │        │  (.zip com os CSVs) │
  │  carrega a camada RAW    │        └─────────────────────┘
  │  (tudo como texto)       │
  └────────────┬─────────────┘
               │
               ▼
  ┌──────────────────────────┐
  │  2_transformar.py        │
  │  Limpa, tipa e carrega   │
  │  a camada SILVER         │
  └────────────┬─────────────┘
               │
               ▼
  ┌──────────────────────────┐
  │  3_analise.ipynb         │
  │  Cria a camada GOLD,     │
  │  responde 7 perguntas    │
  │  e gera os gráficos      │
  └──────────────────────────┘
```

---

## 📂 Estrutura do repositório

```
.
├── .env.example            # Modelo do arquivo de credenciais (copiar para .env)
├── .gitignore              # Ignora .env, data/ e outros arquivos locais
├── 0_criar_banco.sql       # Cria o banco e as tabelas Raw, Silver e Gold
├── 1_extrair.py            # Fase 1: download e carga da camada Raw
├── 2_transformar.py        # Fase 2: transformação Raw → Silver
├── 3_analise.ipynb         # Fase 3: camada Gold, perguntas e gráficos
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

1. Conecte-se ao PostgreSQL e execute a **Parte 1** do `0_criar_banco.sql` (criação do banco `transparencia`);
2. Conecte-se ao banco `transparencia` e execute a **Parte 2** (criação das tabelas Raw e Silver).

### 3. Executar o pipeline

Na ordem:

```bash
python 1_extrair.py       # Baixa os CSVs e carrega a camada Raw
python 2_transformar.py   # Limpa, transforma e carrega a camada Silver
```

Os scripts são **idempotentes**: podem ser rodados várias vezes sem duplicar registros.

### 4. Analisar os dados

Abra o notebook no VS Code ou no Jupyter:

```bash
jupyter notebook 3_analise.ipynb
```

O notebook cria a camada **Gold** (tabelas e views agregadas) e responde as 7 perguntas de negócio.

---

## 🧠 Decisões de modelagem e de negócio

Durante o desenvolvimento, precisei tomar algumas decisões que não estavam definidas no enunciado. Registro aqui o que escolhi e por quê, para que o resultado seja reprodutível e transparente.

**Filtro base: só viagens realizadas**  
Todas as perguntas consideram apenas `situacao = 'Realizada'`. Viagens canceladas ou não realizadas não representam deslocamento nem gasto efetivo, então ficam de fora para não distorcer médias e rankings.

**Cálculo do custo total**  
O enunciado não define como somar os valores, então adotei:

```
custo_total = diárias + passagens + outros gastos - devolução
```

A devolução entra como subtração porque representa valor que voltou aos cofres públicos, ou seja, não é gasto real. A regra está aplicada no `2_transformar.py`, na coluna `valor_total`.

**Cálculo da duração**  
Adotei `(data_fim - data_inicio) + 1` dia. O `+1` existe porque o dia de início e o dia de fim contam como dias de viagem. Sem ele, uma viagem de um único dia apareceria com duração zero.

**Destinos (Pergunta 2)**  
A coluna `destinos` é texto livre e costuma trazer várias cidades separadas por vírgula. Extraí apenas a última cidade do roteiro, que é o destino final de fato. Também impus um piso de 100 viagens por destino, para evitar que cidades visitadas poucas vezes distorçam a média.

**Média por tipo de pagamento (Pergunta 4)**  
Calculei como total pago dividido pela quantidade de pagamentos, e não como média das médias. Essa escolha evita que um tipo com poucos registros de valor alto fique diluído no resultado.

**Meio de transporte (Pergunta 5)**  
A base traz uma categoria chamada "Inválido". Mantive como veio da fonte, porque representa o dado real publicado pelo Portal, mesmo que o nome não ajude a interpretar o resultado.

**Órgão pagador (Pergunta 7)**  
Existe um pagador identificado apenas como "Sigiloso", que aparece entre os maiores valores e não permite saber qual órgão pagou. Optei por manter o registro, sinalizando a limitação, pois removê-lo esconderia parte do gasto real.

---

## 📊 Respostas das 7 perguntas de negócio

### 1. Quais são os 5 órgãos com maior custo total?

| Órgão | Custo total (R$ milhões) |
|---|---|
| Ministério da Justiça e Segurança Pública | 485,75 |
| Ministério da Defesa | 154,60 |
| Ministério da Educação | 109,76 |
| Ministério do Meio Ambiente e Mudança do Clima | 49,30 |
| Ministério da Previdência Social | 40,24 |

**Insight:** há uma diferença de **R$ 331,15 milhões** entre o primeiro e o segundo colocado. O Ministério da Justiça concentra um gasto quase **3 vezes maior** que o segundo da lista, o que indica uma política de deslocamento bastante intensiva nessa pasta.

---

### 2. Quais os 3 destinos finais com maior custo médio por viagem?

| Destino final | Viagens | Custo médio |
|---|---|---|
| Tucumã/PA | 118 | R$ 29.092,23 |
| Guaíra/PR | 129 | R$ 27.402,57 |
| Genebra/Suíça | 254 | R$ 25.530,77 |

**Insight:** dois destinos nacionais de pequeno porte aparecem à frente de um destino internacional (Genebra). Isso indica que **viagens para locais de difícil acesso** tendem a custar mais caro por viagem, provavelmente por causa de passagens mais caras ou necessidade de mais trechos.

---

### 3. Qual a viagem de maior duração e seu custo?

| ID da viagem | Órgão | Período | Dias | Custo |
|---|---|---|---|---|
| 0000000000020699856 | Ministério da Previdência Social | 13/01/2025 a 31/01/2026 | 384 | R$ 0,00 |

**Insight:** a viagem mais longa registrada tem **mais de um ano** de duração e custo zero. Isso é indício de **erro de digitação** na data de fim ou de viagem cancelada que ficou com status "Realizada". É um bom alerta de **qualidade de dados** da fonte.

---

### 4. Qual o tipo de pagamento com maior valor médio?

| Tipo de pagamento | Total pago | Qtde | Valor médio |
|---|---|---|---|
| DIÁRIAS | R$ 832,27 mi | 400.364 | R$ 2.078,79 |
| PASSAGEM | R$ 344,24 mi | 182.883 | R$ 1.882,32 |
| Serviço correlato: seguro | R$ 2,14 mi | 4.789 | R$ 447,26 |
| RESTITUIÇÃO | R$ 2,84 mi | 11.574 | R$ 245,70 |

**Insight:** as **diárias** representam mais de 70% do volume total pago e têm o maior valor médio por pagamento. Passagens vêm em segundo lugar. Juntas, essas duas categorias concentram **quase 100% do gasto** com viagens a serviço.

---

### 5. Qual o meio de transporte mais usado nos trechos?

| Meio de transporte | Trechos | % |
|---|---|---|
| Veículo Oficial | 385.734 | 51,0% |
| Aéreo | 226.707 | 30,0% |
| Rodoviário | 64.454 | 8,5% |
| Veículo Próprio | 42.736 | 5,7% |
| Outros | 36.254 | 4,8% |

**Insight:** o **Veículo Oficial** é o meio mais usado (mais da metade dos trechos), seguido do **Aéreo**. Isso mostra que a maior parte dos deslocamentos é de curta distância, dentro da mesma cidade ou região onde o servidor está lotado.

---

### 6. Qual UF de destino aparece em mais trechos?

| UF de destino | Trechos |
|---|---|
| São Paulo | 81.727 |
| Distrito Federal | 77.962 |
| Minas Gerais | 50.555 |
| Rio de Janeiro | 43.481 |
| Paraná | 42.323 |

**Insight:** **São Paulo** e **Distrito Federal** concentram a maior parte dos destinos, o que faz sentido: SP é o maior polo econômico do país e DF é a sede do Governo Federal. Juntos, respondem por cerca de **21% dos trechos** registrados.

---

### 7. Qual órgão pagou mais no total?

| Órgão pagador | Total pago (R$ milhões) |
|---|---|
| Fundo Nacional de Segurança Pública | 278,29 |
| Sigiloso | 199,31 |
| Comando da Aeronáutica | 81,07 |
| Instituto Nacional do Seguro Social | 37,25 |
| Comando do Exército | 36,58 |

**Insight:** o **Fundo Nacional de Segurança Pública** lidera os pagamentos, mas o dado chama atenção pelo segundo lugar ser **"Sigiloso"**, com R$ 199,31 milhões. Isso mostra que **quase 1/3 dos pagamentos** do top 5 não identifica o órgão real, o que é uma **limitação importante** da transparência pública.

---

## 🧭 Melhorias que podem ser aplicadas

Algumas ideias para evoluir o projeto:

- **Tratamento do dado "Sigiloso"** — investigar se é possível cruzar com outras bases para descobrir o órgão real, ou pelo menos sinalizar visualmente nos gráficos que existe esse agrupamento;
- **Filtro por período** — hoje o dataset cobre apenas jan-jun/2025. Seria interessante incluir uma coluna de ano/mês para facilitar análises temporais;
- **Detecção automática de outliers** — casos como a viagem de 384 dias com custo zero poderiam ser **sinalizados automaticamente** em uma tabela de alertas de qualidade;
- **Dashboard interativo** — migrar os gráficos do notebook para **Streamlit** ou **Power BI**, permitindo que o usuário filtre por órgão, UF ou tipo de pagamento em tempo real;
- **Testes automatizados** — criar testes com `pytest` para validar que as conversões (`texto_para_decimal`, `texto_para_data`) continuam funcionando depois de qualquer alteração no código;
- **Orquestração** — empacotar o pipeline em **Airflow** ou **Prefect** para rodar automaticamente toda vez que o Portal da Transparência publicar novos dados;
- **Camada de dados mais rica** — incluir uma tabela de dimensão de órgãos, com sigla, ministério e esfera (federal/estadual/municipal), para permitir análises cruzadas.

---

## 🧠 Conclusões gerais

Depois de rodar o pipeline inteiro e responder as 7 perguntas, alguns padrões ficaram claros:

1. **Poucos órgãos concentram a maior parte do gasto.** O Ministério da Justiça, sozinho, gasta quase o triplo do segundo colocado. Um gráfico de pizza ilustraria bem essa concentração.

2. **Diárias e passagens são os gastos que realmente importam.** Todas as outras categorias (seguro, restituição) juntas não chegam a 1% do total. Isso ajuda a **direcionar o esforço de análise** para essas duas categorias.

3. **Viagens curtas são a maioria.** O uso intensivo de veículo oficial mostra que a maior parte dos deslocamentos é de curta distância. Isso pode ser um ponto de atenção para políticas de **redução de custo com transporte**.

4. **Existem problemas de qualidade no dado original.** A viagem de 384 dias com custo zero e o pagador "Sigiloso" mostram que o dado público, mesmo sendo oficial, precisa de **validação e limpeza antes de ser usado em decisões**.

5. **A arquitetura medalhão funcionou bem.** Separar Raw, Silver e Gold deixou o pipeline organizado e fácil de dar manutenção. Rodar tudo de novo nunca duplica registros, o que dá **segurança para reexecutar** em qualquer momento.

---

## 👩‍💻 Autora

**Laís Alegri**  
📧 leislaa@gmail.com