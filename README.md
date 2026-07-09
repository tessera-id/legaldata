---
title: legaldata app para dados judiciais Datajud+DJEN
author: Alceu Eilert Nascimento
date: 2026-06-24
---
# legaldata

CLI para coletar dados de processos judiciais das APIs públicas do CNJ (Datajud e DJEN) e persistir em DuckDB.

## APIs

| API | Dados coletados |
|-----|----------------|
| **DataJud** | processos, movimentos, assuntos |
| **DJEN** | comunicações, partes, advogados |

## Instalação

### Pré-requisito: instalar o uv

`uv` é o único pré-requisito, ele gerencia Python, dependências e o install do CLI.

**Linux / macOS:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Fechar e reabrir o terminal após instalar. 

Instalar o python

```bash
uv python install 3.14
```

O uv baixa automaticamente o python da distribuição da própria Astral.

### Instalação do legaldata app

Faça o clone do repositorio em alguma pasta local que contém seus repositórios.

Via HTTPS
```bash
git clone https://github.com/tessera-id/legaldata.git
```

Via SSH
```bash
git clone git@github.com:tessera-id/legaldata.git
```

Instalação do legaldata app via `uv tool`

```bash
uv tool install .
```

Isto disponibiliza o comando `legaldata` globalmente.

## Comandos

### `datajud` — DataJud

Busca processos na API do DataJud e salva em DuckDB.

```bash
# padrão para um processo
legaldata datajud {numero do processo} -o {nome que quiser dar ao arquivo}.db
# padrão para varios processos em um arquivo.csv
legaldata datajud --csv {nome do arquivo}.csv -o {nome que quiser dar ao arquivo}.db
```

Exemplos:

```bash
# Um processo isolado
legaldata datajud 00008323520184013202 -o resultado.db

# CSV com N números de processo
legaldata datajud --csv processos.csv -o resultado.db
```

> [!Important]
> O CSV deve ter um número por linha (20 dígitos, com ou sem formatação). 
> Duplicatas são removidas automaticamente.

> [!Note]
> Números CNJ já presentes no banco de saída não são buscados de novo na API. 
> Para forçar um novo fetch completo, apague o arquivo `.db` antes de rodar.

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

### `xlsx` — XLSX

Exporta todas as tabelas do DuckDB para um único arquivo XLSX, uma aba por tabela.

```bash
legaldata xlsx resultado.db
legaldata xlsx resultado.db --dir ./exports
```

Arquivo gerado: `<db>_YYYYMMDDHHMMSS.xlsx`. Inclui uma aba extra "Orientações" com a descrição, chave primária e contagem de linhas de cada tabela exportada.

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

> [!Note]
> O mesmo `numeroProcesso` CNJ pode ter múltiplos registros com graus distintos (G1, G2...). 
> O campo `id` do DataJud (`Tribunal_Classe_Grau_OrgaoJulgador_NumeroProcesso`) é a chave primária real para individualização dos processos.

Pelo Glossário do Datajud temos:

| Atributos | Tipo | Descrição |
| --------- | ---- | --------- |
| `id` | text/keyword | Identificador da origem do processo no Datajud - Chave `Tribunal_Classe_Grau_OrgaoJulgador_NumeroProcesso` |
| `numeroProcesso` | text/keyword | Numeração Única (CNJ) do processo sem formatação |

Verifica-se que o `id` é uma concatenação das variáveis `Tribunal`, `Classe`, `Grau`, `OrgaoJulgador`, e `NumeroProcesso`.
Um processo `00008323520184013202` vira `TJPR_7_G1_8789_00008323520184013202`, sendo `{Tribunal}_{Classe}_{Grau}_{OrgaoJulgador}_00008323520184013202`.
Contudo, raramente há aderência integral ao formato definido pelo CNJ. O que se vê na prática é apenas a inclusão de `{Tribunal}_{Classe}_{NumeroProcesso}`.

