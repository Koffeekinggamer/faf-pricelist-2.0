#!/usr/bin/env python3
"""
Fill an OrderTrac QUOTE with full line items (never converts to sale).

Default: quote GUID for Grok FullOrder (27514).
Required item field: Manufacture Vendor = SalesOrderItem._Item._ItemVendors[0][VendorGUID]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path.home() / "Documents" / "ordertrac-session"
STATE = OUT / "storage_state.json"
BASE = "https://app.ordertracinventory.com"

DEFAULT_GUID = "643e259e-6753-41d3-9cf5-beec8d176a56"
VENDOR_FIELD = "SalesOrderItem._Item._ItemVendors[0][VendorGUID]"
DEFAULT_VENDOR = "200 WOODCRAFT"

LINES = [
    {
        "qty": "1",
        "price": "2495.00",
        "category": "DINING ROOM",
        "desc": "Amish Solid Oak Dining Table 42x60 — TEST agent line",
        "sku": "TEST-TABLE-42x60",
        "delivery": "To be delivered",
        "vendor": DEFAULT_VENDOR,
    },
    {
        "qty": "4",
        "price": "389.00",
        "category": "DINING ROOM",
        "desc": "Oak Side Chair — TEST agent line",
        "sku": "TEST-CHAIR-SIDE",
        "delivery": "To be delivered",
        "vendor": DEFAULT_VENDOR,
    },
    {
        "qty": "2",
        "price": "449.00",
        "category": "DINING ROOM",
        "desc": "Oak Arm Chair — TEST agent line",
        "sku": "TEST-CHAIR-ARM",
        "delivery": "To be delivered",
        "vendor": DEFAULT_VENDOR,
    },
    {
        "qty": "1",
        "price": "175.00",
        "category": "DELIVERY",
        "desc": "Local delivery / setup Landrum — TEST agent line",
        "sku": "TEST-DELIVERY",
        "delivery": "To be delivered",
        "vendor": DEFAULT_VENDOR,
    },
]


def ensure_quote_type(page) -> None:
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


def open_custom_item(page) -> bool:
    page.evaluate(
        """() => {
      const box = document.querySelector('.jconfirm-open .jconfirm-box');
      if (box) {
        const c = Array.from(box.querySelectorAll('button'))
          .find(b => /^CANCEL$/i.test((b.innerText||'').trim()));
        if (c) c.click();
      }
    }"""
    )
    page.wait_for_timeout(400)
    page.evaluate(
        """() => {
      const p = document.querySelector(
        '.button.add-sales-order-item-btn.primary, .add-sales-order-item-btn.primary'
      );
      if (p) p.click();
    }"""
    )
    page.wait_for_timeout(1800)
    return page.evaluate(
        """() => !!(document.querySelector('.jconfirm-open')
          && document.body.innerText.includes('Sales Order Item'))"""
    )


def fill_line(page, line: dict) -> dict:
    return page.evaluate(
        """(args) => {
      const line = args.line, vendorField = args.vendorField;
      const root = document.querySelector('.jconfirm-open .jconfirm-box') || document;
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
        fire(el);
        return true;
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
      r.qty = setVal(byName('SalesOrderItem.Qty'), line.qty);
      r.orig = setVal(byName('SalesOrderItem[OriginalPriceEach]'), line.price);
      r.price = setVal(byName('SalesOrderItem[PriceEach]'), line.price);
      r.cat = setSelect(byName('SalesOrderItem[CategoryGUID]'), line.category);
      r.del = setSelect(byName('SalesOrderItem[DeliveryIntent]'),
        line.delivery || 'To be delivered');
      r.desc = setVal(byName('SalesOrderItem._Item.Description'), line.desc);
      r.sku = setVal(byName('SalesOrderItem._Item.SKU'), line.sku);

      const vendorEl = byName(vendorField);
      const want = line.vendor || '200 WOODCRAFT';
      if (vendorEl && vendorEl.tagName === 'SELECT') {
        let opt = Array.from(vendorEl.options).find(
          o => o.text.trim() === want || o.text.includes(want)
        );
        if (!opt) {
          opt = Array.from(vendorEl.options).find(
            o => o.value && o.text.trim() && !/select/i.test(o.text)
          );
        }
        if (opt) {
          vendorEl.value = opt.value;
          fire(vendorEl);
          if (window.jQuery) {
            try { window.jQuery(vendorEl).val(opt.value).trigger('change').trigger('chosen:updated'); }
            catch (e) {}
          }
          r.vendor = opt.text.trim();
        }
      }
      return r;
    }""",
        {"line": line, "vendorField": VENDOR_FIELD},
    )


def save_item_form(page) -> bool:
    page.evaluate(
        """() => {
      const box = document.querySelector('.jconfirm-open .jconfirm-box');
      if (!box) return false;
      const save = Array.from(box.querySelectorAll('button'))
        .find(b => /^SAVE$/i.test((b.innerText || '').trim()));
      if (save) { save.click(); return true; }
      return false;
    }"""
    )
    page.wait_for_timeout(2500)
    return True


def main() -> int:
    import argparse
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--guid", default=DEFAULT_GUID)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not STATE.is_file():
        print("No session — run scripts/ordertrac_login.py first")
        return 1

    guid = args.guid or DEFAULT_GUID
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
            browser.close()
            return 1

        ensure_quote_type(page)
        try:
            page.locator("select[name='UserGUID']").select_option(label="Miller, Judson")
            page.locator("#sales-order-location-guid").select_option(label="Landrum")
        except Exception as e:
            print("header select:", e)

        results = []
        for i, line in enumerate(LINES):
            print(f"\n=== {i+1}/{len(LINES)} {line['sku']} ===")
            body = page.inner_text("body")
            if line["sku"] in body:
                print("  already present — skip")
                results.append({**line, "ok": True, "skipped": True})
                continue
            if not open_custom_item(page):
                open_custom_item(page)
            filled = fill_line(page, line)
            print(f"  filled vendor={filled.get('vendor')}")
            page.screenshot(path=str(OUT / f"order-line-{i+1}.png"), full_page=True)
            save_item_form(page)
            body = page.inner_text("body")
            ok = line["sku"] in body
            print(f"  ok={ok}")
            results.append({**line, "ok": ok})

        ensure_quote_type(page)
        page.evaluate("() => { const b = document.querySelector('#save-btn'); if (b) b.click(); }")
        page.wait_for_timeout(2000)

        body = page.inner_text("body")
        page.screenshot(path=str(OUT / "full-order-final.png"), full_page=True)
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
        info = {
            "sales_order_id": "27514",
            "guid": guid,
            "url": url,
            "type": "QUOTE",
            "type_select": type_val,
            "kept_as_quote": type_val == "Quote",
            "customer": "Grok FullOrder",
            "lines": results,
            "skus_present": {s["sku"]: s["sku"] in body for s in LINES},
            "no_items_yet": "No items yet" in body,
        }
        (OUT / "full-order.json").write_text(json.dumps(info, indent=2))
        context.storage_state(path=str(STATE))
        browser.close()
        print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
