"""Tool per la generazione di file PDF esteticamente curati."""

from pathlib import Path

import markdown
from agno.tools import Toolkit
from fpdf import FPDF
from fpdf.fonts import TextStyle

# Colori del tema — palette calma e professionale
_PRIMARY = (45, 55, 72)       # Blu-ardesia scuro per titoli
_ACCENT = (214, 158, 46)      # Oro caldo per linee decorative
_TEXT = (55, 65, 81)           # Grigio antracite per il corpo

# Stili per i tag HTML nel corpo del PDF
_TAG_STYLES = {
    "h1": TextStyle(font_family="Helvetica", font_size_pt=16, font_style="B", color=_PRIMARY),
    "h2": TextStyle(font_family="Helvetica", font_size_pt=14, font_style="B", color=_PRIMARY),
    "h3": TextStyle(font_family="Helvetica", font_size_pt=12, font_style="B", color=_PRIMARY),
    "h4": TextStyle(font_family="Helvetica", font_size_pt=11, font_style="B", color=_TEXT),
    "p":  TextStyle(font_family="Helvetica", font_size_pt=10, color=_TEXT),
    "li": TextStyle(font_family="Helvetica", font_size_pt=10, color=_TEXT),
    "a":  TextStyle(font_family="Helvetica", font_size_pt=10, color=(30, 90, 160)),
    "code": TextStyle(font_family="Courier", font_size_pt=9, color=(80, 80, 80)),
    "pre": TextStyle(font_family="Courier", font_size_pt=9, color=(80, 80, 80)),
    "blockquote": TextStyle(font_family="Helvetica", font_size_pt=10, font_style="I", color=(100, 100, 100)),
}


class PdfTool(Toolkit):
    """Genera file PDF con contenuto Markdown, con resa grafica curata."""

    def __init__(self, base_dir: Path = Path("sandbox")):
        super().__init__(name="pdf_tool")
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.register(self.create_pdf)

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

            # Corpo — converti Markdown in HTML e renderizza con stili appropriati
            pdf.set_text_color(*_TEXT)
            pdf.set_font("Helvetica", size=10)
            body_html = markdown.markdown(
                body,
                extensions=["tables", "sane_lists"],
            )
            pdf.write_html(body_html, tag_styles=_TAG_STYLES)

            pdf.output(str(file_path))
            return f"PDF creato: {file_path}"
        except Exception as e:
            return f"Errore nella creazione del PDF: {e}"
