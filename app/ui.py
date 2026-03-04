from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from .config import get_settings
from .db import init_db
from .services import AuthService, LogService, MarketService, PortfolioService, ShareService


TAB_ITEMS = [
    ("portfolio", "资产"),
    ("add", "新增"),
    ("shares", "共享"),
    ("logs", "日志"),
]


@dataclass
class AppContext:
    auth: AuthService
    portfolio: PortfolioService
    shares: ShareService
    logs: LogService
    market: MarketService


# ------------------------------
# Query / state helpers
# ------------------------------

def init_session_state() -> None:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "current_tab" not in st.session_state:
        st.session_state.current_tab = "portfolio"


def get_query_value(key: str) -> str | None:
    value = None
    try:
        value = st.query_params.get(key)
    except Exception:
        pass

    if value is None:
        try:
            qp = st.experimental_get_query_params()
            value = qp.get(key)
        except Exception:
            value = None

    if isinstance(value, list):
        return value[0] if value else None
    return value


def set_query_value(key: str, value: str) -> None:
    try:
        st.query_params[key] = value
        return
    except Exception:
        pass

    try:
        qp = st.experimental_get_query_params()
        qp[key] = [value]
        st.experimental_set_query_params(**qp)
    except Exception:
        pass


def clear_query_value(key: str) -> None:
    try:
        if key in st.query_params:
            del st.query_params[key]
            return
    except Exception:
        pass

    try:
        qp = st.experimental_get_query_params()
        qp.pop(key, None)
        st.experimental_set_query_params(**qp)
    except Exception:
        pass


# ------------------------------
# Theme + navigation
# ------------------------------