> [!Caution]
> O Datajud não uniformiza o dados de data, há múltiplas representações para data/hora.
> Há registros que adotam ISO completo (`YYYY-MM-DDTHH:MM:SS.mmmZ`) e outros Numérico 14 dígitos (`YYYYMMDDHHMMSS`).

### DJEN

| Tabela | PK | Descrição |
|--------|----|-----------|
| `comunicacoes` | `id` | Publicação do DJEN (texto limpo, sem HTML) |
| `partes` | `comunicacao_id, parte_seq` | Partes da comunicação (polo A/P) |
| `advogados` | `comunicacao_id, advogado_seq` | Advogados com número e UF da OAB |

Todas as tabelas DJEN incluem a coluna `processo` (número CNJ) para join direto com `processos`.

>[!Caution]
> Os Tribunais não têm cuidado na aderência com o contrato de API do DJEN e exitem erros.
> É comum que Tribunais com EPROC lancem o numero da OAB do advogado de forma errada.
> O contrato de de API do DJEN define que são dois campos um `numeroOab` para os numeros e 
> um `ufOab` para a sigla da unidade da federação da seccional da OAB que emitiu o registro.
> Ou seja, os dados são `numeroOab : 000000` e `ufOab: AA`. 
> Contudo, os Tribunais que usam EPROC lançam errado do dado na variavel `numeroOab: AA000000`.
> Como esta variável é uma `string`, esta violação causa problemas de identificação da publicações.

>[!Caution]
> Os Tribunais não têm cuidado na aderência com o contrato de API do DJEN e exitem erros.
> É comum que o nome das partes tenha variações e esteja incorreto.

>[!Caution]
> Os Tribunais não têm cuidado no lançamento dos textos das publicações.
> É comum que o texto contenha traços de HTML, demonstrando ausencia de cuidado no pré-processamento dos dados.

### Exemplos de consulta

