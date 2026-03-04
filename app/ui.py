from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
import time
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .config import get_settings
from .db import DatabaseConnectionError, get_database_display_name, init_db
from .services import AuthService, LogService, MarketService, PortfolioService, ShareService

try:
    from webauthn import (
        generate_authentication_options,
        generate_registration_options,
        options_to_json,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    WEBAUTHN_AVAILABLE = True
    WEBAUTHN_IMPORT_ERROR = ""
except Exception as exc:
    WEBAUTHN_AVAILABLE = False
    WEBAUTHN_IMPORT_ERROR = str(exc)


TAB_ITEMS = [
    ("portfolio", "资产"),
    ("add", "新增"),
    ("shares", "共享"),
    ("logs", "日志"),
]

AUTH_QUERY_KEY = "auth"
THEME_QUERY_KEY = "theme"
PASSKEY_RESULT_QUERY_KEY = "passkey_result"
PASSKEY_CHALLENGE_TTL_SECONDS = 3 * 60
THEME_MODES = ("system", "light", "dark")
THEME_LABELS = {"system": "跟随系统", "light": "浅色", "dark": "深色"}


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
    if "pending_auth_token" not in st.session_state:
        st.session_state.pending_auth_token = None
    if "clear_auth_client" not in st.session_state:
        st.session_state.clear_auth_client = False
    if "passkey_pending_action" not in st.session_state:
        st.session_state.passkey_pending_action = None
    if "passkey_registration_state" not in st.session_state:
        st.session_state.passkey_registration_state = None
    if "passkey_auth_state" not in st.session_state:
        st.session_state.passkey_auth_state = None
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "system"


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
# Auth / theme / passkey helpers
# ------------------------------

def normalize_theme_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in THEME_MODES else "system"


def get_theme_mode() -> str:
    raw_query = get_query_value(THEME_QUERY_KEY)
    if raw_query is not None:
        query_mode = normalize_theme_mode(raw_query)
        st.session_state.theme_mode = query_mode
        return query_mode
    return normalize_theme_mode(st.session_state.get("theme_mode"))


def set_theme_mode(mode: str) -> None:
    normalized = normalize_theme_mode(mode)
    st.session_state.theme_mode = normalized
    set_query_value(THEME_QUERY_KEY, normalized)


def render_theme_switcher(key_prefix: str = "theme") -> None:
    current_mode = get_theme_mode()
    options = [THEME_LABELS[m] for m in THEME_MODES]
    current_label = THEME_LABELS[current_mode]

    if hasattr(st, "segmented_control"):
        selected = st.segmented_control(
            "🎨 主题",
            options=options,
            default=current_label,
            selection_mode="single",
            key=f"{key_prefix}_theme_seg",
        )
    else:
        selected = st.radio(
            "🎨 主题",
            options=options,
            index=options.index(current_label),
            horizontal=True,
            key=f"{key_prefix}_theme_radio",
        )

    selected_mode = next((k for k, v in THEME_LABELS.items() if v == (selected or current_label)), current_mode)
    if selected_mode != current_mode:
        set_theme_mode(selected_mode)
        st.rerun()


def render_theme_bridge(theme_mode: str) -> None:
    mode = normalize_theme_mode(theme_mode)
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const storageKey = "investment_app_theme_mode";
                const serverMode = {json.dumps(mode)};
                let hostWindow = window;
                if (window.parent && window.parent !== window) {{
                    hostWindow = window.parent;
                }}
                const root = hostWindow.document.documentElement;
                const body = hostWindow.document.body;
                const media = hostWindow.matchMedia("(prefers-color-scheme: dark)");

                let mode = serverMode || hostWindow.localStorage.getItem(storageKey) || "system";
                if (!["system","light","dark"].includes(mode)) {{
                    mode = "system";
                }}
                hostWindow.localStorage.setItem(storageKey, mode);

                function applyTheme(nextMode) {{
                    const effective = nextMode === "system" ? (media.matches ? "dark" : "light") : nextMode;
                    root.setAttribute("data-app-theme-mode", nextMode);
                    root.setAttribute("data-app-theme", effective);
                    if (body) {{
                        body.setAttribute("data-app-theme-mode", nextMode);
                        body.setAttribute("data-app-theme", effective);
                    }}
                }}

                applyTheme(mode);
                media.addEventListener("change", function() {{
                    if (mode === "system") {{
                        applyTheme("system");
                    }}
                }});
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def render_client_auth_bridge(token_to_store: str | None = None, clear_client: bool = False) -> None:
    safe_token = token_to_store or ""
    clear_flag = "true" if clear_client else "false"
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const storageKey = "investment_app_auth_token";
                const clearClient = {clear_flag};
                const tokenFromServer = {safe_token!r};
                const queryKey = {json.dumps(AUTH_QUERY_KEY)};
                let hostWindow = window;
                if (window.parent && window.parent !== window) {{
                    hostWindow = window.parent;
                }}

                const params = new URLSearchParams(hostWindow.location.search);
                const urlToken = params.get(queryKey);
                let localToken = hostWindow.localStorage.getItem(storageKey);

                if (clearClient) {{
                    hostWindow.localStorage.removeItem(storageKey);
                    localToken = null;
                    if (urlToken) {{
                        params.delete(queryKey);
                        const q = params.toString();
                        hostWindow.history.replaceState({{}}, "", hostWindow.location.pathname + (q ? "?" + q : ""));
                    }}
                }}

                if (tokenFromServer) {{
                    hostWindow.localStorage.setItem(storageKey, tokenFromServer);
                    localToken = tokenFromServer;
                }}

                if (!urlToken && localToken) {{
                    params.set(queryKey, localToken);
                    hostWindow.location.replace(hostWindow.location.pathname + "?" + params.toString());
                    return;
                }}

                if (urlToken && !localToken) {{
                    hostWindow.localStorage.setItem(storageKey, urlToken);
                }}
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )


