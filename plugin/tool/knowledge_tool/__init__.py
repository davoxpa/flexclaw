"""Tool per salvare contenuti nella knowledge base."""

import logging
from pathlib import Path

from agno.knowledge.knowledge import Knowledge
from agno.tools import Toolkit

logger = logging.getLogger(__name__)


class KnowledgeTool(Toolkit):
    """Permette agli agenti di salvare contenuti nella knowledge base a runtime."""

    def __init__(self, knowledge: Knowledge, base_dir: Path = Path("sandbox")):
        super().__init__(name="knowledge_tool")
        self.knowledge = knowledge
        self.base_dir = base_dir
        self.register(self.save_to_knowledge)
        self.register(self.save_file_to_knowledge)

    def save_to_knowledge(self, name: str, content: str, description: str = "") -> str:
        """Salva un testo nella knowledge base per poterlo consultare in futuro.

        Args:
            name: Nome identificativo del contenuto (es. "Ricerca su AI framework").
            content: Il testo completo da memorizzare.
            description: Descrizione opzionale del contenuto.

        Returns:
            Conferma del salvataggio oppure messaggio di errore.
        """
        try:
            self.knowledge.insert(
                name=name,
                text_content=content,
                metadata={"source": "user_request", "type": "text"},
            )
            logger.info("Contenuto salvato in knowledge: %s", name)
            return f"Contenuto '{name}' salvato nella knowledge base."
        except Exception as e:
            logger.exception("Errore nel salvataggio in knowledge: %s", name)
            return f"Errore nel salvataggio: {e}"

    def save_file_to_knowledge(self, file_path: str, name: str = "", description: str = "") -> str:
        """Salva un file dalla sandbox nella knowledge base.

        Args:
            file_path: Nome del file nella sandbox (es. "report.pdf").
            name: Nome identificativo opzionale. Se vuoto usa il nome del file.
            description: Descrizione opzionale del contenuto.

        Returns:
            Conferma del salvataggio oppure messaggio di errore.
        """
        full_path = self.base_dir / Path(file_path).name
        if not full_path.exists():
            return f"File non trovato: {full_path}"

        doc_name = name or full_path.stem
        try:
            self.knowledge.insert(
                name=doc_name,
                path=str(full_path),
                metadata={
                    "source": "file",
                    "type": full_path.suffix.lstrip("."),
                    "original_name": full_path.name,
                },
            )
            logger.info("File salvato in knowledge: %s → %s", full_path.name, doc_name)
            return f"File '{full_path.name}' salvato nella knowledge base come '{doc_name}'."
        except Exception as e:
            logger.exception("Errore nel salvataggio file in knowledge: %s", full_path.name)
            return f"Errore nel salvataggio: {e}"
