# Creare un tool plugin

Un tool plugin è una classe Python che estende `agno.tools.Toolkit` e viene caricata automaticamente all'avvio dal loader.

## Struttura della directory

```text
plugin/tool/my_tool/
├── __init__.py          # Esporta la classe Toolkit
├── tool.py              # Implementazione (il nome del file è libero)
├── config.yaml          # Configurazione del plugin
└── requirements.txt     # Dipendenze pip (opzionale)
```

## 1. Implementa la classe Toolkit

Crea il modulo principale, ad esempio `tool.py`:

```python
from pathlib import Path
from agno.tools import Toolkit

class MyTool(Toolkit):
    """Descrizione breve del tool."""

    def __init__(self, base_dir: Path = Path("sandbox")):
        super().__init__(name="my_tool")
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.register(self.do_something)

    def do_something(self, text: str, count: int = 1) -> str:
        """Esegue un'operazione.

        Args:
            text: testo di input.
            count: quante volte ripetere (default 1).

        Returns:
            Messaggio con il risultato.
        """
        result = (text + "\n") * count
        out_path = self.base_dir / "output.txt"
        out_path.write_text(result, encoding="utf-8")
        return f"File creato: {out_path}"
```

Regole:

- Eredita da `agno.tools.Toolkit`.
- Chiama `super().__init__(name="...")` nel costruttore.
- Il costruttore riceve automaticamente `base_dir: Path` con il percorso della sandbox definito in `main.config.yaml`.
- Registra ogni metodo che vuoi esporre con `self.register(self.metodo)`. Solo i metodi registrati diventano tool disponibili per gli agenti.
- La docstring del metodo viene usata come descrizione del tool: scrivila chiara.
- I parametri del metodo diventano gli argomenti che l'agente può passare.
- Ritorna sempre una stringa: è il messaggio che l'agente riceve come risultato.

## 2. Esporta la classe

Crea `__init__.py`:

```python
"""My tool plugin."""

from plugin.tool.my_tool.tool import MyTool

__all__ = ["MyTool"]
```

Il loader importa il modulo `plugin.tool.<id>` e prende la classe esportata in `__all__`.

## 3. Scrivi la configurazione

Crea `config.yaml`:

```yaml
id: "my_tool"
name: "My Tool"
description: "Cosa fa il tool in una riga"
version: "0.1.0"
author: "Il tuo nome"

agent_instructions: |
  Usa do_something(text, count) quando l'utente chiede di generare un file di testo ripetuto.
  Restituisci sempre il percorso del file creato.
```

Campi:

| Campo | Obbligatorio | Descrizione |
|---|---|---|
| `id` | sì | Deve corrispondere al nome della directory |
| `name` | sì | Nome leggibile del tool |
| `description` | sì | Descrizione breve |
| `version` | sì | Versione semantica |
| `author` | sì | Autore |
| `agent_instructions` | no | Istruzioni iniettate nel prompt degli agenti: spiega quando e come usare il tool |

Le `agent_instructions` di tutti i tool abilitati vengono aggregate e iniettate negli agenti tramite la variabile `${plugin_instructions}` in `agents.config.yaml`.

## 4. Aggiungi le dipendenze

Crea `requirements.txt` con **tutte** le librerie di cui il plugin ha bisogno,
anche se sono già presenti nel progetto principale. Ogni plugin deve essere
auto-sufficiente e dichiarare esplicitamente le proprie dipendenze:

```text
agno>=2.5.11
markdown>=3.7
requests>=2.32
```

Il loader verifica e installa automaticamente le dipendenze all'avvio con
`uv pip` (o `pip` come fallback). Se il file non esiste viene ignorato.

## 5. Abilita il plugin

Aggiungi il tool in `config/plugin.config.yaml`:

```yaml
tool:
  - id: my_tool
    status: enabled
```

## 6. Assegna il tool a un agente

In `config/agents.config.yaml`, aggiungi il nome del tool nella lista `tools` dell'agente che deve usarlo:

```yaml
agents:
  file_manager:
    name: FileManager
    role: "Gestione file"
    tools:
      - my_tool
      - pdf_tool
    instructions:
      - "Usa i tool disponibili per le operazioni sui file"
```

Il nome usato nella lista `tools` corrisponde al `name` passato a `super().__init__(name="...")`.

## Esempio completo: pdf_tool

Il progetto include `plugin/tool/pdf_tool/` come riferimento:

- classe `PdfTool` in `tool.py`
- un solo metodo registrato: `create_pdf(file_name, title, body)`
- accetta Markdown nel body e genera un PDF formattato
- usa `fpdf2` e `markdown` come dipendenze
- le `agent_instructions` spiegano formato e parametri attesi

## Note

- Il tool viene istanziato una sola volta all'avvio.
- Se l'installazione delle dipendenze fallisce, il loader logga un warning ma prosegue.
- I tool marcati con `special: true` in `plugin.config.yaml` non vengono caricati dal loader standard e richiedono gestione dedicata nel core (es. `knowledge_tool`).
