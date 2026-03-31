# Sistema Operacao e Debug

## Aviso

Este arquivo consolida credenciais, portas, caminhos, comandos e procedimentos do sistema atual.
Ele contem informacoes sensiveis. Mantenha este projeto privado.

## Objetivo do Sistema

Este ambiente faz:

- deteccao de pessoas com Frigate
- captura de snapshots e clips do evento
- deteccao facial e avaliacao de oclusao com o detector Python
- reconhecimento facial com CompreFace
- auditoria local com SQLite
- relatorios HTML para revisar qual frame, qual recorte facial e qual evento foram usados
- identificacao apenas de usuarios previamente cadastrados no CompreFace

## Topologia Atual

- Workspace principal: `/home/paulo/hikvision-docker-ia`
- Rede Docker: `facial-network`
- Servicos principais:
  - `go2rtc`
  - `frigate`
  - `mosquitto`
  - `compreface`
  - `occlusion-detector`

## Credenciais e Identificadores Atuais

### Camera Hikvision

- IP: `192.168.1.34`
- Usuario: `admin`
- Senha: definida em `.env`

### RTSP

- Main stream: `rtsp://${CAMERA_USER}:${CAMERA_PASSWORD}@${CAMERA_IP}:554/Streaming/Channels/101`
- Sub stream: `rtsp://${CAMERA_USER}:${CAMERA_PASSWORD}@${CAMERA_IP}:554/Streaming/Channels/102`

### CompreFace

- URL externa: `http://127.0.0.1:8088`
- URL interna do compose: `http://compreface`
- API key em uso: definida em `.env`

### Frigate

- URL externa: `http://127.0.0.1:5000`
- URL interna do compose: `http://frigate:5000`

### go2rtc

- Painel/API: `http://127.0.0.1:1984`
- RTSP interno: `rtsp://go2rtc:8554/main`
- RTSP interno substream: `rtsp://go2rtc:8554/sub`

### MQTT

- Host interno: `mosquitto`
- Porta externa/interna: `1883`
- Websocket externo: `9001`
- Topico principal do Frigate: `frigate/events`
- Topico de alertas: `alerts/occlusion`
- Topico de reconhecimentos: `facial/recognitions`

## Portas do Sistema

- `1883`: MQTT
- `1984`: go2rtc API
- `5000`: Frigate UI/API
- `8088`: CompreFace UI/API
- `8554`: go2rtc RTSP
- `8555`: go2rtc WebRTC
- `9001`: MQTT websocket
- `8099`: servidor local dos relatorios HTML, quando iniciado manualmente

## Arquivos Principais

- Configuracao geral: [docker-compose.yml](./docker-compose.yml)
- Variaveis sensiveis: [.env](./.env)
- Detector principal: [occlusion-detector/detector.py](./occlusion-detector/detector.py)
- Config do Frigate: [frigate/config.yml](./frigate/config.yml)
- Config do go2rtc: [go2rtc/go2rtc.yaml](./go2rtc/go2rtc.yaml)
- Broker MQTT: [mosquitto/config/mosquitto.conf](./mosquitto/config/mosquitto.conf)

## Bancos e Persistencia

### Banco local do detector

- Arquivo: `volumes/faces/detections.db`
- Tabela principal: `detections`
- Uso:
  - guarda cada tentativa processada
  - salva status do CompreFace
  - salva candidatos retornados
  - salva paths do frame e do recorte facial

### Tabela local de desconhecidos

- Mesmo arquivo: `volumes/faces/detections.db`
- Tabela: `unknown_subjects`
- Uso:
  - estrutura reservada para eventuais experimentos tecnicos
  - no modo atual ela deve permanecer sem uso
  - a politica operacional vigente e nao cadastrar automaticamente pessoas desconhecidas

### Banco interno do CompreFace

- Persistencia em: `volumes/compreface-postgres`
- Tipo: PostgreSQL interno do container all-in-one
- Uso:
  - usuarios do CompreFace
  - subjects cadastrados
  - faces e embeddings
  - configuracoes internas da aplicacao

### Midias e auditoria

- Frames e faces: `volumes/faces`
- Relatorios HTML: `volumes/faces/reviews`
- Midias do Frigate: `volumes/frigate`
- Logs locais do detector: `volumes/logs`
- Dados/logs do Mosquitto: `volumes/mosquitto`

## Fluxo Atual do Sistema

1. A camera envia RTSP.
2. O `go2rtc` redistribui o stream.
3. O `frigate` detecta `person`.
4. O evento vai para `frigate/events` no MQTT.
5. O `occlusion-detector` baixa o snapshot do evento.
6. O detector verifica se ha rosto e se ha oclusao.
7. Se o rosto estiver visivel:
   - envia para o CompreFace
  - pede ate 3 candidatos por comparacao
  - aceita match apenas acima da similaridade minima configurada
   - registra candidatos e resposta
   - salva frame e recorte de face
