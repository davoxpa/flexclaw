# Knowledge Tool

Plugin custom che permette agli agenti di salvare contenuti nella knowledge base a runtime.

> **Nota:** Agno SDK include un proprio `AgnoKnowledgeTool`, ma non è utilizzabile in questo contesto.
> Il tool SDK opera in modalità read-only (solo ricerca nella knowledge base), mentre FlexClaw
> necessita di **scrittura a runtime** (`save_to_knowledge`, `save_file_to_knowledge`).
> Inoltre, il tool richiede l'iniezione dell'istanza `Knowledge` condivisa da `agent_os`,
> cosa non supportata dal loader generico che istanzia i tool SDK con semplici parametri.
> Per queste ragioni è implementato come plugin custom con il flag `special: true`.

## Funzionalità

- **`save_to_knowledge(name, content)`** — salva un testo nella knowledge base
- **`save_file_to_knowledge(file_path)`** — salva un file dalla sandbox nella knowledge base

Il tool viene attivato solo su richiesta esplicita dell'utente (es. "salvalo in memoria", "memorizza questo").

## Configurazione

1. Copiare il contenuto di `config.example.yaml` dentro `config/plugin.config.yaml`, nella sezione `tool:`
2. Il tool è marcato come `special: true` perché richiede l'istanza `Knowledge` iniettata da `core/agent_os.py` (non viene caricato dal loader generico)

## Dipendenze

Installare con:

```bash
uv pip install -r plugin/tool/knowledge_tool/requirements.txt
```

- `agno` (SDK) — per `Toolkit` e `Knowledge`
- `chromadb` — vector database (configurato in `agents.config.yaml`)

## Struttura

```
plugin/tool/knowledge_tool/
├── __init__.py          # Classe KnowledgeTool
├── config.yaml          # Config locale (agent_instructions lette dal loader)
├── config.example.yaml  # Esempio per plugin.config.yaml
├── requirements.txt     # Dipendenze del plugin
└── README.md
```
