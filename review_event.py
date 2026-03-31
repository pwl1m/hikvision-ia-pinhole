#!/usr/bin/env python3
import argparse
import html
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_DB = Path("volumes/faces/detections.db")
DEFAULT_OUTPUT_DIR = Path("volumes/faces/reviews")
DEFAULT_FRIGATE_BASE = "http://127.0.0.1:5000"
DEFAULT_COMPREFACE_BASE = "http://127.0.0.1:8088"
DEFAULT_ENV = Path(".env")
NEAR_THRESHOLD_MARGIN = 0.10

STATUS_META = {
    "matched": ("badge-success", "Match aceito"),
    "below_threshold": ("badge-warning", "Match rejeitado por limiar"),
    "no_match": ("badge-muted", "Sem match"),
    "no_subjects": ("badge-muted", "Sem subjects"),
    "skipped_event_type": ("badge-muted", "Ignorado pela estrategia"),
    "timeout": ("badge-danger", "Timeout no CompreFace"),
    "error": ("badge-danger", "Erro na comparacao"),
    "api_key_missing": ("badge-danger", "API key ausente"),
}


def parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_event_rows(db_path: Path, event_id: str | None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if event_id:
        rows = conn.execute(
            "SELECT * FROM detections WHERE event_id = ? ORDER BY id ASC",
            (event_id,),
        ).fetchall()
    else:
        latest = conn.execute(
            "SELECT event_id FROM detections ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            conn.close()
            raise SystemExit("Nenhum registro encontrado em detections.db")
        event_id = latest["event_id"]
        rows = conn.execute(
            "SELECT * FROM detections WHERE event_id = ? ORDER BY id ASC",
            (event_id,),
        ).fetchall()

    conn.close()

    if not rows:
        raise SystemExit(f"Nenhum registro encontrado para event_id={event_id}")

    return event_id, rows


def parse_candidates(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def format_response(raw: str | None) -> str:
    if not raw:
        return "resposta nao disponivel"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def local_face_path(maybe_path: str | None) -> Path | None:
    if not maybe_path:
        return None
    path = Path(maybe_path.replace("/app/faces", "volumes/faces"))
    return path if path.exists() else None


def relative_asset(report_path: Path, asset_path: Path) -> str:
    return str(asset_path.relative_to(report_path.parent.parent)).replace("\\", "/")


def image_panel_html(report_path: Path, maybe_path: str | None, label: str) -> str:
    image_path = local_face_path(maybe_path)
    if image_path is None:
        return f"<div class=\"panel missing\"><p><strong>{html.escape(label)}:</strong> nao disponivel</p></div>"

    relative = relative_asset(report_path, image_path)
    return (
        f"<div class=\"panel\">"
        f"<p><strong>{html.escape(label)}:</strong> {html.escape(str(image_path))}</p>"
        f"<img src=\"../{html.escape(relative)}\" alt=\"{html.escape(label)}\">"
        f"</div>"
    )


def display_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bytes):
        if value in (b"\x00", b"0"):
            return "0"
        if value in (b"\x01", b"1"):
            return "1"
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return repr(value)
    return str(value)


def parse_float(value) -> float | None:
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def is_near_threshold(similarity, min_similarity: float) -> bool:
    numeric = parse_float(similarity)
    if numeric is None:
        return False
    return max(0.0, min_similarity - NEAR_THRESHOLD_MARGIN) <= numeric < min_similarity


def candidate_tone(similarity, min_similarity: float) -> tuple[str, str]:
    numeric = parse_float(similarity)
    if numeric is None:
        return "candidate-card-neutral", "similaridade indisponivel"
    if numeric >= min_similarity:
        return "candidate-card-accepted", "acima do limiar"
    if is_near_threshold(numeric, min_similarity):
        return "candidate-card-near", "proximo do limiar"
    return "candidate-card-rejected", "abaixo do limiar"


def threshold_hint(similarity, min_similarity: float) -> str:
    numeric = parse_float(similarity)
    if numeric is None:
        return "sem similaridade"
    delta = numeric - min_similarity
    if delta >= 0:
        return f"{numeric:.5f} >= {min_similarity:.2f}"
    return f"{numeric:.5f} ficou {abs(delta):.5f} abaixo do limiar {min_similarity:.2f}"


def status_badge(status: str | None) -> str:
    css_class, label = STATUS_META.get(status or "", ("badge-default", status or "sem status"))
    return f'<span class="badge {css_class}">{html.escape(label)}</span>'


def fetch_subject_faces(subject: str, api_key: str, compreface_base: str) -> list[dict]:
    query = urllib.parse.urlencode({"subject": subject, "page": 0, "size": 15})
    url = f"{compreface_base}/api/v1/recognition/faces?{query}"
    request = urllib.request.Request(url, headers={"x-api-key": api_key})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("faces", [])


def download_reference_image(subject: str, image_id: str, api_key: str, compreface_base: str, output_dir: Path) -> Path | None:
    cache_dir = output_dir / "reference-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{subject}_{image_id}.jpg"
    if target.exists():
        return target

    url = f"{compreface_base}/api/v1/recognition/faces/{image_id}/img"
    request = urllib.request.Request(url, headers={"x-api-key": api_key})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
        return target
    except (urllib.error.URLError, TimeoutError):
        return None


def reference_image_for_subject(subject: str | None, api_key: str | None, compreface_base: str, output_dir: Path) -> tuple[Path | None, str | None]:
    if not subject or not api_key:
        return None, None
    try:
        faces = fetch_subject_faces(subject, api_key, compreface_base)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, None
    if not faces:
        return None, None
    image_id = faces[0].get("image_id")
    if not image_id:
        return None, None
    return download_reference_image(subject, image_id, api_key, compreface_base, output_dir), image_id


def candidate_cards_html(candidates: list[dict], api_key: str | None, compreface_base: str, output_dir: Path, report_path: Path, min_similarity: float) -> str:
    if not candidates:
        return "<p class=\"muted\">Nenhum candidato retornado pelo CompreFace.</p>"

    cards: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        subject = candidate.get("subject")
        similarity = candidate.get("similarity")
        tone_class, tone_label = candidate_tone(similarity, min_similarity)
        ref_path, image_id = reference_image_for_subject(subject, api_key, compreface_base, output_dir)
        preview_html = '<div class="candidate-preview missing">sem referencia local</div>'
        if ref_path is not None:
            relative = relative_asset(report_path, ref_path)
            preview_html = f'<img class="candidate-preview" src="../{html.escape(relative)}" alt="Referencia {html.escape(str(subject))}">' 
        cards.append(
            """
                        <article class="candidate-card {tone_class}">
                            <div class="candidate-head">
                                <p class="candidate-rank">Candidato {index}</p>
                                <span class="mini-chip">{tone_label}</span>
                            </div>
              {preview_html}
              <p><strong>subject:</strong> {subject}</p>
              <p><strong>similarity:</strong> {similarity}</p>
                            <p><strong>avaliacao:</strong> {threshold_hint}</p>
              <p><strong>image_id:</strong> {image_id}</p>
            </article>
            """.format(
                index=index,
                                tone_class=tone_class,
                                tone_label=html.escape(tone_label),
                preview_html=preview_html,
                subject=html.escape(str(subject)),
                similarity=html.escape(str(similarity)),
                                threshold_hint=html.escape(threshold_hint(similarity, min_similarity)),
                image_id=html.escape(str(image_id or "nao encontrado")),
            )
        )
    return f"<div class=\"candidate-grid\">{''.join(cards)}</div>"


def decision_summary(row: sqlite3.Row, candidates: list[dict], min_similarity: float) -> str:
    status = row["compreface_status"] or "sem status"
    if row["recognized_subject"]:
        return f"Subject {row['recognized_subject']} aceito com similaridade {row['recognition_confidence']}"
    if candidates:
        best = candidates[0]
        if is_near_threshold(best.get("similarity"), min_similarity):
            return f"Melhor candidato: {best.get('subject')} ficou proximo do limiar com similarity {best.get('similarity')} e status {status}"
        return f"Melhor candidato: {best.get('subject')} com similarity {best.get('similarity')} e status {status}"
    if row["face_detected"] and not row["occluded"]:
        return f"Nenhum candidato aceito. Status: {status}"
    return f"Status: {status}"


def summary_metrics(row: sqlite3.Row, candidates: list[dict], min_similarity: float) -> str:
    best_similarity = candidates[0].get("similarity") if candidates else None
    near_flag = "sim" if candidates and is_near_threshold(best_similarity, min_similarity) else "nao"
    return (
        '<div class="metric-row">'
        f'<div class="metric"><span>Limiar ativo</span><strong>{min_similarity:.2f}</strong></div>'
        f'<div class="metric"><span>Melhor similarity</span><strong>{display_value(best_similarity)}</strong></div>'
        f'<div class="metric"><span>Quase match</span><strong>{near_flag}</strong></div>'
        f'<div class="metric"><span>Candidatos</span><strong>{len(candidates)}</strong></div>'
        '</div>'
    )


def reference_panel_html(subject: str | None, api_key: str | None, compreface_base: str, output_dir: Path, report_path: Path) -> str:
    ref_path, image_id = reference_image_for_subject(subject, api_key, compreface_base, output_dir)
    if ref_path is None:
        return '<div class="panel missing"><p><strong>Referencia do cadastro:</strong> nao disponivel</p></div>'
    relative = relative_asset(report_path, ref_path)
    return (
        '<div class="panel">'
        f'<p><strong>Referencia do cadastro:</strong> subject={html.escape(str(subject))}</p>'
        f'<p><strong>image_id:</strong> {html.escape(str(image_id or ""))}</p>'
        f'<img src="../{html.escape(relative)}" alt="Referencia do cadastro">'
        '</div>'
    )


def build_report(event_id: str, rows, output_dir: Path, frigate_base: str, compreface_base: str, api_key: str | None, min_similarity: float) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{event_id}.html"

    clip_url = f"{frigate_base}/api/events/{event_id}/clip.mp4"
    snapshot_url = f"{frigate_base}/api/events/{event_id}/snapshot.jpg"

    latest_row = rows[-1]
    latest_candidates = parse_candidates(latest_row["compreface_candidates"])
    summary_subject = latest_row["recognized_subject"] or (latest_candidates[0].get("subject") if latest_candidates else None)

    attempts_html = []
    for row in rows:
        candidates = parse_candidates(row["compreface_candidates"])
        comparison_subject = row["recognized_subject"] or (candidates[0].get("subject") if candidates else None)
        attempts_html.append(
            """
            <section class=\"attempt\">
              <div class=\"attempt-header\">
                <h2>Tentativa</h2>
                {badge}
              </div>
              <p class=\"decision\">{decision}</p>
              <div class=\"meta\">
                <p><strong>timestamp:</strong> {timestamp}</p>
                <p><strong>event_type:</strong> {event_type}</p>
                <p><strong>face_detected:</strong> {face_detected}</p>
                <p><strong>occluded:</strong> {occluded}</p>
                <p><strong>occlusion_type:</strong> {occlusion_type}</p>
                <p><strong>face_confidence:</strong> {confidence}</p>
                <p><strong>recognized_subject:</strong> {recognized_subject}</p>
                <p><strong>recognition_confidence:</strong> {recognition_confidence}</p>
                <p><strong>compreface_status:</strong> {compreface_status}</p>
              </div>
              <div class=\"image-grid\">
                {snapshot_html}
                {face_html}
                {reference_html}
              </div>
              <div class=\"candidate-section\">
                <h3>Candidatos do CompreFace</h3>
                {candidates_html}
              </div>
              <details>
                <summary>Resposta da comparacao</summary>
                <pre>{response}</pre>
              </details>
            </section>
            """.format(
                badge=status_badge(row["compreface_status"]),
                decision=html.escape(decision_summary(row, candidates, min_similarity)),
                timestamp=html.escape(display_value(row["timestamp"])),
                event_type=html.escape(display_value(row["event_type"])),
                face_detected=html.escape(display_value(row["face_detected"])),
                occluded=html.escape(display_value(row["occluded"])),
                occlusion_type=html.escape(display_value(row["occlusion_type"])),
                confidence=html.escape(display_value(row["confidence"])),
                recognized_subject=html.escape(display_value(row["recognized_subject"])),
                recognition_confidence=html.escape(display_value(row["recognition_confidence"])),
                compreface_status=html.escape(display_value(row["compreface_status"])),
                snapshot_html=image_panel_html(report_path, row["snapshot_path"], "Frame salvo"),
                face_html=image_panel_html(report_path, row["face_roi_path"], "Recorte da face usado na comparacao"),
                reference_html=reference_panel_html(comparison_subject, api_key, compreface_base, output_dir, report_path),
                candidates_html=candidate_cards_html(candidates, api_key, compreface_base, output_dir, report_path, min_similarity),
                response=html.escape(format_response(row["compreface_response"])),
            )
        )

        report = f"""
<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
    <meta charset=\"utf-8\">
    <title>Review do Evento {html.escape(event_id)}</title>
    <style>
        :root {{
            --bg: linear-gradient(180deg, #f7f1e8 0%, #efe3d0 100%);
            --surface: rgba(255, 252, 247, 0.92);
            --surface-strong: #fffdf9;
            --text: #1f1a17;
            --muted: #6f655b;
            --line: #dbcdb8;
            --accent: #23415f;
            --accent-soft: #dbe8f4;
            --ok-bg: #d9f5df;
            --ok-text: #14532d;
            --warn-bg: #fff1bf;
            --warn-text: #8a4b00;
            --danger-bg: #ffd8d8;
            --danger-text: #7a1111;
            --shadow: 0 20px 45px rgba(72, 47, 24, 0.08);
        }}
        * {{ box-sizing: border-box; }}
        body {{ font-family: Georgia, "Times New Roman", serif; margin: 0; padding: 24px; background: var(--bg); color: var(--text); }}
        h1, h2, h3, strong {{ font-family: "Trebuchet MS", "Segoe UI", sans-serif; }}
        h1, h2, h3 {{ margin-bottom: 8px; }}
        .page {{ max-width: 1440px; margin: 0 auto; }}
        .summary, .attempt {{ background: var(--surface); border: 1px solid var(--line); border-radius: 20px; padding: 20px; margin-bottom: 18px; box-shadow: var(--shadow); backdrop-filter: blur(6px); }}
        .hero {{ display: grid; grid-template-columns: 1.4fr 0.9fr; gap: 16px; align-items: start; }}
        .hero-copy p {{ margin-top: 0; }}
        .summary-grid, .meta {{ display: grid; gap: 8px; }}
        .summary-grid {{ grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-top: 14px; }}
        .attempt-header {{ display: flex; justify-content: space-between; align-items: start; gap: 12px; }}
        .decision {{ font-size: 1.05rem; font-weight: 700; color: #2e4e45; }}
        .metric-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }}
        .metric {{ background: var(--surface-strong); border: 1px solid var(--line); border-radius: 14px; padding: 12px; }}
        .metric span {{ display: block; color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }}
        .metric strong {{ font-size: 1.05rem; }}
        .image-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 16px; }}
        .panel {{ background: var(--surface-strong); border: 1px solid #e3ddd2; border-radius: 16px; padding: 14px; }}
        .panel.missing {{ color: var(--muted); display: flex; align-items: center; }}
        .candidate-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 12px 0; }}
        .candidate-card {{ background: #f8fbff; border: 1px solid #c8d9ee; border-radius: 16px; padding: 12px; }}
        .candidate-card-accepted {{ border-color: #84c394; background: #effaf2; }}
        .candidate-card-near {{ border-color: #e0b52a; background: #fff9e8; }}
        .candidate-card-rejected {{ border-color: #d9d2c9; background: #f8f5f1; }}
        .candidate-card-neutral {{ border-color: #c8d9ee; background: #f8fbff; }}
        .candidate-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }}
        .candidate-rank {{ margin: 0; font-weight: 700; color: #0b5cad; }}
        .candidate-preview {{ width: 100%; height: 160px; object-fit: cover; border-radius: 8px; border: 1px solid #d7d0c4; margin-bottom: 10px; background: #eee; }}
        .candidate-preview.missing {{ display: flex; align-items: center; justify-content: center; color: var(--muted); }}
        .muted {{ color: var(--muted); }}
        .badge {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 6px 10px; font-size: 0.9rem; font-weight: 700; }}
        .badge-success {{ background: var(--ok-bg); color: var(--ok-text); }}
        .badge-warning {{ background: var(--warn-bg); color: var(--warn-text); }}
        .badge-danger {{ background: var(--danger-bg); color: var(--danger-text); }}
        .badge-muted {{ background: #ece8de; color: #5e584d; }}
        .badge-default {{ background: var(--accent-soft); color: var(--accent); }}
        .mini-chip {{ display: inline-flex; border-radius: 999px; padding: 5px 9px; background: var(--accent-soft); color: var(--accent); font-size: 0.78rem; font-weight: 700; }}
        img {{ max-width: 100%; border-radius: 8px; border: 1px solid #d7d0c4; }}
        pre {{ background: #222; color: #f5f5f5; padding: 12px; border-radius: 8px; overflow-x: auto; }}
        a {{ color: #0b5cad; }}
        details {{ margin-top: 12px; }}
        summary {{ cursor: pointer; font-weight: 700; }}
        video {{ width: 100%; max-width: 960px; border-radius: 8px; border: 1px solid #d7d0c4; background: #000; margin-top: 16px; }}
        @media (max-width: 900px) {{
            .hero {{ grid-template-columns: 1fr; }}
            body {{ padding: 14px; }}
        }}
    </style>
</head>
<body>
    <div class=\"page\">
        <section class=\"summary\">
            <div class=\"hero\">
                <div class=\"hero-copy\">
                    <div class=\"attempt-header\">
                        <h1>Review do Evento {html.escape(event_id)}</h1>
                        {status_badge(latest_row['compreface_status'])}
                    </div>
                    <p class=\"decision\">{html.escape(decision_summary(latest_row, latest_candidates, min_similarity))}</p>
                    <div class=\"summary-grid\">
                        <p><strong>camera:</strong> {html.escape(display_value(latest_row['camera']))}</p>
                        <p><strong>event_type final:</strong> {html.escape(display_value(latest_row['event_type']))}</p>
                        <p><strong>subject final:</strong> {html.escape(display_value(summary_subject))}</p>
                        <p><strong>snapshot do Frigate:</strong> <a href=\"{html.escape(snapshot_url)}\">abrir snapshot</a></p>
                        <p><strong>clip do Frigate:</strong> <a href=\"{html.escape(clip_url)}\">abrir clip</a></p>
                    </div>
                </div>
                {summary_metrics(latest_row, latest_candidates, min_similarity)}
            </div>
            <video controls src=\"{html.escape(clip_url)}\"></video>
        </section>
        {''.join(attempts_html)}
    </div>
</body>
</html>
"""

    report_path.write_text(report, encoding="utf-8")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Gera um relatorio visual de um evento detectado")
    parser.add_argument("event_id", nargs="?", help="Event ID do Frigate")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Caminho do detections.db")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Pasta de saida dos relatorios")
    parser.add_argument("--frigate-base", default=DEFAULT_FRIGATE_BASE, help="URL base do Frigate")
    parser.add_argument("--compreface-base", default=DEFAULT_COMPREFACE_BASE, help="URL base externa do CompreFace")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV), help="Arquivo .env com a API key do CompreFace")
    args = parser.parse_args()

    env_values = parse_env_file(Path(args.env_file))
    api_key = env_values.get("COMPREFACE_API_KEY")
    min_similarity = parse_float(env_values.get("RECOGNITION_MIN_SIMILARITY")) or 0.75
    db_path = Path(args.db)
    output_dir = Path(args.output_dir)
    event_id, rows = load_event_rows(db_path, args.event_id)
    report_path = build_report(event_id, rows, output_dir, args.frigate_base, args.compreface_base, api_key, min_similarity)
    print(report_path)


if __name__ == "__main__":
    main()