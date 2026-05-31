from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def draw_wrapped_text(pdf: canvas.Canvas, text: str, x: int, y: int, max_width: int, line_height: int) -> int:
    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        if pdf.stringWidth(test_line, "Helvetica", 11) <= max_width:
            line = test_line
        else:
            pdf.drawString(x, y, line)
            y -= line_height
            line = word
            if y < 60:
                pdf.showPage()
                pdf.setFont("Helvetica", 11)
                y = 800
    if line:
        pdf.drawString(x, y, line)
        y -= line_height
    return y


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    input_path = base_dir / "docs" / "licencjat-review.txt"
    output_path = base_dir / "docs" / "licencjat-review.pdf"

    content = input_path.read_text(encoding="utf-8")

    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    pdf.setTitle("Licencjat Review")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 820, "Review pracy licencjackiej - StudyFlow")
    pdf.setFont("Helvetica", 11)

    y = 790
    for paragraph in content.splitlines():
        if not paragraph.strip():
            y -= 10
        else:
            y = draw_wrapped_text(pdf, paragraph, x=50, y=y, max_width=495, line_height=15)

        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 11)
            y = 800

    pdf.save()
    print(output_path)


if __name__ == "__main__":
    main()