8. Se houver match:
   - publica no MQTT
   - grava em SQLite
9. Se nao houver match:
  - o sistema registra o evento como sem correspondencia
  - o operador deve revisar apenas se isso fizer sentido para um usuario ja cadastrado
  - o sistema nao deve cadastrar automaticamente pessoas desconhecidas

## Politica Atual de Privacidade

### Modo operacional vigente

- `AUTO_REGISTER_UNKNOWN=false`
- `RECOGNITION_EVENT_TYPES=end`
- `RECOGNITION_MIN_SIMILARITY=0.75`
- `RECOGNITION_PREDICTION_COUNT=3`
- apenas sujeitos cadastrados manualmente no CompreFace devem ser reconhecidos
- pessoas sem cadastro devem permanecer como `sem match`
- a watchlist automatica de desconhecidos nao deve ser usada no fluxo atual

### Motivacao operacional

- reduzir risco de tratamento indevido de dados pessoais
- manter o sistema focado em pessoas previamente autorizadas e cadastradas
- simplificar auditoria e governanca

## Configuracao Reservada da Watchlist de Desconhecidos

### Variaveis atuais

- `AUTO_REGISTER_UNKNOWN=false`
- `UNKNOWN_SUBJECT_PREFIX=unknown_auto_`
- `UNKNOWN_ONLY_ON_EVENT_TYPE=end`
- `UNKNOWN_MIN_FACE_CONFIDENCE=0.80`
- `UNKNOWN_DET_PROB_THRESHOLD=0.80`

### Comportamento

- no modo atual, esse bloco fica desabilitado
- se for reativado no futuro, deve passar por revisao juridica e de governanca

### Risco operacional

- se a face estiver ruim, distante ou estourada, pode criar subjects duplicados
- por isso o limiar foi deixado conservador

## Como Subir e Parar o Sistema

### Subir tudo

```bash
docker compose up -d
```

### Rebuildar detector

```bash
docker compose up -d --build occlusion-detector
```

### Ver status

```bash
docker compose ps
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### Parar tudo

```bash
docker compose down
```

## Logs Importantes

### Detector

```bash
docker compose logs -f occlusion-detector
docker logs occlusion-detector --tail 100
```

O que observar:

- `Evento pessoa`
- `Análise: face=True/False`
- `Reconhecimento ignorado para event_type=...`
- `Comparacao CompreFace: status=...`
- `Match rejeitado por limiar minimo: ...`
- `Reconhecido: ...`
- `Desconhecido entrou na watchlist automatica: unknown_auto_XXXX`

## Estrategia Atual de Reconhecimento dos Cadastrados

- o detector executa reconhecimento apenas em `event_type=end`
- o detector envia preferencialmente o recorte da face, nao o frame inteiro
- `COMPREFACE_DETECT_FACES=false` para evitar uma segunda deteccao no CompreFace quando o recorte facial ja foi feito
- o detector pede ate `3` candidatos ao CompreFace
- o detector so aceita o primeiro candidato quando `similarity >= 0.75`
- candidatos abaixo disso ficam registrados para auditoria, mas sem virar reconhecimento positivo

### Variaveis da estrategia

- `RECOGNITION_EVENT_TYPES=end`
- `RECOGNITION_MIN_SIMILARITY=0.75`
- `RECOGNITION_PREDICTION_COUNT=3`
- `COMPREFACE_DETECT_FACES=false`

### Como ajustar

- para reconhecer em `new` e `end`:
  - `RECOGNITION_EVENT_TYPES=new,end`
- para ficar mais rigoroso:
  - aumentar `RECOGNITION_MIN_SIMILARITY` para `0.80` ou `0.85`
- para ficar menos rigoroso:
  - reduzir `RECOGNITION_MIN_SIMILARITY` para `0.70`
- para deixar o CompreFace detectar rosto novamente no arquivo enviado:
  - `COMPREFACE_DETECT_FACES=true`

### CompreFace

```bash
docker logs compreface --since 10m | tail -n 200
```

O que observar:

- `POST /api/v1/recognition/recognize`
- retorno `200`
- erros `499`, `timeout`, `400 No face`

### Frigate

```bash
docker compose logs -f frigate
```

### go2rtc

```bash
docker compose logs -f go2rtc
```

### Mosquitto

```bash
docker compose logs -f mosquitto
```

## Comandos Uteis de Auditoria

### Historico textual de deteccoes

```bash
python3 inspect_detections.py --limit 10
```

### Estrutura de desconhecidos reservada

```bash
python3 inspect_unknowns.py
```

No modo atual, o esperado e nao haver registros novos nessa tabela.

### Gerar relatorio do evento mais recente

```bash
./ver_evento.sh
```

### Gerar relatorio de evento especifico

```bash
./ver_evento.sh EVENT_ID
```

### Gerar indice HTML dos eventos

```bash
./ver_eventos.sh
```

## Como Abrir os Relatorios no Navegador

### Gerar indice

```bash
./ver_eventos.sh
```

### Servir a pasta localmente

```bash
cd volumes/faces/reviews
python3 -m http.server 8099
```

### Abrir no navegador

- `http://localhost:8099/index.html`