```sql
-- processos por tribunal e grau
SELECT tribunal, grau, COUNT(*)
FROM processos GROUP BY 1, 2 ORDER BY 1, 2;

-- movimentos de um processo
SELECT movimento_data, movimento_nome
FROM movimentos WHERE id LIKE '%00008323520184013202%'
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

| Segmento | Cobertura |
|----------|-----------|
| Justiça Estadual | AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO |
| Justiça do Trabalho | TRT 1 a 24 |
| Justiça Federal | TRF 1 a 6 |

O mapeamento completo de códigos CNJ e endpoints está em `src/legaldata/tribunais.toml`.

>[!Note]
> Os TRFN incluem as JFUF via endpoint único `api_publica_trfN`.


## Estrutura

```
src/legaldata/
├── cli.py          # Comandos: datajud, djen, exportar, dashboard
├── datajud.py      # Fetch concorrente DataJud (30 workers + retry)
├── djen.py         # Fetch sequencial DJEN (1s delay, retry 429)
├── parser.py       # Parse número CNJ (digits, tribunal)
├── storage.py      # Persistência DuckDB (DataJud + DJEN)
├── dashboard.py    # Dashboard HTML + servidor HTTP local
├── xlsx.py         # Exporta todas as tabelas do DuckDB para um único XLSX
├── helpers.py      # parse_date, parse_datetime, safe_int, format_cnj
└── tribunais.toml  # Mapeamento de códigos CNJ por segmento
```

## Desenvolvimento

```bash
uv run legaldata datajud --csv references/processos.csv -o resultado.db
uv run legaldata djen resultado.db
uv run pytest -v
```

## Apendice

### Númeração única de processos no Pode Judiciário (NNNNNNN-DD.AAAA.J.TR.OOOO)

A numeração dos processos judiciais segue o padrão definido pelo CNJ na [Resolução Nº 65 de 16/12/2008](https://atos.cnj.jus.br/atos/detalhar/119).

O CNJ adota um racional de 6 campos obrigatórios (NNNNNNN-DD.AAAA.J.TR.OOOO), sendo:
 
- (NNNNNNN): 7 dígitos, identifica o número seqüencial do processo por unidade de origem (OOOO), a ser reiniciado a cada ano;
- (DD): 2 dígitos, identifica o dígito verificador, algoritmo Módulo 97 Base 10, ISO 7064:2003;
- (AAAA): 4 dígitos, identifica o ano do ajuizamento do processo;
- (J): 1 dígito, identifica o órgão ou segmento do Poder Judiciário de 1 a 9;
- (TR): 2 dígitos, identifica o tribunal do respectivo segmento do Poder Judiciário e, na Justiça Militar da União, a Circunscrição Judiciária; 
- (OOOO): 4 dígitos, identifica a unidade de origem do processo, observadas as estruturas administrativas dos segmentos do Poder Judiciário.

### Órgãos do Poder Judiciário (J)

Para os órgãos do Poder Judiciário, o (J) adota os seguintes numeros:

| órgão | numero
| --- | ---
| Supremo Tribunal Federal | 1
| Conselho Nacional de Justiça | 2
| Superior Tribunal de Justiça | 3
| Justiça Federal | 4
| Justiça do Trabalho | 5
| Justiça Eleitoral | 6
| Justiça Militar da União | 7
| Justiça dos Estados e do Distrito Federal e Territórios | 8
| Justiça Militar Estadual | 9

### Tribunais dos Órgãos do Poder Judiciário (TR)

#### Tribunais Superiores

Para os Tribunais Superiores, o (TR) adota os seguintes numeros:

| tribunal | numero
| --- | --- 
| Supremo Tribunal Federal | 00
| Conselho Nacional de Justiça | 00
| Superior Tribunal de Justiça | 00
| Tribunal Superior do Trabalho | 00
| Tribunal Superior Eleitoral | 00
| Superior Tribunal Militar | 00
| Conselho da Justiça Federal | 90
| Conselho Superior da Justiça do Trabalho | 90

#### Justiça Federal - Tribunais Regionais Federais

Para a Justiça Federal os Tribunais Regionais Federais adotam como (TR) os seguintes numeros:

| tribunal | numero
| --- | --- 
| Justiça Federal - TRF 1ª Região | 01
| Justiça Federal - TRF 2ª Região | 02
| Justiça Federal - TRF 3ª Região | 03
| Justiça Federal - TRF 4ª Região | 04
| Justiça Federal - TRF 5ª Região | 05
| Justiça Federal - TRF 6ª Região | 06

#### Justiça do Trabalho - Tribunais Regionais do Trabalho

Para a Justiça do Trabalho os Tribunais Regionais do Trabalho adotam como (TR) os seguintes numeros:

| tribunal | numero
| --- | --- 
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 1ª Região | 01
| TRT 24ª Região | 24

#### Justiça Eleitoral - Tribunais Regionais Eleitorais

Para a Justiça Eleitoral os Tribunais Regionais Eleitorais adotam como (TR) os seguintes numeros:

| tribunal | numero
| --- | --- 
| TRE AC | 01
| TRE AL | 02
| TRE AP | 03
| TRE AM | 04
| TRE BA | 05
| TRE CE | 06
| TRE DF | 07
| TRE ES | 08
| TRE GO | 09
| TRE MA | 10
| TRE MT | 11
| TRE MS | 12
| TRE MG | 13
| TRE PA | 14
| TRE PB | 15
| TRE PR | 16
| TRE PE | 17
| TRE PI | 18
| TRE RJ | 19
| TRE RN | 20
| TRE RS | 21
| TRE RO | 22
| TRE RR | 23
| TRE SC | 24
| TRE SE | 25
| TRE SP | 26
| TRE TO | 27

#### Justiça Militar da União - Circunscrição Judiciária Militar

Para a Justiça Militar da União a Circunscrições Judiciárias Militares adotam como (TR) os seguintes numeros:

| tribunal | numero
| --- | --- 
| 1ª CJM UF | 01
| 2ª CJM UF | 02
| 3ª CJM UF | 03
| 4ª CJM UF | 04
| 5ª CJM UF | 05
| 6ª CJM UF | 06
| 7ª CJM UF | 07
| 8ª CJM UF | 08
| 9ª CJM UF | 09
| 10ª CJM UF | 10
| 11ª CJM UF | 11
| 12ª CJM UF | 12

#### Justiça dos Estados e do Distrito Federal e Territórios - Tribunal de Justiça

Para a dos Estados e do Distrito Federal e Territórios os Tribunais de Justiça adotam como (TR) os seguintes numeros:

| tribunal | numero
| --- | --- 
| TJ AC | 01
| TJ AL | 02
| TJ AP | 03
| TJ AM | 04
| TJ BA | 05
| TJ CE | 06
| TJ DF | 07
| TJ ES | 08
| TJ GO | 09
| TJ MA | 10
| TJ MT | 11
| TJ MS | 12
| TJ MG | 13
| TJ PA | 14
| TJ PB | 15
| TJ PR | 16
| TJ PE | 17
| TJ PI | 18
| TJ RJ | 19
| TJ RN | 20
| TJ RS | 21
| TJ RO | 22
| TJ RR | 23
| TJ SC | 24
| TJ SE | 25
| TJ SP | 26
| TJ TO | 27



#### Justiça Militar Estadual, os Tribunais Militares dos Estados de Minas Gerais, Rio Grande do Sul e São Paulo

Para a Justiça Militar Estadual, os Tribunais Militares dos Estados de Minas Gerais, Rio Grande do Sul e São Paulo adotam como (TR) os seguintes numeros:

| tribunal | numero
| --- | --- 
| TM AC | 01
| TM AL | 02
| TM AP | 03
| TM AM | 04
| TM BA | 05
| TM CE | 06
| TM DF | 07
| TM ES | 08
| TM GO | 09
| TM MA | 10
| TM MT | 11
| TM MS | 12
| TM MG | 13
| TM PA | 14
| TM PB | 15
| TM PR | 16
| TM PE | 17
| TM PI | 18
| TM RJ | 19
| TM RN | 20
| TM RS | 21
| TM RO | 22
| TM RR | 23
| TM SC | 24
| TM SE | 25
| TM SP | 26
| TM TO | 27


## Unidades de origem dos processos

Para (OOOO), os tribunais devem codificar as suas respectivas unidades de origem do processo no primeiro grau de jurisdição (OOOO) com utilização dos números 0001 (um) a 8999 (oito mil, novecentos e noventa e nove), observando-se:
- na Justiça Federal, as subseções judiciárias e as turmas recursais;
- na Justiça do Trabalho, as varas do trabalho;
- na Justiça Eleitoral, as zonas eleitorais;
- na Justiça Militar da União, as auditorias militares;
- na Justiça dos Estados, do Distrito Federal e dos Territórios, os foros de tramitação;
- na Justiça Militar Estadual, as auditorias militares.


## Notas

> nos processos de competência originária dos tribunais, o campo (OOOO) deve ser preenchido com zero, facultada a utilização de funcionalidade que oculte a sua visibilidade e/ou torne desnecessário o seu preenchimento para a localização do processo;

> nos processos de competência originária das turmas recursais, o primeiro algarismo do campo (OOOO) deve ser preenchido com o número 9 (nove), facultada a utilização dos demais campos para a identificação específica da turma recursal responsável pela tramitação do processo;

> A Resolução preve que até 30 de junho de 2009, os tribunais devem encaminhar ao Conselho Nacional de Justiça, preferencialmente por meio eletrônico, relação das suas unidades de origem do processo (OOOO), com os respectivos códigos. Contudo, verifica-se que não há um uso correto do (OOOO) pelos tribunais.


> Pela Resolução, os tribunais devem disponibilizar a relação das unidades de origem do processo (OOOO) nos seus respectivos sítios na rede mundial de computadores (internet), mas isso não é obedecido.

