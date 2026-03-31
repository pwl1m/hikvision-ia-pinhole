#!/usr/bin/env python3
"""
Orquestrador de Detecção de Oclusão e Reconhecimento Facial
Integra Frigate, CompreFace e MediaPipe
"""

import os
import json
import logging
import sqlite3
import time
import requests
import cv2
import numpy as np
import mediapipe as mp
import paho.mqtt.client as mqtt
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

# ============================================
# CONFIGURAÇÕES
# ============================================
FRIGATE_URL = os.getenv("FRIGATE_URL", "http://frigate:5000")
COMPREFACE_URL = os.getenv("COMPREFACE_URL", "http://compreface")
COMPREFACE_API_KEY = os.getenv("COMPREFACE_API_KEY")
COMPREFACE_TIMEOUT = int(os.getenv("COMPREFACE_TIMEOUT", 30))
COMPREFACE_RETRIES = int(os.getenv("COMPREFACE_RETRIES", 2))
RECOGNITION_MIN_SIMILARITY = float(os.getenv("RECOGNITION_MIN_SIMILARITY", 0.75))
RECOGNITION_PREDICTION_COUNT = int(os.getenv("RECOGNITION_PREDICTION_COUNT", 3))
RECOGNITION_EVENT_TYPES = {
    event_type.strip()
    for event_type in os.getenv("RECOGNITION_EVENT_TYPES", "end").split(",")
    if event_type.strip()
}
COMPREFACE_DETECT_FACES = os.getenv("COMPREFACE_DETECT_FACES", "false").lower() in {"1", "true", "yes", "on"}
AUTO_REGISTER_UNKNOWN = os.getenv("AUTO_REGISTER_UNKNOWN", "false").lower() in {"1", "true", "yes", "on"}
UNKNOWN_SUBJECT_PREFIX = os.getenv("UNKNOWN_SUBJECT_PREFIX", "unknown_auto_")
UNKNOWN_ONLY_ON_EVENT_TYPE = os.getenv("UNKNOWN_ONLY_ON_EVENT_TYPE", "end")
UNKNOWN_MIN_FACE_CONFIDENCE = float(os.getenv("UNKNOWN_MIN_FACE_CONFIDENCE", 0.8))
UNKNOWN_DET_PROB_THRESHOLD = float(os.getenv("UNKNOWN_DET_PROB_THRESHOLD", 0.8))
MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "frigate/events")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
STORAGE_PATH = Path("/app/faces")
LOGS_PATH = Path("/app/logs")

# Configura logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("occlusion-detector")

# Cria diretórios
STORAGE_PATH.mkdir(parents=True, exist_ok=True)
LOGS_PATH.mkdir(parents=True, exist_ok=True)

# ============================================
# BANCO DE DADOS SQLITE
# ============================================
DB_PATH = STORAGE_PATH / "detections.db"


def ensure_column(cursor, name: str, definition: str):
    """Adiciona colunas novas sem recriar a tabela existente."""
    columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(detections)").fetchall()
    }
    if name not in columns:
        cursor.execute(f"ALTER TABLE detections ADD COLUMN {name} {definition}")


