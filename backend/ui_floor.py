"""Streamlit sections for email login, quote cart, users, and activity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping

import streamlit as st

from backend.activity.log_activity import (
    ACTION_GROUPS,
    ActivityStore,
    date_preset_bounds,
    export_activity_csv,
    human_action_label,
)
from backend.auth.bootstrap import DEV_ADMIN_EMAIL
from backend.auth.passwords import MIN_PASSWORD_LENGTH, is_valid_email
from backend.auth.permissions import AuthDenied, can
from backend.auth.roles import ROLES, SessionUser
from backend.auth.session import user_from_session
from backend.auth.store import RESET_MESSAGE, AuthStore
from backend.config import resolve_app_db_path
from backend.county_sales_tax import format_county_selection, grouped_counties, search_counties
from backend.quote.calc_quote_totals import calc_quote_totals
from backend.quote.cart import QuoteCart
from backend.quote.store import QuoteStore


def app_stores() -> tuple[AuthStore, QuoteStore, ActivityStore]:
    path = resolve_app_db_path()
    activity = ActivityStore(path)
    return AuthStore(path, activity), QuoteStore(path, activity), activity


def current_user() -> SessionUser | None:
    return user_from_session(st.session_state.get("auth_session"))


def cart_from_state() -> QuoteCart:
    return QuoteCart.from_payload(st.session_state.get("quote_cart"))


def save_cart(cart: QuoteCart) -> None:
    st.session_state["quote_cart"] = cart.to_payload()


def import_anon_cart_once(user: SessionUser) -> None:
    if st.session_state.get("_anon_quote_imported"):
        return
    anon = st.session_state.pop("_anon_quote_draft", None)
    st.session_state["_anon_quote_imported"] = True
    if not anon:
        return
    existing = st.session_state.get("quote_cart")
    if existing and QuoteCart.from_payload(existing).lines:
        return
    st.session_state["quote_cart"] = anon
    _ = user


def render_login() -> bool:
    invite = str(st.query_params.get("invite") or "")
    if invite:
        return render_accept_invite(invite)

    auth, _quotes, _act = app_stores()
    st.markdown(
        """
        <div style="max-width:420px;margin:4rem auto 1rem auto;text-align:center;">
          <div style="font-size:2rem;font-weight:700;color:#244a2e;">FAF Price Book</div>
          <div style="color:#1f2937;margin-top:0.25rem;">Foothills Amish Furniture · sign in to continue</div>
          <div style="color:#4b5563;margin-top:0.5rem;font-size:0.9rem;">
            Email + password
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", autocomplete="username")
            pw = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submitted:
                if not is_valid_email(email):
                    st.error("Enter a valid email address.")
                    return False
                try:
                    user = auth.authenticate(email, pw)
                except AuthDenied as exc:
                    st.error(str(exc))
                    return False
                session = {
                    "user_id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "username": user.email,
                    "display_name": user.name,
                    "role": user.role,
                    "active": user.active,
                    "must_change_password": user.must_change_password,
                }
                st.session_state["_pending_login"] = session
                return True
        with st.expander("Forgot password"):
            reset_email = st.text_input("Email", key="reset_email")
            if st.button("Send reset link", key="btn_reset_request"):
                auth.request_password_reset(reset_email)
                st.info(RESET_MESSAGE)
        st.caption(
            f"Local first admin is often `{DEV_ADMIN_EMAIL}` when secrets still say Foothills."
        )
    return False


