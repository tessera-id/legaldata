import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from legaldata.api import fetch_all
from legaldata.dashboard import serve
from legaldata.djen import fetch_djen
from legaldata.parser import parse_cnj
from legaldata.storage import save, djen_save

app = typer.Typer(
    name="legaldata",
    help=(
        "Coleta dados judiciais das APIs públicas do CNJ e persiste em DuckDB.\n\n"
        "[bold]APIs:[/bold]\n"
        "  [cyan]DataJud[/cyan]   processos, movimentos e assuntos\n"
        "  [cyan]DJEN[/cyan]      comunicações, partes e advogados"
    ),
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)
console = Console()


def _header() -> None:
    console.print(Panel.fit(
        "[bold cyan]Legaldata CLI[/bold cyan]  [dim]v0.2.0[/dim]\n"
        "[dim]DataJud · DJEN → DuckDB[/dim]",
        border_style="cyan",
    ))


def _read_csv(csv_path: Path) -> tuple[list[str], int]:
    seen: set[str] = set()
    numeros: list[str] = []
    total_lines = 0
    with open(csv_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            total_lines += 1
            if line not in seen:
                seen.add(line)
                numeros.append(line)
    duplicatas = total_lines - len(numeros)
    return numeros, duplicatas


def _already_fetched(output: Path) -> set[str]:
    if not output.exists():
        return set()
    con = duckdb.connect(str(output), read_only=True)
    rows = con.execute("SELECT DISTINCT processo FROM processos").fetchall()
    con.close()
    return {r[0] for r in rows if r[0]}


def _summary_table(output: Path) -> None:
    con = duckdb.connect(str(output), read_only=True)
    n_proc  = con.execute("SELECT COUNT(*) FROM processos").fetchone()[0]
    n_mov   = con.execute("SELECT COUNT(*) FROM movimentos").fetchone()[0]
    n_ass   = con.execute("SELECT COUNT(*) FROM assuntos").fetchone()[0]
    tribs   = con.execute("SELECT tribunal, COUNT(*) FROM processos GROUP BY 1 ORDER BY 2 DESC").fetchall()
    graus   = con.execute("SELECT grau, COUNT(*) FROM processos GROUP BY 1 ORDER BY 1").fetchall()
    con.close()

    t = Table(box=box.ROUNDED, border_style="green", show_header=False, padding=(0, 2))
    t.add_column(style="dim")
    t.add_column(style="bold green", justify="right")
    t.add_row("Processos salvos", str(n_proc))
    t.add_row("Movimentos",       str(n_mov))
    t.add_row("Assuntos",         str(n_ass))
    t.add_row("Tribunais",        "  ".join(f"[cyan]{r[0]}[/cyan]" for r in tribs))
    t.add_row("Graus",            "  ".join(f"[yellow]{r[0]}[/yellow] ({r[1]})" for r in graus))
    t.add_row("Arquivo",          f"[bold]{output}[/bold]")

    console.print(Panel(t, title="[bold green]Concluído[/bold green]", border_style="green", expand=False))


@app.command()
def datajud(
    numero: Optional[str] = typer.Argument(None, help="Número CNJ do processo (20 dígitos)"),
    csv: Optional[Path] = typer.Option(None, "--csv", "-c", help="CSV com um número por linha"),
    output: Path = typer.Option("legaldata.db", "--output", "-o", help="Arquivo DuckDB de saída"),
) -> None:
    """[bold]Busca processos[/bold] no DataJud e salva em DuckDB.

    \b
    Exemplos:
      legaldata datajud 00194332920248160001 -o resultado.db
      legaldata datajud --csv processos.csv -o resultado.db
    """
    _header()

    if not numero and not csv:
        console.print("[red]Erro:[/red] informe um número de processo ou [bold]--csv[/bold]")
        raise typer.Exit(1)
    if numero and csv:
        console.print("[red]Erro:[/red] use número OU [bold]--csv[/bold], não os dois")
        raise typer.Exit(1)

    numeros: list[str] = []
    duplicatas = 0

    if numero:
        numeros = [numero]
    else:
        if not csv.exists():
            console.print(f"[red]Erro:[/red] arquivo não encontrado: [bold]{csv}[/bold]")
            raise typer.Exit(1)
        numeros, duplicatas = _read_csv(csv)

    # Parâmetros da execução
    info = Table(box=None, show_header=False, padding=(0, 1))
    info.add_column(style="dim", width=12)
    info.add_column()
    if csv:
        info.add_row("Fonte", f"[bold]{csv}[/bold]")
    info.add_row("Saída",  f"[bold]{output}[/bold]")
    info.add_row("Lidos",  f"[bold]{len(numeros)}[/bold] número(s)" +
                 (f"  [dim]({duplicatas} duplicata(s) removida(s))[/dim]" if duplicatas else ""))
    console.print(info)
    console.print()

    # Validação + filtro de já processados
    existentes = {re.sub(r"\D", "", p) for p in _already_fetched(output)}

    validos: list[str] = []
    invalidos = 0
    ja_no_banco = 0
    for n in numeros:
        try:
            digits, _ = parse_cnj(n)
        except ValueError as e:
            console.print(f"  [yellow]⚠[/yellow]  {e}")
            invalidos += 1
            continue
        if digits in existentes:
            ja_no_banco += 1
            continue
        validos.append(n)

    if not validos:
        if ja_no_banco and not invalidos:
            console.print(f"[green]Todos os {ja_no_banco} processo(s) já estão no banco.[/green] Nada a buscar.")
            raise typer.Exit(0)
        console.print("[red]Nenhum número válido. Abortando.[/red]")
        raise typer.Exit(1)

    if invalidos:
        console.print(f"  [dim]{invalidos} número(s) inválido(s) ignorado(s)[/dim]")
    if ja_no_banco:
        console.print(f"  [dim]{ja_no_banco} já no banco (pulado(s))[/dim]")
    console.print()

    records = fetch_all(validos)

    if not records:
        console.print("\n[yellow]Nenhum processo encontrado na API.[/yellow]")
        raise typer.Exit(0)

    save(records, str(output))
    console.print()
    _summary_table(output)


@app.command()
def djen(
    db: Path = typer.Argument(..., help="Arquivo DuckDB existente (com tabela processos)"),
    csv: Optional[Path] = typer.Option(None, "--csv", "-c", help="CSV alternativo com números de processo"),
) -> None:
    """[bold]Busca comunicações do DJEN[/bold] e adiciona ao DuckDB.

    \b
    Lê os números de processo da tabela `processos` do DuckDB ou de um CSV.
    Adiciona as tabelas: comunicacoes, partes, advogados.

    \b
    Exemplos:
      legaldata djen resultado.db
      legaldata djen resultado.db --csv processos.csv
    """
    _header()

    if not db.exists():
        console.print(f"[red]Erro:[/red] arquivo não encontrado: [bold]{db}[/bold]")
        raise typer.Exit(1)

    if csv:
        if not csv.exists():
            console.print(f"[red]Erro:[/red] arquivo não encontrado: [bold]{csv}[/bold]")
            raise typer.Exit(1)
        numeros, duplicatas = _read_csv(csv)
    else:
        con = duckdb.connect(str(db), read_only=True)
        rows = con.execute("SELECT DISTINCT processo FROM processos").fetchall()
        con.close()
        numeros = [r[0] for r in rows if r[0]]
        duplicatas = 0

    info = Table(box=None, show_header=False, padding=(0, 1))
    info.add_column(style="dim", width=12)
    info.add_column()
    info.add_row("Banco",      f"[bold]{db}[/bold]")
    info.add_row("Processos",  f"[bold]{len(numeros)}[/bold] número(s)" +
                 (f"  [dim]({duplicatas} duplicata(s))[/dim]" if duplicatas else ""))
    console.print(info)
    console.print()

    if not numeros:
        console.print("[yellow]Nenhum número de processo encontrado.[/yellow]")
        raise typer.Exit(0)

    items = fetch_djen(numeros)

    if not items:
        console.print("\n[yellow]Nenhuma comunicação encontrada no DJEN.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[bold]{len(items)}[/bold] comunicação(ões) encontrada(s)\n")
    djen_save(items, str(db))

    # Resumo final
    con = duckdb.connect(str(db), read_only=True)
    n_comm = con.execute("SELECT COUNT(*) FROM comunicacoes").fetchone()[0]
    n_part = con.execute("SELECT COUNT(*) FROM partes").fetchone()[0]
    n_adv  = con.execute("SELECT COUNT(*) FROM advogados").fetchone()[0]
    con.close()

    t = Table(box=box.ROUNDED, border_style="green", show_header=False, padding=(0, 2))
    t.add_column(style="dim")
    t.add_column(style="bold green", justify="right")
    t.add_row("Comunicações", str(n_comm))
    t.add_row("Partes",       str(n_part))
    t.add_row("Advogados",    str(n_adv))
    t.add_row("Arquivo",      f"[bold]{db}[/bold]")
    console.print(Panel(t, title="[bold green]DJEN Concluído[/bold green]", border_style="green", expand=False))


TABELAS_DISPONIVEIS = (
    "processos", "movimentos", "assuntos",
    "comunicacoes", "partes", "advogados",
)


@app.command()
def exportar(
    tabela: str = typer.Argument(..., help="Tabela a exportar: " + ", ".join(TABELAS_DISPONIVEIS)),
    db: Path = typer.Argument(..., help="Arquivo DuckDB de origem"),
    destino: Optional[Path] = typer.Option(None, "--dir", "-d", help="Diretório de saída (padrão: diretório atual)"),
) -> None:
    """[bold]Exporta uma tabela[/bold] do DuckDB para CSV.

    \b
    Tabelas disponíveis:
      processos     — dados principais do processo
      movimentos    — histórico de movimentação
      assuntos      — assuntos do processo
      comunicacoes  — publicações do DJEN
      partes        — partes das comunicações DJEN
      advogados     — advogados das comunicações DJEN

    \b
    O arquivo gerado usa delimitador ";" e segue o padrão:
      <db>_<tabela>_YYYYMMDDHHMMSS.csv

    \b
    Exemplos:
      legaldata exportar processos resultado.db
      legaldata exportar movimentos resultado.db --dir ./exports
    """
    _header()

    if tabela not in TABELAS_DISPONIVEIS:
        console.print(f"[red]Erro:[/red] tabela inválida: [bold]{tabela}[/bold]")
        console.print(f"  Disponíveis: {', '.join(TABELAS_DISPONIVEIS)}")
        raise typer.Exit(1)

    if not db.exists():
        console.print(f"[red]Erro:[/red] arquivo não encontrado: [bold]{db}[/bold]")
        raise typer.Exit(1)

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    stem = db.stem
    fname = f"{stem}_{tabela}_{ts}.csv"
    out_dir = destino or Path(".")
    out_path = out_dir / fname

    con = duckdb.connect(str(db), read_only=True)

    # verifica se tabela existe no banco
    tabelas_existentes = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()}

    if tabela not in tabelas_existentes:
        con.close()
        console.print(f"[red]Erro:[/red] tabela [bold]{tabela}[/bold] não existe em [bold]{db}[/bold]")
        console.print(f"  Tabelas presentes: {', '.join(sorted(tabelas_existentes)) or 'nenhuma'}")
        raise typer.Exit(1)

    n_rows = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]

    info = Table(box=None, show_header=False, padding=(0, 1))
    info.add_column(style="dim", width=10)
    info.add_column()
    info.add_row("Banco",   f"[bold]{db}[/bold]")
    info.add_row("Tabela",  f"[bold]{tabela}[/bold]  [dim]({n_rows} linhas)[/dim]")
    info.add_row("Saída",   f"[bold]{out_path}[/bold]")
    console.print(info)
    console.print()

    con.execute(f"""
        COPY (SELECT * FROM {tabela})
        TO '{out_path.as_posix()}'
        (FORMAT CSV, HEADER, DELIMITER ';')
    """)
    con.close()

    console.print(f"[bold green]✓[/bold green] Exportado: [bold]{out_path}[/bold]  [dim]({n_rows} linhas)[/dim]")


@app.command()
def dashboard(
    db: Path = typer.Argument(..., help="Arquivo DuckDB"),
    port: int = typer.Option(8765, "--port", "-p", help="Porta HTTP"),
) -> None:
    """[bold]Abre dashboard[/bold] HTML com os dados do DuckDB."""
    _header()
    if not db.exists():
        console.print(f"[red]Erro:[/red] arquivo não encontrado: [bold]{db}[/bold]")
        raise typer.Exit(1)
    console.print(f"  Abrindo [bold]{db}[/bold] na porta [bold]{port}[/bold]...\n")
    serve(str(db), port)


if __name__ == "__main__":
    app()
