<div align="center">

# 🦀 FlexClaw

### Framework AI modulare per team di agenti intelligenti

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Agno SDK](https://img.shields.io/badge/Powered%20by-Agno-FF6B35)](https://docs.agno.com)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-Private-gray)]()

**Architettura a plugin per creare le tue integrazioni.<br>Definisci agenti, team e strumenti in YAML — il framework fa tutto il resto.**

[Quick Start](#-quick-start) · [Funzionalità](#-funzionalità) · [Architettura](#-architettura) · [Plugin](#-sistema-a-plugin) · [Documentazione](#-documentazione)

</div>

---

## ✨ Cos'è FlexClaw?

FlexClaw è un **framework AI modulare** costruito attorno a un **sistema a plugin completamente estensibile**: ogni canale di comunicazione (Telegram, Discord, Slack…) e ogni strumento (PDF, meteo, knowledge base…) è un plugin indipendente che puoi aggiungere, rimuovere o **creare da zero** senza toccare il core. Basato su [Agno SDK](https://docs.agno.com), orchestra team di agenti specializzati attraverso una configurazione interamente dichiarativa in YAML — ti basta descrivere *cosa* vuoi, il framework si occupa del *come*.

```yaml
# Definisci un agente in poche righe
agents:
  researcher:
    role: "Ricercatore web esperto"
    tools: [websearch, wikipedia, crawl4ai]

# Componi un team
teams:
  flexclaw:
    mode: coordinate
    members: [researcher, writer, file_manager]
```

### Perché FlexClaw?

| | Approccio tradizionale | FlexClaw |
|---|---|---|
| **Configurazione** | Codice Python per ogni agente | YAML dichiarativo — zero codice |
| **Tool** | Integrati nel core | Plugin modulari hot-pluggable |
| **Canali** | Hardcoded | Plugin canale indipendenti |
| **Modello AI** | Fisso a build time | Switch a runtime con persistenza |
| **Estensibilità** | Fork del progetto | Aggiungi una cartella, abilita in YAML |

---

## 🚀 Quick Start

### Prerequisiti

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- API key per almeno un provider (OpenRouter, OpenAI, Google)

### Installazione

```bash
# Clona il repository
git clone <repo-url> && cd flexClaw

# Installa le dipendenze
uv sync

# Configura le variabili d'ambiente
cp .env.example .env
# Imposta: TELEGRAM_TOKEN, OPENROUTER_API_KEY (o altri provider)
```

### Configurazione minima

1. **Scegli i modelli** — modifica `config/main.config.yaml`
2. **Abilita i plugin** — controlla `config/plugin.config.yaml`
3. **Configura Telegram** — compila `plugin/channel/telegram_bot/config.yaml`

### Avvio

```bash
# Avvio diretto
uv run python main.py

# Oppure con Docker
docker compose up -d --build
```

Apri Telegram, cerca il tuo bot e scrivi `/help` — sei operativo.

---

## 💡 Funzionalità

### 🤖 Team di agenti dichiarativo

Il cuore di FlexClaw è un team di agenti coordinati, ognuno specializzato in un dominio. Il team leader orchestra automaticamente le richieste verso l'agente più adatto.

| Agente | Specializzazione | Tool principali |
|--------|-----------------|-----------------|
| **Researcher** | Ricerca web, articoli, scraping | WebSearch, Wikipedia, YouTube, Crawl4AI, HackerNews |
| **Writer** | Scrittura articoli strutturati | — (riceve contesto dal Researcher) |
| **FileManager** | File, PDF, knowledge base | LocalFileSystem, PDF Tool, Knowledge Tool |
| **Analyst** | Calcoli, ragionamento, analisi | Calculator, ReasoningTools |
| **WeatherExpert** | Previsioni meteo con infografiche | WebSearch, Weather Tool, Crawl4AI |

**Routing intelligente:** il team leader instrada automaticamente le richieste. Le domande meteo vanno *sempre* al WeatherExpert, le richieste di articoli seguono la catena Researcher → Writer → FileManager.

### 🔄 Model switching a runtime

Cambia modello AI in qualsiasi momento — da Telegram con `/model` o via API. La scelta viene persistita e sopravvive ai riavvii.

**Provider supportati:**
- OpenRouter (GPT-4o, Claude, Gemini, Llama, Mistral…)
- OpenAI diretto
- Google AI (Gemini)
- Anthropic (Claude)

### 🧠 Knowledge Base vettoriale

Knowledge base integrata su **ChromaDB** con ricerca semantica:

- Salva contenuti e file dalla conversazione con il comando `/knowledge` o automaticamente tramite l'agente FileManager
- Ricerca semantica su tutto il contenuto salvato
- Embedding via OpenAI `text-embedding-3-small`
- Condivisa tra tutti gli agenti del team

### 📡 Streaming progressivo

Visibilità in tempo reale su cosa stanno facendo gli agenti:

```
🔄 Task: Ricerca informazioni su quantum computing
  ├─ 🔧 websearch: "quantum computing 2026" ✅
  ├─ 🔧 crawl4ai: lettura articolo ✅
  └─ 🔧 wikipedia: "quantum computing" ⏳
```

Task e tool step vengono aggiornati live nel messaggio Telegram — configurabile con `show_tool_steps: true/false`.

### 🔐 Sicurezza

- **Whitelist utenti** — accesso limitato a utenti autorizzati o aperto a tutti
- **Admin privilegiato** — comandi `/users`, `/logs`, `/reload` riservati
- **Sanitizzazione input** — rimozione caratteri di controllo, normalizzazione spazi
- **Whitelist estensioni** — solo file sicuri (.pdf, .txt, .md, .csv, .json, .png, .jpg…)
- **Limite upload** — 10 MB per file
- **Audit log** — ogni azione tracciata in JSON strutturato

### 📊 Audit e logging

Sistema di logging multi-livello con file separati per dominio:

| Log file | Contenuto |
|----------|-----------|
| `app.log` | Log generale applicazione |
| `core.log` | Operazioni core (bootstrap, model switch) |
| `agents.log` | Attività agenti e team |
| `telegram.log` | Interazioni canale Telegram |
| `tools.log` | Esecuzione tool plugin |
| `audit.log` | Audit strutturato (who, what, when, context, result) |

Rotating automatico: 5 MB per file, 3 backup conservati.

---

## 🧩 Sistema a plugin

FlexClaw separa nettamente il core dai plugin. Esistono due tipi: **channel** (canali di comunicazione) e **tool** (strumenti per gli agenti).

### Channel plugin

#### 📱 Telegram Bot

Integrazione Telegram completa, pronta all'uso:

**Comandi utente:**

| Comando | Descrizione |
|---------|-------------|
| `/start` | Messaggio di benvenuto |
| `/help` | Elenco comandi disponibili |
| `/status` | Stato modello, plugin attivi, sessione |
| `/model` | Cambia modello AI (bottoni inline) |
| `/reset` | Resetta la sessione corrente |
| `/history` | Cronologia della conversazione |
| `/knowledge` | Ricerca nella knowledge base |

**Comandi admin:**

| Comando | Descrizione |
|---------|-------------|
| `/users` | Gestione utenti autorizzati |
| `/logs` | Consulta log recenti |
| `/reload` | Ricarica configurazione a caldo |

**Supporto media completo:**
- 📷 Foto e immagini
- 🎤 Messaggi vocali e audio
- 🎬 Video
- 📄 Documenti (PDF, TXT, MD, CSV, JSON…)
- Lettura inline automatica dei file testuali
- Salvataggio automatico nella sandbox

**Modalità operative:**
- `polling` — ideale per sviluppo locale
- `webhook` — per ambienti di produzione

### Tool plugin

#### 📄 PDF Tool

Generazione PDF professionale da Markdown con temi CSS:

| Tema | Stile |
|------|-------|
| `minimal` | Pulito e leggero |
| `modern` | Contemporaneo con accenti colore |
| `editorial` | Elegante, stile rivista |
| `dark` | Sfondo scuro, ideale per report tecnici |

Auto-selezione del tema in base al contenuto: il tool analizza i tag del documento e sceglie il tema più adatto.

#### 🌤️ Weather Tool

Infografiche meteo in PNG con design glassmorphism:

- Layout adattivo da 1 a 14 giorni
- Rendering HTML → PNG via Playwright
- Icone emoji meteo standard
- Dati: temperatura, umidità, vento, precipitazioni

#### 🧠 Knowledge Tool

Gestione della knowledge base vettoriale:

- `save_to_knowledge()` — salva contenuto testuale
- `save_file_to_knowledge()` — salva file dalla sandbox
- Metadata tracciamento (source, type, original_name)
- Ricerca semantica via ChromaDB

#### 🔧 Tool SDK Agno integrati

Oltre ai tool custom, FlexClaw integra nativamente i tool dell'SDK Agno:

| Tool | Funzione |
|------|----------|
| WebSearch | Ricerca web |
| Wikipedia | Consultazione Wikipedia |
| Crawl4AI | Scraping avanzato di pagine web |
| Calculator | Calcoli matematici |
| LocalFileSystem | Lettura/scrittura file nella sandbox |
| FileTools | Operazioni avanzate su file |
| YouTube | Ricerca e analisi video |
| Newspaper4k | Estrazione articoli da URL |
| HackerNews | Feed Hacker News |
| ReasoningTools | Ragionamento strutturato |

---

## 🏗️ Architettura

```
┌──────────────────────────────────────────────────────────┐
│                     FlexClaw                             │
├──────────────┬───────────────────────────────────────────┤
│              │                                           │
│   Config     │   config/main.config.yaml      Globale    │
│   (YAML)     │   config/agents.config.yaml    Agenti     │
│              │   config/plugin.config.yaml    Plugin     │
│              │                                           │
├──────────────┼───────────────────────────────────────────┤
│              │                                           │
│              │   agent_os        Bootstrap & model mgmt  │
│   Core       │   agent_builder   YAML → Agenti & Team   │
│              │   loader          Plugin discovery & load │
│              │   agent_api       Bridge canali ↔ team    │
│              │   event_stream    Streaming progressivo   │
│              │   session         Gestione sessioni       │
│              │   audit           Audit log strutturato   │
│              │                                           │
├──────────────┼───────────────────────────────────────────┤
│              │                                           │
│   Plugin     │   channel/  telegram_bot  (+ futuri)     │
│              │   tool/     pdf_tool · weather_tool       │
│              │             knowledge_tool · SDK tools    │
│              │                                           │
├──────────────┼───────────────────────────────────────────┤
│              │                                           │
│   Data       │   data/chromadb/   Knowledge base         │
│              │   data/db/         Database sessioni      │
│              │   data/logs/       Log & audit            │
│              │   data/state.yaml  Stato persistente      │
│              │   sandbox/         File operativi         │
│              │                                           │
└──────────────┴───────────────────────────────────────────┘
```

### Flusso di una richiesta

```
Utente (Telegram) → Handler → agent_api → Team Leader
                                              │
                                    ┌─────────┼─────────┐
                                    ▼         ▼         ▼
                               Researcher  Analyst  WeatherExpert
                                    │                    │
                                    ▼                    ▼
                                 Writer            Weather Tool
                                    │                    │
                                    ▼                    ▼
                              FileManager          Infografica PNG
                                    │
                                    ▼
                              PDF / Knowledge
```

---

## 🐳 Docker

### Build e avvio

```bash
docker compose up -d --build
```

### Caratteristiche del container

- **Multi-stage build** — immagine ottimizzata con Python 3.11-slim
- **Playwright integrato** — browser Chromium per rendering HTML → PNG
- **Health check** — endpoint `/health` su porta 7777
- **Volumi persistenti** — dati e sandbox sopravvivono ai riavvii
- **Config read-only** — file di configurazione montati in sola lettura
- **Limiti risorse** — 2 GB RAM max
- **Log gestiti** — JSON format, 10 MB max, 3 file di rotazione
- **Restart policy** — `unless-stopped`

### Ricarica configurazione

```bash
# Dopo modifiche ai file YAML
docker compose restart flexclaw
```

---

## 🔌 Estendere il sistema

### Creare un tool plugin

```bash
plugin/tool/my_tool/
├── __init__.py          # Esporta la classe Toolkit
├── tool.py              # Implementazione del tool
├── config.yaml          # Configurazione e istruzioni per l'agente
├── config.example.yaml  # Template di configurazione
├── requirements.txt     # Dipendenze (installate automaticamente)
└── README.md            # Documentazione del tool
```

```python
# tool.py
from agno.tools import Toolkit

class MyTool(Toolkit):
    def __init__(self):
        super().__init__(name="my_tool")
        self.register(self.my_method)

    def my_method(self, param: str) -> str:
        """Descrizione del metodo per l'agente."""
        return f"Risultato: {param}"
```

```yaml
# config/plugin.config.yaml — abilita il tool
tool:
  - id: my_tool
    status: enabled
```

```yaml
# config/agents.config.yaml — assegna il tool a un agente
agents:
  my_agent:
    tools: [my_tool]
```

Il loader si occupa di tutto: discovery, installazione dipendenze, caricamento dinamico.

### Creare un channel plugin

```bash
plugin/channel/my_channel/
├── __init__.py          # Esporta start_bot
├── bot.py               # start_bot(stop_event) — loop del canale
├── config.yaml          # Configurazione del canale
├── config.example.yaml
├── requirements.txt
└── README.md
```

Il canale può usare le API del core:
- `core.agent_api` — invia messaggi al team
- `core.event_stream` — streaming eventi
- `core.session` — gestione sessioni
- `core.audit` — audit log

### Configurare agenti e team

Tutto in `config/agents.config.yaml` — nessun codice da modificare:

```yaml
# Variabili globali riutilizzabili
vars:
  sandbox_dir: "sandbox"

# Istruzioni condivise tra agenti
shared_instructions:
  file_instructions: >
    I file vanno salvati nella sandbox.

# Agenti con ruolo, tool e istruzioni
agents:
  my_agent:
    role: "Il mio agente personalizzato"
    tools: [websearch, my_tool]
    instructions: |
      Sei un esperto di ${sandbox_dir}.
      ${file_instructions}

# Team con routing e coordinamento
teams:
  my_team:
    mode: coordinate
    members: [my_agent, researcher]
    knowledge: true
```

---

## 📚 Documentazione

| Guida | Descrizione |
|-------|-------------|
| [Primo avvio](docs/primo-avvio.md) | Installazione, configurazione e primo test |
| [Creare un tool plugin](docs/creare-un-tool-plugin.md) | Guida completa per tool custom |
| [Creare un channel plugin](docs/creare-un-channel-plugin.md) | Guida completa per canali custom |
| [Providers](docs/providers.md) | Configurazione modelli e provider supportati |

---

## 🗺️ Roadmap

### In arrivo

- 🔴 **API REST / WebSocket** — interfaccia programmatica via FastAPI
- 🟡 **Multi-modello per agente** — modello diverso per ogni ruolo
- 🟡 **Token tracking** — monitoraggio consumo e costi
- 🟡 **Sessioni avanzate** — TTL, archiviazione, esportazione
- 🟡 **Nuovi agenti** — Coder, Summarizer, Scheduler, Translator
- 🟡 **Nuovi tool** — Image generation, STT, TTS, Email, Code execution, DB query
- 🟢 **Nuovi canali** — Discord, Slack, WhatsApp, CLI
- 🟢 **UX Telegram** — inline keyboards avanzate, typing indicator

---

## 🛠️ Tech stack

| Componente | Tecnologia |
|------------|------------|
| Framework AI | [Agno SDK](https://docs.agno.com) |
| Linguaggio | Python 3.11+ |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Vector DB | ChromaDB |
| Database | SQLite (via SQLAlchemy) |
| API server | FastAPI + Uvicorn |
| Canale | python-telegram-bot |
| Rendering | Playwright (Chromium) |
| Container | Docker + Docker Compose |

---

<div align="center">

**FlexClaw** — Agenti AI modulari, orchestrati, estensibili.

*Creato da Davide Salvato*

</div>
