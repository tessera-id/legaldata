import duckdb
from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

from legaldata.helpers import safe_int, parse_date, parse_datetime


def save(records: list[dict], output_path: str) -> None:
    con = duckdb.connect(output_path)
    _create_tables(con)
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task(f"Salvando no DuckDB", total=len(records))
        _insert_records(con, records, progress, task)
    con.close()


def _create_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS processos (
            id                    VARCHAR PRIMARY KEY,
            processo              VARCHAR,
            classe_codigo         VARCHAR,
            classe_nome           VARCHAR,
            data_ajuizamento      DATE,
            orgao_codigo          INTEGER,
            orgao_nome            VARCHAR,
            orgao_codigo_ibge     INTEGER,
            tribunal              VARCHAR,
            grau                  VARCHAR,
            nivel_sigilo          INTEGER,
            data_atualizacao      TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS movimentos (
            id                           VARCHAR,
            movimento_seq                INTEGER,
            movimento_codigo             INTEGER,
            movimento_nome               VARCHAR,
            movimento_data               TIMESTAMP,
            movimento_complemento_codigo INTEGER,
            movimento_complemento_nome   VARCHAR,
            movimento_complemento_value  VARCHAR,
            PRIMARY KEY (id, movimento_seq)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS assuntos (
            id              VARCHAR,
            assunto_seq     INTEGER,
            assunto_codigo  INTEGER,
            assunto_nome    VARCHAR,
            principal       BOOLEAN,
            PRIMARY KEY (id, assunto_seq)
        )
    """)


def _insert_records(con: duckdb.DuckDBPyConnection, records: list[dict], progress, task) -> None:
    for rec in records:
        doc_id = rec.get("id", "")
        processo = rec.get("numeroProcesso", "")
        classe = rec.get("classe") or {}
        orgao = rec.get("orgaoJulgador") or {}

        con.execute(
            "INSERT OR REPLACE INTO processos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                doc_id,
                processo,
                str(classe.get("codigo", "") or ""),
                classe.get("nome"),
                parse_date(rec.get("dataAjuizamento")),
                safe_int(orgao.get("codigo")),
                orgao.get("nome"),
                safe_int(orgao.get("codigoMunicipioIBGE")),
                rec.get("tribunal"),
                rec.get("grau"),
                safe_int(rec.get("nivelSigilo")),
                parse_datetime(rec.get("dataHoraUltimaAtualizacao")),
            ],
        )

        movimentos = rec.get("movimentos") or []
        for seq, mov in enumerate(movimentos, start=1):
            complementos = (mov.get("complementosTabelados") or [{}])
            comp = complementos[0] if complementos else {}
            con.execute(
                "INSERT OR REPLACE INTO movimentos VALUES (?,?,?,?,?,?,?,?)",
                [
                    doc_id,
                    seq,
                    safe_int(mov.get("codigo")),
                    mov.get("nome"),
                    parse_datetime(mov.get("dataHora")),
                    safe_int(comp.get("codigo")),
                    comp.get("nome"),
                    comp.get("valor"),
                ],
            )

        assuntos = rec.get("assuntos") or []
        for seq, ass in enumerate(assuntos, start=1):
            con.execute(
                "INSERT OR REPLACE INTO assuntos VALUES (?,?,?,?,?)",
                [
                    doc_id,
                    seq,
                    safe_int(ass.get("codigo")),
                    ass.get("nome"),
                    bool(ass.get("principal", False)),
                ],
            )

        progress.advance(task)


# ─── DJEN ──────────────────────────────────────────────────────────────────

def djen_save(items: list[dict], db_path: str) -> None:
    """Abre o DuckDB existente e insere dados do DJEN (cria tabelas se necessário)."""
    con = duckdb.connect(db_path)
    _create_djen_tables(con)
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
    ) as progress:
        task = progress.add_task("Salvando DJEN no DuckDB", total=len(items))
        _insert_djen_records(con, items, progress, task)
    con.close()


def _create_djen_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS comunicacoes (
            id                    BIGINT PRIMARY KEY,
            processo              VARCHAR,
            classe_nome           VARCHAR,
            orgao_nome            VARCHAR,
            tribunal              VARCHAR,
            data_disponibilizacao DATE,
            texto                 VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS partes (
            comunicacao_id  BIGINT,
            processo        VARCHAR,
            parte_seq       INTEGER,
            polo            VARCHAR,
            nome            VARCHAR,
            PRIMARY KEY (comunicacao_id, parte_seq)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS advogados (
            comunicacao_id  BIGINT,
            processo        VARCHAR,
            advogado_seq    INTEGER,
            nome            VARCHAR,
            oab_numero      VARCHAR,
            oab_uf          VARCHAR,
            PRIMARY KEY (comunicacao_id, advogado_seq)
        )
    """)


def _insert_djen_records(
    con: duckdb.DuckDBPyConnection,
    items: list[dict],
    progress,
    task,
) -> None:
    from legaldata.djen import clean_html

    for item in items:
        comm_id = item.get("id")
        if not comm_id:
            progress.advance(task)
            continue

        data_raw = item.get("data_disponibilizacao") or ""
        data_disp = data_raw[:10] if len(data_raw) >= 10 else None

        processo = item.get("numero_processo")

        con.execute(
            "INSERT OR REPLACE INTO comunicacoes VALUES (?,?,?,?,?,?,?)",
            [
                comm_id,
                processo,
                item.get("nomeClasse"),
                item.get("nomeOrgao"),
                item.get("siglaTribunal"),
                data_disp,
                clean_html(item.get("texto")),
            ],
        )

        for seq, dest in enumerate(item.get("destinatarios") or [], start=1):
            con.execute(
                "INSERT OR REPLACE INTO partes VALUES (?,?,?,?,?)",
                [comm_id, processo, seq, dest.get("polo"), dest.get("nome")],
            )

        for seq, adv_dest in enumerate(item.get("destinatarioadvogados") or [], start=1):
            adv = adv_dest.get("advogado") or {}
            con.execute(
                "INSERT OR REPLACE INTO advogados VALUES (?,?,?,?,?,?)",
                [comm_id, processo, seq, adv.get("nome"), adv.get("numero_oab"), adv.get("uf_oab")],
            )

        progress.advance(task)
