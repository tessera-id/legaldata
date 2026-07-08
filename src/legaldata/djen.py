import re
import time
from html import unescape

import httpx
from rich.progress import Progress, SpinnerColumn, BarColumn, MofNCompleteColumn, TextColumn

DJEN_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
DJEN_HEADERS = {"accept": "application/json"}
REQUEST_DELAY = 1.0   # segundos entre requests (rate limit público)
RETRY_WAIT    = 60    # segundos ao receber 429


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _get(numero: str) -> list[dict]:
    try:
        resp = httpx.get(
            DJEN_URL,
            params={"numeroProcesso": numero},
            headers=DJEN_HEADERS,
            timeout=30,
        )
    except (httpx.TimeoutException, httpx.RequestError):
        return []

    if resp.status_code == 200:
        return resp.json().get("items", []) or []

    if resp.status_code == 429:
        time.sleep(RETRY_WAIT)
        return _get(numero)

    return []


def fetch_djen(numeros: list[str]) -> list[dict]:
    """Consulta o DJEN para cada número de processo e retorna todos os itens."""
    all_items: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[green]{task.fields[found]} comunicações"),
    ) as progress:
        task = progress.add_task(
            f"DJEN — {len(numeros)} processo(s)",
            total=len(numeros),
            found=0,
        )
        for i, numero in enumerate(numeros):
            if i > 0:
                time.sleep(REQUEST_DELAY)
            items = _get(numero)
            all_items.extend(items)
            progress.update(task, advance=1, found=len(all_items))

    return all_items
