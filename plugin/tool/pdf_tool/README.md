# PDF Tool

Plugin custom per la generazione di file PDF esteticamente curati a partire da contenuto Markdown.

## Funzionalità

- **`create_pdf(file_name, title, body)`** — crea un PDF nella sandbox con titolo e corpo in Markdown

Il body supporta la sintassi Markdown completa: titoli, grassetto, corsivo, elenchi puntati e numerati, link, codice.

## Configurazione

1. Copiare il contenuto di `config.example.yaml` dentro `config/plugin.config.yaml`, nella sezione `tool:`
2. Il tool riceve automaticamente `base_dir` dalla config globale (`sandbox_dir` in `main.config.yaml`)

## Dipendenze

Installare con:

```bash
uv pip install -r plugin/tool/pdf_tool/requirements.txt
```

- `agno` (SDK) — per `Toolkit`
- `fpdf2` — generazione PDF
- `markdown` — conversione Markdown → HTML

## Struttura

```
plugin/tool/pdf_tool/
├── __init__.py          # Export della classe PdfTool
├── tool.py              # Implementazione del generatore PDF
├── config.yaml          # Config locale (agent_instructions lette dal loader)
├── config.example.yaml  # Esempio per plugin.config.yaml
├── requirements.txt     # Dipendenze del plugin
└── README.md
```