def render_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --app-bg: #f3f7fb;
            --app-card: #ffffff;
            --app-border: #d5e4f0;
            --app-text: #122b46;
            --app-sub: #5a718a;
            --app-accent: #0f766e;
            --nav-bg: rgba(255,255,255,0.92);
        }

        [data-testid="stAppViewContainer"] {
            background:
              radial-gradient(900px 360px at 6% -12%, #d9ecff 0%, transparent 60%),
              radial-gradient(850px 330px at 100% 0%, #d6f6ef 0%, transparent 58%),
              var(--app-bg);
            color: var(--app-text);
        }

        header[data-testid="stHeader"],
        [data-testid="stAppHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            max-height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        .block-container {
            max-width: 1180px;
            padding-top: 0.12rem !important;
            padding-bottom: calc(6.6rem + env(safe-area-inset-bottom));
        }

        h1, h2, h3 {
            color: var(--app-text);
            letter-spacing: -0.01em;
        }

        [data-testid="stSidebar"] > div:first-child {
            background: linear-gradient(180deg, rgba(232,242,252,0.93) 0%, rgba(244,248,252,0.9) 100%);
            backdrop-filter: blur(10px);
            border-right: 1px solid #d6e4f0;
        }

        [data-testid="stExpander"],
        [data-testid="stMetric"] {
            border: 1px solid var(--app-border);
            border-radius: 16px;
            background: var(--app-card);
            box-shadow: 0 8px 22px rgba(17, 45, 73, 0.06);
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] > div {
            border-radius: 12px;
            border-color: #cddcea;
            background: #fbfdff;
        }

        .stButton > button {
            border-radius: 12px;
            min-height: 44px;
            transition: transform .12s ease;
        }

        .stButton > button:active {
            transform: scale(.986);
        }

        .stButton > button[data-testid="baseButton-primary"] {
            border: none;
            color: #fff;
            background: linear-gradient(120deg, #0f766e 0%, #14b8a6 100%);
            box-shadow: 0 10px 20px rgba(15,118,110,.24);
        }

        @media (max-width: 768px) {
            .block-container {
                padding-left: .72rem !important;
                padding-right: .72rem !important;
                padding-bottom: calc(7.2rem + env(safe-area-inset-bottom));
            }
            .stButton > button {
                width: 100%;
                min-height: 46px;
            }
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --app-bg: #0b1220;
                --app-card: #111b2e;
                --app-border: #24344e;
                --app-text: #e6eef8;
                --app-sub: #9eb2c8;
                --app-accent: #2dd4bf;
                --nav-bg: rgba(17,27,46,0.9);
            }
        }

        html[data-theme="dark"] [data-testid="stAppViewContainer"],
        body[data-theme="dark"] [data-testid="stAppViewContainer"],
        [data-theme="dark"] [data-testid="stAppViewContainer"] {
            background:
              radial-gradient(900px 360px at 0% -10%, #142540 0%, transparent 62%),
              radial-gradient(820px 320px at 100% 0%, #103436 0%, transparent 58%),
              #0b1220 !important;
            color: #e6eef8 !important;
        }

        html[data-theme="dark"] h1,
        html[data-theme="dark"] h2,
        html[data-theme="dark"] h3,
        html[data-theme="dark"] p,
        html[data-theme="dark"] label,
        html[data-theme="dark"] span,
        body[data-theme="dark"] h1,
        body[data-theme="dark"] h2,
        body[data-theme="dark"] h3,
        body[data-theme="dark"] p,
        body[data-theme="dark"] label,
        body[data-theme="dark"] span,
        [data-theme="dark"] h1,
        [data-theme="dark"] h2,
        [data-theme="dark"] h3,
        [data-theme="dark"] p,
        [data-theme="dark"] label,
        [data-theme="dark"] span {
            color: #e6eef8 !important;
        }

        html[data-theme="dark"] [data-testid="stExpander"],
        html[data-theme="dark"] [data-testid="stMetric"],
        body[data-theme="dark"] [data-testid="stExpander"],
        body[data-theme="dark"] [data-testid="stMetric"],
        [data-theme="dark"] [data-testid="stExpander"],
        [data-theme="dark"] [data-testid="stMetric"] {
            background: #111b2e !important;
            border-color: #24344e !important;
            box-shadow: none !important;
        }

        html[data-theme="dark"] div[data-baseweb="input"] > div,
        html[data-theme="dark"] div[data-baseweb="select"] > div,
        body[data-theme="dark"] div[data-baseweb="input"] > div,
        body[data-theme="dark"] div[data-baseweb="select"] > div,
        [data-theme="dark"] div[data-baseweb="input"] > div,
        [data-theme="dark"] div[data-baseweb="select"] > div {
            background: #0f1727 !important;
            border-color: #334866 !important;
            color: #e6eef8 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_current_tab(tab: str) -> None:
    keys = {k for k, _ in TAB_ITEMS}
    safe_tab = tab if tab in keys else "portfolio"
    st.session_state.current_tab = safe_tab
    set_query_value("tab", safe_tab)


def render_bottom_nav(active_tab: str) -> None:
    label_map = {k: v for k, v in TAB_ITEMS}
    key_map = {v: k for k, v in TAB_ITEMS}
    active_label = label_map.get(active_tab, TAB_ITEMS[0][1])

    st.markdown("### ")
    if hasattr(st, "segmented_control"):
        selected = st.segmented_control(
            "底部导航",
            options=[label for _, label in TAB_ITEMS],
            default=active_label,
            selection_mode="single",
            label_visibility="collapsed",
            key="bottom_nav_control",
        )
    else:
        selected = st.radio(
            "底部导航",
            options=[label for _, label in TAB_ITEMS],
            index=[label for _, label in TAB_ITEMS].index(active_label),
            horizontal=True,
            label_visibility="collapsed",
            key="bottom_nav_control",
        )

    target_tab = key_map.get(selected or active_label, active_tab)
    if target_tab != active_tab:
        set_current_tab(target_tab)
        st.rerun()


# ------------------------------
# App pages
# ------------------------------

def currency_symbol(currency: str) -> str:
    return {"CNY": "¥", "USD": "$"}.get(currency, "")


def render_login_page(ctx: AppContext) -> None:
    st.subheader("🔐 登录")
    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("登录", type="primary"):
                if ctx.auth.login(username, password):
                    token = ctx.auth.make_token(username)
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    set_query_value("auth", token)
                    st.success(f"欢迎回来，{username}")
                    st.rerun()
                st.error("用户名或密码错误")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("新用户名")
            new_password = st.text_input("新密码", type="password")
            if st.form_submit_button("注册", type="primary"):
                ok, msg = ctx.auth.register(new_username.strip(), new_password)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


def render_share_page(ctx: AppContext, current_user: str) -> None:
    st.subheader("🔗 共享管理")

    invited = ctx.shares.invited(current_user)
    if invited:
        st.caption("我邀请的用户")
        for item in invited:
            u = item["shared_with"]
            perm = item["permission"]
            c1, c2 = st.columns([4, 1])
            c1.write(f"• {u}（{'可编辑' if perm == 'edit' else '只读'}）")
            if c2.button("撤销", key=f"revoke_{u}"):
                ctx.shares.revoke(current_user, u)
                st.rerun()

    with st.expander("邀请新用户", expanded=True):
        invite_user = st.text_input("对方用户名")
        invite_permission = st.selectbox("权限", ["read", "edit"], format_func=lambda x: "只读" if x == "read" else "可编辑")
        if st.button("发送邀请", key="invite_send", type="primary"):
            ok, msg = ctx.shares.invite(current_user, invite_user.strip(), invite_permission)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    mapping = ctx.shares.permission_map(current_user)
    if mapping:
        st.caption("共享给我的人")
        st.write("，".join([f"{k}（{'可编辑' if v == 'edit' else '只读'}）" for k, v in mapping.items()]))


def render_add_page(ctx: AppContext, current_user: str) -> None:
    st.subheader("➕ 添加投资")

    investor_options = ctx.portfolio.list_investor_options(current_user, owner_only=True)

    c1, c2 = st.columns(2)
    with c1:
        investor = st.selectbox("投资人", investor_options)
        if investor == "新增投资人":
            investor = st.text_input("新投资人", value=current_user).strip() or current_user
        symbol_query = st.text_input("标的代码（支持模糊查询）").strip().upper()

        selected_name = ""
        selected_market = ""
        selected_code = symbol_query
        if symbol_query:
            candidates = ctx.portfolio.search_symbol_options(symbol_query, limit=20)
            if candidates:
                labels = ["保持手动输入"] + [
                    f"{x['symbol_code']} | {x['symbol_name']} | {x['market']}" for x in candidates
                ]
                pick = st.selectbox("匹配结果", labels)
                if pick != "保持手动输入":
                    idx = labels.index(pick) - 1
                    selected = candidates[idx]
                    selected_code = selected["symbol_code"]
                    selected_name = selected["symbol_name"]
                    selected_market = selected["market"]
                    st.caption(f"已选：{selected_name}（{selected_market}）")

    with c2:
        channel = st.text_input("渠道")
        inferred_market = selected_market or ctx.market.identify_market(selected_code)
        is_fund = inferred_market == "A股" and selected_code.isdigit() and len(selected_code) == 6
        cost_price = st.number_input(
            "成本价",
            min_value=0.0,
            step=0.0001 if is_fund else 0.01,
            format="%.4f" if is_fund else "%.2f",
        )
        quantity = st.number_input("数量", min_value=0.0)

    if st.button("提交", type="primary"):
        result = ctx.portfolio.add_investment(
            current_user,
            investor,
            selected_code,
            channel,
            cost_price,
            quantity,
        )
        if result.ok:
            st.success("添加成功")
            st.rerun()
        else:
            st.error(result.message)

    st.divider()
    st.subheader("🧑‍💼 投资人管理")
    names = [x for x in ctx.portfolio.list_investor_options(current_user, owner_only=True) if x != "新增投资人"]
    if names:
        delete_target = st.selectbox("删除投资人", names)
        replacement = st.selectbox("转移到", [current_user] + [x for x in names if x != delete_target and x != current_user])
        if st.button("删除并转移", type="primary"):
            affected = ctx.portfolio.delete_investor_and_reassign(current_user, delete_target, replacement)
            if affected:
                st.success(f"已转移 {affected} 条记录")
                st.rerun()
            else:
                st.warning("没有需要转移的记录")


def render_portfolio_page(ctx: AppContext, current_user: str) -> None:
    st.subheader("📊 资产面板")

    valuation_mode = st.selectbox("计价方式", ["原币种", "人民币 (CNY)", "美元 (USD)"])
    rows = ctx.portfolio.accessible_view_rows(current_user)
    if not rows:
        st.info("暂无数据")
        return

    summary = ctx.portfolio.valuation_summary(rows, valuation_mode)
    for group in summary["groups"]:
        ccy = group["currency"]
        symbol = currency_symbol(ccy)
        st.markdown(f"**{ccy} 汇总**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总成本", f"{symbol}{group['total_cost']:,.2f}")
        c2.metric("当前市值", f"{symbol}{group['total_mv']:,.2f}")
        c3.metric("总收益", f"{symbol}{group['total_profit']:,.2f}")
        c4.metric("总收益率", f"{group['total_yield']}%")

    st.subheader("📋 投资明细")
    investor_options = ctx.portfolio.list_investor_options(current_user, owner_only=True)
    for row in rows:
        can_edit = ctx.shares.can_edit(row.owner_username, current_user)
        owner_tip = "可编辑" if can_edit else "只读"
        with st.expander(f"{row.investor} - {row.symbol_name} ({row.symbol_code})"):
            st.caption(f"归属：{row.owner_username} · {owner_tip}")
            col1, col2, col3, col4, col5 = st.columns([1.3, 1, 1, 0.8, 0.8])
            selected_investor = col1.selectbox(
                "投资人",
                investor_options,
                index=investor_options.index(row.investor) if row.investor in investor_options else 0,
                key=f"investor_{row.id}",
            )
            if selected_investor == "新增投资人":
                selected_investor = col1.text_input("新投资人", value=row.investor, key=f"investor_new_{row.id}")

            is_fund = row.market == "A股" and row.symbol_code.isdigit() and len(row.symbol_code) == 6
            new_cost = col2.number_input(
                "成本",
                value=float(row.cost_price),
                step=0.0001 if is_fund else 0.01,
                format="%.4f" if is_fund else "%.2f",
                key=f"cost_{row.id}",
            )
            new_qty = col3.number_input("数量", value=float(row.quantity), key=f"qty_{row.id}")

            if can_edit:
                if col4.button("保存", key=f"save_{row.id}"):
                    ok = ctx.portfolio.update_investment(
                        current_user,
                        row.id,
                        str(selected_investor).strip() or current_user,
                        new_cost,
                        new_qty,
                    )
                    if ok:
                        st.rerun()
                if col5.button("删除", key=f"del_{row.id}"):
                    ok = ctx.portfolio.delete_investment(current_user, row.id)
                    if ok:
                        st.rerun()
            else:
                col5.info("只读")

            symbol = currency_symbol(row.currency)
            st.write(f"当前价：{row.current_price:.4f} {row.currency}")
            st.write(f"当前市值：{symbol}{row.current_market_value:,.2f}")
            st.write(f"收益率：{row.yield_pct}%")


def render_logs_page(ctx: AppContext) -> None:
    st.subheader("🧭 操作日志")
    limit = st.selectbox("显示条数", [50, 100, 200, 500], index=2)
    logs = ctx.logs.list_friendly(limit)
    if not logs:
        st.caption("暂无日志")
        return
    st.dataframe(pd.DataFrame(logs), width="stretch", hide_index=True)


def render_sidebar(ctx: AppContext, current_user: str) -> None:
    with st.sidebar:
        st.success(f"👤 当前用户：**{current_user}**")
        if st.button("🚪 登出"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            clear_query_value("auth")
            st.rerun()


def get_current_tab() -> str:
    keys = {k for k, _ in TAB_ITEMS}
    tab = get_query_value("tab")
    if tab in keys:
        st.session_state.current_tab = tab
        return tab
    session_tab = st.session_state.get("current_tab")
    if session_tab in keys:
        return session_tab
    return "portfolio"


def maybe_restore_login(ctx: AppContext) -> None:
    if st.session_state.logged_in:
        return
    token = get_query_value("auth")
    username = ctx.auth.parse_token(token)
    if username:
        st.session_state.logged_in = True
        st.session_state.username = username


def run_app() -> None:
    settings = get_settings()
    st.set_page_config(page_title=settings.app_name, layout="wide", page_icon="🌍")
    render_theme()
    st.title("🌍 全球资产管理系统 Pro")

    init_session_state()
    init_db()

    auth = AuthService()
    auth.ensure_admin_user()
    market = MarketService()
    ctx = AppContext(
        auth=auth,
        portfolio=PortfolioService(market),
        shares=ShareService(),
        logs=LogService(),
        market=market,
    )

    maybe_restore_login(ctx)

    if not st.session_state.logged_in:
        render_login_page(ctx)
        return

    current_user = st.session_state.username
    render_sidebar(ctx, current_user)

    tab = get_current_tab()
    if tab == "portfolio":
        render_portfolio_page(ctx, current_user)
    elif tab == "add":
        render_add_page(ctx, current_user)
    elif tab == "shares":
        render_share_page(ctx, current_user)
    elif tab == "logs":
        render_logs_page(ctx)
    else:
        render_portfolio_page(ctx, current_user)

    set_current_tab(tab)
    render_bottom_nav(tab)
