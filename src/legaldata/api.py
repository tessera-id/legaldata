import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

from legaldata.parser import parse_cnj

API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
BASE_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search"
HEADERS = {"Authorization": f"ApiKey {API_KEY}", "Content-Type": "application/json"}
MAX_WORKERS = 30
RETRY_WORKERS = 5
RETRY_WAIT = 15  # segundos antes do segundo passe


def _build_query(digits: str) -> dict:
    return {"query": {"match": {"numeroProcesso": digits}}}


def _fetch_one(tribunal: str, digits: str, retries: int = 3, base_delay: int = 2) -> list[dict]:
    url = BASE_URL.format(tribunal=tribunal)
    delay = base_delay

    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(url, headers=HEADERS, json=_build_query(digits), timeout=60)
        except (httpx.TimeoutException, httpx.RequestError) as e:
            if attempt == retries:
                raise RuntimeError(f"{tribunal}/{digits}: {e}") from e
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 200:
            return [hit["_source"] for hit in resp.json().get("hits", {}).get("hits", [])]

        if resp.status_code in (429, 503) or resp.status_code >= 500:
            if attempt == retries:
                raise RuntimeError(f"{tribunal}/{digits}: HTTP {resp.status_code} após {retries} tentativas")
            time.sleep(delay)
            delay *= 2
            continue

        raise RuntimeError(f"{tribunal}/{digits}: HTTP {resp.status_code} — {resp.text[:200]}")

    raise RuntimeError(f"{tribunal}/{digits}: máximo de tentativas excedido")


def _run_pass(
    tasks: list[tuple[str, str]],
    workers: int,
    base_delay: int,
    progress,
    task_id,
    found_ref: list[int],
) -> tuple[list[dict], list[tuple[str, str]]]:
    records: list[dict] = []
    failed: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_fetch_one, t, d, 3, base_delay): (t, d)
            for t, d in tasks
        }
        for future in as_completed(futures):
            tribunal, digits = futures[future]
            try:
                batch = future.result()
                found_ref[0] += len(batch)
                records.extend(batch)
            except RuntimeError:
                failed.append((tribunal, digits))
            progress.update(task_id, advance=1, found=found_ref[0])

    return records, failed


def fetch_all(numeros: list[str]) -> list[dict]:
    tasks: list[tuple[str, str]] = []
    for numero in numeros:
        digits, tribunal = parse_cnj(numero)
        tasks.append((tribunal, digits))

    records: list[dict] = []
    found_ref = [0]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[green]{task.fields[found]} encontrados"),
    ) as progress:
        task_id = progress.add_task(
            f"Consultando {len(tasks)} processo(s)",
            total=len(tasks),
            found=0,
        )

        batch, failed = _run_pass(tasks, MAX_WORKERS, 2, progress, task_id, found_ref)
        records.extend(batch)

        if failed:
            progress.console.print(
                f"[yellow]{len(failed)} falhos — aguardando {RETRY_WAIT}s e retentando com {RETRY_WORKERS} workers...[/yellow]"
            )
            time.sleep(RETRY_WAIT)

            progress.reset(task_id, total=len(failed), description=f"Retry {len(failed)} processo(s)")
            found_ref = [0]

            batch2, still_failed = _run_pass(failed, RETRY_WORKERS, 5, progress, task_id, found_ref)
            records.extend(batch2)

            for tribunal, digits in still_failed:
                progress.console.print(f"[red]falhou definitivamente: {tribunal}/{digits}[/red]")

    return records
