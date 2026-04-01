"""Tool per la generazione di file PDF da template HTML/CSS con supporto temi."""

import re
import tempfile
from pathlib import Path

import markdown
import yaml
from agno.tools import Toolkit

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_THEMES_CONFIG = _TEMPLATES_DIR / "themes.yaml"
_DEFAULT_THEME = "minimal"


def _load_themes_config() -> dict:
    """Legge themes.yaml e restituisce il dizionario dei temi."""
    if not _THEMES_CONFIG.exists():
        return {}
    return yaml.safe_load(_THEMES_CONFIG.read_text(encoding="utf-8")).get("themes", {})


class PdfTool(Toolkit):
    """Genera file PDF di alta qualità da template HTML/CSS tematizzati."""

    def __init__(self, base_dir: Path = Path("sandbox")):
        super().__init__(name="pdf_tool")
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # Tema corrente — modificabile a runtime tramite set_pdf_theme() o get_theme_for_tags()
        self._current_theme: str = _DEFAULT_THEME
        self.register(self.create_pdf)
        self.register(self.set_pdf_theme)
        self.register(self.get_theme_for_tags)
        self.register(self.list_themes)

    @staticmethod
    def _prepare_body(body: str) -> str:
        """Sanitizza il body Markdown prima della conversione in HTML."""
        # Rimuove il titolo H1 iniziale (già usato come title nel template del PDF)
        lines = body.strip().splitlines()
        if lines and lines[0].lstrip().startswith("# "):
            lines = lines[1:]
        text = "\n".join(lines).strip()
        # Rimuove la riga "ARTICOLO COMPLETATO" eventualmente aggiunta dal writer
        text = re.sub(r"\n?ARTICOLO COMPLETATO[^\n]*\n?", "", text).strip()
        return text

    @staticmethod
    def _load_template(theme: str) -> str | None:
        """Carica il template HTML del tema richiesto.

        Fallback al tema 'modern' se il tema richiesto non esiste.
        Restituisce None se nessun template è disponibile.
        """
        template_path = _TEMPLATES_DIR / f"{theme}.html"
        if not template_path.exists():
            template_path = _TEMPLATES_DIR / f"{_DEFAULT_THEME}.html"
        if not template_path.exists():
            return None
        return template_path.read_text(encoding="utf-8")

    def list_themes(self) -> str:
        """Elenca i temi grafici disponibili con i loro tag e il tema attualmente attivo.

        Usa questo tool per scoprire quali temi e tag sono disponibili.

        Returns:
            Lista dei temi con descrizione, tag e tema corrente selezionato.
        """
        themes = _load_themes_config()
        if not themes:
            return "Nessun tema disponibile."

        lines = [f"Tema corrente: **{self._current_theme}**\n"]
        for name, data in themes.items():
            if not (_TEMPLATES_DIR / f"{name}.html").exists():
                continue
            tags_str = ", ".join(data.get("tags", []))
            lines.append(f"**{name}** — {data.get('description', '')}")
            lines.append(f"  Tag: {tags_str}")
        return "\n".join(lines)

    def get_theme_for_tags(self, tags: str) -> str:
        """Restituisce il tema PDF migliore in base ai tag del contenuto dell'articolo.

        Analizza i tag forniti e seleziona automaticamente il tema più adatto,
        impostandolo come tema corrente per il prossimo create_pdf.

        Chiama questo tool PRIMA di create_pdf, passando i tag che descrivono
        il tipo di contenuto dell'articolo (es. "tech, ai, cybersecurity").

        Args:
            tags: Stringa di tag separati da virgola che descrivono il contenuto
                  (es. "tech, intelligenza-artificiale, startup").

        Returns:
            Nome del tema selezionato e impostato, con spiegazione.
        """
        themes = _load_themes_config()
        if not themes:
            self._current_theme = _DEFAULT_THEME
            return f"Tema impostato: {_DEFAULT_THEME} (nessun registro temi trovato)"

        # Normalizza i tag in input
        input_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}

        # Conta le corrispondenze per ogni tema
        best_theme = _DEFAULT_THEME
        best_score = 0
        for theme_name, data in themes.items():
            if not (_TEMPLATES_DIR / f"{theme_name}.html").exists():
                continue
            theme_tags = {t.lower() for t in data.get("tags", [])}
            score = len(input_tags & theme_tags)
            if score > best_score:
                best_score = score
                best_theme = theme_name

        self._current_theme = best_theme
        if best_score == 0:
            return (
                f"Tema impostato: **{best_theme}** (default — nessun tag corrispondente trovato)"
            )
        matched = input_tags & {t.lower() for t in themes[best_theme].get("tags", [])}
        return (
            f"Tema impostato: **{best_theme}** "
            f"(tag corrispondenti: {', '.join(sorted(matched))})"
        )

    def set_pdf_theme(self, theme: str) -> str:
        """Seleziona manualmente il tema grafico da usare per il prossimo PDF generato.

        Usa get_theme_for_tags() per la selezione automatica basata sul contenuto.
        Usa questo tool solo se l'utente specifica esplicitamente un nome di tema.

        Args:
            theme: Nome del tema. Valori validi: "modern", "editorial", "dark".

        Returns:
            Conferma del tema impostato oppure errore se il tema non esiste.
        """
        if not (_TEMPLATES_DIR / f"{theme}.html").exists():
            available = ", ".join(p.stem for p in _TEMPLATES_DIR.glob("*.html"))
            return f"Tema '{theme}' non trovato. Temi disponibili: {available}"
        self._current_theme = theme
        return f"Tema impostato: {theme}"

    def create_pdf(self, file_name: str, title: str, body: str) -> str:
        """Crea un PDF di alta qualità renderizzando un template HTML/CSS con Playwright.

        Usa il tema selezionato con set_pdf_theme() (default: "modern").

        Args:
            file_name: Nome del file di output (es. "articolo.pdf").
            title: Titolo del documento mostrato nell'header del PDF.
            body: Contenuto in formato Markdown.

        Returns:
            Percorso del file creato, oppure messaggio di errore.
        """
        safe_name = Path(file_name).name
        if not safe_name.endswith(".pdf"):
            safe_name += ".pdf"
        file_path = self.base_dir / safe_name

        template_html = self._load_template(self._current_theme)
        if not template_html:
            return "Errore: nessun template HTML trovato nella cartella templates/."

        try:
            from playwright.sync_api import sync_playwright

            # Converti Markdown → HTML e inietta nel template
            clean_body = self._prepare_body(body)
            body_html = markdown.markdown(
                clean_body,
                extensions=["tables", "sane_lists"],
            )
            page_html = (
                template_html
                .replace("__TITLE__", title)
                .replace("__BODY_HTML__", body_html)
            )

            # Scrivi HTML temporaneo, renderizza con Playwright, rimuovi il temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", encoding="utf-8", delete=False
            ) as tmp:
                tmp.write(page_html)
                tmp_path = Path(tmp.name)

            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(
                        args=["--no-sandbox", "--disable-setuid-sandbox"]
                    )
                    page = browser.new_page()
                    page.goto(f"file://{tmp_path.resolve()}", wait_until="networkidle")
                    page.pdf(
                        path=str(file_path),
                        format="A4",
                        print_background=True,
                    )
                    browser.close()
            finally:
                tmp_path.unlink(missing_ok=True)

            return f"PDF creato: {file_path}"

        except Exception as e:
            return f"Errore nella creazione del PDF: {e}"
