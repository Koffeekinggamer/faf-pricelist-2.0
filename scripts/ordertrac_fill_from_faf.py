#!/usr/bin/env python3
"""
Build an OrderTrac QUOTE from FAF master_pricebook.db line items.

Uses session from scripts/ordertrac_login.py.
Default: quote 27514 (Grok FullOrder) + Barkman Red Oak dining set.
Never converts to sale.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

OUT = Path.home() / "Documents" / "ordertrac-session"
STATE = OUT / "storage_state.json"
BASE = "https://app.ordertracinventory.com"
DEFAULT_GUID = "643e259e-6753-41d3-9cf5-beec8d176a56"
DB = Path(__file__).resolve().parents[1] / "master_pricebook.db"
VENDOR_FIELD = "SalesOrderItem._Item._ItemVendors[0][VendorGUID]"

# FAF row ids → qty (Barkman Red Oak dining)
FAF_PICK = [
    (479060, 1, "DINING ROOM"),  # 60" Extension Table
    (479078, 2, "DINING ROOM"),  # Additional 18" Leaf
    (482875, 4, "DINING ROOM"),  # Salem Side Chair
    (482881, 2, "DINING ROOM"),  # Salem Arm Chair
]


def load_faf_lines() -> list[dict]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    lines = []
    for row_id, qty, category in FAF_PICK:
        r = con.execute("SELECT * FROM pricebook WHERE id=?", (row_id,)).fetchone()
        if not r:
            raise SystemExit(f"FAF id {row_id} missing in {DB}")
        r = dict(r)
        species = (r.get("species") or "Red Oak")
        if "Red Oak" in species:
            sp = "Red Oak"
        else:
            sp = species.split("/")[0].strip()
        price = float(r["adjusted_price"])
        lines.append(
            {
                "faf_id": r["id"],
                "qty": str(qty),
                "price": f"{price:.2f}",
                "base_price": r["base_price"],
                "multiplier": r["multiplier"],
                "category": category,
                "sku": (r["part_number"] or r["description"] or f"FAF-{r['id']}")[:40],
                "vendor_faf": r["vendor"],
                "vendor_ot": "BARKMAN FURNITURE",
                "desc": (
                    f"{r['part_number']} — {r['description']} | {sp} | "
                    f"{r['finish_state']} | FAF #{r['id']} | "
                    f"WH ${float(r['base_price']):.2f} x{r['multiplier']}"
                ),
                "delivery": "To be delivered",
            }
        )
    lines.append(
        {
            "faf_id": None,
            "qty": "1",
            "price": "175.00",
            "category": "DELIVERY",
            "sku": "DELIVERY-LOCAL",
            "vendor_ot": "BARKMAN FURNITURE",
            "desc": "Local delivery / setup — Landrum area (shop fee, not from FAF catalog)",
            "delivery": "To be delivered",
        }
    )
    con.close()
    return lines


def ensure_quote(page) -> None:
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


def close_dialogs(page) -> None:
    for _ in range(3):
        closed = page.evaluate(
            """() => {
          const box = document.querySelector('.jconfirm-open .jconfirm-box');
          if (!box) return false;
          const cancel = Array.from(box.querySelectorAll('button'))
            .find(b => /cancel/i.test((b.innerText||'').trim()));
          if (cancel) { cancel.click(); return true; }
          return false;
        }"""
        )
        if not closed:
            break
        page.wait_for_timeout(400)


def open_form(page) -> bool:
    close_dialogs(page)
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


def fill_line(page, line: dict) -> dict:
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
      const byName = (name) => {
        const all = Array.from(root.querySelectorAll(`[name="${name}"]`));
        const vis = all.filter(el => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        });
        return vis[0] || all[0] || null;
      };
      const r = {};
      r.qty = setVal(byName('SalesOrderItem.Qty'), String(line.qty));
      r.orig = setVal(byName('SalesOrderItem[OriginalPriceEach]'), String(line.price));
      r.price = setVal(byName('SalesOrderItem[PriceEach]'), String(line.price));
      r.cat = setSelect(byName('SalesOrderItem[CategoryGUID]'), line.category);
      r.del = setSelect(byName('SalesOrderItem[DeliveryIntent]'),
        line.delivery || 'To be delivered');
      r.desc = setVal(byName('SalesOrderItem._Item.Description'), line.desc);
      r.sku = setVal(byName('SalesOrderItem._Item.SKU'), line.sku);
      const vendorEl = byName(vendorField);
      if (vendorEl && vendorEl.tagName === 'SELECT') {
        let opt = Array.from(vendorEl.options).find(o => /barkman/i.test(o.text));
        if (!opt) {
          opt = Array.from(vendorEl.options).find(o => o.value && o.text.trim());
        }
        if (opt) {
          vendorEl.value = opt.value;
          fire(vendorEl);
          if (window.jQuery) {
            try {
              window.jQuery(vendorEl).val(opt.value)
                .trigger('change').trigger('chosen:updated');
            } catch (e) {}
          }
          r.vendor = opt.text.trim();
        }
      }
      return r;
    }""",
        {"line": line, "vendorField": VENDOR_FIELD},
    )