def init_db():
    """Inicializa banco de dados SQLite"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            camera TEXT,
            event_id TEXT,
            face_detected BOOLEAN,
            occluded BOOLEAN,
            occlusion_type TEXT,
            confidence REAL,
            recognized_subject TEXT,
            recognition_confidence REAL,
            snapshot_path TEXT
        )
    ''')
    ensure_column(c, "event_type", "TEXT")
    ensure_column(c, "face_roi_path", "TEXT")
    ensure_column(c, "compreface_status", "TEXT")
    ensure_column(c, "compreface_candidates", "TEXT")
    ensure_column(c, "compreface_response", "TEXT")
    c.execute('''
        CREATE TABLE IF NOT EXISTS unknown_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT UNIQUE,
            created_at TEXT,
            last_seen_at TEXT,
            sightings INTEGER DEFAULT 1,
            last_event_id TEXT,
            best_face_path TEXT,
            source_camera TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Banco de dados inicializado em %s", DB_PATH)


# ============================================
# MEDIAPIPE - DETECÇÃO FACIAL
# ============================================
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(
    model_selection=1,  # 0: rostos próximos, 1: rostos distantes
    min_detection_confidence=0.5
)


def extract_face_roi(image: np.ndarray) -> Tuple[Optional[np.ndarray], float]:
    """Extrai o rosto principal com uma pequena margem para melhorar o reconhecimento."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_detection.process(rgb)

    if not results.detections:
        return None, 0.0

    detection = results.detections[0]
    bbox = detection.location_data.relative_bounding_box
    height, width, _ = image.shape
    x = int(bbox.xmin * width)
    y = int(bbox.ymin * height)
    face_width = int(bbox.width * width)
    face_height = int(bbox.height * height)

    pad_x = int(face_width * 0.15)
    pad_y = int(face_height * 0.15)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(width, x + face_width + pad_x)
    y2 = min(height, y + face_height + pad_y)

    face_roi = image[y1:y2, x1:x2]
    if face_roi.size == 0:
        return None, detection.score[0]

    return face_roi, detection.score[0]


def analyze_face_occlusion(image: np.ndarray) -> Tuple[bool, bool, Optional[str], float]:
    """
    Analisa se há face e se está oculta.

    Returns:
        (face_detectada, occluded, tipo_oclusao, confianca)
    """
    face_roi, score = extract_face_roi(image)
    if face_roi is None:
        return False, False, None, 0.0

    # Análise de textura (variância)
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    variance = np.var(gray)

    # Threshold ajustável: valores baixos indicam textura uniforme (oclusão)
    occluded = variance < 500
    occlusion_type = "occluded" if occluded else "visible"

    return True, occluded, occlusion_type, score


# ============================================
# COMPREFACE - RECONHECIMENTO FACIAL
# ============================================
def send_to_compreface(image: np.ndarray) -> dict:
    """Envia imagem para CompreFace e retorna detalhes da comparação."""
    if not COMPREFACE_API_KEY:
        logger.warning("COMPREFACE_API_KEY não configurada")
        return {
            "status": "api_key_missing",
            "subject": None,
            "confidence": None,
            "candidates": [],
            "response": None,
        }

    _, img_encoded = cv2.imencode('.jpg', image)
    payload = img_encoded.tobytes()
    headers = {'x-api-key': COMPREFACE_API_KEY}

    for attempt in range(1, COMPREFACE_RETRIES + 1):
        try:
            files = {'file': ('snapshot.jpg', payload, 'image/jpeg')}
            response = requests.post(
                (
                    f"{COMPREFACE_URL}/api/v1/recognition/recognize"
                    f"?prediction_count={RECOGNITION_PREDICTION_COUNT}"
                    f"&status=true"
                    f"&detect_faces={'true' if COMPREFACE_DETECT_FACES else 'false'}"
                ),
                files=files,
                headers=headers,
                timeout=COMPREFACE_TIMEOUT
            )

            if response.status_code == 200:
                result = response.json()
                matches = result.get('result') or []
                if matches:
                    subjects = matches[0].get('subjects') or []
                    candidates = [
                        {
                            "subject": candidate.get("subject"),
                            "similarity": candidate.get("similarity"),
                        }
                        for candidate in subjects[:5]
                    ]
                    if subjects:
                        subject = subjects[0].get('subject')
                        confidence = subjects[0].get('similarity')
                        return {
                            "status": "matched",
                            "subject": subject,
                            "confidence": confidence,
                            "candidates": candidates,
                            "response": result,
                        }
                    return {
                        "status": "no_subjects",
                        "subject": None,
                        "confidence": None,
                        "candidates": [],
                        "response": result,
                    }
                return {
                    "status": "no_match",
                    "subject": None,
                    "confidence": None,
                    "candidates": [],
                    "response": result,
                }

            logger.error("CompreFace error: %d - %s", response.status_code, response.text)
            return {
                "status": f"http_{response.status_code}",
                "subject": None,
                "confidence": None,
                "candidates": [],
                "response": response.text,
            }
        except requests.exceptions.Timeout:
            logger.warning(
                "Timeout ao conectar com CompreFace (tentativa %d/%d)",
                attempt,
                COMPREFACE_RETRIES,
            )
            if attempt < COMPREFACE_RETRIES:
                time.sleep(2)
                continue
            logger.error("CompreFace excedeu o tempo limite após %d tentativas", COMPREFACE_RETRIES)
            return {
                "status": "timeout",
                "subject": None,
                "confidence": None,
                "candidates": [],
                "response": None,
            }
        except Exception as e:
            logger.error("Erro ao enviar para CompreFace: %s", e)
            return {
                "status": "error",
                "subject": None,
                "confidence": None,
                "candidates": [],
                "response": str(e),
            }

    return {
        "status": "unknown",
        "subject": None,
        "confidence": None,
        "candidates": [],
        "response": None,
    }


