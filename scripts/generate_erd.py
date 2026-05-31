"""
Generuje ERD z metadanych SQLAlchemy (modele z app.py).
Zapisuje: docs/erd.mmd (Mermaid), docs/erd.svg (Graphviz, jeśli dot dostępny), docs/erd.dot.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Katalog główny projektu (scripts/ -> parent)
ROOT = Path(__file__).resolve().parent.parent


def _find_dot_exe() -> str | None:
    if p := os.environ.get("GRAPHVIZ_DOT"):
        if Path(p).is_file():
            return p
    candidates = [
        Path(r"C:\Program Files\Graphviz\bin\dot.exe"),
        Path(r"C:\Program Files (x86)\Graphviz\bin\dot.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None
DOCS = ROOT / "docs"
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mermaid_type(col) -> str:
    """Mapuje typ SQLAlchemy na krótką nazwę zgodną z erDiagram."""
    t = col.type.__class__.__name__.lower()
    if t == "integer":
        return "int"
    if t in ("string", "varchar", "nvarchar", "char"):
        return "varchar"
    if t == "text":
        return "text"
    if t == "boolean":
        return "boolean"
    if "datetime" in t:
        return "datetime"
    return "varchar"


def build_mermaid(metadata) -> str:
    lines = [
        "%% ERD wygenerowany z SQLAlchemy metadata (models/__init__.py via app)",
        "erDiagram",
    ]
    table_order = sorted(metadata.tables.keys())
    for tname in table_order:
        table = metadata.tables[tname]
        lines.append(f"    {tname} {{")
        for col in table.columns:
            mt = _mermaid_type(col)
            pk = " PK" if col.primary_key else ""
            fk = " FK" if col.foreign_keys else ""
            lines.append(f"        {mt} {col.name}{pk}{fk}")
        lines.append("    }")

    seen_rel = set()
    for tname in table_order:
        table = metadata.tables[tname]
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            child = tname
            key = (parent, child)
            if key in seen_rel:
                continue
            seen_rel.add(key)
            lines.append(f'    {parent} ||--o{{ {child} : has')

    lines.append("")
    return "\n".join(lines)


def build_graphviz_dot(metadata) -> str:
    """Czysty DOT (bez pygraphviz) — do ręcznego renderu lub graphviz Python."""
    lines = [
        "digraph ERD {",
        '  rankdir=LR;',
        '  node [shape=plaintext fontname="Segoe UI" fontsize=10];',
        '  edge [fontsize=9 fontname="Segoe UI"];',
    ]
    for tname in sorted(metadata.tables.keys()):
        table = metadata.tables[tname]
        rows = []
        for col in table.columns:
            flags = []
            if col.primary_key:
                flags.append("PK")
            if col.foreign_keys:
                flags.append("FK")
            fl = f" ({','.join(flags)})" if flags else ""
            rows.append(f'<tr><td align="left" balign="left">{col.name}: {col.type}{fl}</td></tr>')
        label = (
            f'<<table border="0" cellborder="1" cellspacing="0">'
            f'<tr><td bgcolor="#e8e8f8"><b>{tname}</b></td></tr>'
            + "".join(rows)
            + "</table>>"
        )
        safe_id = tname.replace("-", "_")
        lines.append(f'  "{safe_id}" [label={label}];')

    for tname in sorted(metadata.tables.keys()):
        table = metadata.tables[tname]
        for fk in table.foreign_keys:
            ref_table = fk.column.table.name
            # Strzałka od tabeli z FK do tabeli referencjonowanej (dziecko -> rodzic)
            lines.append(f'  "{tname}" -> "{ref_table}" [label="FK", arrowhead=vee];')

    lines.append("}")
    return "\n".join(lines)


def render_erd_matplotlib(metadata, out_png: Path, out_svg: Path | None = None) -> None:
    """Fallback: diagram ERD jako PNG/SVG (matplotlib), bez Graphviz."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    tables = sorted(metadata.tables.keys())
    # Układ stały dopasowany do 5 tabel projektu (czytelność > automatyczny layout force)
    positions = {
        "users": (5.0, 8.5),
        "notes": (1.2, 5.5),
        "quizzes": (5.0, 5.5),
        "flashcards": (8.8, 5.5),
        "quiz_attempts": (5.0, 2.2),
    }
    box_w, box_h_base = 2.6, 1.05

    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 10)
    ax.axis("off")
    fig.patch.set_facecolor("#fafafa")
    ax.set_facecolor("#fafafa")

    boxes: dict[str, tuple[float, float, float, float]] = {}

    for tname in tables:
        table = metadata.tables[tname]
        lines = [tname]
        for col in table.columns:
            flags = []
            if col.primary_key:
                flags.append("PK")
            if col.foreign_keys:
                flags.append("FK")
            suf = f" ({','.join(flags)})" if flags else ""
            lines.append(f"{col.name}: {col.type}{suf}")
        nlines = len(lines)
        h = max(box_h_base, 0.28 * nlines + 0.5)
        cx, cy = positions.get(tname, (5.0, 5.0))
        x = cx - box_w / 2
        y = cy - h / 2
        boxes[tname] = (x, y, box_w, h)
        patch = FancyBboxPatch(
            (x, y),
            box_w,
            h,
            boxstyle="round,pad=0.06,rounding_size=0.08",
            linewidth=1.2,
            edgecolor="#4f46e5",
            facecolor="#ffffff",
        )
        ax.add_patch(patch)
        ax.text(
            cx,
            y + h - 0.35,
            lines[0],
            ha="center",
            va="top",
            fontsize=11,
            fontweight="bold",
            color="#1e1b4b",
        )
        body = "\n".join(lines[1:])
        ax.text(
            x + 0.12,
            y + h - 0.65,
            body,
            ha="left",
            va="top",
            fontsize=8,
            family="monospace",
            color="#334155",
        )

    # Strzałki FK: dziecko (ma kolumnę FK) -> rodzic
    drawn = set()
    for tname in sorted(metadata.tables.keys()):
        table = metadata.tables[tname]
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            key = (tname, parent)
            if key in drawn:
                continue
            drawn.add(key)
            if tname not in boxes or parent not in boxes:
                continue
            x1, y1, w1, h1 = boxes[tname]
            x2, y2, w2, h2 = boxes[parent]
            # Środek górnej krawędzi dziecka -> środek dolnej krawędzi rodzica (uproszczone)
            sx = x1 + w1 / 2
            sy = y1 + h1
            tx = x2 + w2 / 2
            ty = y2
            arrow = FancyArrowPatch(
                (sx, sy),
                (tx, ty),
                arrowstyle="-|>",
                mutation_scale=12,
                linewidth=1.0,
                color="#64748b",
                connectionstyle="arc3,rad=0.1",
                shrinkA=4,
                shrinkB=4,
            )
            ax.add_patch(arrow)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    if out_svg:
        fig.savefig(out_svg, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    from app import app, db

    DOCS.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        metadata = db.metadata

    mmd = build_mermaid(metadata)
    (DOCS / "erd.mmd").write_text(mmd, encoding="utf-8")

    dot_src = build_graphviz_dot(metadata)
    (DOCS / "erd.dot").write_text(dot_src, encoding="utf-8")

    graphviz_ok = False
    try:
        import graphviz

        dot_path = _find_dot_exe()
        if dot_path:
            graphviz.backend.dot_command.DOT_BINARY = dot_path  # type: ignore[attr-defined]

        source = graphviz.Source(dot_src)
        out_base = str(DOCS / "erd")
        source.render(filename=out_base, format="svg", cleanup=True)
        print(f"OK: {DOCS / 'erd.svg'}")
        source.render(filename=out_base, format="png", cleanup=True)
        print(f"OK: {DOCS / 'erd.png'}")
        graphviz_ok = True
    except Exception as e:
        print(f"Graphviz render: {e}")

    if not graphviz_ok or not (DOCS / "erd.png").exists():
        try:
            render_erd_matplotlib(metadata, DOCS / "erd.png", DOCS / "erd.svg")
            print(f"OK (matplotlib fallback): {DOCS / 'erd.png'}")
            print(f"OK (matplotlib fallback): {DOCS / 'erd.svg'}")
        except Exception as e:
            print(f"Matplotlib fallback: {e}")

    print(f"OK: {DOCS / 'erd.mmd'}")
    print(f"OK: {DOCS / 'erd.dot'}")


if __name__ == "__main__":
    main()
