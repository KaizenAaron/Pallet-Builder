"""Box-index spreadsheet: template, import (xlsx/csv) and export.

One row per box. A product with two boxes has two rows with the same SKU and Box # 1 and 2.
Rows match products on SKU and boxes on (SKU, Box #). Import upserts and **never deletes** —
a partial file only touches what it lists. A row with a SKU but no box columns at all creates or
renames the product without boxes.

`parse_rows` is pure (no database); `apply_import` writes, and runs as a dry run when asked so
the UI can preview the outcome first.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Product, ProductBox

MAX_ROWS = 20000

# (canonical key, header text in the template, accepted aliases)
COLUMNS: list[tuple[str, str, tuple[str, ...]]] = [
    ("sku", "SKU", ("sku", "internalreference", "productcode", "itemnumber", "partnumber", "defaultcode")),
    ("product_name", "Product Name", ("productname", "name", "product", "description")),
    ("box_no", "Box #", ("box", "boxno", "boxnumber", "boxnum")),
    ("box_name", "Box Name", ("boxname", "boxdescription")),
    ("qty_per_unit", "Qty per Unit", ("qtyperunit", "boxesperunit", "quantityperunit")),
    ("units_per_box", "Units per Box", ("unitsperbox", "unitspercarton", "packqty", "casepack")),
    ("length", "Length in", ("lengthin", "length", "l", "lengthinches")),
    ("width", "Width in", ("widthin", "width", "w", "widthinches")),
    ("height", "Height in", ("heightin", "height", "h", "heightinches")),
    ("weight", "Weight lb", ("weightlb", "weightlbs", "weight", "wt", "weightpounds")),
    ("this_side_up", "This Side Up (Y/N)", ("thissideupyn", "thissideup", "upright", "keepupright")),
    ("stackable", "Stackable (Y/N)", ("stackableyn", "stackable", "canstack")),
    ("max_load_on_top", "Max Load on Top lb", ("maxloadontoplb", "maxloadontop", "maxtopload", "maxstackweight")),
]
HEADERS = [c[1] for c in COLUMNS]
BOX_FIELDS = ("length", "width", "height", "weight")

TRUE = {"y", "yes", "true", "1", "x"}
FALSE = {"n", "no", "false", "0", ""}


def _norm(h: object) -> str:
    return re.sub(r"[^a-z0-9#]", "", str(h or "").lower()).replace("#", "")


ALIASES = {alias: key for key, _, aliases in COLUMNS for alias in aliases}
ALIASES.update({_norm(header): key for key, header, _ in COLUMNS})


class ImportFileError(ValueError):
    """The file as a whole can't be read (wrong type, no SKU column, too many rows…)."""


@dataclass
class BoxRow:
    row: int
    sku: str
    product_name: str | None
    box: dict | None  # None = product-only row


@dataclass
class ParseResult:
    rows: list[BoxRow] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- reading files
