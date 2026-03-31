#!/usr/bin/env python3
import argparse
import html
import json
import sqlite3
from pathlib import Path

from review_event import build_report, is_near_threshold, load_event_rows, parse_env_file, parse_float, status_badge, threshold_hint


DEFAULT_DB = Path("volumes/faces/detections.db")
DEFAULT_OUTPUT_DIR = Path("volumes/faces/reviews")
DEFAULT_FRIGATE_BASE = "http://127.0.0.1:5000"
DEFAULT_COMPREFACE_BASE = "http://127.0.0.1:8088"
DEFAULT_ENV = Path(".env")


def display_value(value) -> str:
  if value in (None, ""):
    return "-"
  return str(value)


def load_recent_events(db_path: Path, limit: int):
  conn = sqlite3.connect(db_path)
  conn.row_factory = sqlite3.Row
  rows = conn.execute(
    """
    SELECT d.event_id,
         d.timestamp,
         d.camera,
         d.event_type,
         d.recognized_subject,
         d.recognition_confidence,
         d.compreface_status,
         d.compreface_candidates,
         d.snapshot_path,
         d.face_roi_path,
         d.occluded,
         d.face_detected
    FROM detections d
    INNER JOIN (
      SELECT event_id, MAX(id) AS max_id
      FROM detections
      GROUP BY event_id
    ) latest ON latest.max_id = d.id
    ORDER BY d.id DESC
    LIMIT ?
    """,
    (limit,),
  ).fetchall()
  conn.close()
  return rows


def maybe_image(path_value: str | None, output_dir: Path) -> str:
  if not path_value:
    return "<div class=\"thumb missing\">sem imagem</div>"
  image_path = Path(path_value.replace("/app/faces", "volumes/faces"))
  if not image_path.exists():
    return "<div class=\"thumb missing\">arquivo ausente</div>"
  relative = image_path.relative_to(output_dir.parent)
  return f'<img class="thumb" src="../{relative}" alt="snapshot">'


def top_candidate(raw: str | None) -> tuple[str | None, str | None]:
  if not raw:
    return None, None
  try:
    parsed = json.loads(raw)
  except json.JSONDecodeError:
    return None, None
  if not parsed:
    return None, None
  candidate = parsed[0]
  return candidate.get("subject"), candidate.get("similarity")


def outcome_text(row: sqlite3.Row, min_similarity: float) -> str:
  candidate_subject, candidate_similarity = top_candidate(row["compreface_candidates"])
  if row["recognized_subject"]:
    return f"{row['recognized_subject']} aceito com {row['recognition_confidence']}"
  if candidate_subject:
    if is_near_threshold(candidate_similarity, min_similarity):
      return f"Quase match: {candidate_subject} com {candidate_similarity}"
    return f"Melhor candidato {candidate_subject} com {candidate_similarity}"
  if row["occluded"]:
    return "Oclusao detectada"
  if not row["face_detected"]:
    return "Face nao detectada"
  return "Sem correspondencia"


def filter_options(rows, field: str) -> str:
  values = sorted({display_value(row[field]) for row in rows})
  return "".join(
    f'<option value="{html.escape(value)}">{html.escape(value)}</option>' for value in values
  )


def card_flag(row: sqlite3.Row, min_similarity: float) -> str:
  candidate_subject, candidate_similarity = top_candidate(row["compreface_candidates"])
  if candidate_subject and is_near_threshold(candidate_similarity, min_similarity):
    return '<span class="mini-chip mini-chip-warning">quase match</span>'
  if row["recognized_subject"]:
    return '<span class="mini-chip mini-chip-success">aceito</span>'
  return '<span class="mini-chip">revisar</span>'