def save_item(page) -> bool:
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
    return True


def main() -> int:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--guid", default=DEFAULT_GUID)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not STATE.is_file():
        print("No session — run scripts/ordertrac_login.py first")
        return 1
    if not DB.is_file():
        print("Missing", DB)
        return 1

    lines = load_faf_lines()
    (OUT / "faf-quote-lines.json").write_text(
        json.dumps(
            {
                "source": str(DB),
                "theme": "Barkman Red Oak dining set",
                "lines": lines,
                "subtotal": sum(float(l["price"]) * int(l["qty"]) for l in lines),
            },
            indent=2,
        )
    )

    guid = args.guid
    url = f"{BASE}/SalesOrders/SalesOrder?salesOrderGUID={guid}"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE))
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        if "Login" in page.title():
            print("SESSION DEAD")
            return 1

        ensure_quote(page)
        try:
            page.locator("select[name='UserGUID']").select_option(label="Miller, Judson")
            page.locator("#sales-order-location-guid").select_option(label="Landrum")
        except Exception as e:
            print("header:", e)
        page.locator("input[name='Project']").fill("FAF Barkman Dining Set — Red Oak")
        page.locator("textarea[name='Notes']").fill(
            "QUOTE from FAF master_pricebook.db (mult 2.7). "
            "Barkman Red Oak dining set. Grok agent. DO NOT convert to sale."
        )
        page.evaluate("() => { const b=document.querySelector('#save-btn'); if(b) b.click(); }")
        page.wait_for_timeout(1500)

        results = []
        for i, line in enumerate(lines):
            print(f"=== {i+1}/{len(lines)} {line['sku']} ${line['price']} x{line['qty']}")
            if not open_form(page):
                open_form(page)
            filled = fill_line(page, line)
            print("  ", filled)
            save_item(page)
            body = page.inner_text("body")
            ok = line["sku"][:18] in body or (
                line.get("faf_id") and f"FAF #{line['faf_id']}" in body
            )
            results.append({**line, "ok": ok, "vendor_set": filled.get("vendor")})
            print("  ok=", ok)

        ensure_quote(page)
        page.evaluate("() => { const b=document.querySelector('#save-btn'); if(b) b.click(); }")
        page.wait_for_timeout(2000)
        body = page.inner_text("body")
        page.screenshot(path=str(OUT / "faf-quote-final.png"), full_page=True)
        info = {
            "guid": guid,
            "url": url,
            "type": "QUOTE",
            "lines": results,
            "kept_as_quote": "Convert to sale" in body or "QUOTE" in body,
        }
        (OUT / "full-order.json").write_text(json.dumps(info, indent=2))
        context.storage_state(path=str(STATE))
        browser.close()
        print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