def read_table(filename: str, data: bytes) -> list[list[object]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 — openpyxl raises many types for bad files
            raise ImportFileError("This doesn't look like a valid Excel (.xlsx) file.") from e
        ws = wb["Boxes"] if "Boxes" in wb.sheetnames else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return table
    if name.endswith((".csv", ".txt")):
        text = data.decode("utf-8-sig", errors="replace")
        return [list(r) for r in csv.reader(io.StringIO(text))]
    if name.endswith(".xls"):
        raise ImportFileError("Old .xls files aren't supported. Open it in Excel and save as .xlsx (or .csv).")
    raise ImportFileError("Upload an .xlsx or .csv file.")


def _num(v: object, label: str, *, integer: bool = False, positive: bool = False) -> float | int:
    if isinstance(v, bool):
        raise ValueError(f"{label} must be a number")
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = re.sub(r"(?i)\s*(in|inch|inches|lb|lbs|\"|')\s*$", "", str(v).strip()).replace(",", "")
        try:
            n = float(s)
        except ValueError:
            raise ValueError(f"{label} must be a number (got {str(v)!r})") from None
    if positive and n <= 0:
        raise ValueError(f"{label} must be greater than 0")
    if n < 0:
        raise ValueError(f"{label} can't be negative")
    if integer:
        if n != int(n):
            raise ValueError(f"{label} must be a whole number")
        return int(n)
    return n


def _bool(v: object, label: str, default: bool) -> bool:
    if v is None or (isinstance(v, str) and not v.strip()):
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in TRUE:
        return True
    if s in FALSE:
        return False
    raise ValueError(f"{label} must be Y or N (got {str(v)!r})")


def _blank(v: object) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def parse_rows(table: list[list[object]]) -> ParseResult:
    res = ParseResult()
    # header = first row with any cell matching a known column
    header_idx = next(
        (i for i, r in enumerate(table[:20]) if any(_norm(c) in ALIASES for c in r if not _blank(c))), None
    )
    if header_idx is None:
        raise ImportFileError("Couldn't find a header row. Start from the template (it has an SKU column).")
    header = table[header_idx]
    colmap: dict[str, int] = {}
    for i, h in enumerate(header):
        if _blank(h):
            continue
        key = ALIASES.get(_norm(h))
        if key and key not in colmap:
            colmap[key] = i
        elif not key:
            res.ignored_columns.append(str(h))
    if "sku" not in colmap:
        raise ImportFileError("The file needs an SKU column.")
    body = table[header_idx + 1 :]
    if len(body) > MAX_ROWS:
        raise ImportFileError(f"Too many rows (max {MAX_ROWS:,}). Split the file and import in parts.")

    seen: dict[tuple[str, int], int] = {}
    next_box: dict[str, int] = {}
    for offset, raw in enumerate(body):
        rownum = header_idx + offset + 2  # 1-based spreadsheet row number
        cell = lambda k: raw[colmap[k]] if k in colmap and colmap[k] < len(raw) else None  # noqa: E731
        if all(_blank(c) for c in raw):
            continue
        sku = "" if _blank(cell("sku")) else str(cell("sku")).strip()
        if isinstance(cell("sku"), float) and cell("sku").is_integer():
            sku = str(int(cell("sku")))  # Excel turns numeric SKUs into floats
        if not sku:
            res.errors.append({"row": rownum, "message": "SKU is empty"})
            continue
        name = None if _blank(cell("product_name")) else str(cell("product_name")).strip()
        box_values = [cell(k) for k in BOX_FIELDS]
        if all(_blank(v) for v in box_values) and _blank(cell("box_no")):
            res.rows.append(BoxRow(rownum, sku, name, None))
            continue
        try:
            missing = [lbl for k, lbl in zip(BOX_FIELDS, ("Length", "Width", "Height", "Weight")) if _blank(cell(k))]
            if missing:
                raise ValueError(f"missing {', '.join(missing)}")
            if _blank(cell("box_no")):
                box_no = next_box.get(sku, 0) + 1
            else:
                box_no = _num(cell("box_no"), "Box #", integer=True, positive=True)
            box = {
                "box_no": box_no,
                "name": (str(cell("box_name")).strip() if not _blank(cell("box_name")) else f"Box {box_no}")[:200],
                "qty_per_unit": 1 if _blank(cell("qty_per_unit")) else _num(cell("qty_per_unit"), "Qty per Unit", integer=True, positive=True),
                "units_per_box": 1 if _blank(cell("units_per_box")) else _num(cell("units_per_box"), "Units per Box", integer=True, positive=True),
                "length": _num(cell("length"), "Length", positive=True),
                "width": _num(cell("width"), "Width", positive=True),
                "height": _num(cell("height"), "Height", positive=True),
                "weight": _num(cell("weight"), "Weight"),
                "this_side_up": _bool(cell("this_side_up"), "This Side Up", False),
                "stackable": _bool(cell("stackable"), "Stackable", True),
                "max_load_on_top": 0.0 if _blank(cell("max_load_on_top")) else _num(cell("max_load_on_top"), "Max Load on Top"),
            }
        except ValueError as e:
            res.errors.append({"row": rownum, "sku": sku, "message": str(e)})
            continue
        key = (sku.lower(), box["box_no"])
        if key in seen:
            res.errors.append(
                {"row": rownum, "sku": sku, "message": f"Box #{box['box_no']} for {sku} is already on row {seen[key]}"}
            )
            continue
        seen[key] = rownum
        next_box[sku] = max(next_box.get(sku, 0), box["box_no"])
        res.rows.append(BoxRow(rownum, sku, name, box))
    return res


# ---------------------------------------------------------------- applying
BOX_ATTRS = ("name", "qty_per_unit", "units_per_box", "length", "width", "height", "weight",
             "this_side_up", "stackable", "max_load_on_top")


def apply_import(db: Session, company_id: int, parsed: ParseResult, *, dry_run: bool) -> dict:
    products = {
        p.sku.lower(): p
        for p in db.scalars(select(Product).where(Product.company_id == company_id)).all()
    }
    summary = {
        "products_created": 0, "products_updated": 0, "boxes_created": 0, "boxes_updated": 0,
        "unchanged_rows": 0, "rows_read": len(parsed.rows) + len(parsed.errors),
    }
    touched_products: set[str] = set()
    for row in parsed.rows:
        key = row.sku.lower()
        p = products.get(key)
        changed = False
        if p is None:
            p = Product(company_id=company_id, sku=row.sku, name=row.product_name or row.sku, source="import")
            products[key] = p
            db.add(p)
            summary["products_created"] += 1
            touched_products.add(key)
            changed = True
        elif row.product_name and row.product_name != p.name:
            p.name = row.product_name
            if key not in touched_products:
                summary["products_updated"] += 1
                touched_products.add(key)
            changed = True
        if row.box is not None:
            existing = next((b for b in p.boxes if b.box_no == row.box["box_no"]), None)
            if existing is None:
                p.boxes.append(ProductBox(company_id=company_id, box_no=row.box["box_no"], **{a: row.box[a] for a in BOX_ATTRS}))
                summary["boxes_created"] += 1
                changed = True
            elif any(getattr(existing, a) != row.box[a] for a in BOX_ATTRS):
                for a in BOX_ATTRS:
                    setattr(existing, a, row.box[a])
                summary["boxes_updated"] += 1
                changed = True
        if not changed:
            summary["unchanged_rows"] += 1
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return {**summary, "errors": parsed.errors, "ignored_columns": parsed.ignored_columns, "dry_run": dry_run}


# ---------------------------------------------------------------- template / export
_HEAD_FILL = PatternFill("solid", fgColor="1F6FEB")
_HEAD_FONT = Font(bold=True, color="FFFFFF")
_WIDTHS = [16, 34, 7, 22, 12, 12, 10, 10, 10, 10, 18, 15, 18]

INSTRUCTIONS = [
    ("How to fill in the Boxes sheet", True),
    ("One row per box. If one unit of a product ships in two boxes, give it two rows with the same SKU and Box # 1 and 2.", False),
    ("SKU matches the product's Internal Reference in Odoo. Product Name is optional when the product already exists.", False),
    ("Box # defaults to 1, 2, 3… in the order rows appear for a SKU. Box Name defaults to 'Box 1', 'Box 2'…", False),
    ("Qty per Unit: how many of this box one unit needs (usually 1).", False),
    ("Units per Box: for small items packed several to a carton — e.g. 12 means one box holds 12 units.", False),
    ("Length / Width / Height in inches, Weight in pounds (the packed box, not the bare product).", False),
    ("This Side Up: Y means the box may turn but never tip over. Stackable: N means nothing may go on top.", False),
    ("Max Load on Top: the most weight (lb) that may rest on the box. Leave blank or 0 for no limit.", False),
    ("Re-importing updates matching boxes and adds new ones. Nothing is ever deleted by an import.", False),
    ("", False),
    ("Example", True),
]
EXAMPLE = [
    ["FIX-2400", "24 in Linear Fixture", 1, "Housing", 1, 1, 50, 8, 6, 22.5, "N", "Y", 150],
    ["FIX-2400", "24 in Linear Fixture", 2, "Lens + driver", 1, 1, 26, 10, 4, 6, "Y", "Y", 40],
    ["CLIP-10", "Mounting clip", 1, "Carton of 50", 1, 50, 12, 10, 8, 14, "N", "Y", ""],
]


def _style_header(ws) -> None:
    for i, cell in enumerate(ws[1]):
        cell.fill = _HEAD_FILL
        cell.font = _HEAD_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = _WIDTHS[i] if i < len(_WIDTHS) else 14
    ws.freeze_panes = "A2"
    yn = DataValidation(type="list", formula1='"Y,N"', allow_blank=True)
    ws.add_data_validation(yn)
    yn.add("K2:L20000")


def _to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Boxes"
    ws.append(HEADERS)
    _style_header(ws)
    info = wb.create_sheet("Instructions")
    for text, bold in INSTRUCTIONS:
        info.append([text])
        if bold:
            info.cell(info.max_row, 1).font = Font(bold=True, size=12)
    info.append(HEADERS)
    for c in info[info.max_row]:
        c.font = Font(bold=True)
    for r in EXAMPLE:
        info.append(r)
    info.column_dimensions["A"].width = 18
    return _to_bytes(wb)


def template_csv() -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerow(HEADERS)
    return buf.getvalue().encode("utf-8-sig")


def export_xlsx(products: list[Product]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Boxes"
    ws.append(HEADERS)
    _style_header(ws)
    for p in sorted(products, key=lambda p: p.sku.lower()):
        if not p.boxes:
            ws.append([p.sku, p.name] + [None] * (len(HEADERS) - 2))
        for b in p.boxes:
            ws.append([
                p.sku, p.name, b.box_no, b.name, b.qty_per_unit, b.units_per_box,
                b.length, b.width, b.height, b.weight,
                "Y" if b.this_side_up else "N", "Y" if b.stackable else "N",
                b.max_load_on_top or None,
            ])
    return _to_bytes(wb)