# ============================================
# UTILITÁRIOS
# ============================================
def save_snapshot(image: np.ndarray, event_id: str, camera: str) -> Path:
    """Salva snapshot no disco"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{camera}_{event_id}_{timestamp}.jpg"
    filepath = STORAGE_PATH / filename
    cv2.imwrite(str(filepath), image)
    return filepath


def save_face_roi(image: np.ndarray, event_id: str, camera: str) -> Path:
    """Salva a imagem recortada do rosto usada na comparação."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{camera}_{event_id}_{timestamp}_face.jpg"
    filepath = STORAGE_PATH / filename
    cv2.imwrite(str(filepath), image)
    return filepath


def should_auto_register_unknown(event_data: dict) -> bool:
    """Decide se um desconhecido deve entrar na watchlist automatica."""
    if not AUTO_REGISTER_UNKNOWN:
        return False
    if event_data.get("event_type") != UNKNOWN_ONLY_ON_EVENT_TYPE:
        return False
    if event_data.get("confidence", 0) < UNKNOWN_MIN_FACE_CONFIDENCE:
        return False
    return True


def should_run_recognition(event_type: Optional[str]) -> bool:
    """Controla em quais tipos de evento o reconhecimento deve rodar."""
    if not RECOGNITION_EVENT_TYPES:
        return True
    return (event_type or "") in RECOGNITION_EVENT_TYPES


def apply_recognition_threshold(comparison: dict) -> dict:
    """Aceita o match apenas quando a similaridade minima for atendida."""
    subject = comparison.get("subject")
    confidence = comparison.get("confidence")
    if not subject or confidence is None:
        return comparison

    if confidence < RECOGNITION_MIN_SIMILARITY:
        return {
            **comparison,
            "status": "below_threshold",
            "subject": None,
        }

    return comparison