def build_index(rows, output_dir: Path, min_similarity: float) -> Path:
  output_dir.mkdir(parents=True, exist_ok=True)
  cards = []
  for row in rows:
    report_name = f"{row['event_id']}.html"
    candidate_subject, candidate_similarity = top_candidate(row["compreface_candidates"])
    data_camera = html.escape(display_value(row["camera"]))
    data_status = html.escape(display_value(row["compreface_status"]))
    data_subject = html.escape(display_value(row["recognized_subject"] or candidate_subject))
    cards.append(
      """
      <article class="card" data-camera="{data_camera}" data-status="{data_status}" data-subject="{data_subject}">
        <a class=\"card-link\" href=\"{report_name}\">
        {thumb}
        <div class=\"content\">
          <div class=\"card-head\">
            <h2>{event_id}</h2>
            <div class="card-head-right">
              {flag}
              {badge}
            </div>
          </div>
          <p class=\"outcome\">{outcome}</p>
          <p class="candidate-note">{candidate_note}</p>
          <p><strong>camera:</strong> {camera}</p>
          <p><strong>timestamp:</strong> {timestamp}</p>
          <p><strong>event_type:</strong> {event_type}</p>
          <p><strong>recognized_subject:</strong> {recognized_subject}</p>
          <p><strong>recognition_confidence:</strong> {recognition_confidence}</p>
          <p><strong>compreface_status:</strong> {compreface_status}</p>
        </div>
        </a>
      </article>
      """.format(
        data_camera=data_camera,
        data_status=data_status,
        data_subject=data_subject,
        report_name=report_name,
        thumb=maybe_image(row["face_roi_path"] or row["snapshot_path"], output_dir),
        flag=card_flag(row, min_similarity),
        badge=status_badge(row["compreface_status"]),
        outcome=html.escape(outcome_text(row, min_similarity)),
        candidate_note=html.escape(threshold_hint(candidate_similarity, min_similarity) if candidate_subject else "sem candidato para comparar"),
        event_id=html.escape(str(row["event_id"])),
        camera=html.escape(display_value(row["camera"])),
        timestamp=html.escape(display_value(row["timestamp"])),
        event_type=html.escape(display_value(row["event_type"])),
        recognized_subject=html.escape(display_value(row["recognized_subject"])),
        recognition_confidence=html.escape(display_value(row["recognition_confidence"])),
        compreface_status=html.escape(display_value(row["compreface_status"])),
      )
    )

  html_doc = """
<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\">
  <title>Indice de Eventos</title>
  <style>
  :root {{
    --bg: radial-gradient(circle at top, #f8f2e8 0%, #efe3d0 42%, #ead8bf 100%);
    --surface: rgba(255, 252, 247, 0.94);
    --surface-strong: #fffdf8;
    --line: #dbcdb8;
    --text: #221b17;
    --muted: #6f655b;
    --accent: #23415f;
    --accent-soft: #dbe8f4;
    --shadow: 0 18px 42px rgba(84, 55, 30, 0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: Georgia, "Times New Roman", serif; margin: 0; padding: 24px; background: var(--bg); color: var(--text); }}
  h1, h2, strong, label, button {{ font-family: "Trebuchet MS", "Segoe UI", sans-serif; }}
  .page {{ max-width: 1440px; margin: 0 auto; }}
  .hero {{ background: var(--surface); border: 1px solid var(--line); border-radius: 24px; padding: 22px; box-shadow: var(--shadow); margin-bottom: 18px; }}
  h1 {{ margin: 0 0 10px; }}
  .hero p {{ margin: 0; color: var(--muted); max-width: 900px; }}
  .toolbar {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 18px; }}
  .filter {{ background: var(--surface-strong); border: 1px solid var(--line); border-radius: 16px; padding: 12px; }}
  .filter label {{ display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 6px; }}
  .filter select {{ width: 100%; border: 1px solid #ccbda7; border-radius: 10px; padding: 10px; background: #fff; color: var(--text); }}
  .summary-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
  .summary-pill {{ background: var(--surface-strong); border: 1px solid var(--line); border-radius: 999px; padding: 8px 12px; font-weight: 700; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
  .card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 18px; overflow: hidden; box-shadow: var(--shadow); }}
  .card-link {{ display: block; color: inherit; text-decoration: none; }}
  .content {{ padding: 14px; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: start; gap: 12px; }}
  .card-head-right {{ display: flex; flex-wrap: wrap; justify-content: end; gap: 8px; }}
  .thumb {{ display: block; width: 100%; height: 240px; object-fit: cover; background: #ddd; }}
  .missing {{ display: flex; align-items: center; justify-content: center; color: #666; }}
  .outcome {{ font-weight: 700; color: #294e43; font-size: 1.02rem; }}
  .candidate-note {{ color: var(--muted); }}
  .badge {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 6px 10px; font-size: 0.85rem; font-weight: 700; }}
  .badge-success {{ background: #d9f5df; color: #14532d; }}
  .badge-warning {{ background: #fff1bf; color: #8a4b00; }}
  .badge-danger {{ background: #ffd8d8; color: #7a1111; }}
  .badge-muted {{ background: #ece8de; color: #5e584d; }}
  .badge-default {{ background: #dde8f6; color: #23415f; }}
  .mini-chip {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 6px 10px; background: var(--accent-soft); color: var(--accent); font-size: 0.78rem; font-weight: 700; }}
  .mini-chip-success {{ background: #d9f5df; color: #14532d; }}
  .mini-chip-warning {{ background: #fff1bf; color: #8a4b00; }}
  .hidden {{ display: none !important; }}
  p {{ margin: 6px 0; }}
  @media (max-width: 900px) {{
    body {{ padding: 14px; }}
  }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>Indice de Eventos Recentes</h1>
      <p>Use os filtros para reduzir a revisao por camera, status ou sujeito. Eventos com candidato proximo do limiar ficam marcados como quase match.</p>
      <div class="summary-row">
        <span class="summary-pill">Limiar ativo: {min_similarity:.2f}</span>
        <span class="summary-pill">Faixa de revisao: {review_floor:.2f} ate {min_similarity:.2f}</span>
        <span class="summary-pill">Eventos listados: <span id="visible-count">{count}</span></span>
      </div>
      <div class="toolbar">
        <div class="filter">
          <label for="camera-filter">Camera</label>
          <select id="camera-filter">
            <option value="">Todas</option>
            {camera_options}
          </select>
        </div>
        <div class="filter">
          <label for="status-filter">Status</label>
          <select id="status-filter">
            <option value="">Todos</option>
            {status_options}
          </select>
        </div>
        <div class="filter">
          <label for="subject-filter">Sujeito</label>
          <select id="subject-filter">
            <option value="">Todos</option>
            {subject_options}
          </select>
        </div>
      </div>
    </section>
    <div class="grid" id="event-grid">{cards}</div>
  </div>
  <script>
    const cameraFilter = document.getElementById('camera-filter');
    const statusFilter = document.getElementById('status-filter');
    const subjectFilter = document.getElementById('subject-filter');
    const visibleCount = document.getElementById('visible-count');
    const cards = Array.from(document.querySelectorAll('.card'));

    function applyFilters() {{
      let count = 0;
      for (const card of cards) {{
        const matchesCamera = !cameraFilter.value || card.dataset.camera === cameraFilter.value;
        const matchesStatus = !statusFilter.value || card.dataset.status === statusFilter.value;
        const matchesSubject = !subjectFilter.value || card.dataset.subject === subjectFilter.value;
        const visible = matchesCamera && matchesStatus && matchesSubject;
        card.classList.toggle('hidden', !visible);
        if (visible) count += 1;
      }}
      visibleCount.textContent = String(count);
    }}

    cameraFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    subjectFilter.addEventListener('change', applyFilters);
    applyFilters();
  </script>
</body>
</html>
""".format(
    cards="".join(cards),
    min_similarity=min_similarity,
    review_floor=max(0.0, min_similarity - 0.10),
    count=len(rows),
    camera_options=filter_options(rows, "camera"),
    status_options=filter_options(rows, "compreface_status"),
    subject_options="".join(
      sorted({
        f'<option value="{html.escape(display_value(row["recognized_subject"] or top_candidate(row["compreface_candidates"])[0]))}">{html.escape(display_value(row["recognized_subject"] or top_candidate(row["compreface_candidates"])[0]))}</option>'
        for row in rows
      })
    ),
  )

  index_path = output_dir / "index.html"
  index_path.write_text(html_doc, encoding="utf-8")
  return index_path