Observacao:

- `http://localhost/index.html` abre o Apache da maquina, nao os relatorios

## APIs Uteis do CompreFace

### Listar subjects

```bash
curl -s -H 'x-api-key: SEU_COMPREFACE_API_KEY' \
  http://127.0.0.1:8088/api/v1/recognition/subjects
```

### Listar faces de um subject

```bash
curl -s -H 'x-api-key: SEU_COMPREFACE_API_KEY' \
  'http://127.0.0.1:8088/api/v1/recognition/faces?subject=A&page=0&size=15'
```

### Testar reconhecimento manual de uma imagem

```bash
latest=$(find volumes/faces -maxdepth 1 -type f -name '*.jpg' | sort | tail -n 1)
curl -s -X POST \
  -H 'x-api-key: SEU_COMPREFACE_API_KEY' \
  -F "file=@$latest" \
  http://127.0.0.1:8088/api/v1/recognition/recognize
```

### Baixar uma imagem cadastrada por `image_id`

```bash
curl -s -H 'x-api-key: SEU_COMPREFACE_API_KEY' \
  http://127.0.0.1:8088/api/v1/recognition/faces/IMAGE_ID/img --output face.jpg
```

## APIs Uteis do Frigate

### Listar eventos recentes

```bash
curl -s 'http://127.0.0.1:5000/api/events?limit=10'
```

### Snapshot de um evento

```bash
curl -o snapshot.jpg http://127.0.0.1:5000/api/events/EVENT_ID/snapshot.jpg
```

### Clip de um evento

```bash
curl -o clip.mp4 http://127.0.0.1:5000/api/events/EVENT_ID/clip.mp4
```

## Como Fazer Debug por Sintoma

### Sintoma: detector nao reconhece nada

Verificar:

1. se `occlusion-detector` esta `healthy`
2. se `COMPREFACE_API_KEY` esta correta em `.env`
3. se o CompreFace responde em `http://127.0.0.1:8088`
4. se o log mostra `Timeout ao conectar com CompreFace`
5. se o snapshot realmente contem uma face visivel

### Sintoma: abre Apache no navegador em vez do relatorio

Solucao:

```bash
cd volumes/faces/reviews
python3 -m http.server 8099
```

Depois abrir:

- `http://localhost:8099/index.html`

### Sintoma: Frigate detecta pessoa mas detector nao reconhece face

Verificar:

1. log `Análise: face=False`
2. qualidade do snapshot salvo em `volumes/faces`
3. posicao da pessoa, distancia e iluminacao

### Sintoma: reconheceu a pessoa errada

Verificar:

1. `compreface_candidates`
2. `recognition_confidence`
3. qualidade das faces cadastradas no subject
4. possivel necessidade de mais exemplos por pessoa

### Sintoma: houve cadastro automatico de desconhecido

Verificar:

1. se `AUTO_REGISTER_UNKNOWN` esta realmente `false` no `.env`
2. se o `occlusion-detector` foi reiniciado apos a alteracao
3. se nao existe algum container antigo em execucao

## Onde Estao os Logs e Evidencias

- logs de runtime dos containers: `docker compose logs ...`
- frames e recortes locais: `volumes/faces`
- relatorios HTML: `volumes/faces/reviews`
- banco local do detector: `volumes/faces/detections.db`
- banco interno do CompreFace: `volumes/compreface-postgres`
- midias do Frigate: `volumes/frigate`

## Estado Atual Conhecido

- reconhecimento de subjects conhecidos esta funcional
- relatorios HTML por evento estao prontos
- indice HTML de eventos estah pronto
- sistema focado em reconhecimento de usuarios cadastrados no CompreFace
- watchlist automatica de desconhecidos desabilitada por padrao

## Procedimento Rapido de Uso Diario

1. subir stack:

```bash
docker compose up -d
```

2. acompanhar detector:

```bash
docker compose logs -f occlusion-detector
```

3. depois do evento, gerar indice:

```bash
./ver_eventos.sh
```

4. abrir no navegador:

- `http://localhost:8099/index.html`

5. revisar estrutura reservada de desconhecidos, se necessario:

```bash
python3 inspect_unknowns.py
```

## Proximos Passos Sugeridos

- melhorar a qualidade de reconhecimento dos usuarios cadastrados no CompreFace
- revisar fotos de cadastro dos subjects existentes
- opcionalmente elevar a qualidade dos recortes e do limiar de aceitacao