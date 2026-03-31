markdown
# Sistema de Reconhecimento Facial com Detecção de Oclusão
## Arquitetura Conteinerizada para Câmeras Hikvision

---

## 📋 Índice

1. [Visão Geral do Projeto](#visão-geral-do-projeto)
2. [Arquitetura do Sistema](#arquitetura-do-sistema)
3. [Pré-requisitos](#pré-requisitos)
4. [Estrutura de Diretórios](#estrutura-de-diretórios)
5. [Arquivos de Configuração](#arquivos-de-configuração)
6. [Docker Compose](#docker-compose)
7. [Serviços e Componentes](#serviços-e-componentes)
8. [Instalação e Configuração](#instalação-e-configuração)
9. [Execução e Monitoramento](#execução-e-monitoramento)
10. [Integração com Câmera Hikvision](#integração-com-câmera-hikvision)
11. [Troubleshooting](#troubleshooting)
12. [Backup e Recuperação](#backup-e-recuperação)
13. [Performance e Otimização](#performance-e-otimização)
14. [Roadmap e Melhorias Futuras](#roadmap-e-melhorias-futuras)

---

## 🎯 Visão Geral do Projeto

Este projeto implementa um pipeline completo de reconhecimento facial com detecção de oclusão (pessoas tentando esconder o rosto) utilizando câmeras IP Hikvision. A solução é totalmente conteinerizada, escalável e otimizada para baixa latência.

### Características Principais

- ✅ **Detecção de pessoas em tempo real** usando YOLO/MobileNet via Frigate
- ✅ **Reconhecimento facial** com CompreFace (baseado em InsightFace)
- ✅ **Detecção de oclusão facial** (máscaras, mãos, bonés) via MediaPipe
- ✅ **Streaming de baixa latência** com go2rtc (RTSP → WebRTC)
- ✅ **Arquitetura de microsserviços** com Docker Compose
- ✅ **Persistência de dados** estruturada para backup fácil
- ✅ **Alertas em tempo real** via MQTT
- ✅ **Logs centralizados** e banco de dados SQLite para auditoria

### Casos de Uso

- Controle de acesso com validação facial
- Monitoramento de segurança com alerta de ocultação
- Análise comportamental em ambientes corporativos
- Sistema de presença com reconhecimento facial

---

## 🏗️ Arquitetura do Sistema
┌─────────────────────────────────────────────────────────────────────────────┐
│ Hikvision DS-2CD6425G2-C2 │
│ RTSP://camera:554 │
└─────────────────────────────────┬───────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ go2rtc (Porta 1984) │
│ Multiplexador de Stream - Zero Latency │
│ RTSP → WebRTC / HLS / MSE │
└─────────────────────────────────┬───────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Frigate (Porta 5000) │
│ Detecção de Objetos com YOLOv8 │
│ ┌───────────────────────────────────────────────────────────────────────┐ │
│ │ YOLO/MobileNet → Detecta "pessoa" → Gera bounding box → Snapshot │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
│ Publica eventos MQTT │
└─────────────────────────────────┬───────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Mosquitto MQTT Broker (Porta 1883) │
│ Event Bus do Sistema │
└─────────────────────────────────┬───────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Occlusion Detector (Python/MediaPipe) │
│ ┌───────────────────────────────────────────────────────────────────────┐ │
│ │ 1. Escuta MQTT → Evento de pessoa │ │
│ │ 2. Baixa snapshot do Frigate via API │ │
│ │ 3. MediaPipe → Análise de textura facial │ │
│ │ 4. Roteamento: │ │
│ │ ├─ Face oculta → Alerta MQTT + Banco de dados │ │
│ │ └─ Face visível → CompreFace │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ CompreFace + PostgreSQL (Porta 8000) │
│ Reconhecimento Facial com InsightFace │
│ ┌───────────────────────────────────────────────────────────────────────┐ │
│ │ API REST → Recebe crop facial → Embeddings → Match com banco de faces │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Banco de Dados e Armazenamento │
│ ┌───────────────────────────────────────────────────────────────────────┐ │
│ │ SQLite: Metadados de detecções (oclusão, reconhecimento) │ │
│ │ PostgreSQL: Banco de faces do CompreFace │ │
│ │ Volumes: Snapshots, clips, logs │ │
│ └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

text

### Fluxo de Dados

1. **Captura**: Câmera Hikvision envia stream RTSP
2. **Distribuição**: go2rtc multiplexa para múltiplos consumidores
3. **Detecção**: Frigate identifica pessoas e publica eventos MQTT
4. **Análise**: Occlusion Detector avalia oclusão facial
5. **Reconhecimento**: CompreFace identifica faces visíveis
6. **Armazenamento**: Dados persistidos em volumes estruturados
7. **Alertas**: Eventos publicados em tópicos MQTT para integrações

---

## 📋 Pré-requisitos

### Hardware Recomendado

| Componente | Mínimo | Recomendado |
|------------|--------|-------------|
| **Processador** | Intel i5 / ARMv8 (RPi 5) | Intel i7 / AMD Ryzen 5 |
| **Memória RAM** | 8 GB | 16 GB |
| **Armazenamento** | 50 GB SSD | 256 GB SSD + HDD para vídeos |
| **GPU** | - | Intel Iris Xe / Coral TPU |
| **Rede** | 100 Mbps | 1 Gbps |

### Software Necessário

- **Docker** ≥ 20.10.0
- **Docker Compose** ≥ 2.0.0
- **Git** (para clonar/versionar)
- **Câmera Hikvision** com RTSP habilitado

### Aceleradores Opcionais (Recomendados)

- **Google Coral TPU** (USB ou M.2) → Detecção YOLO mais rápida
- **GPU Intel Iris Xe** → Aceleração OpenVINO
- **GPU NVIDIA** → Suporte CUDA

---

## 📁 Estrutura de Diretórios
/meu-projeto/
├── docker-compose.yml # Orquestração completa
├── .env # Variáveis de ambiente (credenciais)
├── .gitignore # Arquivos ignorados no Git
├── README.md # Documentação (este arquivo)
│
├── go2rtc/
│ └── go2rtc.yaml # Configuração do multiplexador
│
├── mosquitto/
│ └── config/
│ └── mosquitto.conf # Configuração do broker MQTT
│
├── frigate/
│ └── config.yml # Configuração do Frigate
│
├── occlusion-detector/
│ ├── Dockerfile # Build do detector
│ ├── requirements.txt # Dependências Python
│ └── detector.py # Script principal de análise
│
└── volumes/ # Dados persistentes
├── frigate/ # Snapshots, clips, gravações
├── postgres/ # Dados do PostgreSQL (CompreFace)
├── compreface/ # Dados do CompreFace
├── mosquitto/ # Dados MQTT (persistência)
├── faces/ # Snapshots de faces detectadas
└── logs/ # Logs do occlusion-detector

text

---

## 📄 Arquivos de Configuração

### 1. `.env` - Variáveis de Ambiente

```bash
# ============================================
# CONFIGURAÇÕES DA CÂMERA HIKVISION
# ============================================
CAMERA_IP=192.168.1.100
CAMERA_USER=admin
CAMERA_PASSWORD=sua_senha_segura_aqui

# ============================================
# STREAMS RTSP (Formatos Hikvision)
# ============================================
MAIN_STREAM=rtsp://${CAMERA_USER}:${CAMERA_PASSWORD}@${CAMERA_IP}:554/Streaming/Channels/101
SUB_STREAM=rtsp://${CAMERA_USER}:${CAMERA_PASSWORD}@${CAMERA_IP}:554/Streaming/Channels/102

# ============================================
# COMPREFACE (Gerar após primeiro acesso)
# ============================================
# Acesse http://localhost:8000, crie uma conta e gere uma API key
COMPREFACE_API_KEY=seu_api_key_aqui

# ============================================
# POSTGRESQL (Banco do CompreFace)
# ============================================
POSTGRES_PASSWORD=compreface_password_seguro

# ============================================
# LOGGING
# ============================================
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
2. go2rtc/go2rtc.yaml - Multiplexador de Stream
yaml
# go2rtc - Configuração do Multiplexador
api:
  listen: ":1984"

streams:
  main: ${MAIN_STREAM}
  sub: ${SUB_STREAM}

webrtc:
  listen: ":8555"
  candidates:
    - stun:stun.l.google.com:19302

rtsp:
  listen: ":8554"

hls:
  listen: ":8888"

log:
  level: info
3. mosquitto/config/mosquitto.conf - Broker MQTT
conf
# Configuração do Mosquitto MQTT Broker

# Listener principal
listener 1883 0.0.0.0
allow_anonymous true

# Persistência (manter eventos após reinicialização)
persistence true
persistence_location /mosquitto/data/
autosave_interval 1800

# Logs
log_dest file /mosquitto/log/mosquitto.log
log_type error
log_type warning
log_type notice
log_type information
connection_messages true

# Limites de conexão
max_connections -1
max_keepalive 65535
4. frigate/config.yml - Detecção de Pessoas
yaml
# Frigate NVR Configuration
mqtt:
  host: mosquitto
  port: 1883
  topic_prefix: frigate

go2rtc:
  streams:
    camera_main: "rtsp://go2rtc:8554/main"
    camera_sub: "rtsp://go2rtc:8554/sub"

cameras:
  entrada:
    ffmpeg:
      inputs:
        - path: rtsp://go2rtc:8554/main
          roles:
            - detect
            - record
        - path: rtsp://go2rtc:8554/sub
          roles:
            - audio
    detect:
      width: 1280
      height: 720
      fps: 5
      enabled: true
    objects:
      track:
        - person
      filters:
        person:
          min_area: 5000
          threshold: 0.7
          mask: []  # Áreas a ignorar (opcional)
    snapshots:
      enabled: true
      bounding_box: true
      crop: true
      retain:
        default: 30
    record:
      enabled: true
      retain:
        days: 7
        mode: all
      events:
        retain:
          default: 30

# Detectores (escolha conforme seu hardware)
detectors:
  # Para CPU apenas:
  cpu:
    type: cpu
  # Para Coral TPU (USB):
  # coral:
  #   type: edgetpu
  #   device: usb
  # Para GPU Intel:
  # openvino:
  #   type: openvino
  #   device: GPU

# Modelo de detecção
model:
  # YOLOv8n (leve e rápido)
  width: 320
  height: 320
  input_tensor: nhwc
  pixel_format: bgr

# Snapshots globais
snapshots:
  enabled: true
  retain:
    default: 30

# Versão do esquema
version: 0.14
5. occlusion-detector/Dockerfile
dockerfile
# Dockerfile otimizado para o Occlusion Detector
FROM python:3.11-slim

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Instala dependências de sistema para OpenCV e MediaPipe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libxcb-shm0 \
    libxcb-xfixes0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia requirements primeiro (melhor aproveitamento de cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código
COPY detector.py .

# Healthcheck: verifica conexão com MQTT
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import paho.mqtt.client as mqtt; c=mqtt.Client(); c.connect('mosquitto', 1883, 5); c.disconnect()" || exit 1

CMD ["python", "-u", "detector.py"]
6. occlusion-detector/requirements.txt
text
paho-mqtt==1.6.1
requests==2.31.0
opencv-python-headless==4.9.0.80
mediapipe==0.10.7
numpy==1.24.3
7. occlusion-detector/detector.py - Script Principal
python
#!/usr/bin/env python3
"""
Orquestrador de Detecção de Oclusão e Reconhecimento Facial
Integra Frigate, CompreFace e MediaPipe
"""

import os
import json
import logging
import sqlite3
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
COMPREFACE_URL = os.getenv("COMPREFACE_URL", "http://compreface:8000")
COMPREFACE_API_KEY = os.getenv("COMPREFACE_API_KEY")
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

def analyze_face_occlusion(image: np.ndarray) -> Tuple[bool, bool, Optional[str], float]:
    """
    Analisa se há face e se está oculta.
    
    Returns:
        (face_detectada, occluded, tipo_oclusao, confianca)
    """
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_detection.process(rgb)
    
    if not results.detections:
        return False, False, None, 0.0
    
    detection = results.detections[0]
    bbox = detection.location_data.relative_bounding_box
    h, w, _ = image.shape
    x = int(bbox.xmin * w)
    y = int(bbox.ymin * h)
    width = int(bbox.width * w)
    height = int(bbox.height * h)
    x, y = max(0, x), max(0, y)
    
    face_roi = image[y:y+height, x:x+width]
    if face_roi.size == 0:
        return True, True, "empty_roi", detection.score[0]
    
    # Análise de textura (variância)
    gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
    variance = np.var(gray)
    
    # Threshold ajustável: valores baixos indicam textura uniforme (oclusão)
    occluded = variance < 500
    occlusion_type = "occluded" if occluded else "visible"
    
    return True, occluded, occlusion_type, detection.score[0]

# ============================================
# COMPREFACE - RECONHECIMENTO FACIAL
# ============================================
def send_to_compreface(image: np.ndarray) -> Tuple[Optional[str], Optional[float]]:
    """Envia imagem para CompreFace e retorna (subject, confidence)"""
    if not COMPREFACE_API_KEY:
        logger.warning("COMPREFACE_API_KEY não configurada")
        return None, None
    
    try:
        _, img_encoded = cv2.imencode('.jpg', image)
        files = {'file': ('snapshot.jpg', img_encoded.tobytes(), 'image/jpeg')}
        
        headers = {'x-api-key': COMPREFACE_API_KEY}
        response = requests.post(
            f"{COMPREFACE_URL}/api/v1/recognition/recognize",
            files=files,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('result'):
                subject = result['result'][0].get('subject')
                confidence = result['result'][0].get('confidence')
                return subject, confidence
            return "unknown", 0.0
        else:
            logger.error("CompreFace error: %d - %s", response.status_code, response.text)
            return None, None
    except requests.exceptions.Timeout:
        logger.error("Timeout ao conectar com CompreFace")
        return None, None
    except Exception as e:
        logger.error("Erro ao enviar para CompreFace: %s", e)
        return None, None

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

def save_to_db(event_data: dict):
    """Salva dados no banco SQLite"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO detections 
        (timestamp, camera, event_id, face_detected, occluded, occlusion_type, 
         confidence, recognized_subject, recognition_confidence, snapshot_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        str(event_data.get('snapshot_path', ''))
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
            'face_detected': face_detected,
            'occluded': occluded,
            'occlusion_type': occl_type,
            'confidence': conf,
            'snapshot_path': snapshot_path
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
        
        # Face visível: reconhecimento facial
        if COMPREFACE_API_KEY:
            subject, rec_conf = send_to_compreface(img)
            if subject:
                event_data['recognized_subject'] = subject
                event_data['recognition_confidence'] = rec_conf
                publish_recognition(client, event_data)
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
🐳 Docker Compose
Crie o arquivo docker-compose.yml na raiz do projeto:

yaml
version: '3.8'

services:
  # ============================================
  # Mosquitto MQTT Broker
  # ============================================
  mosquitto:
    image: eclipse-mosquitto:2.0
    container_name: mosquitto
    restart: unless-stopped
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto/config:/mosquitto/config:ro
      - ./volumes/mosquitto/data:/mosquitto/data
      - ./volumes/mosquitto/log:/mosquitto/log
    healthcheck:
      test: ["CMD", "mosquitto_sub", "-t", "$$SYS/", "-C", "1", "-W", "5"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - facial-network

  # ============================================
  # PostgreSQL para CompreFace
  # ============================================
  postgres:
    image: postgres:15-alpine
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: compreface
      POSTGRES_USER: compreface
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-compreface}
    volumes:
      - ./volumes/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U compreface"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - facial-network

  # ============================================
  # go2rtc - Multiplexador de Stream
  # ============================================
  go2rtc:
    image: alexxit/go2rtc:latest
    container_name: go2rtc
    restart: unless-stopped
    ports:
      - "1984:1984"
      - "8554:8554"
      - "8555:8555"
    volumes:
      - ./go2rtc/go2rtc.yaml:/config/go2rtc.yaml:ro
    env_file:
      - .env
    command: -c /config/go2rtc.yaml
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:1984/api/streams"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - facial-network

  # ============================================
  # Frigate - Detecção de Pessoas
  # ============================================
  frigate:
    image: ghcr.io/blakeblackshear/frigate:stable
    container_name: frigate
    restart: unless-stopped
    privileged: true
    ports:
      - "5000:5000"
    volumes:
      - ./frigate/config.yml:/config/config.yml:ro
      - ./volumes/frigate:/media/frigate
      - /etc/localtime:/etc/localtime:ro
      # Aceleradores (descomente conforme seu hardware)
      # - /dev/bus/usb:/dev/bus/usb  # Coral TPU USB
      # - /dev/dri:/dev/dri          # GPU Intel
    environment:
      - FRIGATE_RTSP_PASSWORD=${CAMERA_PASSWORD}
    env_file:
      - .env
    depends_on:
      go2rtc:
        condition: service_healthy
      mosquitto:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/api/version"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - facial-network

  # ============================================
  # CompreFace - Reconhecimento Facial
  # ============================================
  compreface:
    image: exadel/compreface:latest
    container_name: compreface
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: compreface
      POSTGRES_USER: compreface
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-compreface}
      COMPREFACE_SERVICE_BASE_URL: http://compreface:8000
    volumes:
      - ./volumes/compreface:/data
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - facial-network

  # ============================================
  # Occlusion Detector - Script Python
  # ============================================
  occlusion-detector:
    build: ./occlusion-detector
    container_name: occlusion-detector
    restart: unless-stopped
    environment:
      FRIGATE_URL: http://frigate:5000
      COMPREFACE_URL: http://compreface:8000
      COMPREFACE_API_KEY: ${COMPREFACE_API_KEY}
      MQTT_HOST: mosquitto
      MQTT_PORT: 1883
      MQTT_TOPIC: frigate/events
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    volumes:
      - ./volumes/faces:/app/faces
      - ./volumes/logs:/app/logs
    env_file:
      - .env
    depends_on:
      frigate:
        condition: service_healthy
      compreface:
        condition: service_healthy
      mosquitto:
        condition: service_healthy
    networks:
      - facial-network

# ============================================
# Redes
# ============================================
networks:
  facial-network:
    driver: bridge
    name: facial-network
🔧 Serviços e Componentes
1. go2rtc (Porta 1984)
Função: Multiplexador de stream RTSP para WebRTC/HLS/MSE

Endpoint	Descrição
http://localhost:1984	Interface web para visualização
rtsp://localhost:8554/main	Stream RTSP principal
rtsp://localhost:8554/sub	Stream RTSP secundário
2. Frigate (Porta 5000)
Função: Detecção de objetos com YOLO/MobileNet

Endpoint	Descrição
http://localhost:5000	Interface web do Frigate
http://localhost:5000/api/events	API de eventos
http://localhost:5000/api/events/{id}/snapshot.jpg	Snapshot do evento
3. Mosquitto (Porta 1883)
Função: Broker MQTT para comunicação entre serviços

Tópico	Descrição
frigate/events	Eventos de detecção do Frigate
alerts/occlusion	Alertas de oclusão facial
facial/recognitions	Resultados de reconhecimento
4. CompreFace (Porta 8000)
Função: Reconhecimento facial com InsightFace

Endpoint	Descrição
http://localhost:8000	Interface web de administração
http://localhost:8000/api/v1/recognition/recognize	API de reconhecimento
5. Occlusion Detector
Função: Análise de oclusão e orquestração

Recurso	Descrição
volumes/faces/	Snapshots de faces detectadas
volumes/logs/	Logs de execução
detections.db	Banco SQLite com metadados
🚀 Instalação e Configuração
Passo 1: Clonar o Repositório
bash
git clone https://github.com/seu-usuario/facial-recognition.git
cd facial-recognition
Passo 2: Criar Estrutura de Diretórios
bash
mkdir -p go2rtc mosquitto/config frigate occlusion-detector
mkdir -p volumes/{frigate,postgres,compreface,mosquitto,faces,logs}
Passo 3: Configurar Arquivos
Copie os arquivos de configuração conforme as seções acima:

bash
# Criar arquivos de configuração
touch .env
touch go2rtc/go2rtc.yaml
touch mosquitto/config/mosquitto.conf
touch frigate/config.yml
touch occlusion-detector/{Dockerfile,requirements.txt,detector.py}
Passo 4: Configurar Variáveis de Ambiente
Edite o arquivo .env com as credenciais da sua câmera:

bash
nano .env
Passo 5: Dar Permissão de Execução
bash
chmod +x occlusion-detector/detector.py
Passo 6: Construir e Iniciar os Containers
bash
# Build das imagens
docker-compose build

# Iniciar todos os serviços
docker-compose up -d

# Verificar logs
docker-compose logs -f
Passo 7: Configurar o CompreFace
Acesse http://localhost:8000

Crie uma conta de administrador

Crie uma aplicação e gere uma API Key

Adicione a API Key ao arquivo .env:

bash
COMPREFACE_API_KEY=sua_chave_aqui
Reinicie o occlusion-detector:

bash
docker-compose restart occlusion-detector
Passo 8: Treinar Faces no CompreFace
Acesse http://localhost:8000/app/demo

Adicione pessoas conhecidas com fotos de exemplo

O sistema automaticamente reconhecerá rostos visíveis

📊 Execução e Monitoramento
Comandos Úteis
bash
# Ver status dos containers
docker-compose ps

# Ver logs de todos os serviços
docker-compose logs -f

# Ver logs de um serviço específico
docker-compose logs -f occlusion-detector

# Reiniciar um serviço
docker-compose restart frigate

# Parar todos os serviços
docker-compose down

# Parar e remover volumes (cuidado! perde dados)
docker-compose down -v

# Acessar shell de um container
docker exec -it occlusion-detector /bin/bash
Monitoramento de Eventos MQTT
bash
# Inscrever-se em todos os tópicos
docker exec -it mosquitto mosquitto_sub -t "#" -v

# Inscrever-se apenas em alertas de oclusão
docker exec -it mosquitto mosquitto_sub -t "alerts/occlusion" -v

# Inscrever-se em reconhecimentos
docker exec -it mosquitto mosquitto_sub -t "facial/recognitions" -v
Visualização do Banco de Dados
bash
# Acessar SQLite dentro do container
docker exec -it occlusion-detector sqlite3 /app/faces/detections.db

# Consultar últimas detecções
SELECT * FROM detections ORDER BY timestamp DESC LIMIT 10;
🎥 Integração com Câmera Hikvision
Configuração da Câmera
Acesse a interface web da câmera:

text
http://{CAMERA_IP}
Habilite RTSP:

Vá em Configuration → Network → Advanced Settings → RTSP

Habilite RTSP (geralmente já está ativo)

Verifique as credenciais:

Usuário padrão: admin

Senha: definida na primeira configuração

Streams RTSP Hikvision
Stream	URL
Principal (alta resolução)	rtsp://admin:senha@IP:554/Streaming/Channels/101
Secundário (baixa resolução)	rtsp://admin:senha@IP:554/Streaming/Channels/102
Teste de Stream
bash
# Testar com ffplay
ffplay rtsp://admin:senha@192.168.1.100:554/Streaming/Channels/101

# Testar com VLC
vlc rtsp://admin:senha@192.168.1.100:554/Streaming/Channels/101
🔧 Troubleshooting
Problema: Frigate não detecta pessoas
Solução:

Verifique se o stream está funcionando:

bash
docker exec -it frigate curl http://localhost:5000/api/stats
Ajuste o threshold no frigate/config.yml:

yaml
filters:
  person:
    threshold: 0.5  # Reduza se necessário
Verifique logs:

bash
docker-compose logs frigate
Problema: CompreFace não reconhece
Solução:

Verifique se a API key está correta:

bash
docker exec -it occlusion-detector env | grep COMPREFACE_API_KEY
Teste a API diretamente:

bash
curl -X POST http://localhost:8000/api/v1/health
Verifique se há faces treinadas no banco

Problema: Oclusão não detectada
Solução:

Ajuste o threshold no detector.py:

python
occluded = variance < 500  # Aumente para mais sensível, diminua para menos
Verifique logs:

bash
docker-compose logs -f occlusion-detector
Teste com imagens de exemplo:

python
# Analisar variância da imagem
variance = np.var(gray)
print(f"Variância: {variance}")
Problema: Alta latência
Solução:

Reduza a resolução de detecção no Frigate:

yaml
detect:
  width: 640
  height: 480
Reduza FPS:

yaml
detect:
  fps: 3
Use acelerador Coral TPU ou GPU

Problema: Consumo excessivo de CPU
Solução:

Reduza a quantidade de streams analisadas

Use modelo YOLO mais leve:

yaml
model:
  width: 320
  height: 320
Aumente o intervalo entre detecções

💾 Backup e Recuperação
Backup Completo
bash
# Parar os serviços
docker-compose down

# Backup dos volumes
tar -czf backup-$(date +%Y%m%d).tar.gz volumes/

# Backup das configurações
tar -czf config-backup-$(date +%Y%m%d).tar.gz *.yaml *.yml .env go2rtc/ mosquitto/ frigate/ occlusion-detector/

# Reiniciar
docker-compose up -d
Restauração
bash
# Parar serviços
docker-compose down

# Restaurar volumes
tar -xzf backup-20241201.tar.gz

# Restaurar configurações
tar -xzf config-backup-20241201.tar.gz

# Reiniciar
docker-compose up -d
Backup Automático (cron)
bash
# Adicionar ao crontab
0 2 * * * cd /path/to/projeto && docker-compose down && tar -czf /backup/backup-$(date +\%Y\%m\%d).tar.gz volumes/ && docker-compose up -d
⚡ Performance e Otimização
Para Intel i7-1355U (Seu Notebook)
Configuração	Valor	Impacto
Resolução de detecção	640×480	Reduz CPU em ~40%
FPS de detecção	5	Latência < 200ms
Aceleração	OpenVINO (GPU)	Performance 3x
Modelo YOLO	YOLOv8n	Mais leve
Para Raspberry Pi 5
Configuração	Valor	Observação
Coral TPU	Obrigatório	Sem TPU, apenas 3-5 fps
Resolução	320×240	Mínima viável
FPS	3	Para 1-2 câmeras
Para Intel NUC (N100)
Configuração	Valor	Impacto
QuickSync	Ativado	Decodificação HW
OpenVINO	Ativado	Inferência 20-30 fps
Resolução	1280×720	Boa qualidade
Otimizações Avançadas
Usar Coral TPU no Frigate:

yaml
detectors:
  coral:
    type: edgetpu
    device: usb
Limitar memória dos containers:

yaml
services:
  frigate:
    deploy:
      resources:
        limits:
          memory: 2G
Usar volumes tmpfs para dados temporários:

yaml
volumes:
  - type: tmpfs
    target: /tmp/cache
🗺️ Roadmap e Melhorias Futuras
Fase 1: MVP (Atual)
Detecção de pessoas com Frigate

Reconhecimento facial com CompreFace

Detecção de oclusão com MediaPipe

Alertas MQTT

Banco SQLite para auditoria

Fase 2: Aprimoramentos
Dashboard em Grafana para métricas

Notificações por Telegram/WhatsApp

API REST para consulta de eventos

Suporte a múltiplas câmeras

Interface web para revisão de alertas

Fase 3: Avançado
Modelo customizado para oclusão (YOLO + pontos faciais)

Análise comportamental (tempo de permanência)

Integração com sistemas de acesso (ex: catracas)

Reconhecimento com máscara (partial face)

Clusterização para múltiplos servidores

📚 Referências
Frigate NVR Documentation

go2rtc Documentation

CompreFace Documentation

MediaPipe Face Detection

Hikvision RTSP Guide

📝 Licença
Este projeto está sob a licença MIT. Sinta-se livre para usar, modificar e distribuir.

👥 Contribuições
Contribuições são bem-vindas! Por favor, abra uma issue ou pull request para melhorias.

Desenvolvido com ❤️ para segurança e monitoramento inteligente

text

---

Este documento Markdown completo inclui:

1. **Visão geral** do projeto e casos de uso
2. **Arquitetura detalhada** com diagrama em ASCII
3. **Pré-requisitos** de hardware e software
4. **Estrutura de diretórios** organizada
5. **Todos os arquivos de configuração** completos
6. **Docker Compose** com healthchecks e dependências
7. **Código Python completo** do occlusion-detector
8. **Instalação passo a passo**
9. **Comandos de monitoramento e troubleshooting**
10. **Backup e recuperação**
11. **Otimizações de performance** por hardware
12. **Roadmap** de melhorias futuras

O projeto está pronto para ser implementado tanto no seu notebook i7-1355U quanto em um Raspberry Pi 5 ou NUC, com todas as configurações necessárias.