def create_login_state(ctx: AppContext, username: str) -> None:
    token = ctx.auth.make_token(username)
    st.session_state.logged_in = True
    st.session_state.username = username
    st.session_state.pending_auth_token = token
    st.session_state.clear_auth_client = False
    set_query_value(AUTH_QUERY_KEY, token)


def b64url_encode(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("utf-8")


def b64url_decode(raw_str: str) -> bytes:
    padded = raw_str + "=" * ((4 - len(raw_str) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def get_setting(name: str, default: str = "") -> str:
    env_value = os.getenv(name, "").strip()
    if env_value:
        return env_value
    try:
        value = st.secrets.get(name, "")
        if isinstance(value, str):
            value = value.strip()
        return value or default
    except Exception:
        return default


def get_request_headers() -> dict[str, str]:
    try:
        ctx = getattr(st, "context", None)
        if ctx is not None and hasattr(ctx, "headers"):
            return dict(ctx.headers)
    except Exception:
        pass
    return {}


def get_webauthn_context() -> tuple[str, str, str]:
    headers = get_request_headers()
    host = headers.get("Host", "") or headers.get("host", "")
    proto = headers.get("X-Forwarded-Proto", "") or headers.get("x-forwarded-proto", "")
    forwarded = headers.get("Forwarded", "") or headers.get("forwarded", "")

    if "," in host:
        host = host.split(",")[0].strip()
    if "," in proto:
        proto = proto.split(",")[0].strip()
    if not proto and forwarded:
        for segment in [x.strip() for x in forwarded.split(";")]:
            if segment.lower().startswith("proto="):
                proto = segment.split("=", 1)[1].strip().strip('"').lower()
                break

    host_name = host.split(":")[0] if host else ""
    if not proto:
        if host_name.endswith(".streamlit.app"):
            proto = "https"
        elif host_name in ("localhost", "127.0.0.1"):
            proto = "http"
        else:
            proto = "https"

    rp_name = get_setting("WEBAUTHN_RP_NAME", "Investment App")
    rp_id = get_setting("WEBAUTHN_RP_ID", "") or host_name
    origin = get_setting("WEBAUTHN_ORIGIN", "") or (f"{proto}://{host}" if host else "")
    return rp_name, rp_id, origin


def is_secure_webauthn_origin(origin: str) -> bool:
    return bool(
        origin
        and (
            origin.startswith("https://")
            or origin.startswith("http://localhost")
            or origin.startswith("http://127.0.0.1")
        )
    )


def challenge_is_expired(state: dict[str, Any] | None) -> bool:
    if not state:
        return True
    created_at = int(state.get("created_at") or 0)
    return int(time.time()) - created_at > PASSKEY_CHALLENGE_TTL_SECONDS


def start_passkey_registration(ctx: AppContext, username: str) -> tuple[bool, str]:
    if not WEBAUTHN_AVAILABLE:
        return False, f"未安装 webauthn 依赖：{WEBAUTHN_IMPORT_ERROR}"

    rp_name, rp_id, origin = get_webauthn_context()
    if not rp_id or not origin:
        return False, "无法识别当前域名，请配置 WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN。"
    if not is_secure_webauthn_origin(origin):
        return False, "Face ID 需要 HTTPS 域名（或 localhost）。请改用 HTTPS 访问。"

    user_id = hashlib.sha256(f"user:{username}".encode("utf-8")).digest()
    try:
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=rp_name,
            user_id=user_id,
            user_name=username,
            user_display_name=username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
    except TypeError:
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=rp_name,
            user_id=user_id,
            user_name=username,
            user_display_name=username,
        )

    payload = json.loads(options_to_json(options))
    challenge = payload.get("challenge")
    if not challenge:
        return False, "生成 Face ID 注册挑战失败。"

    st.session_state.passkey_registration_state = {
        "username": username,
        "rp_id": rp_id,
        "origin": origin,
        "challenge": challenge,
        "created_at": int(time.time()),
    }
    st.session_state.passkey_pending_action = {
        "mode": "register",
        "options": payload,
        "state": st.session_state.passkey_registration_state,
    }
    return True, "请在系统弹窗中完成 Face ID 注册。"


def start_passkey_authentication() -> tuple[bool, str]:
    if not WEBAUTHN_AVAILABLE:
        return False, f"未安装 webauthn 依赖：{WEBAUTHN_IMPORT_ERROR}"

    _rp_name, rp_id, origin = get_webauthn_context()
    if not rp_id or not origin:
        return False, "无法识别当前域名，请配置 WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN。"
    if not is_secure_webauthn_origin(origin):
        return False, "Face ID 需要 HTTPS 域名（或 localhost）。请改用 HTTPS 访问。"

    try:
        options = generate_authentication_options(
            rp_id=rp_id,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
    except TypeError:
        options = generate_authentication_options(rp_id=rp_id)

    payload = json.loads(options_to_json(options))
    challenge = payload.get("challenge")
    if not challenge:
        return False, "生成 Face ID 登录挑战失败。"

    st.session_state.passkey_auth_state = {
        "rp_id": rp_id,
        "origin": origin,
        "challenge": challenge,
        "created_at": int(time.time()),
    }
    st.session_state.passkey_pending_action = {
        "mode": "authenticate",
        "options": payload,
        "state": st.session_state.passkey_auth_state,
    }
    return True, "请在系统弹窗中完成 Face ID 验证。"


def consume_passkey_query_result() -> dict[str, Any] | None:
    encoded = get_query_value(PASSKEY_RESULT_QUERY_KEY)
    if not encoded:
        return None
    clear_query_value(PASSKEY_RESULT_QUERY_KEY)
    try:
        raw_json = b64url_decode(encoded).decode("utf-8")
        return json.loads(raw_json)
    except Exception:
        st.error("Face ID 回调数据解析失败，请重试。")
        return None


def finalize_passkey_registration(
    ctx: AppContext, payload: dict[str, Any], state_override: dict[str, Any] | None = None
) -> tuple[bool, str]:
    state = st.session_state.passkey_registration_state or state_override
    st.session_state.passkey_registration_state = None
    if not state:
        return False, "Face ID 注册会话不存在，请重新点击“启用 Face ID”。"
    if challenge_is_expired(state):
        return False, "Face ID 注册已超时，请重试。"

    try:
        verification = verify_registration_response(
            credential=payload,
            expected_challenge=b64url_decode(state["challenge"]),
            expected_origin=state["origin"],
            expected_rp_id=state["rp_id"],
            require_user_verification=True,
        )
        credential_id_raw = getattr(verification, "credential_id")
        public_key_raw = getattr(verification, "credential_public_key")
        sign_count = int(getattr(verification, "sign_count", 0) or 0)
        credential_id = (
            credential_id_raw if isinstance(credential_id_raw, str) else b64url_encode(credential_id_raw)
        )
        public_key = public_key_raw if isinstance(public_key_raw, str) else b64url_encode(public_key_raw)

        ctx.auth.upsert_passkey(
            username=state["username"],
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            transports=payload.get("response", {}).get("transports", []),
        )
        return True, "Face ID 已启用，下次可直接刷脸登录。"
    except Exception as exc:
        return False, f"Face ID 注册失败：{exc}"


def finalize_passkey_authentication(
    ctx: AppContext, payload: dict[str, Any], state_override: dict[str, Any] | None = None
) -> tuple[bool, str, str | None]:
    state = st.session_state.passkey_auth_state or state_override
    st.session_state.passkey_auth_state = None
    if not state:
        return False, "Face ID 登录会话不存在，请重试。", None
    if challenge_is_expired(state):
        return False, "Face ID 登录已超时，请重试。", None

    credential_id = payload.get("id") or payload.get("rawId")
    passkey = ctx.auth.get_passkey_by_credential_id(str(credential_id or ""))
    if not passkey and payload.get("rawId"):
        credential_id = payload.get("rawId")
        passkey = ctx.auth.get_passkey_by_credential_id(str(credential_id))
    if not passkey:
        return False, "未找到该设备的 Passkey，请先用密码登录并启用 Face ID。", None

    try:
        verification = verify_authentication_response(
            credential=payload,
            expected_challenge=b64url_decode(state["challenge"]),
            expected_origin=state["origin"],
            expected_rp_id=state["rp_id"],
            credential_public_key=b64url_decode(passkey["public_key"]),
            credential_current_sign_count=int(passkey["sign_count"]),
            require_user_verification=True,
        )
        new_sign_count = int(getattr(verification, "new_sign_count", passkey["sign_count"]) or 0)
        ctx.auth.update_passkey_sign_count(str(credential_id), new_sign_count)
        return True, "Face ID 登录成功。", str(passkey["username"])
    except Exception as exc:
        return False, f"Face ID 登录失败：{exc}", None


def handle_passkey_query_result(ctx: AppContext) -> None:
    result = consume_passkey_query_result()
    if not result:
        return

    mode = result.get("mode")
    ok = bool(result.get("ok"))
    if not ok:
        st.session_state.passkey_registration_state = None
        st.session_state.passkey_auth_state = None
        st.error(f"Face ID 操作失败：{result.get('error') or '未知错误'}")
        return

    payload = result.get("payload") or {}
    state_payload = result.get("state") if isinstance(result.get("state"), dict) else None
    if mode == "register":
        success, message = finalize_passkey_registration(ctx, payload, state_payload)
        if success:
            st.success(message)
        else:
            st.error(message)
        return

    if mode == "authenticate":
        success, message, username = finalize_passkey_authentication(ctx, payload, state_payload)
        if not success or not username:
            st.error(message)
            return
        create_login_state(ctx, username)
        st.toast("✅ Face ID 登录成功", icon="✅")
        st.rerun()


def render_pending_passkey_action() -> None:
    action = st.session_state.passkey_pending_action
    if not action:
        return
    st.session_state.passkey_pending_action = None

    mode = action.get("mode")
    options = action.get("options") or {}
    state_payload = action.get("state") or {}
    payload_json = json.dumps(options, ensure_ascii=False)
    state_json = json.dumps(state_payload, ensure_ascii=False)
    query_key = PASSKEY_RESULT_QUERY_KEY

    components.html(
        f"""
        <div style="padding: 8px 0;">
          <button id="passkey-trigger-btn" style="width:100%;padding:10px 12px;border:0;border-radius:8px;background:#0f766e;color:#fff;font-weight:600;">
            Face ID 重试
          </button>
          <div id="passkey-status" style="margin-top:8px;font-size:13px;color:#475569;">
            正在自动拉起 Face ID...
          </div>
        </div>
        <script>
        (function() {{
            const mode = {json.dumps(mode)};
            const options = {payload_json};
            const statePayload = {state_json};
            const queryKey = {json.dumps(query_key)};
            const triggerBtn = document.getElementById("passkey-trigger-btn");
            const statusEl = document.getElementById("passkey-status");
            let hasTriggered = false;

            function setStatus(text, isError) {{
                if (!statusEl) return;
                statusEl.textContent = text;
                statusEl.style.color = isError ? "#b91c1c" : "#475569";
            }}

            function toBytes(value) {{
                if (value instanceof Uint8Array) return value;
                if (value instanceof ArrayBuffer) return new Uint8Array(value);
                if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
                return new Uint8Array();
            }}

            function encodeBase64Url(value) {{
                const bytes = toBytes(value);
                let binary = "";
                for (let i = 0; i < bytes.length; i += 1) {{
                    binary += String.fromCharCode(bytes[i]);
                }}
                return btoa(binary).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/g, "");
            }}

            function decodeBase64Url(value) {{
                const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
                const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
                const binary = atob(base64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i += 1) {{
                    bytes[i] = binary.charCodeAt(i);
                }}
                return bytes.buffer;
            }}

            function encodeJson(obj) {{
                return encodeBase64Url(new TextEncoder().encode(JSON.stringify(obj)));
            }}

            function normalizeCreateOptions(raw) {{
                const next = {{ ...raw }};
                next.challenge = decodeBase64Url(next.challenge);
                if (next.user && next.user.id) {{
                    next.user = {{ ...next.user, id: decodeBase64Url(next.user.id) }};
                }}
                if (Array.isArray(next.excludeCredentials)) {{
                    next.excludeCredentials = next.excludeCredentials.map((item) => ({{ ...item, id: decodeBase64Url(item.id) }}));
                }}
                return next;
            }}

            function normalizeGetOptions(raw) {{
                const next = {{ ...raw }};
                next.challenge = decodeBase64Url(next.challenge);
                if (Array.isArray(next.allowCredentials)) {{
                    next.allowCredentials = next.allowCredentials.map((item) => ({{ ...item, id: decodeBase64Url(item.id) }}));
                }}
                return next;
            }}

            function serializeRegistrationCredential(credential) {{
                const response = credential.response;
                return {{
                    id: credential.id,
                    rawId: encodeBase64Url(credential.rawId),
                    type: credential.type,
                    response: {{
                        clientDataJSON: encodeBase64Url(response.clientDataJSON),
                        attestationObject: encodeBase64Url(response.attestationObject),
                        transports: typeof response.getTransports === "function" ? response.getTransports() : [],
                    }},
                    clientExtensionResults: typeof credential.getClientExtensionResults === "function"
                        ? credential.getClientExtensionResults()
                        : {{}},
                }};
            }}

            function serializeAuthenticationCredential(credential) {{
                const response = credential.response;
                return {{
                    id: credential.id,
                    rawId: encodeBase64Url(credential.rawId),
                    type: credential.type,
                    response: {{
                        authenticatorData: encodeBase64Url(response.authenticatorData),
                        clientDataJSON: encodeBase64Url(response.clientDataJSON),
                        signature: encodeBase64Url(response.signature),
                        userHandle: response.userHandle ? encodeBase64Url(response.userHandle) : null,
                    }},
                    clientExtensionResults: typeof credential.getClientExtensionResults === "function"
                        ? credential.getClientExtensionResults()
                        : {{}},
                }};
            }}

            function sendResult(result) {{
                let hostWindow = window;
                if (window.parent && window.parent !== window) {{
                    hostWindow = window.parent;
                }}
                const url = new URL(hostWindow.location.href);
                url.searchParams.set(queryKey, encodeJson(result));
                hostWindow.location.replace(url.toString());
            }}

            async function runPasskey() {{
                if (hasTriggered) return;
                hasTriggered = true;
                if (!window.PublicKeyCredential) {{
                    sendResult({{ mode, ok: false, error: "当前浏览器不支持 Passkey/Face ID", state: statePayload }});
                    return;
                }}
                try {{
                    if (window.parent && window.parent !== window && typeof window.parent.focus === "function") {{
                        window.parent.focus();
                    }}
                    if (typeof window.focus === "function") {{
                        window.focus();
                    }}
                    if (mode === "register") {{
                        const credential = await navigator.credentials.create({{
                            publicKey: normalizeCreateOptions(options),
                        }});
                        sendResult({{
                            mode,
                            ok: true,
                            payload: serializeRegistrationCredential(credential),
                            state: statePayload,
                        }});
                        return;
                    }}
                    const credential = await navigator.credentials.get({{
                        publicKey: normalizeGetOptions(options),
                    }});
                    sendResult({{
                        mode,
                        ok: true,
                        payload: serializeAuthenticationCredential(credential),
                        state: statePayload,
                    }});
                }} catch (error) {{
                    hasTriggered = false;
                    sendResult({{
                        mode,
                        ok: false,
                        error: error && error.message ? error.message : String(error),
                        state: statePayload,
                    }});
                }}
            }}

            if (!triggerBtn) {{
                setStatus("无法渲染 Face ID 按钮，请刷新页面重试。", true);
                return;
            }}

            triggerBtn.addEventListener("click", function() {{
                triggerBtn.disabled = true;
                triggerBtn.style.opacity = "0.7";
                setStatus("正在请求 Face ID，请在系统弹窗中确认...", false);
                runPasskey();
            }});

            setTimeout(function() {{
                try {{
                    triggerBtn.disabled = true;
                    triggerBtn.style.opacity = "0.7";
                    setStatus("正在自动拉起 Face ID，请在系统弹窗中确认...", false);
                    runPasskey();
                }} catch (e) {{
                    triggerBtn.disabled = false;
                    triggerBtn.style.opacity = "1";
                    setStatus("自动拉起失败，请点击按钮重试。", true);
                }}
            }}, 120);
        }})();
        </script>
        """,
        height=120,
    )


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
            --sidebar-bg: linear-gradient(180deg, rgba(232,242,252,0.95) 0%, rgba(244,248,252,0.92) 100%);
            --sidebar-border: #d6e4f0;
            --sidebar-text: #122b46;
            --input-bg: #fbfdff;
            --input-border: #cddcea;
        }

        html[data-app-theme="light"],
        body[data-app-theme="light"],
        [data-app-theme="light"] {
            --app-bg: #f3f7fb;
            --app-card: #ffffff;
            --app-border: #d5e4f0;
            --app-text: #122b46;
            --app-sub: #5a718a;
            --app-accent: #0f766e;
            --nav-bg: rgba(255,255,255,0.92);
            --sidebar-bg: linear-gradient(180deg, rgba(232,242,252,0.95) 0%, rgba(244,248,252,0.92) 100%);
            --sidebar-border: #d6e4f0;
            --sidebar-text: #122b46;
            --input-bg: #fbfdff;
            --input-border: #cddcea;
        }

        [data-testid="stAppViewContainer"] {
            background:
              radial-gradient(900px 360px at 6% -12%, #d9ecff 0%, transparent 60%),
              radial-gradient(850px 330px at 100% 0%, #d6f6ef 0%, transparent 58%),
              var(--app-bg);
            color: var(--app-text);
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
            background: var(--sidebar-bg);
            backdrop-filter: blur(10px);
            border-right: 1px solid var(--sidebar-border);
            color: var(--sidebar-text);
        }

        [data-testid="stSidebar"] * {
            color: var(--sidebar-text);
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
            border-color: var(--input-border);
            background: var(--input-bg);
            color: var(--app-text);
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

        html[data-app-theme="dark"],
        body[data-app-theme="dark"],
        [data-app-theme="dark"] {
            --app-bg: #0b1220;
            --app-card: #111b2e;
            --app-border: #24344e;
            --app-text: #e6eef8;
            --app-sub: #9eb2c8;
            --app-accent: #2dd4bf;
            --nav-bg: rgba(17,27,46,0.9);
            --sidebar-bg: linear-gradient(180deg, rgba(17,27,46,0.97) 0%, rgba(14,23,39,0.95) 100%);
            --sidebar-border: #2a3c58;
            --sidebar-text: #e6eef8;
            --input-bg: #0f1727;
            --input-border: #334866;
        }

        html[data-app-theme="dark"] [data-testid="stAppViewContainer"],
        body[data-app-theme="dark"] [data-testid="stAppViewContainer"],
        [data-app-theme="dark"] [data-testid="stAppViewContainer"] {
            background:
              radial-gradient(900px 360px at 0% -10%, #142540 0%, transparent 62%),
              radial-gradient(820px 320px at 100% 0%, #103436 0%, transparent 58%),
              #0b1220 !important;
            color: #e6eef8 !important;
        }

        html[data-app-theme="dark"] h1,
        html[data-app-theme="dark"] h2,
        html[data-app-theme="dark"] h3,
        html[data-app-theme="dark"] p,
        html[data-app-theme="dark"] label,
        html[data-app-theme="dark"] span,
        body[data-app-theme="dark"] h1,
        body[data-app-theme="dark"] h2,
        body[data-app-theme="dark"] h3,
        body[data-app-theme="dark"] p,
        body[data-app-theme="dark"] label,
        body[data-app-theme="dark"] span,
        [data-app-theme="dark"] h1,
        [data-app-theme="dark"] h2,
        [data-app-theme="dark"] h3,
        [data-app-theme="dark"] p,
        [data-app-theme="dark"] label,
        [data-app-theme="dark"] span {
            color: #e6eef8 !important;
        }

        html[data-app-theme="dark"] [data-testid="stExpander"],
        html[data-app-theme="dark"] [data-testid="stMetric"],
        body[data-app-theme="dark"] [data-testid="stExpander"],
        body[data-app-theme="dark"] [data-testid="stMetric"],
        [data-app-theme="dark"] [data-testid="stExpander"],
        [data-app-theme="dark"] [data-testid="stMetric"] {
            background: #111b2e !important;
            border-color: #24344e !important;
            box-shadow: none !important;
        }

        html[data-app-theme="dark"] div[data-baseweb="input"] > div,
        html[data-app-theme="dark"] div[data-baseweb="select"] > div,
        body[data-app-theme="dark"] div[data-baseweb="input"] > div,
        body[data-app-theme="dark"] div[data-baseweb="select"] > div,
        [data-app-theme="dark"] div[data-baseweb="input"] > div,
        [data-app-theme="dark"] div[data-baseweb="select"] > div {
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


def render_data_source_status() -> None:
    name = get_database_display_name()
    st.caption(f"数据源：{name}")


def render_login_page(ctx: AppContext) -> None:
    st.subheader("🔐 登录")
    render_theme_switcher("login")
    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("登录", type="primary"):
                if ctx.auth.login(username, password):
                    create_login_state(ctx, username)
                    st.success(f"欢迎回来，{username}")
                    st.rerun()
                else:
                    st.error("用户名或密码错误")

        st.divider()
        st.caption("📱 iPhone 可直接用 Face ID 登录（先用密码登录一次后启用）")
        if st.button("使用 Face ID 登录", key="passkey_auth_button", type="primary"):
            ok, msg = start_passkey_authentication()
            if ok:
                st.info(msg)
                st.rerun()
            else:
                st.error(msg)

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
        render_theme_switcher("sidebar")
        st.divider()

        with st.expander("🔐 Face ID 登录", expanded=False):
            if WEBAUTHN_AVAILABLE:
                st.caption("在这台设备启用后，可在登录页直接刷脸进入。")
                if st.button("在当前设备启用 Face ID", key="passkey_register_btn", type="primary"):
                    ok, msg = start_passkey_registration(ctx, current_user)
                    if ok:
                        st.info(msg)
                        st.rerun()
                    else:
                        st.error(msg)

                passkeys = ctx.auth.list_passkeys(current_user)
                st.caption(f"已绑定 Passkey 数量：{len(passkeys)}")
                for item in passkeys:
                    short_id = f"{item['credential_id'][:16]}..."
                    st.write(f"设备凭证：`{short_id}`")
                    created = str(item.get("created_at") or "-")
                    last_used = str(item.get("last_used_at") or "-")
                    st.caption(f"创建时间：{created} | 最近使用：{last_used}")
                    if st.button("删除此凭证", key=f"delete_passkey_{item['id']}"):
                        if ctx.auth.delete_passkey(current_user, int(item["id"])):
                            st.success("已删除该 Face ID 凭证")
                        else:
                            st.warning("未找到该凭证")
                        st.rerun()
                    st.divider()
            else:
                st.error(f"缺少 webauthn 依赖：{WEBAUTHN_IMPORT_ERROR}")
                st.caption("请先安装：`pip install webauthn`")

        st.divider()
        if st.button("🚪 登出"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.pending_auth_token = None
            st.session_state.clear_auth_client = True
            st.session_state.passkey_pending_action = None
            st.session_state.passkey_registration_state = None
            st.session_state.passkey_auth_state = None
            clear_query_value(AUTH_QUERY_KEY)
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
    token = get_query_value(AUTH_QUERY_KEY)
    username = ctx.auth.parse_token(token)
    if username:
        st.session_state.logged_in = True
        st.session_state.username = username


def run_app() -> None:
    settings = get_settings()
    st.set_page_config(
        page_title=settings.app_name,
        layout="wide",
        page_icon="🌍",
        initial_sidebar_state="expanded",
    )

    init_session_state()

    render_theme_bridge(get_theme_mode())
    render_client_auth_bridge(
        token_to_store=st.session_state.pending_auth_token,
        clear_client=bool(st.session_state.clear_auth_client),
    )
    if st.session_state.pending_auth_token:
        st.session_state.pending_auth_token = None
    if st.session_state.clear_auth_client:
        st.session_state.clear_auth_client = False

    render_theme()
    st.title("🌍 全球资产管理系统 Pro")

    init_db()
    render_data_source_status()

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

    handle_passkey_query_result(ctx)
    maybe_restore_login(ctx)
    render_pending_passkey_action()

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