def main():
  parser = argparse.ArgumentParser(description="Gera um indice HTML com os eventos recentes")
  parser.add_argument("--db", default=str(DEFAULT_DB), help="Caminho do detections.db")
  parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Pasta de saida dos relatorios")
  parser.add_argument("--limit", type=int, default=20, help="Quantidade de eventos no indice")
  parser.add_argument("--frigate-base", default=DEFAULT_FRIGATE_BASE, help="URL base do Frigate")
  parser.add_argument("--compreface-base", default=DEFAULT_COMPREFACE_BASE, help="URL base externa do CompreFace")
  parser.add_argument("--env-file", default=str(DEFAULT_ENV), help="Arquivo .env com a API key do CompreFace")
  args = parser.parse_args()

  env_values = parse_env_file(Path(args.env_file))
  api_key = env_values.get("COMPREFACE_API_KEY")
  min_similarity = parse_float(env_values.get("RECOGNITION_MIN_SIMILARITY")) or 0.75
  db_path = Path(args.db)
  output_dir = Path(args.output_dir)
  rows = load_recent_events(db_path, args.limit)

  for row in rows:
    event_id, event_rows = load_event_rows(db_path, row["event_id"])
    build_report(event_id, event_rows, output_dir, args.frigate_base, args.compreface_base, api_key, min_similarity)

  index_path = build_index(rows, output_dir, min_similarity)
  print(index_path)


if __name__ == "__main__":
  main()