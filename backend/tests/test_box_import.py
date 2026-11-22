import io

from openpyxl import load_workbook

from app.services import box_import

from .conftest import signup_verified

H = ",".join(box_import.HEADERS)


def _csv(*rows: str) -> bytes:
    return ("\n".join([H, *rows]) + "\n").encode()


def _import(s, data: bytes, name="boxes.csv", dry_run=False):
    r = s.post(f"/api/products/import?dry_run={'true' if dry_run else 'false'}", files={"file": (name, data)})
    assert r.status_code == 200, r.text
    return r.json()


def test_template_is_importable_and_has_instructions():
    a = signup_verified("alice@a.com")
    r = a.get("/api/products/import-template.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Boxes", "Instructions"]
    assert [c.value for c in wb["Boxes"][1]] == box_import.HEADERS
    # fill the template's Boxes sheet with the documented example and import it
    ws = wb["Boxes"]
    for row in box_import.EXAMPLE:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    res = _import(a, buf.getvalue(), "filled.xlsx")
    assert (res["products_created"], res["boxes_created"], res["errors"]) == (2, 3, [])
    fix = a.get("/api/products?q=FIX-2400").json()["items"][0]
    detail = a.get(f"/api/products/{fix['id']}").json()
    assert [(b["box_no"], b["name"], b["this_side_up"]) for b in detail["boxes"]] == [(1, "Housing", False), (2, "Lens + driver", True)]
    clip = a.get("/api/products?q=CLIP").json()["items"][0]
    assert a.get(f"/api/products/{clip['id']}").json()["boxes"][0]["units_per_box"] == 50


def test_dry_run_writes_nothing():
    a = signup_verified("alice@a.com")
    res = _import(a, _csv("A,Alpha,1,,1,1,10,10,10,5,N,Y,"), dry_run=True)
    assert res["dry_run"] and res["products_created"] == 1 and res["boxes_created"] == 1
    assert a.get("/api/products").json()["total"] == 0


def test_upsert_never_deletes_and_counts_changes():
    a = signup_verified("alice@a.com")
    _import(a, _csv("A,Alpha,1,,1,1,10,10,10,5,N,Y,", "A,Alpha,2,,1,1,5,5,5,1,N,Y,", "B,Beta,1,,1,1,8,8,8,2,,,"))
    # second file: only A box 1 changes weight, B renamed, A box 2 not mentioned
    res = _import(a, _csv("A,Alpha,1,,1,1,10,10,10,6,N,Y,", "B,Beta Two,,,,,,,,,,,"))
    assert (res["products_created"], res["products_updated"], res["boxes_created"], res["boxes_updated"]) == (0, 1, 0, 1)
    items = {p["sku"]: p for p in a.get("/api/products").json()["items"]}
    assert items["A"]["box_count"] == 2 and items["B"]["name"] == "Beta Two" and items["B"]["box_count"] == 1
    again = _import(a, _csv("A,Alpha,1,,1,1,10,10,10,6,N,Y,"))
    assert again["unchanged_rows"] == 1 and again["boxes_updated"] == 0


def test_row_errors_are_reported_with_row_numbers():
    a = signup_verified("alice@a.com")
    res = _import(a, _csv(
        "A,Alpha,1,,1,1,10,10,10,5,N,Y,",
        ",NoSku,1,,1,1,1,1,1,1,,,",
        "B,Beta,1,,1,1,10,,10,5,,,",
        "C,Gamma,1,,1,1,10,ten,10,5,,,",
        "D,Delta,1,,1,1,10,10,10,5,maybe,,",
        "A,Alpha,1,,1,1,9,9,9,5,N,Y,",
    ))
    errs = {e["row"]: e["message"] for e in res["errors"]}
    assert set(errs) == {3, 4, 5, 6, 7}
    assert errs[3] == "SKU is empty"
    assert "missing Width" in errs[4]
    assert "Width must be a number" in errs[5]
    assert "This Side Up must be Y or N" in errs[6]
    assert "already on row 2" in errs[7]
    assert res["products_created"] == 1  # the good row still imports


def test_box_numbers_default_in_row_order_and_aliases_and_units_in_cells():
    a = signup_verified("alice@a.com")
    data = b"Internal Reference,Name,L,W,H,Weight\nX-1,Thing,12 in,10,8\",4 lb\nX-1,,6,6,6,1\n12345,Numeric sku,1,1,1,1\n"
    res = _import(a, data)
    assert res["errors"] == [] and res["boxes_created"] == 3
    x = a.get("/api/products?q=X-1").json()["items"][0]
    boxes = a.get(f"/api/products/{x['id']}").json()["boxes"]
    assert [(b["box_no"], b["name"], b["length"], b["weight"]) for b in boxes] == [(1, "Box 1", 12, 4), (2, "Box 2", 6, 1)]


def test_numeric_sku_from_excel_is_not_a_float():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(box_import.HEADERS)
    ws.append([12345, "Numeric", 1, None, 1, 1, 10, 10, 10, 5, "N", "Y", None])
    buf = io.BytesIO()
    wb.save(buf)
    a = signup_verified("alice@a.com")
    _import(a, buf.getvalue(), "n.xlsx")
    assert a.get("/api/products").json()["items"][0]["sku"] == "12345"


def test_bad_files_rejected_cleanly():
    a = signup_verified("alice@a.com")
    for name, data, msg in [
        ("x.xls", b"whatever", "save as .xlsx"),
        ("x.pdf", b"%PDF", "Upload an .xlsx or .csv"),
        ("x.xlsx", b"not a zip", "valid Excel"),
        ("x.csv", b"foo,bar\n1,2\n", "header row"),
    ]:
        r = a.post("/api/products/import", files={"file": (name, data)})
        assert r.status_code == 400 and msg in r.json()["detail"], (name, r.text)


def test_export_round_trips():
    a = signup_verified("alice@a.com")
    _import(a, _csv("A,Alpha,1,Body,2,1,10,10,10,5,Y,N,40", "A,Alpha,2,,1,1,5,5,5,1,N,Y,", "B,Beta,,,,,,,,,,,"))
    r = a.get("/api/products/export.xlsx")
    assert r.status_code == 200 and "Acme-box-index.xlsx" in r.headers["content-disposition"]
    b = signup_verified("bob@b.com", "Beta Co")
    res = _import(b, r.content, "export.xlsx")
    assert (res["products_created"], res["boxes_created"], res["errors"]) == (2, 2, [])
    a_items = {p["sku"]: p for p in a.get("/api/products").json()["items"]}
    b_items = {p["sku"]: p for p in b.get("/api/products").json()["items"]}
    for sku in a_items:
        ad = a.get(f"/api/products/{a_items[sku]['id']}").json()
        bd = b.get(f"/api/products/{b_items[sku]['id']}").json()
        strip = lambda d: [{k: v for k, v in x.items() if k != "id"} for x in d["boxes"]]  # noqa: E731
        assert (ad["name"], strip(ad)) == (bd["name"], strip(bd))