def next_unknown_subject_name(conn: sqlite3.Connection) -> str:
    """Gera o proximo identificador de desconhecido acompanhado."""
    row = conn.execute(
        "SELECT subject FROM unknown_subjects ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row or not row[0]:
        return f"{UNKNOWN_SUBJECT_PREFIX}0001"

    current = row[0]
    if current.startswith(UNKNOWN_SUBJECT_PREFIX):
        suffix = current.replace(UNKNOWN_SUBJECT_PREFIX, "", 1)
        if suffix.isdigit():
            return f"{UNKNOWN_SUBJECT_PREFIX}{int(suffix) + 1:04d}"

    return f"{UNKNOWN_SUBJECT_PREFIX}0001"


def register_unknown_subject(image: np.ndarray, event_data: dict) -> dict:
    """Cadastra um desconhecido como watchlist automatica no CompreFace e no SQLite."""
    if not COMPREFACE_API_KEY:
        return {"status": "api_key_missing", "subject": None, "image_id": None}

    conn = sqlite3.connect(DB_PATH)
    try:
        subject = next_unknown_subject_name(conn)
        _, img_encoded = cv2.imencode('.jpg', image)
        files = {'file': ('unknown.jpg', img_encoded.tobytes(), 'image/jpeg')}
        headers = {'x-api-key': COMPREFACE_API_KEY}
        response = requests.post(
            f"{COMPREFACE_URL}/api/v1/recognition/faces?subject={subject}&det_prob_threshold={UNKNOWN_DET_PROB_THRESHOLD}",
            files=files,
            headers=headers,
            timeout=COMPREFACE_TIMEOUT,
        )

        if response.status_code not in (200, 201):
            logger.error("Falha ao cadastrar desconhecido: %d - %s", response.status_code, response.text)
            return {
                "status": f"register_http_{response.status_code}",
                "subject": None,
                "image_id": None,
                "response": response.text,
            }

        payload = response.json()
        conn.execute(
            '''
            INSERT INTO unknown_subjects
            (subject, created_at, last_seen_at, sightings, last_event_id, best_face_path, source_camera)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                subject,
                event_data['timestamp'],
                event_data['timestamp'],
                1,
                event_data['event_id'],
                str(event_data.get('face_roi_path') or event_data.get('snapshot_path') or ''),
                event_data.get('camera'),
            ),
        )
        conn.commit()
        logger.info("Desconhecido cadastrado automaticamente: %s", subject)
        return {
            "status": "unknown_registered",
            "subject": subject,
            "image_id": payload.get('image_id'),
            "response": payload,
        }
    except Exception as exc:
        logger.error("Erro ao cadastrar desconhecido automaticamente: %s", exc)
        return {
            "status": "register_error",
            "subject": None,
            "image_id": None,
            "response": str(exc),
        }
    finally:
        conn.close()


def update_unknown_subject_sighting(subject: str, event_data: dict):
    """Atualiza metricas quando um desconhecido ja acompanhado reaparece."""
    if not subject.startswith(UNKNOWN_SUBJECT_PREFIX):
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id, sightings FROM unknown_subjects WHERE subject = ?",
            (subject,),
        ).fetchone()
        if row is None:
            conn.execute(
                '''
                INSERT INTO unknown_subjects
                (subject, created_at, last_seen_at, sightings, last_event_id, best_face_path, source_camera)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    subject,
                    event_data['timestamp'],
                    event_data['timestamp'],
                    1,
                    event_data['event_id'],
                    str(event_data.get('face_roi_path') or event_data.get('snapshot_path') or ''),
                    event_data.get('camera'),
                ),
            )
        else:
            conn.execute(
                '''
                UPDATE unknown_subjects
                SET last_seen_at = ?,
                    sightings = sightings + 1,
                    last_event_id = ?,
                    best_face_path = COALESCE(NULLIF(?, ''), best_face_path),
                    source_camera = ?
                WHERE subject = ?
                ''',
                (
                    event_data['timestamp'],
                    event_data['event_id'],
                    str(event_data.get('face_roi_path') or event_data.get('snapshot_path') or ''),
                    event_data.get('camera'),
                    subject,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def save_to_db(event_data: dict):
    """Salva dados no banco SQLite"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO detections
        (timestamp, camera, event_id, face_detected, occluded, occlusion_type,
         confidence, recognized_subject, recognition_confidence, snapshot_path,
         event_type, face_roi_path, compreface_status, compreface_candidates,
         compreface_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        event_data['timestamp'],
        event_data['camera'],
        event_data['event_id'],
        event_data['face_detected'],
        event_data['occluded'],
        event_data.get('occlusion_type'),
        event_data.get('confidence'),
        event_data.get('recognized_subject'),
        event_data.get('recognition_confidence'),
        str(event_data.get('snapshot_path', '')),
        event_data.get('event_type'),
        str(event_data.get('face_roi_path', '')),
        event_data.get('compreface_status'),
        event_data.get('compreface_candidates'),
        event_data.get('compreface_response'),
    ))
    conn.commit()
    conn.close()


def publish_alert(client: mqtt.Client, event_data: dict):
    """Publica alerta de oclusão no MQTT"""
    topic = "alerts/occlusion"
    payload = json.dumps({
        "camera": event_data['camera'],
        "timestamp": event_data['timestamp'],
        "event_id": event_data['event_id'],
        "type": event_data.get('occlusion_type'),
        "snapshot": str(event_data.get('snapshot_path', ''))
    })
    client.publish(topic, payload, retain=False)
    logger.warning("ALERTA: Oclusão detectada em %s - Tipo: %s",
                   event_data['camera'], event_data.get('occlusion_type'))


def publish_recognition(client: mqtt.Client, event_data: dict):
    """Publica resultado de reconhecimento no MQTT"""
    topic = "facial/recognitions"
    payload = json.dumps({
        "camera": event_data['camera'],
        "timestamp": event_data['timestamp'],
        "subject": event_data.get('recognized_subject'),
        "confidence": event_data.get('recognition_confidence'),
        "event_id": event_data['event_id']
    })
    client.publish(topic, payload, retain=False)
    logger.info("Reconhecido: %s (confiança: %.2f)",
                event_data.get('recognized_subject'),
                event_data.get('recognition_confidence', 0))


# ============================================
# MQTT CALLBACK
# ============================================
def on_message(client: mqtt.Client, userdata, msg):
    """Callback MQTT para eventos do Frigate"""
    try:
        payload = json.loads(msg.payload.decode())

        # Processa apenas eventos de pessoa (type='new' ou 'end')
        if payload.get('type') not in ['new', 'end']:
            return

        after = payload.get('after', {})
        if after.get('label') != 'person':
            return

        camera = after.get('camera')
        event_id = after.get('id')
        timestamp = after.get('start_time', datetime.now().isoformat())

        logger.info("Evento pessoa: camera=%s, id=%s, type=%s",
                    camera, event_id, payload.get('type'))

        # Baixa snapshot do Frigate
        snapshot_url = f"{FRIGATE_URL}/api/events/{event_id}/snapshot.jpg"
        response = requests.get(snapshot_url, timeout=5)
        if response.status_code != 200:
            logger.error("Falha ao baixar snapshot: %d", response.status_code)
            return

        # Converte para OpenCV
        img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("Imagem inválida")
            return

        # Salva snapshot
        snapshot_path = save_snapshot(img, event_id, camera)

        # Analisa oclusão
        face_detected, occluded, occl_type, conf = analyze_face_occlusion(img)

        event_data = {
            'timestamp': timestamp,
            'camera': camera,
            'event_id': event_id,
            'event_type': payload.get('type'),
            'face_detected': face_detected,
            'occluded': occluded,
            'occlusion_type': occl_type,
            'confidence': conf,
            'snapshot_path': snapshot_path,
            'face_roi_path': None,
            'compreface_status': None,
            'compreface_candidates': None,
            'compreface_response': None,
        }

        logger.info("Análise: face=%s, occluded=%s, type=%s, conf=%.2f",
                    face_detected, occluded, occl_type, conf)

        if not face_detected:
            event_data['recognized_subject'] = None
            save_to_db(event_data)
            return

        if occluded:
            publish_alert(client, event_data)
            event_data['recognized_subject'] = None
            save_to_db(event_data)
            return

        if not should_run_recognition(event_data.get('event_type')):
            logger.info("Reconhecimento ignorado para event_type=%s", event_data.get('event_type'))
            event_data['recognized_subject'] = None
            event_data['compreface_status'] = 'skipped_event_type'
            save_to_db(event_data)
            return

        # Face visível: reconhecimento facial
        if COMPREFACE_API_KEY:
            face_roi, _ = extract_face_roi(img)
            image_for_recognition = face_roi if face_roi is not None else img
            if face_roi is not None:
                event_data['face_roi_path'] = save_face_roi(face_roi, event_id, camera)

            comparison = apply_recognition_threshold(send_to_compreface(image_for_recognition))
            event_data['compreface_status'] = comparison.get('status')
            event_data['compreface_candidates'] = json.dumps(
                comparison.get('candidates', []),
                ensure_ascii=True,
            )
            event_data['compreface_response'] = json.dumps(
                comparison.get('response'),
                ensure_ascii=True,
            ) if isinstance(comparison.get('response'), (dict, list)) else comparison.get('response')

            logger.info(
                "Comparacao CompreFace: status=%s, candidatos=%s",
                event_data['compreface_status'],
                event_data['compreface_candidates'],
            )

            if comparison.get('subject'):
                event_data['recognized_subject'] = comparison.get('subject')
                event_data['recognition_confidence'] = comparison.get('confidence')
                update_unknown_subject_sighting(event_data['recognized_subject'], event_data)
                publish_recognition(client, event_data)
            else:
                if comparison.get('status') == 'below_threshold':
                    logger.info(
                        "Match rejeitado por limiar minimo: %.2f < %.2f",
                        comparison.get('confidence', 0) or 0,
                        RECOGNITION_MIN_SIMILARITY,
                    )
                if should_auto_register_unknown(event_data):
                    registration = register_unknown_subject(image_for_recognition, event_data)
                    event_data['recognized_subject'] = registration.get('subject')
                    event_data['recognition_confidence'] = 0.0
                    event_data['compreface_status'] = registration.get('status')
                    event_data['compreface_response'] = json.dumps(
                        registration.get('response'),
                        ensure_ascii=True,
                    ) if isinstance(registration.get('response'), (dict, list)) else registration.get('response')
                    if event_data['recognized_subject']:
                        logger.info(
                            "Desconhecido entrou na watchlist automatica: %s",
                            event_data['recognized_subject'],
                        )
                        publish_recognition(client, event_data)
                    else:
                        logger.info("Nenhum match no CompreFace e falha ao cadastrar desconhecido")
                else:
                    logger.info("Nenhum match no CompreFace")
                    event_data['recognized_subject'] = None
        else:
            logger.warning("COMPREFACE_API_KEY não configurada")
            event_data['recognized_subject'] = None

        save_to_db(event_data)

    except json.JSONDecodeError:
        logger.error("Erro ao decodificar JSON: %s", msg.payload)
    except requests.exceptions.Timeout:
        logger.error("Timeout ao baixar snapshot do Frigate")
    except Exception as e:
        logger.exception("Erro processando evento: %s", e)


# ============================================
# MAIN
# ============================================
def main():
    """Ponto de entrada principal"""
    logger.info("=" * 50)
    logger.info("Iniciando Orquestrador de Detecção de Oclusão")
    logger.info("=" * 50)
    logger.info("Frigate URL: %s", FRIGATE_URL)
    logger.info("CompreFace URL: %s", COMPREFACE_URL)
    logger.info("Eventos de reconhecimento: %s", ",".join(sorted(RECOGNITION_EVENT_TYPES)) or "todos")
    logger.info("Similaridade minima aceita: %.2f", RECOGNITION_MIN_SIMILARITY)
    logger.info("Auto watchlist desconhecidos: %s", AUTO_REGISTER_UNKNOWN)
    logger.info("MQTT Host: %s:%d", MQTT_HOST, MQTT_PORT)
    logger.info("Storage Path: %s", STORAGE_PATH)
    logger.info("Log Level: %s", LOG_LEVEL)

    init_db()

    # Conecta ao MQTT
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC)

    logger.info("Aguardando eventos no tópico %s...", MQTT_TOPIC)
    client.loop_forever()


if __name__ == "__main__":
    main()
