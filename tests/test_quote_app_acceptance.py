"""Twenty acceptance tests for quote cart, tax, email RBAC, and activity."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.activity.log_activity import ActivityStore, export_activity_csv
from backend.auth.bootstrap import bootstrap_users, is_dev_seed
from backend.auth.permissions import AuthDenied, can
from backend.auth.store import AuthStore
from backend.pricing import retail_from_wholesale
from backend.quote.calc_quote_totals import calc_quote_totals
from backend.quote.cart import QuoteCart, priced_catalog_row
from backend.quote.store import QuoteStore


def _app_db(tmp_path: Path) -> Path:
    return tmp_path / "pricebook_app.db"


def _chair() -> dict[str, object]:
    return priced_catalog_row(
        sku="CH-1",
        name="Side Chair",
        wholesale=100,
        multiplier=2.7,
        options={"wood": "Oak", "finish": "finished", "size": "std"},
    )


def _table() -> dict[str, object]:
    return priced_catalog_row(
        sku="TB-1",
        name="Dining Table",
        wholesale=100,
        multiplier=2.7,
        options={"wood": "Maple", "finish": "finished", "size": "42x72"},
    )


def test_01_add_two_different_items_from_row_and_search() -> None:
    cart = QuoteCart()
    cart.add_from_row(_chair())  # catalog row
    cart.add_from_row(_table())  # another search result
    assert [ln.sku for ln in cart.lines] == ["CH-1", "TB-1"]
    assert all(ln.unit_price == 270.0 for ln in cart.lines)


def test_02_change_qty_reset_remove() -> None:
    cart = QuoteCart()
    chair = cart.add_from_row(_chair())
    table = cart.add_from_row(_table())
    cart.set_qty(chair.id, 3)
    cart.set_line_options(chair.id, {"wood": "Cherry", "finish": "finished", "size": "std"})
    cart.reset_line_options(chair.id)
    assert cart.line(chair.id).options_snapshot["wood"] == "Oak"
    cart.remove_line(table.id)
    assert [ln.sku for ln in cart.lines] == ["CH-1"]
    assert cart.line(chair.id).qty == 3


def test_03_spartanburg_client_total_uses_7_percent() -> None:
    cart = QuoteCart()
    cart.add_from_row(_chair())
    cart.select_county("Spartanburg", "SC")
    totals = calc_quote_totals(cart.lines, cart.tax_rate)
    assert cart.tax_rate == 0.07
    assert totals.subtotal == 270.0
    assert totals.tax_amount == 18.90
    assert totals.total == 288.90


def test_04_mecklenburg_client_total_uses_8_25_percent() -> None:
    cart = QuoteCart()
    cart.add_from_row(_chair())
    cart.select_county("Mecklenburg", "NC")
    totals = calc_quote_totals(cart.lines, cart.tax_rate)
    assert cart.tax_rate == 0.0825
    assert totals.tax_amount == 22.28
    assert totals.total == 292.28


def test_05_tax_exempt_sets_tax_to_zero() -> None:
    cart = QuoteCart()
    cart.add_from_row(_chair())
    cart.select_county("Spartanburg", "SC")
    cart.set_exempt(True)
    totals = calc_quote_totals(cart.lines, cart.tax_rate)
    assert cart.tax_rate == 0.0
    assert cart.tax_label == "Exempt"
    assert totals.tax_amount == 0.0
    assert totals.total == 270.0


def test_06_clear_quote_resets_lines_and_tax() -> None:
    cart = QuoteCart()
    cart.add_from_row(_chair())
    cart.select_county("Spartanburg", "SC")
    cart.clear_quote()
    assert cart.lines == []
    assert cart.tax_rate == 0.0
    assert cart.county is None
    assert cart.tax_label == "Select delivery county"


def test_07_empty_db_boots_admin_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    path = _app_db(tmp_path)
    created = bootstrap_users(path)
    assert created is not None
    store = AuthStore(path)
    user = store.authenticate("OWNER@faf.example", "admin-pass-1")
    assert user is not None
    assert user.role == "admin"
    assert user.email == "owner@faf.example"


def test_08_admin_creates_jane_as_sales(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    store = AuthStore(path)
    admin = store.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = store.create_user(
        actor=admin,
        email="jane@example.com",
        role="sales",
        password="jane-pass-1",
        name="Jane",
    )
    assert jane.role == "sales"
    assert jane.email == "jane@example.com"


def test_admin_create_user_accepts_a_short_temp_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    store = AuthStore(path)
    admin = store.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    michael = store.create_user(
        actor=admin,
        email="michael@example.com",
        role="manager",
        password="Admin",
        name="Michael",
    )
    assert michael.email == "michael@example.com"
    signed_in = store.authenticate("michael@example.com", "Admin")
    assert signed_in is not None
    assert signed_in.role == "manager"


def test_09_jane_logs_in_any_case_builds_quote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1", name="Jane"
    )
    jane = auth.authenticate("Jane@Example.com", "jane-pass-1")
    assert jane is not None
    quotes = QuoteStore(path, activity=ActivityStore(path))
    qid = quotes.create_quote(jane, name="Jane quote")
    quotes.add_line(jane, qid, _chair())
    owned = quotes.list_quotes(jane)
    assert len(owned) == 1
    assert owned[0].owner_id == jane.id
    auth.logout(jane)


def test_10_second_sales_cannot_see_janes_quote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1"
    )
    bob = auth.create_user(
        actor=admin, email="bob@example.com", role="sales", password="bob-pass-11"
    )
    activity = ActivityStore(path)
    quotes = QuoteStore(path, activity=activity)
    qid = quotes.create_quote(jane, name="Jane quote")
    assert quotes.list_quotes(bob) == []
    with pytest.raises(AuthDenied) as exc:
        quotes.get_quote(bob, qid)
    assert exc.value.status_code == 404
    denied = [e for e in activity.list_events() if e.action == "quote.view.denied"]
    assert denied


def test_11_manager_can_see_janes_quote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1"
    )
    mgr = auth.create_user(
        actor=admin, email="manager@example.com", role="manager", password="mgr-pass-11"
    )
    quotes = QuoteStore(path, activity=ActivityStore(path))
    qid = quotes.create_quote(jane, name="Jane quote")
    listed = quotes.list_quotes(mgr)
    assert [q.id for q in listed] == [qid]
    assert listed[0].owner_name == "jane"
    got = quotes.get_quote(mgr, qid)
    assert got.id == qid


def test_12_viewer_cannot_add_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    viewer = auth.create_user(
        actor=admin, email="view@example.com", role="viewer", password="view-pass-1"
    )
    assert not can(viewer, "quote.create")
    quotes = QuoteStore(path, activity=ActivityStore(path))
    with pytest.raises(AuthDenied):
        quotes.create_quote(viewer, name="Nope")


def test_13_disabled_jane_cannot_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1"
    )
    auth.set_active(admin, jane.id, False)
    with pytest.raises(AuthDenied) as exc:
        auth.authenticate("jane@example.com", "jane-pass-1")
    assert "disabled" in str(exc.value).lower()


def test_14_last_admin_cannot_be_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    with pytest.raises(AuthDenied):
        auth.set_active(admin, admin.id, False)
    with pytest.raises(AuthDenied):
        auth.set_role(admin, admin.id, "sales")


def test_15_three_failures_do_not_lock_jane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    activity = ActivityStore(path)
    auth.activity = activity
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    auth.create_user(actor=admin, email="jane@example.com", role="sales", password="jane-pass-1")
    for _ in range(3):
        with pytest.raises(AuthDenied):
            auth.authenticate("jane@example.com", "wrong-password")
    fails = [e for e in activity.list_events() if e.action == "auth.login.failure"]
    assert len(fails) == 3
    jane = auth.authenticate("jane@example.com", "jane-pass-1")
    assert jane is not None


def test_16_jane_quote_events_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    activity = ActivityStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1"
    )
    quotes = QuoteStore(path, activity=activity)
    qid = quotes.create_quote(jane, name="Jane quote")
    quotes.add_line(jane, qid, _chair())
    quotes.add_line(jane, qid, _table())
    quotes.select_tax(jane, qid, county="Spartanburg", state="SC")
    lines = quotes.get_quote(jane, qid).lines
    quotes.remove_line(jane, qid, lines[0].id)
    actions = [
        e.action
        for e in reversed(activity.list_events(resource_id=str(qid), limit=50))
        if e.action.startswith("quote.")
    ]
    assert actions == [
        "quote.create",
        "quote.line.add",
        "quote.line.add",
        "quote.tax.select",
        "quote.line.remove",
    ]


def test_17_jane_denied_other_quote_no_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    activity = ActivityStore(path)
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1"
    )
    quotes = QuoteStore(path, activity=activity)
    qid = quotes.create_quote(admin, name="Admin quote")
    with pytest.raises(AuthDenied):
        quotes.get_quote(jane, qid)
    denied = [e for e in activity.list_events() if e.action == "quote.view.denied"]
    assert denied


def test_18_view_activity_prefilters_jane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    auth = AuthStore(path)
    activity = ActivityStore(path)
    auth.activity = activity
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    jane = auth.create_user(
        actor=admin, email="jane@example.com", role="sales", password="jane-pass-1"
    )
    auth.authenticate("jane@example.com", "jane-pass-1")
    trail = activity.list_events(actor_id=jane.id)
    assert trail
    assert all(e.actor_email == "jane@example.com" for e in trail)


def test_19_problems_only_filters_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    activity = ActivityStore(path)
    auth = AuthStore(path)
    auth.activity = activity
    admin = auth.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    auth.create_user(actor=admin, email="jane@example.com", role="sales", password="jane-pass-1")
    with pytest.raises(AuthDenied):
        auth.authenticate("jane@example.com", "nope")
    activity.log_activity(
        None,
        action="system.error",
        status="error",
        summary="boom",
        resource_type="system",
    )
    problems = activity.list_events(problems_only=True)
    assert problems
    assert all(e.status in {"failure", "denied", "error"} for e in problems)
    assert not any(e.status == "success" for e in problems)


def test_20_csv_export_of_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    path = _app_db(tmp_path)
    bootstrap_users(path)
    activity = ActivityStore(path)
    activity.log_activity(None, action="system.client_error", status="error", summary="calc failed")
    rows = activity.list_events(problems_only=True)
    csv_text = export_activity_csv(rows)
    assert "system.client_error" in csv_text
    assert csv_text.count("\n") >= 2


def test_dev_seed_flag_helper() -> None:
    assert is_dev_seed({"NODE_ENV": "development"}) is True
    assert is_dev_seed({"FAF_DEV_SEED": "1"}) is True
    assert is_dev_seed({"FLY_APP_NAME": "faf-pricebook"}) is False


def test_retail_math_not_reinvented() -> None:
    assert retail_from_wholesale(100, 2.7) == 270.0
    assert retail_from_wholesale(715, 2.7) == 1932.0
