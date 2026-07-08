# legaldata

CLI para coletar dados judiciais das APIs públicas do CNJ e persistir em DuckDB.

## APIs

| API | Dados coletados |
|-----|----------------|
| **DataJud** | processos, movimentos, assuntos |
| **DJEN** | comunicações, partes, advogados |

## Instalação

```bash
uv tool install .
```

Disponibiliza o comando `legaldata` globalmente.

## Comandos

### `datajud` — DataJud

Busca processos na API do DataJud e salva em DuckDB.

```bash
# Um processo isolado
legaldata datajud 00194332920248160001 -o resultado.db

# CSV com N números de processo
legaldata datajud --csv processos.csv -o resultado.db
```

O CSV deve ter um número por linha (20 dígitos, com ou sem formatação). Duplicatas são removidas automaticamente.

Números CNJ já presentes no banco de saída são pulados automaticamente (não são buscados de novo na API). Para forçar um novo fetch completo, apague o arquivo `.db` antes de rodar.

Fetch concorrente com 30 workers + retry automático (5 workers após 15s) em caso de 429/timeout.

---

### `djen` — DJEN

Busca comunicações processuais no DJEN e adiciona ao DuckDB existente.

```bash
# Lê os números da tabela processos do próprio banco
legaldata djen resultado.db

# Ou a partir de um CSV
legaldata djen resultado.db --csv processos.csv
```

Execução sequencial com 1s de intervalo entre requests (rate limit público).

---

### `exportar` — CSV

Exporta qualquer tabela do DuckDB para CSV com delimitador `;`.

```bash
legaldata exportar processos resultado.db
legaldata exportar advogados resultado.db --dir ./exports
```

Arquivo gerado: `<db>_<tabela>_YYYYMMDDHHMMSS.csv`

Tabelas disponíveis: `processos`, `movimentos`, `assuntos`, `comunicacoes`, `partes`, `advogados`

---

### `dashboard` — HTML

Abre dashboard HTML no browser com estatísticas do banco.

```bash
legaldata dashboard resultado.db
legaldata dashboard resultado.db --port 9000
```

Seções DataJud: totais, distribuição por tribunal/grau, classes processuais, assuntos.
Seções DJEN (se disponível): comunicações por tribunal, polo ativo, polo passivo, advogados.

---

## Banco de dados

Arquivo DuckDB com até 6 tabelas:

### DataJud

| Tabela | PK | Descrição |
|--------|----|-----------|
| `processos` | `id` | Dados do processo (classe, órgão, grau, datas) |
| `movimentos` | `id, movimento_seq` | Histórico de movimentação |
| `assuntos` | `id, assunto_seq` | Assuntos do processo |

> O mesmo `numeroProcesso` CNJ pode ter múltiplos registros com graus distintos (G1, G2...). O campo `id` do DataJud (`Tribunal_Classe_Grau_OrgaoJulgador_NumeroProcesso`) é a chave primária real.

### DJEN

| Tabela | PK | Descrição |
|--------|----|-----------|
| `comunicacoes` | `id` | Publicação do DJEN (texto limpo, sem HTML) |
| `partes` | `comunicacao_id, parte_seq` | Partes da comunicação (polo A/P) |
| `advogados` | `comunicacao_id, advogado_seq` | Advogados com número e UF da OAB |

Todas as tabelas DJEN incluem a coluna `processo` (número CNJ) para join direto com `processos`.

### Exemplos de consulta

```sql
-- processos por tribunal e grau
SELECT tribunal, grau, COUNT(*)
FROM processos GROUP BY 1, 2 ORDER BY 1, 2;

-- movimentos de um processo
SELECT movimento_data, movimento_nome
FROM movimentos WHERE id LIKE '%00194332920248160001%'
ORDER BY movimento_seq;

-- advogados com mais processos
SELECT nome, oab_numero, oab_uf, COUNT(DISTINCT processo) AS total
FROM advogados GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 10;

-- polo passivo mais frequente
SELECT nome, COUNT(DISTINCT processo) AS total
FROM partes WHERE polo = 'P' GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- join processo + comunicação
SELECT p.tribunal, c.data_disponibilizacao, c.texto
FROM processos p JOIN comunicacoes c ON c.processo = p.processo
ORDER BY c.data_disponibilizacao DESC;
```

## Tribunais suportados

| Segmento | J | Cobertura |
|----------|---|-----------|
| Justiça Estadual (TJ) | 8 | AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO |
| Justiça do Trabalho (TRT) | 5 | TRT 1–24 |
| Justiça Federal (TRF) | 4 | TRF 1–6 (inclui JFPR, JFSC, JFRS via `api_publica_trf4`) |

O mapeamento completo de códigos CNJ → endpoints está em `src/legaldata/tribunais.toml`.

## Estrutura

```
src/legaldata/
├── cli.py          # Comandos: datajud, djen, exportar, dashboard
├── datajud.py      # Fetch concorrente DataJud (30 workers + retry)
├── djen.py         # Fetch sequencial DJEN (1s delay, retry 429)
├── parser.py       # Parse número CNJ → (digits, tribunal)
├── storage.py      # Persistência DuckDB (DataJud + DJEN)
├── dashboard.py    # Dashboard HTML + servidor HTTP local
├── helpers.py      # parse_date, parse_datetime, safe_int, format_cnj
└── tribunais.toml  # Mapeamento de códigos CNJ por segmento
```

## Desenvolvimento

```bash
uv run legaldata datajud --csv references/processos.csv -o resultado.db
uv run legaldata djen resultado.db
uv run pytest -v
```
