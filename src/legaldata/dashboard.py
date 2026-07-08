import http.server
import threading
import webbrowser

import duckdb


def _q(con, sql, fallback=None):
    try:
        return con.execute(sql).fetchall()
    except Exception:
        return fallback or []


def _table(rows, headers):
    if not rows:
        return '<p class="text-muted small mb-0">Sem dados</p>'
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c or ''}</td>" for c in row) + "</tr>" for row in rows)
    return (
        '<table class="table table-sm table-striped table-hover mb-0">'
        f'<thead class="table-dark"><tr>{th}</tr></thead>'
        f"<tbody>{trs}</tbody></table>"
    )


def _stat(val, label, color):
    return (
        f'<div class="col-6 col-md-2"><div class="card p-3 text-center">'
        f'<div class="stat-val text-{color}">{val}</div>'
        f'<div class="text-muted small">{label}</div>'
        f"</div></div>"
    )


def generate_html(db_path: str) -> str:
    con = duckdb.connect(db_path, read_only=True)

    # DataJud
    total_proc  = _q(con, "SELECT COUNT(*) FROM processos")[0][0]
    total_mov   = _q(con, "SELECT COUNT(*) FROM movimentos")[0][0]
    total_ass   = _q(con, "SELECT COUNT(*) FROM assuntos")[0][0]
    n_tribunais = _q(con, "SELECT COUNT(DISTINCT tribunal) FROM processos")[0][0]

    by_tribunal = _q(con, "SELECT tribunal, COUNT(*) FROM processos GROUP BY 1 ORDER BY 2 DESC")
    by_grau     = _q(con, "SELECT COALESCE(grau,'?'), COUNT(*) FROM processos GROUP BY 1 ORDER BY 1")
    by_classe   = _q(con, "SELECT classe_nome, COUNT(*) FROM processos GROUP BY 1 ORDER BY 2 DESC LIMIT 15")
    top_assuntos = _q(con, "SELECT assunto_nome, COUNT(*) FROM assuntos GROUP BY 1 ORDER BY 2 DESC LIMIT 15")

    # DJEN (tabelas podem não existir)
    total_comm = _q(con, "SELECT COUNT(*) FROM comunicacoes", [(0,)])[0][0]
    total_part = _q(con, "SELECT COUNT(*) FROM partes",       [(0,)])[0][0]
    total_adv  = _q(con, "SELECT COUNT(*) FROM advogados",    [(0,)])[0][0]

    partes_ativo = _q(con, """
        SELECT nome, COUNT(DISTINCT processo) as processos
        FROM partes
        WHERE polo = 'A'
          AND nome IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 20
    """)

    partes_passivo = _q(con, """
        SELECT nome, COUNT(DISTINCT processo) as processos
        FROM partes
        WHERE polo = 'P'
          AND nome IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 20
    """)

    top_advogados = _q(con, """
        SELECT nome, oab_numero, oab_uf, COUNT(DISTINCT processo) as processos
        FROM advogados
        WHERE nome IS NOT NULL
        GROUP BY 1, 2, 3
        ORDER BY 4 DESC
        LIMIT 20
    """)

    com_por_tribunal = _q(con, """
        SELECT tribunal, COUNT(*) as total
        FROM comunicacoes
        WHERE tribunal IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """)

    baixa_definitiva = _q(con, """
        SELECT p.processo, p.tribunal, p.grau, MAX(m.movimento_data) AS data
        FROM processos p
        JOIN movimentos m ON m.id = p.id
        WHERE m.movimento_codigo = 22
        GROUP BY 1, 2, 3
        ORDER BY 4 DESC
    """)

    transito_julgado = _q(con, """
        SELECT p.processo, p.tribunal, p.grau, MAX(m.movimento_data) AS data
        FROM processos p
        JOIN movimentos m ON m.id = p.id
        WHERE m.movimento_codigo = 848
        GROUP BY 1, 2, 3
        ORDER BY 4 DESC
    """)

    con.close()

    trib_labels = str([r[0] for r in by_tribunal])
    trib_values = str([r[1] for r in by_tribunal])

    djen_section = ""
    if total_comm > 0:
        djen_section = f"""
  <hr class="my-4">
  <h5 class="mb-3 text-secondary">DJEN — Comunicações</h5>

  <div class="row g-3 mb-4">
    <div class="col-md-4"><div class="card p-3">
      <h6 class="mb-3">Por Tribunal</h6>
      {_table(com_por_tribunal, ["Tribunal", "Total"])}
    </div></div>
    <div class="col-md-4"><div class="card p-3">
      <h6 class="mb-3">Polo Ativo — top 20</h6>
      {_table(partes_ativo, ["Nome", "Processos"])}
    </div></div>
    <div class="col-md-4"><div class="card p-3">
      <h6 class="mb-3">Polo Passivo — top 20</h6>
      {_table(partes_passivo, ["Nome", "Processos"])}
    </div></div>
  </div>

  <div class="row g-3">
    <div class="col-12"><div class="card p-3">
      <h6 class="mb-3">Advogados — top 20 por processos</h6>
      {_table(top_advogados, ["Nome", "OAB", "UF", "Processos"])}
    </div></div>
  </div>
"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>DataJud — {db_path}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    body {{ background: #f0f2f5; }}
    .card {{ box-shadow: 0 1px 4px rgba(0,0,0,.1); border: none; }}
    .stat-val {{ font-size: 2rem; font-weight: 700; }}
  </style>
</head>
<body>
<div class="container-fluid py-4 px-4">
  <h3 class="mb-1">DataJud · DJEN <span class="text-muted fs-6 fw-normal">Dashboard</span></h3>
  <p class="text-muted small mb-4">{db_path}</p>

  <div class="row g-3 mb-4">
    {_stat(total_proc,  "Processos",     "primary")}
    {_stat(total_mov,   "Movimentos",    "secondary")}
    {_stat(total_ass,   "Assuntos",      "warning")}
    {_stat(n_tribunais, "Tribunais",     "danger")}
    {_stat(total_comm,  "Comunicações",  "info")}
    {_stat(total_adv,   "Advogados",     "success")}
  </div>

  <div class="row g-3 mb-4">
    <div class="col-md-8"><div class="card p-3">
      <h6 class="mb-3">Processos por Tribunal</h6>
      <canvas id="chartTrib" height="100"></canvas>
    </div></div>
    <div class="col-md-4"><div class="card p-3">
      <h6 class="mb-3">Por Grau</h6>
      {_table(by_grau, ["Grau", "Total"])}
    </div></div>
  </div>

  <div class="row g-3 mb-4">
    <div class="col-md-6"><div class="card p-3">
      <h6 class="mb-3">Classe Processual (top 15)</h6>
      {_table(by_classe, ["Classe", "Total"])}
    </div></div>
    <div class="col-md-6"><div class="card p-3">
      <h6 class="mb-3">Assuntos (top 15)</h6>
      {_table(top_assuntos, ["Assunto", "Total"])}
    </div></div>
  </div>

  {djen_section}

  <hr class="my-4">
  <h5 class="mb-3 text-secondary">Encerramento de Processos</h5>

  <div class="row g-3">
    <div class="col-md-6"><div class="card p-3">
      <h6 class="mb-1">Baixa Definitiva <span class="text-muted small">(movimento 22)</span></h6>
      <div class="stat-val text-danger mb-2">{len(baixa_definitiva)}</div>
      {_table(baixa_definitiva, ["Processo", "Tribunal", "Grau", "Data"])}
    </div></div>
    <div class="col-md-6"><div class="card p-3">
      <h6 class="mb-1">Trânsito em Julgado <span class="text-muted small">(movimento 848)</span></h6>
      <div class="stat-val text-success mb-2">{len(transito_julgado)}</div>
      {_table(transito_julgado, ["Processo", "Tribunal", "Grau", "Data"])}
    </div></div>
  </div>
</div>

<script>
new Chart(document.getElementById('chartTrib'), {{
  type: 'bar',
  data: {{
    labels: {trib_labels},
    datasets: [{{ label: 'Processos', data: {trib_values}, backgroundColor: 'rgba(13,110,253,0.75)' }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
}});
</script>
</body>
</html>"""


def serve(db_path: str, port: int = 8765) -> None:
    html = generate_html(db_path)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        def log_message(self, fmt, *args):
            pass

    url = f"http://localhost:{port}"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print(f"Dashboard em {url}  (Ctrl+C para sair)")
    try:
        http.server.HTTPServer(("127.0.0.1", port), _Handler).serve_forever()
    except KeyboardInterrupt:
        pass
