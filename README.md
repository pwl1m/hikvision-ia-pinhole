# Hikvision IA Pinhole

Sistema completo de **detecção de pessoas, reconhecimento facial e detecção de oclusão** para câmeras IP Hikvision, totalmente containerizado com Docker.

## Arquitetura

```
Câmera Hikvision (RTSP)
       ↓
   go2rtc (multiplexador de stream)
       ↓
   Frigate (detecção de pessoas com YOLO)
       ↓
   Mosquitto (barramento MQTT)
       ↓
   Occlusion Detector (Python / MediaPipe)
       ├─ Análise de oclusão facial
       └─ Se rosto visível → CompreFace (reconhecimento facial)
       ↓
   SQLite (auditoria) + Relatórios HTML
```

## Funcionalidades Principais

| Funcionalidade | Descrição |
|---|---|
| **Detecção de pessoas** | Frigate processa o stream em tempo real e detecta pessoas via YOLO/MobileNet |
| **Detecção de oclusão** | MediaPipe analisa se o rosto está visível ou coberto (máscara, mão, boné) |
| **Reconhecimento facial** | CompreFace compara o rosto com subjects pré-cadastrados e retorna candidatos com score de similaridade |
| **Auditoria local** | Cada evento é gravado em SQLite com snapshot, recorte facial, candidatos e resultado |
| **Relatórios HTML** | Geração de relatórios individuais por evento e índice navegável com filtros |
| **Política de privacidade** | Apenas pessoas previamente cadastradas são reconhecidas; sem cadastro automático de desconhecidos |

## Serviços Docker

| Serviço | Função | Porta |
|---|---|---|
| `mosquitto` | Broker MQTT | 1883, 9001 |
| `go2rtc` | Multiplexador RTSP/WebRTC | 1984, 8554, 8555 |
| `frigate` | Detecção de pessoas (NVR) | 5000 |
| `compreface` | Reconhecimento facial | 8088 |
| `occlusion-detector` | Orquestrador: oclusão + reconhecimento | — |
| `reviews-generator` | Gerador de relatórios HTML | — |
| `reviews-web` | Servidor dos relatórios | 8080 |

## Fluxo Operacional

1. A câmera envia RTSP → `go2rtc` redistribui o stream
2. `frigate` detecta `person` e publica evento no MQTT (`frigate/events`)
3. `occlusion-detector` baixa o snapshot e verifica rosto + oclusão
4. Se rosto visível, envia para o CompreFace e pede até 3 candidatos
5. Aceita match apenas acima do limiar mínimo de similaridade (padrão: 0.75)
6. Grava resultado em SQLite e publica no MQTT (`facial/recognitions`)
7. Relatórios HTML ficam disponíveis para revisão manual

## Quick Start

```bash
# 1. Configurar variáveis
cp .env.example .env
# Editar .env com IP da câmera, credenciais e API key do CompreFace

# 2. Subir os serviços
docker compose up -d

# 3. Acompanhar o detector
docker compose logs -f occlusion-detector

# 4. Gerar relatórios
./ver_eventos.sh          # índice de eventos recentes
./ver_evento.sh [EVENT_ID] # relatório de evento específico
```

## Scripts Utilitários

| Script | Função |
|---|---|
| `inspect_detections.py` | Consulta as últimas detecções no banco SQLite |
| `inspect_unknowns.py` | Lista registros de desconhecidos (reservado) |
| `review_event.py` | Gera relatório HTML de um evento |
| `review_index.py` | Gera índice HTML dos eventos recentes |
| `ver_evento.sh` | Wrapper para gerar relatório + atualizar índice |
| `ver_eventos.sh` | Wrapper para gerar índice de eventos |

## Configurações Principais

| Variável | Padrão | Descrição |
|---|---|---|
| `RECOGNITION_MIN_SIMILARITY` | `0.75` | Limiar mínimo de similaridade para aceitar match |
| `RECOGNITION_EVENT_TYPES` | `end` | Tipos de evento que disparam reconhecimento |
| `RECOGNITION_PREDICTION_COUNT` | `3` | Candidatos solicitados ao CompreFace |
| `COMPREFACE_DETECT_FACES` | `false` | Envia recorte facial (não o frame inteiro) |
| `AUTO_REGISTER_UNKNOWN` | `false` | Não cadastra automaticamente desconhecidos |

## Documentação Detalhada

- [SISTEMA_OPERACAO_E_DEBUG.md](./SISTEMA_OPERACAO_E_DEBUG.md) — credenciais, portas, debug por sintoma e procedimentos operacionais completos
- [instruction.md](./instruction.md) — instruções e contexto detalhado do projeto