def render_accept_invite(token: str) -> bool:
    auth, _, _ = app_stores()
    st.subheader("Accept invite")
    with st.form("accept_invite"):
        email = st.text_input("Email", disabled=True, value="", key="invite_email_locked")
        st.caption("Email is locked to the invite. Set your password and name.")
        name = st.text_input("Name")
        pw = st.text_input("Password", type="password")
        pw2 = st.text_input("Confirm password", type="password")
        if st.form_submit_button("Create account", type="primary"):
            if pw != pw2:
                st.error("Passwords do not match.")
                return False
            try:
                user = auth.accept_invite(token, pw, name=name)
            except AuthDenied as exc:
                st.error(str(exc))
                return False
            st.session_state["_pending_login"] = {
                "user_id": user.id,
                "email": user.email,
                "name": user.name,
                "username": user.email,
                "display_name": user.name,
                "role": user.role,
                "active": True,
                "must_change_password": False,
            }
            _ = email
            return True
    return False


def render_account(user: SessionUser) -> None:
    auth, _, _ = app_stores()
    st.subheader("Account")
    st.write(f"**{user.name}** · `{user.email}` · {user.role}")
    with st.form("change_password"):
        current = st.text_input("Current password", type="password")
        new_pw = st.text_input("New password", type="password")
        new_pw2 = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Change password", type="primary"):
            if new_pw != new_pw2:
                st.error("Passwords do not match.")
            elif len(new_pw) < MIN_PASSWORD_LENGTH:
                st.error(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            else:
                try:
                    auth.change_own_password(user, current, new_pw)
                    st.success("Password updated.")
                except AuthDenied as exc:
                    st.error(str(exc))


def render_quotes_list(user: SessionUser) -> None:
    _, quotes, activity = app_stores()
    st.subheader("Quotes")
    if not can(user, "quote.view.own") and not can(user, "quote.view.team"):
        st.info("Catalog only — your role cannot open quotes.")
        return
    rows = quotes.list_quotes(user)
    if not rows:
        st.info("No saved quotes yet. Add items from Search.")
        return
    show_owner = can(user, "quote.view.team")
    for q in rows:
        label = f"{q.name} · {len(q.lines)} lines"
        if show_owner:
            label += f" · {q.owner_name}"
        cols = st.columns([4, 1, 1])
        cols[0].write(label)
        if cols[1].button("Open", key=f"open_q_{q.id}"):
            loaded = quotes.get_quote(user, q.id)
            cart = QuoteCart()
            cart.quote_id = loaded.id
            cart.name = loaded.name
            cart.client_name = loaded.client_name
            cart.lines = list(loaded.lines)
            cart.exempt = loaded.tax_exempt
            if loaded.tax_county and loaded.tax_state:
                cart.select_county(loaded.tax_county, loaded.tax_state)
            save_cart(cart)
            st.session_state["quote_cart_open"] = True
            st.session_state["faf_nav"] = "Search"
            st.rerun()
        if (can(user, "quote.delete.any") or q.owner_id == user.id) and cols[2].button(
            "Delete", key=f"del_q_{q.id}"
        ):
            try:
                quotes.delete_quote(user, q.id)
                st.rerun()
            except AuthDenied as exc:
                st.error(str(exc))
        if can(user, "quote.view.team"):
            hist = activity.list_events(resource_id=str(q.id), limit=12)
            if hist:
                with st.expander(f"History · quote {q.id}"):
                    for ev in hist:
                        st.caption(f"{ev.created_at} · {ev.action} · {ev.summary}")


def render_quote_cart(user: SessionUser | None) -> None:
    cart = cart_from_state()
    can_edit = can(user, "quote.create") if user else False
    badge = cart.badge_count
    st.markdown(f"##### Quote ({badge})")
    if not cart.name:
        cart.name = f"Quote {datetime.now().strftime('%Y-%m-%d')}"
    cart.name = st.text_input("Quote name", value=cart.name, key="quote_name_in")
    cart.client_name = st.text_input("Client name", value=cart.client_name, key="quote_client_in")
    st.caption(f"{badge} line{'s' if badge != 1 else ''}")
    if not cart.lines:
        st.info("Search catalog to add items")
        save_cart(cart)
        return
    if not can_edit:
        st.info("Viewer — catalog only. Ask an admin for quote access.")
    for line in cart.lines:
        with st.container(border=True):
            st.write(f"**{line.name}** · {line.sku}")
            snap = ", ".join(f"{k}: {v}" for k, v in line.options_snapshot.items() if v)
            if snap:
                st.caption(snap)
            st.caption(f"${line.unit_price:,.2f} each")
            if can_edit:
                c1, c2, c3, c4 = st.columns(4)
                new_qty = c1.number_input(
                    "Qty", min_value=1, value=int(line.qty), step=1, key=f"qty_{line.id}"
                )
                if int(new_qty) != line.qty:
                    cart.set_qty(line.id, int(new_qty))
                    _log_cart(user, "quote.line.qty", f"qty {new_qty}")
                if c2.button("Reset options", key=f"rst_{line.id}"):
                    cart.reset_line_options(line.id)
                    _log_cart(user, "quote.line.reset", "reset options")
                if c3.button("Clear item", key=f"rm_{line.id}"):
                    cart.remove_line(line.id)
                    _log_cart(user, "quote.line.remove", "removed line")
                    save_cart(cart)
                    st.rerun()
                line.notes = c4.text_input("Notes", value=line.notes, key=f"note_{line.id}")
            else:
                st.write(f"Qty {line.qty}")
    if can(user, "tax.select") if user else False:
        _render_tax_picker(cart, user)
    totals = calc_quote_totals(cart.lines, cart.tax_rate)
    st.markdown(f"**Subtotal** ${totals.subtotal:,.2f}")
    st.markdown(f"Tax {cart.tax_label} — **${totals.tax_amount:,.2f}**")
    st.markdown(f"### Client total ${totals.total:,.2f}")
    if can_edit:
        b1, b2 = st.columns(2)
        if b1.button("Save quote", type="primary", key="save_quote_btn"):
            try:
                _, store, _ = app_stores()
                assert user is not None
                qid = store.save_from_cart(user, cart)
                cart.quote_id = qid
                st.success(f"Saved quote #{qid}")
            except AuthDenied as exc:
                st.error(str(exc))
                _report_client_error(user, str(exc), path="quote.save")
        if b2.button("Clear quote", key="clear_quote_btn"):
            st.session_state["confirm_clear_quote"] = True
        if st.session_state.get("confirm_clear_quote"):
            st.warning("Clear all lines and tax?")
            if st.button("Yes, clear quote", key="confirm_clear_yes"):
                cart.clear_quote()
                _log_cart(user, "quote.clear", "cleared quote")
                st.session_state.pop("confirm_clear_quote", None)
                save_cart(cart)
                st.rerun()
    save_cart(cart)


def _render_tax_picker(cart: QuoteCart, user: SessionUser | None) -> None:
    exempt = st.checkbox("Tax exempt", value=cart.exempt, key="tax_exempt_box")
    if exempt != cart.exempt:
        cart.set_exempt(exempt)
        _log_cart(user, "quote.tax.exempt" if exempt else "quote.tax.select", cart.tax_label)
    query = st.text_input("Delivery county", key="tax_county_q", placeholder="spart, meck, fulton…")
    matches = search_counties(query) if query.strip() else []
    if not query.strip():
        groups = grouped_counties()
        matches = (
            groups["Georgia"][:8] + groups["North Carolina"][:8] + groups["South Carolina"][:8]
        )
    labels = ["Select delivery county"] + [format_county_selection(r) for r in matches[:80]]
    current = cart.tax_label if cart.county and not cart.exempt else "Select delivery county"
    index = labels.index(current) if current in labels else 0
    pick = st.selectbox("County", labels, index=index, key="tax_county_pick")
    if pick != "Select delivery county" and not exempt:
        chosen = next((r for r in matches if format_county_selection(r) == pick), None)
        if chosen and (cart.county is None or cart.county != chosen):
            cart.select_county(chosen.county, chosen.state)
            _log_cart(
                user,
                "quote.tax.select",
                f"{chosen.county} {chosen.state} {chosen.rate}",
            )


def add_search_row_to_cart(
    user: SessionUser | None,
    row: Mapping[str, object],
    *,
    qty: int = 1,
    add_as_separate_line: bool = False,
) -> None:
    if user is None or not can(user, "quote.create"):
        raise AuthDenied("Not allowed.", action="quote.create")
    cart = cart_from_state()
    cart.add_from_row(row, qty=max(1, int(qty)), add_as_separate_line=add_as_separate_line)
    save_cart(cart)
    st.session_state["quote_cart_open"] = True
    _log_cart(user, "quote.line.add", str(row.get("description") or row.get("part_number") or ""))


def _log_cart(user: SessionUser | None, action: str, summary: str) -> None:
    try:
        _, _, activity = app_stores()
        activity.log_activity(
            user,
            action=action,
            resource_type="quote",
            resource_id=str(cart_from_state().quote_id or ""),
            summary=summary,
        )
    except Exception:
        pass


def _report_client_error(user: SessionUser | None, message: str, *, path: str) -> None:
    try:
        _, _, activity = app_stores()
        activity.report_client_error(user, message=message, path=path)
    except Exception:
        pass


def render_admin_users(user: SessionUser) -> None:
    if not can(user, "users.manage"):
        st.error("Admin only.")
        st.stop()
    auth, _, _ = app_stores()
    st.subheader("Users")
    rows = auth.list_user_rows()
    if not rows:
        st.info("No users.")
        return
    for row in rows:
        c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1.4, 1.4])
        c1.write(str(row.get("name") or ""))
        c2.write(str(row.get("email") or ""))
        c3.write(str(row.get("role") or ""))
        c4.write("active" if row.get("active") else "disabled")
        c5.caption(str(row.get("last_login_at") or "—"))
        a1, a2, a3 = st.columns(3)
        uid = int(row["id"])
        if a1.button("View activity", key=f"act_{uid}"):
            st.session_state["faf_nav"] = "Activity"
            st.session_state["activity_user_id"] = uid
            st.rerun()
        new_role = a2.selectbox(
            "Role",
            list(ROLES),
            index=list(ROLES).index(str(row.get("role") or "sales")),
            key=f"role_{uid}",
        )
        if new_role != row.get("role"):
            try:
                auth.set_role(user, uid, new_role)  # type: ignore[arg-type]
                st.rerun()
            except AuthDenied as exc:
                st.error(str(exc))
        label = "Disable" if row.get("active") else "Enable"
        if a3.button(label, key=f"en_{uid}"):
            try:
                auth.set_active(user, uid, not bool(row.get("active")))
                st.rerun()
            except AuthDenied as exc:
                st.error(str(exc))
    st.markdown("##### Invite / create")
    with st.form("create_user"):
        email = st.text_input("Email")
        name = st.text_input("Name (optional)")
        role = st.selectbox("Role", list(ROLES), index=2)
        temp = st.text_input("Temporary password (optional)", type="password")
        if st.form_submit_button("Create / invite", type="primary"):
            try:
                if temp:
                    created = auth.create_user(
                        actor=user,
                        email=email,
                        role=role,
                        password=temp,
                        name=name,  # type: ignore[arg-type]
                    )
                    st.success(f"Created {created.email}")
                else:
                    invite = auth.create_invite(
                        actor=user,
                        email=email,
                        role=role,
                        name=name,  # type: ignore[arg-type]
                    )
                    st.success(
                        f"Invite for {invite.email} · last4 {invite.token_last4} · "
                        f"open `?invite=` with the full token (shown once below)."
                    )
                    st.code(invite.invite_token or "", language=None)
            except AuthDenied as exc:
                st.error(str(exc))
            except ValueError as exc:
                st.error(str(exc))
    st.markdown("##### Admin password reset")
    emails = [str(r.get("email") or "") for r in rows]
    if emails:
        target = st.selectbox("User", emails, key="admin_reset_email")
        new_pw = st.text_input("New password", type="password", key="admin_reset_pw")
        if st.button("Reset password"):
            match = next(r for r in rows if r.get("email") == target)
            try:
                auth.admin_reset_password(user, int(match["id"]), new_pw)
                st.success("Password reset. They must change it on next login.")
            except AuthDenied as exc:
                st.error(str(exc))
            except ValueError as exc:
                st.error(str(exc))


