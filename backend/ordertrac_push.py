"""
Push FAF quote / line items into OrderTrac as a QUOTE (never a sale).

Requires live Playwright session (scripts/ordertrac_login.py).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = Path.home() / "Documents" / "ordertrac-session"
STORAGE = SESSION_DIR / "storage_state.json"
VENDOR_MAP_PATH = ROOT / "config" / "ordertrac_vendor_map.json"
VENDOR_FIELD = "SalesOrderItem._Item._ItemVendors[0][VendorGUID]"


def load_vendor_map() -> dict[str, str]:
    if VENDOR_MAP_PATH.is_file():
        data = json.loads(VENDOR_MAP_PATH.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}


def map_vendor(faf_vendor: str) -> str:
    m = load_vendor_map()
    if faf_vendor in m:
        return m[faf_vendor]
    # case-insensitive
    for k, v in m.items():
        if k.lower() == (faf_vendor or "").lower():
            return v
    return (faf_vendor or "200 WOODCRAFT").upper()


def map_category(collection: str = "", description: str = "") -> str:
    text = f"{collection} {description}".lower()
    if any(w in text for w in ("deliver", "freight", "ship")):
        return "DELIVERY"
    if any(w in text for w in ("chair", "table", "dining", "bench", "stool", "buffet", "hutch")):
        return "DINING ROOM"
    if any(w in text for w in ("bed", "dresser", "night", "chest", "wardrobe")):
        return "BEDROOM"
    if any(w in text for w in ("sofa", "living", "coffee", "end table", "ottoman")):
        return "LIVING ROOM"
    if any(w in text for w in ("cabinet", "kitchen")):
        return "CABINETS"
    if any(w in text for w in ("office", "desk")):
        return "OFFICE"
    if any(w in text for w in ("outdoor", "poly")):
        return "OUTDOOR"
    return "OTHER"


def line_from_pricebook_row(
    row: dict,
    *,
    qty: float = 1.0,
    wood: str = "",
    stain: str = "",
    finish: str = "",
) -> dict:
    """Build one OrderTrac custom-line payload from a FAF pricebook row."""
    vendor_faf = row.get("vendor") or ""
    part = row.get("part_number") or ""
    desc = row.get("description") or part
    species = wood or (row.get("species") or "")
    if species and " / " in species:
        # Prefer explicit wood token if provided
        species_short = wood or species.split("/")[0].strip()
    else:
        species_short = species
    finish_state = finish or (row.get("finish_state") or "finished")
    retail = float(row.get("adjusted_price") or 0)
    base = row.get("base_price")
    mult = row.get("multiplier") or 2.7
    faf_id = row.get("id")
    bits = [f"{part} — {desc}" if part and desc and part != desc else (desc or part)]
    if species_short:
        bits.append(f"Wood: {species_short}")
    if stain:
        bits.append(f"Stain: {stain}")
    bits.append(f"Finish: {finish_state}")
    if faf_id:
        bits.append(f"FAF #{faf_id}")
    if base is not None:
        bits.append(f"WH ${float(base):.2f} x{mult}")
    full_desc = " | ".join(bits)
    return {
        "faf_id": faf_id,
        "qty": str(int(qty) if float(qty) == int(qty) else qty),
        "price": f"{retail:.2f}",
        "category": map_category(row.get("collection") or "", desc),
        "sku": (part or f"FAF-{faf_id}")[:40],
        "vendor_faf": vendor_faf,
        "vendor_ot": map_vendor(vendor_faf),
        "desc": full_desc,
        "delivery": "To be delivered",
        "wood": species_short,
        "stain": stain,
        "finish": finish_state,
    }


def build_payload_from_faf_quote(
    quote: dict,
    lines_df,
    *,
    ot_user_display: str = "Miller, Judson",
    location: str = "Landrum",
    project: str = "",
) -> dict:
    """Build OrderTrac push payload from FAF quote + lines (FAF is price source)."""
    lines = []
    for _, r in lines_df.iterrows():
        row = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        qty = row.get("qty") or 1
        try:
            qty_s = str(int(qty)) if float(qty) == int(float(qty)) else str(qty)
        except Exception:
            qty_s = "1"
        price = f"{float(row.get('unit_retail') or 0):.2f}"
        notes = str(row.get("notes") or "")
        wood = str(row.get("species") or "").strip()
        finish = str(row.get("finish_state") or "finished").strip()
        part = str(row.get("part_number") or "").strip()
        desc0 = str(row.get("description") or part or "Item").strip()
        faf_id = row.get("pricebook_id")
        vendor = row.get("vendor") or ""

        bits = [f"{part} — {desc0}" if part and part not in desc0 else desc0]
        if wood:
            bits.append(f"Wood: {wood}")
        if notes and "Stain:" in notes:
            # keep stain fragment from FAF line notes
            for part_n in notes.split("·"):
                if "Stain:" in part_n:
                    bits.append(part_n.strip())
                    break
        elif notes:
            bits.append(notes[:80])
        if finish:
            bits.append(f"Finish: {finish}")
        if faf_id:
            bits.append(f"FAF #{faf_id}")
        if row.get("unit_base") is not None:
            bits.append(f"WH ${float(row['unit_base']):.2f}")

        lines.append(
            {
                "faf_id": faf_id,
                "qty": qty_s,
                "price": price,
                "category": map_category(
                    row.get("collection") or "", desc0
                ),
                "sku": (part or (f"FAF-{faf_id}" if faf_id else "CUSTOM"))[:40],
                "vendor_faf": vendor,
                "vendor_ot": map_vendor(vendor or "200 WOODCRAFT"),
                "desc": " | ".join(bits),
                "delivery": "To be delivered",
            }
        )

    qn = quote.get("quote_number") or quote.get("id")
    return {
        "type": "QUOTE",
        "customer_name": quote.get("customer_name") or "FAF Quote Customer",
        "customer_phone": quote.get("customer_phone") or "",
        "customer_email": quote.get("customer_email") or "",
        "project": project or str(qn),
        "notes": (
            f"Created from FAF Price Book quote {qn}. "
            f"{quote.get('notes') or ''} "
            "DO NOT convert to sale unless authorized."
        ).strip(),
        "user_display": ot_user_display,
        "location": location,
        "lines": lines,
        "faf_quote_id": quote.get("id"),
        "faf_quote_number": quote.get("quote_number"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def push_quote_to_ordertrac(
    payload: dict,
    *,
    headless: bool = True,
    sales_order_guid: Optional[str] = None,
    skip_existing_lines: bool = False,
) -> dict[str, Any]:
    """
    Create (or open) an OrderTrac QUOTE and add custom lines from FAF payload.

    New quotes: Sales Orders → New Quote (UI). Never use newSalesOrderType=QUOTE URL.
    If sales_order_guid is set, opens that quote and adds lines (optionally skipping
    ones already on the page when skip_existing_lines=True).
    """
    from backend.ordertrac_connect import load_ordertrac_creds

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if not STORAGE.is_file():
        return {
            "ok": False,
            "error": "No OrderTrac session — run scripts/ordertrac_login.py",
        }

    from playwright.sync_api import sync_playwright

    creds = load_ordertrac_creds()
    base = creds["base_url"]
    lines = payload.get("lines") or []
    if not lines:
        return {"ok": False, "error": "No lines in payload"}

    results: list[dict] = []
    so_id = None
    guid = sales_order_guid
    url = None
    type_val = None
    error = None
    skipped = 0
    added = 0

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(STORAGE))
        page = context.new_page()
        try:
            page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            if "Login" in page.title() or "/Account/Login" in page.url:
                error = "Session expired — run scripts/ordertrac_login.py"
            elif sales_order_guid:
                # Append to existing OrderTrac quote
                page.goto(
                    f"{base}/SalesOrders/SalesOrder?salesOrderGUID={sales_order_guid}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(2500)
                url = page.url
                guid = sales_order_guid
                if "Login" in page.title() or "Error" in page.title():
                    error = f"Could not open OrderTrac quote {sales_order_guid}"
            else:
                # Create new OrderTrac quote via UI
                page.goto(
                    base + "/SalesOrders",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(2000)
                clicked = False
                for sel in (
                    "text=New Quote",
                    "a:has-text('New Quote')",
                    "button:has-text('New Quote')",
                ):
                    try:
                        page.locator(sel).first.click(timeout=5000)
                        clicked = True
                        break
                    except Exception:
                        continue
                if not clicked:
                    error = "Could not click New Quote on Sales Orders list"
                else:
                    try:
                        page.wait_for_url(
                            re.compile(r"salesOrderGUID=", re.I), timeout=30000
                        )
                    except Exception:
                        page.wait_for_timeout(3000)
                    url = page.url
                    m = re.search(r"salesOrderGUID=([a-f0-9-]+)", url, re.I)
                    if m:
                        guid = m.group(1)
                    if not guid:
                        error = f"No salesOrderGUID after New Quote (url={url})"

            if not error and guid:
                _ensure_quote(page)
                try:
                    page.locator("select[name='UserGUID']").select_option(
                        label=payload.get("user_display") or "Miller, Judson"
                    )
                except Exception:
                    pass
                try:
                    page.locator("#sales-order-location-guid").select_option(
                        label=payload.get("location") or "Landrum"
                    )
                except Exception:
                    pass
                try:
                    page.locator("input[name='Project']").fill(
                        (payload.get("project") or "FAF Quote")[:80]
                    )
                except Exception:
                    pass
                try:
                    page.locator("textarea[name='Notes']").fill(
                        (payload.get("notes") or "")[:2000]
                    )
                except Exception:
                    pass

                # New customer only when creating (not append)
                cust = (payload.get("customer_name") or "").strip()
                if cust and not sales_order_guid:
                    try:
                        page.get_by_text("Select", exact=True).first.click(timeout=4000)
                        page.wait_for_timeout(600)
                        page.get_by_text("New Customer", exact=True).click(timeout=4000)
                        page.wait_for_timeout(1000)
                        parts = cust.split(None, 1)
                        first = parts[0] if parts else "FAF"
                        last = parts[1] if len(parts) > 1 else "Customer"
                        page.locator("input[name='Customer.FirstName']").last.fill(
                            first, force=True
                        )
                        page.locator("input[name='Customer.LastName']").last.fill(
                            last, force=True
                        )
                        if payload.get("customer_email"):
                            page.locator("input[name='Customer.Email']").last.fill(
                                str(payload["customer_email"]), force=True
                            )
                        if payload.get("customer_phone"):
                            page.locator("input[name='Customer.Phone1']").last.fill(
                                str(payload["customer_phone"]), force=True
                            )
                        page.locator("#add-customer-btn").click()
                        page.wait_for_timeout(2500)
                    except Exception:
                        pass

                page.evaluate(
                    "() => { const b=document.querySelector('#save-btn'); if(b) b.click(); }"
                )
                page.wait_for_timeout(2000)
                _dismiss_ok(page)

                body = page.inner_text("body")
                m2 = re.search(r"SALES ORDER ID\s*\n?\s*(\d+)", body)
                if m2:
                    so_id = m2.group(1)

                # Add lines from FAF quote cart
                for line in lines:
                    body = page.inner_text("body")
                    already = False
                    if skip_existing_lines:
                        markers = []
                        if line.get("faf_id"):
                            markers.append(f"FAF #{line['faf_id']}")
                        sku = (line.get("sku") or "").strip()
                        if sku:
                            markers.append(sku)
                        already = any(m and m in body for m in markers)
                    if already:
                        skipped += 1
                        results.append(
                            {
                                "sku": line.get("sku"),
                                "faf_id": line.get("faf_id"),
                                "ok": True,
                                "skipped": True,
                                "vendor": None,
                            }
                        )
                        continue

                    _close_dialogs(page)
                    ok_open = _open_custom_item(page)
                    if not ok_open:
                        ok_open = _open_custom_item(page)
                    filled = _fill_line(page, line) if ok_open else {"err": "no form"}
                    if ok_open:
                        _save_item(page)
                        added += 1
                    page.wait_for_timeout(800)
                    body = page.inner_text("body")
                    present = (
                        (line.get("sku") or "")[:16] in body
                        or (line.get("desc") or "")[:24] in body
                        or (
                            line.get("faf_id")
                            and f"FAF #{line['faf_id']}" in body
                        )
                    )
                    results.append(
                        {
                            "sku": line.get("sku"),
                            "faf_id": line.get("faf_id"),
                            "ok": present or already,
                            "form_opened": ok_open,
                            "skipped": False,
                            "vendor": filled.get("vendor"),
                        }
                    )

                _ensure_quote(page)
                page.evaluate(
                    "() => { const b=document.querySelector('#save-btn'); if(b) b.click(); }"
                )
                page.wait_for_timeout(1500)
                _dismiss_ok(page)
                body = page.inner_text("body")
                if not so_id:
                    m2 = re.search(r"SALES ORDER ID\s*\n?\s*(\d+)", body)
                    if m2:
                        so_id = m2.group(1)
                type_val = page.evaluate(
                    """() => {
                  for (const s of document.querySelectorAll('select')) {
                    const opts = Array.from(s.options).map(o => o.text.trim());
                    if (opts.includes('Sale') && opts.includes('Quote'))
                      return s.options[s.selectedIndex]?.text;
                  }
                  return null;
                }"""
                )
                page.screenshot(
                    path=str(SESSION_DIR / "faf-push-final.png"), full_page=True
                )
                context.storage_state(path=str(STORAGE))
                url = page.url
                m = re.search(r"salesOrderGUID=([a-f0-9-]+)", url, re.I)
                if m:
                    guid = m.group(1)
        except Exception as e:
            error = str(e)
            try:
                page.screenshot(
                    path=str(SESSION_DIR / "faf-push-error.png"), full_page=True
                )
            except Exception:
                pass
        finally:
            browser.close()

    # Success if no hard error and every line was added, skipped, or present
    line_ok = bool(results) and all(r.get("ok") for r in results)
    # Append with all skipped is still ok
    if skip_existing_lines and results and not error:
        line_ok = all(r.get("ok") or r.get("skipped") for r in results)

    info = {
        "ok": (not error) and line_ok,
        "error": error,
        "sales_order_id": so_id,
        "guid": guid,
        "url": url
        or (
            f"{base}/SalesOrders/SalesOrder?salesOrderGUID={guid}" if guid else None
        ),
        "type_select": type_val,
        "kept_as_quote": type_val == "Quote",
        "lines": results,
        "lines_added": added,
        "lines_skipped": skipped,
        "payload_project": payload.get("project"),
        "faf_quote_id": payload.get("faf_quote_id"),
        "mode": "append" if sales_order_guid else "create",
    }
    (SESSION_DIR / "last-push.json").write_text(json.dumps(info, indent=2))
    return info


def _dismiss_ok(page) -> None:
    page.evaluate(
        """() => {
      const box = document.querySelector('.jconfirm-open .jconfirm-box');
      if (!box) return;
      if ((box.innerText||'').includes('Orig Price')) return;
      const ok = Array.from(box.querySelectorAll('button'))
        .find(b => /^(OK|Yes|Close)$/i.test((b.innerText||'').trim()));
      if (ok) ok.click();
    }"""
    )
    page.wait_for_timeout(300)


def _ensure_quote(page) -> None:
    page.evaluate(
        """() => {
      for (const s of document.querySelectorAll('select')) {
        const opts = Array.from(s.options).map(o => o.text.trim());
        if (opts.includes('Sale') && opts.includes('Quote')) {
          const q = Array.from(s.options).find(o => o.text.trim() === 'Quote');
          if (q) {
            s.value = q.value;
            s.dispatchEvent(new Event('change', {bubbles: true}));
          }
        }
      }
    }"""
    )


def _close_dialogs(page) -> None:
    for _ in range(3):
        closed = page.evaluate(
            """() => {
          const box = document.querySelector('.jconfirm-open .jconfirm-box');
          if (!box) return false;
          const c = Array.from(box.querySelectorAll('button'))
            .find(b => /cancel/i.test((b.innerText||'').trim()));
          if (c) { c.click(); return true; }
          return false;
        }"""
        )
        if not closed:
            break
        page.wait_for_timeout(300)


def _open_custom_item(page) -> bool:
    _close_dialogs(page)
    page.evaluate(
        """() => {
      const p = document.querySelector('.button.add-sales-order-item-btn.primary');
      if (p) p.click();
    }"""
    )
    page.wait_for_timeout(1800)
    return page.evaluate(
        """() => {
      const box = document.querySelector('.jconfirm-open .jconfirm-box');
      return !!(box && (box.innerText||'').includes('Orig Price'));
    }"""
    )


def _fill_line(page, line: dict) -> dict:
    return page.evaluate(
        """(args) => {
      const line = args.line, vendorField = args.vendorField;
      const root = document.querySelector('.jconfirm-open .jconfirm-box');
      if (!root) return {err: 'no form'};
      const fire = (el) => {
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('blur', {bubbles: true}));
      };
      const setVal = (el, val) => {
        if (!el) return false;
        el.focus();
        const proto = el.tagName === 'TEXTAREA'
          ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const d = Object.getOwnPropertyDescriptor(proto, 'value');
        if (d && d.set) d.set.call(el, val); else el.value = val;
        fire(el); return true;
      };
      const setSelect = (el, text) => {
        if (!el || el.tagName !== 'SELECT') return false;
        const opt = Array.from(el.options).find(
          o => o.text.trim() === text || o.text.includes(text)
        );
        if (!opt) return false;
        el.value = opt.value; fire(el); return true;
      };
      // Prefer the select with the most options (Chosen hides the real select)
      const byName = (name) => {
        const all = Array.from(root.querySelectorAll(`[name="${name}"]`));
        if (!all.length) return null;
        all.sort((a, b) => {
          const ao = a.tagName === 'SELECT' ? a.options.length : 0;
          const bo = b.tagName === 'SELECT' ? b.options.length : 0;
          return bo - ao;
        });
        return all[0];
      };
      const pickVendor = (el, want) => {
        if (!el || el.tagName !== 'SELECT') return null;
        const opts = Array.from(el.options);
        const w = (want || '').trim().toUpperCase();
        let opt = null;
        if (w) {
          opt = opts.find(o => o.text.trim().toUpperCase() === w);
          if (!opt) opt = opts.find(o => o.text.toUpperCase().includes(w));
          if (!opt) {
            const token = w.split(/\\s+/)[0];
            if (token.length >= 3)
              opt = opts.find(o => o.text.toUpperCase().includes(token));
          }
        }
        if (!opt) opt = opts.find(o => o.value && o.text.trim() && !/select/i.test(o.text));
        if (!opt) return null;
        el.value = opt.value;
        fire(el);
        if (window.jQuery) {
          try {
            window.jQuery(el).val(opt.value).trigger('change').trigger('chosen:updated');
          } catch (e) {}
        }
        return opt.text.trim();
      };
      const r = {};
      r.qty = setVal(byName('SalesOrderItem.Qty'), String(line.qty));
      r.orig = setVal(byName('SalesOrderItem[OriginalPriceEach]'), String(line.price));
      r.price = setVal(byName('SalesOrderItem[PriceEach]'), String(line.price));
      r.cat = setSelect(byName('SalesOrderItem[CategoryGUID]'), line.category || 'OTHER');
      r.del = setSelect(byName('SalesOrderItem[DeliveryIntent]'),
        line.delivery || 'To be delivered');
      r.desc = setVal(byName('SalesOrderItem._Item.Description'), line.desc || '');
      r.sku = setVal(byName('SalesOrderItem._Item.SKU'), line.sku || '');
      r.vendor = pickVendor(
        byName(vendorField),
        line.vendor_ot || line.vendor_faf || ''
      );
      return r;
    }""",
        {"line": line, "vendorField": VENDOR_FIELD},
    )


def _save_item(page) -> None:
    page.evaluate(
        """() => {
      const box = document.querySelector('.jconfirm-open .jconfirm-box');
      if (!box) return;
      const save = Array.from(box.querySelectorAll('button'))
        .find(b => /^SAVE$/i.test((b.innerText||'').trim()));
      if (save) save.click();
    }"""
    )
    page.wait_for_timeout(2800)
