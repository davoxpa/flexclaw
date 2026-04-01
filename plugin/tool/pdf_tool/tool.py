"""Tool per la generazione di file PDF da template HTML/CSS con supporto temi."""

import re
import tempfile
from pathlib import Path

import markdown
from agno.tools import Toolkit

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_DEFAULT_THEME = "modern"

# Descrizione dei temi disponibili
_THEME_DESCRIPTIONS: dict[str, str] = {
    "modern": "Moderno e professionale — header blu navy, accenti dorati, sans-serif",
    "editorial": "Editoriale — stile magazine, font serif, drop cap, layout giornalistico",
    "dark": "Dark mode — sfondo scuro, accenti indaco, ideale per contenuti tech",
}


class PdfTool(Toolkit):
    """Genera file PDF di alta qualità da template HTML/CSS tematizzati."""

    def __init__(self, base_dir: Path = Path("sandbox")):
        super().__init__(name="pdf_tool")
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.register(self.create_pdf)
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
        """Elenca i temi grafici disponibili per la generazione PDF.

        Returns:
            Lista dei temi disponibili con la loro descrizione.
        """
        available = [
            f"- **{name}**: {desc}"
            for name, desc in _THEME_DESCRIPTIONS.items()
            if (_TEMPLATES_DIR / f"{name}.html").exists()
        ]
        if not available:
            return "Nessun tema disponibile."
        return "Temi PDF disponibili:\n" + "\n".join(available)

    def create_pdf(
        self,
        file_name: str,
        title: str,
        body: str,
        theme: str = "modern",
    ) -> str:
        """Crea un PDF di alta qualità renderizzando un template HTML/CSS con Playwright.

        Args:
            file_name: Nome del file di output (es. "articolo.pdf").
            title: Titolo del documento mostrato nell'header del PDF.
            body: Contenuto in formato Markdown.
            theme: Tema grafico — "modern" (default), "editorial", "dark".

        Returns:
            Percorso del file creato, oppure messaggio di errore.
        """
        safe_name = Path(file_name).name
        if not safe_name.endswith(".pdf"):
            safe_name += ".pdf"
        file_path = self.base_dir / safe_name

        template_html = self._load_template(theme)
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



class PdfTool(Toolkit):
    """Genera file PDF con contenuto Markdown, con resa grafica curata."""

    def __init__(self, base_dir: Path = Path("sandbox")):
        super().__init__(name="pdf_tool")
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.register(self.create_pdf)

    @staticmethod
    def _prepare_body(body: str) -> str:
        """Sanitizza il body prima della conversione Markdown → HTML."""
        # Rimuove il titolo H1 iniziale (viene già usato nel frontespizio come 'title')
        lines = body.strip().splitlines()
        if lines and lines[0].lstrip().startswith("# "):
            lines = lines[1:]
        text = "\n".join(lines).strip()
        # Rimuove la riga "ARTICOLO COMPLETATO" aggiunta dal writer
        text = re.sub(r"\n?ARTICOLO COMPLETATO[^\n]*\n?", "", text).strip()
        return text

    @staticmethod
    def _sanitize_html(html: str) -> str:
        """Rimuove o sostituisce tag HTML non supportati da fpdf2 write_html."""
        # <hr> non è supportato: sostituisci con uno spazio vuoto
        html = re.sub(r"<hr\s*/?>", "<br/>", html, flags=re.IGNORECASE)
        return html

    def create_pdf(self, file_name: str, title: str, body: str) -> str:
        """Crea un PDF esteticamente curato a partire da contenuto Markdown.

        Il body supporta la sintassi Markdown: **grassetto**, *corsivo*,
        # titoli, - elenchi, 1. elenchi numerati, ecc.

        Args:
            file_name: Nome del file (es. "barzelletta.pdf").
            title: Titolo del documento mostrato in copertina.
            body: Contenuto in formato Markdown.

        Returns:
            Percorso del file creato, oppure un messaggio di errore.
        """
        safe_name = Path(file_name).name
        if not safe_name.endswith(".pdf"):
            safe_name += ".pdf"
        file_path = self.base_dir / safe_name

        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=20)
            pdf.set_margins(25, 20, 25)
            pdf.add_page()

            # Linea decorativa superiore
            pdf.set_draw_color(*_ACCENT)
            pdf.set_line_width(0.8)
            pdf.line(25, 18, pdf.w - 25, 18)

            # Titolo principale
            pdf.ln(8)
            pdf.set_text_color(*_PRIMARY)
            pdf.set_font("Helvetica", style="B", size=18)
            pdf.multi_cell(0, 8, title, align="C")
            pdf.ln(4)

            # Linea sotto il titolo
            y = pdf.get_y()
            pdf.line(60, y, pdf.w - 60, y)
            pdf.ln(6)

            # Corpo — sanitizza body, converti Markdown in HTML e renderizza
            pdf.set_text_color(*_TEXT)
            pdf.set_font("Helvetica", size=10)
            clean_body = self._prepare_body(body)
            body_html = markdown.markdown(
                clean_body,
                extensions=["tables", "sane_lists"],
            )
            body_html = self._sanitize_html(body_html)
            pdf.write_html(body_html, tag_styles=_TAG_STYLES)

            pdf.output(str(file_path))
            return f"PDF creato: {file_path}"
        except Exception as e:
            return f"Errore nella creazione del PDF: {e}"