def render_admin_activity(user: SessionUser) -> None:
    if not can(user, "activity.view"):
        st.error("Admin only.")
        st.stop()
    _, _, activity = app_stores()
    auth, _, _ = app_stores()
    st.subheader("Activity")
    users = auth.list_users()
    user_labels = ["All"] + ["Unknown / anonymous"] + [f"{u.name} · {u.email}" for u in users]
    preset_user_id = st.session_state.pop("activity_user_id", None)
    default_ix = 0
    if preset_user_id is not None:
        for i, u in enumerate(users):
            if u.id == preset_user_id:
                default_ix = i + 2
                break
    pick = st.selectbox("User", user_labels, index=default_ix, key="act_user")
    email_contains = st.text_input("Email contains", key="act_email")
    group = st.selectbox("Action group", ["All", *ACTION_GROUPS.keys()], key="act_group")
    status = st.selectbox(
        "Status", ["All", "success", "failure", "denied", "error"], key="act_status"
    )
    resource_id = st.text_input("Resource id", key="act_rid")
    preset = st.selectbox("Date range", ["All", "Today", "7", "30"], key="act_preset")
    problems = st.checkbox("Problems only", key="act_problems")
    actor_id = None
    unknown_only = False
    if pick == "Unknown / anonymous":
        unknown_only = True
    elif pick != "All":
        ix = user_labels.index(pick) - 2
        if 0 <= ix < len(users):
            actor_id = users[ix].id
    since = until = None
    if preset == "Today":
        since, until = date_preset_bounds("today")
    elif preset in {"7", "30"}:
        since, until = date_preset_bounds(preset)
    events = activity.list_events(
        actor_id=actor_id,
        actor_email_contains=email_contains,
        unknown_only=unknown_only,
        action_group="" if group == "All" else group,
        status="" if status == "All" else status,
        resource_id=resource_id,
        problems_only=problems,
        since=since,
        until=until,
        limit=50,
    )
    if st.button("Refresh"):
        st.rerun()
    if not events:
        st.info("No events for this filter.")
        return
    colors = {"success": "green", "failure": "orange", "denied": "red", "error": "red"}
    for ev in events:
        when = ev.created_at
        try:
            when = datetime.fromisoformat(ev.created_at).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
        st.markdown(
            f"**{when}** · {ev.actor_email or 'anonymous'} · "
            f"{human_action_label(ev.action)} · :{colors.get(ev.status, 'gray')}[{ev.status}] · {ev.summary}"
        )
        if ev.resource_id:
            st.caption(f"Resource {ev.resource_type or ''} `{ev.resource_id}`")
        with st.expander(f"Details {ev.id}"):
            st.json(ev.metadata)
            st.caption(f"ip {ev.ip or '—'} · {ev.user_agent or ''} · {ev.path or ''}")
            if ev.error_message:
                st.error(ev.error_message)
    export_rows = activity.list_events(
        actor_id=actor_id,
        actor_email_contains=email_contains,
        unknown_only=unknown_only,
        action_group="" if group == "All" else group,
        status="" if status == "All" else status,
        resource_id=resource_id,
        problems_only=problems,
        since=since,
        until=until,
        limit=5000,
    )
    start = (since or datetime.now(timezone.utc) - timedelta(days=30)).date()
    end = (until or datetime.now(timezone.utc)).date()
    st.download_button(
        "Export CSV",
        data=export_activity_csv(export_rows),
        file_name=f"activity-{start}-{end}.csv",
        mime="text/csv",
    )
