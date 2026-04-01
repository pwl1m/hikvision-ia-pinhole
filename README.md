# Hikvision IA Pinhole — Resumo do Sistema

Sistema de reconhecimento facial com detecção de oclusão para câmeras IP Hikvision, totalmente conteinerizado com Docker Compose.

---

## Fluxo Resumido do Pipeline

```
Camera Hikvision (RTSP)
        │
        ▼
   go2rtc (porta 1984)
   Redistribui o stream para os consumidores internos
        │
        ▼
   Frigate (porta 5000)
   Detecta "pessoa" com YOLO/MobileNet
   Gera snapshot e publica evento em frigate/events (MQTT)
        │
        ▼
   Mosquitto (porta 1883)
   Barramento de eventos interno
        │
        ▼
   occlusion-detector (Python / MediaPipe)
   1. Escuta frigate/events
   2. Baixa snapshot do Frigate
   3. Verifica se há rosto e se está ocluído
   4. Se rosto visível → envia para CompreFace
   5. Se match (similarity >= 0.75) → publica reconhecimento no MQTT
   6. Grava tudo no SQLite (volumes/faces/detections.db)
        │
        ▼
   CompreFace (porta 8088)
   Reconhecimento facial com InsightFace/PostgreSQL interno
   Retorna até 3 candidatos por comparação
        │
        ▼
   reviews-generator (Python)
   Monitora o banco e gera relatórios HTML por evento
   Salva em volumes/faces/reviews/
        │
        ▼
   reviews-web (porta 8080)
   Serve os relatórios HTML estaticamente
   Acesse: http://localhost:8080/reviews/index.html
```

---

## Serviços Docker

| Serviço            | Porta(s)      | Função                                    |
|--------------------|---------------|-------------------------------------------|
| mosquitto          | 1883, 9001    | Broker MQTT                               |
| go2rtc             | 1984, 8554, 8555 | Multiplexador de stream RTSP            |
| frigate            | 5000          | Detecção de pessoas (YOLO)                |
| compreface         | 8088          | Reconhecimento facial (InsightFace)       |
| occlusion-detector | —             | Detector Python (oclusão + reconhecimento)|
| reviews-generator  | —             | Gera HTMLs de auditoria automaticamente   |
| reviews-web        | 8080          | Servidor HTTP dos relatórios HTML         |

---

## Últimas Modificações

- **Ajuste no `index.html` para Docker** (último commit): o servidor de relatórios HTML foi migrado de um comando manual (`python -m http.server 8099`) para o serviço `reviews-web` no Docker Compose, agora acessível em `http://localhost:8080/reviews/index.html`.

- **Serviço `reviews-generator` adicionado** ao `docker-compose.yml`: gera e atualiza automaticamente os relatórios HTML de auditoria por evento, monitorando o banco SQLite em `volumes/faces/detections.db`.

- **Serviço `reviews-web` adicionado** ao `docker-compose.yml`: serve os relatórios HTML em `http://localhost:8080` sem necessidade de comando manual.

- **Watchlist automática de desconhecidos desabilitada por padrão** (`AUTO_REGISTER_UNKNOWN=false`): o sistema reconhece apenas sujeitos previamente cadastrados no CompreFace, não cadastra automaticamente pessoas desconhecidas.

- **Estratégia de reconhecimento ajustada**: reconhecimento executado apenas em `event_type=end`, limiar mínimo de similaridade em `0.75`, até `3` candidatos por consulta, com `COMPREFACE_DETECT_FACES=false` para evitar dupla detecção facial.

---

## Uso Rápido

```bash
# Subir tudo
docker compose up -d

# Acompanhar o detector
docker compose logs -f occlusion-detector

# Ver relatórios de auditoria
# Abrir no navegador: http://localhost:8080/reviews/index.html

# Parar tudo
docker compose down
```

---

Para detalhes completos de configuração, credenciais, debug e procedimentos operacionais, consulte [SISTEMA_OPERACAO_E_DEBUG.md](./SISTEMA_OPERACAO_E_DEBUG.md).
