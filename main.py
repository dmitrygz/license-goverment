import hashlib
import json
import os
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dash import ALL, Dash, Input, Output, State, callback_context, dash_table, dcc, html, no_update

try:
    import psycopg2
except ImportError:
    psycopg2 = None


DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).with_name("license_app.db")))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

DEFAULT_LICENSES = {
    "День": [
        {"code": "ОР", "name": "Оружие", "price": 20000, "treasury": 10000, "cash": 10000},
        {"code": "ОР ГОСС", "name": "Оружие госс сотрудникам", "price": 10000, "treasury": 0, "cash": 10000},
        {"code": "ОХОТ", "name": "Охота", "price": 30000, "treasury": 15000, "cash": 15000},
        {"code": "РЫБ", "name": "Рыбалка", "price": 15000, "treasury": 7500, "cash": 7500},
    ],
    "Ночь": [
        {"code": "ОР", "name": "Оружие", "price": 27500, "treasury": 13750, "cash": 13750},
        {"code": "ОР ГОСС", "name": "Оружие госс сотрудникам", "price": 17500, "treasury": 7500, "cash": 10000},
        {"code": "ОХОТ", "name": "Охота", "price": 37500, "treasury": 18750, "cash": 18750},
        {"code": "РЫБ", "name": "Рыбалка", "price": 22500, "treasury": 11250, "cash": 11250},
    ],
}

THEMES = {
    "Светлая": {"page": "theme-light", "accent": "#6b7cff"},
    "Черная": {"page": "theme-dark", "accent": "#8ba4ff"},
}


def get_connection():
    if USE_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError("Для PostgreSQL нужен пакет psycopg2-binary.")
        return psycopg2.connect(DATABASE_URL)
    connection = sqlite3.connect(DB_PATH)
    return connection


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db() -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        if USE_POSTGRES:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    theme TEXT NOT NULL,
                    tariffs_json TEXT NOT NULL,
                    draft_records_json TEXT NOT NULL DEFAULT '[]',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS action_logs (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    theme TEXT NOT NULL,
                    tariffs_json TEXT NOT NULL,
                    draft_records_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        connection.commit()
        try:
            if USE_POSTGRES:
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            connection.commit()
        except Exception:
            connection.rollback()


def fetchone(query: str, params: tuple = ()) -> tuple | None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()


def fetchall(query: str, params: tuple = ()) -> list[tuple]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def execute(query: str, params: tuple = ()) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        connection.commit()


def users_count() -> int:
    if USE_POSTGRES:
        row = fetchone("SELECT COUNT(*) FROM users")
    else:
        row = fetchone("SELECT COUNT(*) FROM users")
    return int(row[0]) if row else 0


def add_action_log(username: str, action_type: str, details: dict) -> None:
    payload = json.dumps(details, ensure_ascii=False)
    if USE_POSTGRES:
        execute(
            "INSERT INTO action_logs (username, action_type, details_json) VALUES (%s, %s, %s)",
            (username, action_type, payload),
        )
    else:
        execute(
            "INSERT INTO action_logs (username, action_type, details_json) VALUES (?, ?, ?)",
            (username, action_type, payload),
        )


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def clone_tariffs() -> dict:
    return deepcopy(DEFAULT_LICENSES)


def normalize_record(record: dict) -> dict:
    return {
        "id": int(record["id"]),
        "period": record["period"],
        "code": record["code"],
        "name": record["name"],
        "status": record["status"],
        "price": int(record["price"]),
        "treasury": int(record["treasury"]),
        "cash": int(record["cash"]),
    }


def format_money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def year_options() -> list[dict]:
    current_year = datetime.now().year
    return [{"label": str(year), "value": str(year)} for year in range(current_year - 3, current_year + 4)]


def month_options() -> list[dict]:
    months = [
        ("01", "Январь"),
        ("02", "Февраль"),
        ("03", "Март"),
        ("04", "Апрель"),
        ("05", "Май"),
        ("06", "Июнь"),
        ("07", "Июль"),
        ("08", "Август"),
        ("09", "Сентябрь"),
        ("10", "Октябрь"),
        ("11", "Ноябрь"),
        ("12", "Декабрь"),
    ]
    return [{"label": name, "value": value} for value, name in months]


def create_user(username: str, password: str) -> tuple[bool, str]:
    try:
        role = "admin" if users_count() == 0 else "user"
        if USE_POSTGRES:
            execute(
                """
                INSERT INTO users (username, password_hash, role, theme, tariffs_json, draft_records_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    username,
                    hash_password(password),
                    role,
                    "Светлая",
                    json.dumps(clone_tariffs(), ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                ),
            )
        else:
            execute(
                """
                INSERT INTO users (username, password_hash, role, theme, tariffs_json, draft_records_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    hash_password(password),
                    role,
                    "Светлая",
                    json.dumps(clone_tariffs(), ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                ),
            )
        add_action_log(username, "register", {"message": "Регистрация нового пользователя", "role": role})
        return True, "Аккаунт создан. Можно входить."
    except Exception as error:
        if "unique" in str(error).lower():
            return False, "Пользователь с таким логином уже существует."
        return False, "Пользователь с таким логином уже существует."


def verify_user(username: str, password: str) -> bool:
    if USE_POSTGRES:
        row = fetchone("SELECT password_hash FROM users WHERE username = %s", (username,))
    else:
        row = fetchone("SELECT password_hash FROM users WHERE username = ?", (username,))
    return bool(row and row[0] == hash_password(password))


def load_user_state(username: str) -> dict | None:
    if USE_POSTGRES:
        row = fetchone(
            "SELECT role, theme, tariffs_json, draft_records_json FROM users WHERE username = %s",
            (username,),
        )
    else:
        row = fetchone(
            "SELECT role, theme, tariffs_json, draft_records_json FROM users WHERE username = ?",
            (username,),
        )
    if not row:
        return None
    role, theme, tariffs_json, draft_records_json = row
    tariffs = json.loads(tariffs_json)
    records = [normalize_record(record) for record in json.loads(draft_records_json or "[]")]
    return {"username": username, "role": role, "theme": theme, "tariffs": tariffs, "records": records}


def save_user_state(username: str, theme: str, tariffs: dict, records: list[dict]) -> None:
    normalized_records = [normalize_record(record) for record in records]
    if USE_POSTGRES:
        execute(
            """
            UPDATE users
            SET theme = %s, tariffs_json = %s, draft_records_json = %s
            WHERE username = %s
            """,
            (
                theme,
                json.dumps(tariffs, ensure_ascii=False),
                json.dumps(normalized_records, ensure_ascii=False),
                username,
            ),
        )
    else:
        execute(
            """
            UPDATE users
            SET theme = ?, tariffs_json = ?, draft_records_json = ?
            WHERE username = ?
            """,
            (
                theme,
                json.dumps(tariffs, ensure_ascii=False),
                json.dumps(normalized_records, ensure_ascii=False),
                username,
            ),
        )


def fetch_action_logs(username: str, limit: int = 200) -> list[dict]:
    state = load_user_state(username)
    is_admin = bool(state and state.get("role") == "admin")
    if USE_POSTGRES:
        rows = fetchall(
            "SELECT username, action_type, details_json, created_at FROM action_logs "
            + ("ORDER BY created_at DESC LIMIT %s" if is_admin else "WHERE username = %s ORDER BY created_at DESC LIMIT %s"),
            ((limit,) if is_admin else (username, limit)),
        )
    else:
        rows = fetchall(
            "SELECT username, action_type, details_json, created_at FROM action_logs "
            + ("ORDER BY created_at DESC LIMIT ?" if is_admin else "WHERE username = ? ORDER BY created_at DESC LIMIT ?"),
            ((limit,) if is_admin else (username, limit)),
        )
    logs = []
    for actor, action_type, details_json, created_at in rows:
        details = json.loads(details_json or "{}")
        logs.append(
            {
                "Пользователь": actor,
                "Время": str(created_at),
                "Действие": action_type,
                "Описание": details.get("message", ""),
                "Детали": json.dumps(details, ensure_ascii=False),
            }
        )
    return logs


def fetch_license_history(username: str) -> list[dict]:
    state = load_user_state(username)
    is_admin = bool(state and state.get("role") == "admin")
    if USE_POSTGRES:
        rows = fetchall(
            "SELECT username, details_json, created_at FROM action_logs "
            + ("WHERE action_type = %s ORDER BY created_at DESC" if is_admin else "WHERE username = %s AND action_type = %s ORDER BY created_at DESC"),
            (("add_license",) if is_admin else (username, "add_license")),
        )
    else:
        rows = fetchall(
            "SELECT username, details_json, created_at FROM action_logs "
            + ("WHERE action_type = ? ORDER BY created_at DESC" if is_admin else "WHERE username = ? AND action_type = ? ORDER BY created_at DESC"),
            (("add_license",) if is_admin else (username, "add_license")),
        )
    history = []
    for actor, details_json, created_at in rows:
        details = json.loads(details_json or "{}")
        history.append(
            {
                "Пользователь": actor,
                "Дата": str(created_at).split(" ")[0].split("T")[0],
                "Время": details.get("period", ""),
                "Код": details.get("code", ""),
                "Лицензия": details.get("name", ""),
                "Статус": details.get("status", ""),
                "Продажа": format_money(int(details.get("price", 0))),
                "В казну": format_money(int(details.get("treasury", 0))),
                "На руки": format_money(int(details.get("cash", 0))),
            }
        )
    return history


def build_breakdown(records: list[dict]) -> str:
    lines = ["Итоги:"]
    for period in ("День", "Ночь"):
        passed = {}
        failed = {}
        for record in records:
            if record["period"] != period:
                continue
            bucket = failed if record["status"] == "Не сдал" else passed
            bucket[record["code"]] = bucket.get(record["code"], 0) + 1

        parts = [f"| {code} {count} |" for code, count in passed.items()]
        if failed:
            parts.append("((НЕ СДАЛ)):")
            parts.extend(f"| {code} {count} |" for code, count in failed.items())
        lines.append(f"{period}: {' '.join(parts) if parts else '|'}")
    return "\n".join(lines)


def compute_totals(records: list[dict]) -> dict:
    return {
        "sales": sum(record["price"] for record in records),
        "treasury": sum(record["treasury"] for record in records),
        "cash": sum(record["cash"] for record in records),
        "count": len(records),
        "breakdown": build_breakdown(records),
    }


def records_to_rows(records: list[dict]) -> list[dict]:
    return [
        {
            "№": record["id"],
            "Время": record["period"],
            "Код": record["code"],
            "Лицензия": record["name"],
            "Статус": record["status"],
            "Продажа": format_money(record["price"]),
            "В казну": format_money(record["treasury"]),
            "На руки": format_money(record["cash"]),
        }
        for record in records
    ]


def tariffs_to_table_data(tariffs: dict, period: str) -> list[dict]:
    return [
        {
            "Код": item["code"],
            "Лицензия": item["name"],
            "Цена": item["price"],
            "В казну": item["treasury"],
            "На руки": item["cash"],
        }
        for item in tariffs[period]
    ]


def merge_tariff_tables(day_rows: list[dict], night_rows: list[dict]) -> dict:
    tariffs = {"День": [], "Ночь": []}
    for period, rows in (("День", day_rows), ("Ночь", night_rows)):
        for row in rows:
            tariffs[period].append(
                {
                    "code": row["Код"],
                    "name": row["Лицензия"],
                    "price": int(row["Цена"]),
                    "treasury": int(row["В казну"]),
                    "cash": int(row["На руки"]),
                }
            )
    return tariffs


def license_cards(tariffs: dict, period: str) -> list:
    cards = []
    for item in tariffs[period]:
        cards.append(
            html.Div(
                className="license-card fade-up",
                children=[
                    html.Div(item["code"], className="license-badge"),
                    html.Div(
                        className="license-content",
                        children=[
                            html.Div(
                                [
                                    html.Div(item["name"], className="license-title"),
                                    html.Div(
                                        f"Цена: {format_money(item['price'])} | Казна: {format_money(item['treasury'])} | На руки: {format_money(item['cash'])}",
                                        className="license-meta",
                                    ),
                                ]
                            ),
                            html.Div(
                                className="license-actions",
                                children=[
                                    html.Button(
                                        "Сдал",
                                        id={"type": "add-license", "period": period, "code": item["code"], "status": "Сдал"},
                                        className="action-btn action-success",
                                        n_clicks=0,
                                    ),
                                    html.Button(
                                        "Не сдал",
                                        id={"type": "add-license", "period": period, "code": item["code"], "status": "Не сдал"},
                                        className="action-btn action-danger",
                                        n_clicks=0,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            )
        )
    return cards


def app_layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="session-user", storage_type="local"),
            dcc.Store(id="user-role"),
            dcc.Store(id="user-theme"),
            dcc.Store(id="tariffs-store"),
            dcc.Store(id="records-store"),
            dcc.Store(id="click-state", data={}),
            dcc.Store(id="selected-period", data="День"),
            html.Div(
                id="page-root",
                className="theme-light",
                children=[
                    html.Div(
                        id="auth-screen",
                        className="auth-shell",
                        children=[
                            html.Div(
                                className="auth-card fade-up",
                                children=[
                                    html.Div("License Flow", className="auth-brand"),
                                    html.H1("Вход и регистрация", className="auth-title"),
                                    html.P("Авторизуйся, чтобы вести учет лицензий и сохранять настройки.", className="auth-subtitle"),
                                    dcc.Tabs(
                                        id="auth-mode",
                                        value="login",
                                        className="custom-tabs",
                                        parent_className="custom-tabs-wrap",
                                        children=[
                                            dcc.Tab(label="Вход", value="login", className="custom-tab", selected_className="custom-tab-selected"),
                                            dcc.Tab(label="Регистрация", value="register", className="custom-tab", selected_className="custom-tab-selected"),
                                        ],
                                    ),
                                    dcc.Input(id="username-input", type="text", placeholder="Логин", className="auth-input"),
                                    dcc.Input(id="password-input", type="password", placeholder="Пароль", className="auth-input"),
                                    html.Button("Продолжить", id="auth-submit", className="primary-btn", n_clicks=0),
                                    html.Div(id="auth-message", className="auth-message"),
                                ],
                            )
                        ],
                    ),
                    html.Div(
                        id="app-screen",
                        className="app-shell hidden",
                        children=[
                            html.Div(
                                className="hero-panel fade-up",
                                children=[
                                    html.Div(
                                        [
                                            html.Div("Учет лицензий", className="hero-eyebrow"),
                                            html.H1("License Goverment", className="hero-title"),
                                            html.P("Удобно и практично!", className="hero-subtitle"),
                                        ]
                                    ),
                                    html.Div(
                                        className="hero-side",
                                        children=[
                                            html.Div("Добавлено", className="hero-side-label"),
                                            html.Div(id="hero-count", className="hero-side-value"),
                                            html.Div(id="hero-user", className="hero-side-user"),
                                            html.Div(
                                                className="hero-side-actions",
                                                children=[
                                                    html.Button("Настройки", id="go-settings", className="secondary-btn", n_clicks=0),
                                                    html.Button("Выйти", id="logout-btn", className="ghost-btn", n_clicks=0),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Tabs(
                                id="main-tabs",
                                value="work",
                                className="main-tabs",
                                parent_className="main-tabs-wrap",
                                children=[
                                    dcc.Tab(
                                        label="Работа",
                                        value="work",
                                        className="main-tab",
                                        selected_className="main-tab-selected",
                                        children=[
                                            html.Div(
                                                className="work-grid",
                                                children=[
                                                    html.Div(
                                                        className="panel fade-up",
                                                        children=[
                                                            html.Div("Режим работы", className="panel-title"),
                                                            html.Div("Выбери время суток и добавляй лицензии одним нажатием.", className="panel-subtitle"),
                                                            html.Div(
                                                                className="segmented",
                                                                children=[
                                                                    html.Button("День", id="day-btn", className="segment-btn", n_clicks=0),
                                                                    html.Button("Ночь", id="night-btn", className="segment-btn", n_clicks=0),
                                                                ],
                                                            ),
                                                            html.Div(id="license-list", className="license-list"),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="panel fade-up delay-1",
                                                        children=[
                                                            html.Div(
                                                                className="summary-grid",
                                                                children=[
                                                                    html.Div([html.Div("Общая сумма", className="kpi-label"), html.Div(id="sales-kpi", className="kpi-value")], className="kpi-card sales"),
                                                                    html.Div([html.Div("В казну", className="kpi-label"), html.Div(id="treasury-kpi", className="kpi-value")], className="kpi-card treasury"),
                                                                    html.Div([html.Div("На руки", className="kpi-label"), html.Div(id="cash-kpi", className="kpi-value")], className="kpi-card cash"),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                className="breakdown-card",
                                                                children=[
                                                                    html.Div("Итоги", className="panel-title"),
                                                                    html.Pre(id="breakdown-text", className="breakdown-text"),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                className="report-head",
                                                                children=[
                                                                    html.Div(
                                                                        [
                                                                            html.Div("Итоговый отчет", className="panel-title"),
                                                                            html.Div("Выдели строку и удали ее, если нажал случайно.", className="panel-subtitle"),
                                                                        ]
                                                                    ),
                                                                    html.Button("Удалить выбранную", id="delete-row-btn", className="action-btn action-danger", n_clicks=0),
                                                                ],
                                                            ),
                                                            dash_table.DataTable(
                                                                id="records-table",
                                                                columns=[{"name": name, "id": name} for name in ["№", "Время", "Код", "Лицензия", "Статус", "Продажа", "В казну", "На руки"]],
                                                                data=[],
                                                                row_selectable="multi",
                                                                selected_rows=[],
                                                                page_size=10,
                                                                style_as_list_view=True,
                                                                style_table={"overflowX": "auto"},
                                                                style_header={"fontWeight": "600"},
                                                                style_cell={"padding": "14px 12px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.45", "textAlign": "left"},
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                    dcc.Tab(
                                        label="Настройки",
                                        value="settings",
                                        className="main-tab",
                                        selected_className="main-tab-selected",
                                        children=[
                                            html.Div(
                                                className="settings-grid fade-up",
                                                children=[
                                                    html.Div(
                                                        className="panel history-filter-panel",
                                                        children=[
                                                            html.Div("Тема оформления", className="panel-title"),
                                                            html.Div("Выбери светлую или черную тему интерфейса.", className="panel-subtitle"),
                                                            html.Div(
                                                                className="theme-switch",
                                                                children=[
                                                                    html.Button("Светлая", id="theme-light-btn", className="segment-btn theme-btn", n_clicks=0),
                                                                    html.Button("Темная", id="theme-dark-btn", className="segment-btn theme-btn", n_clicks=0),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="panel history-archive-panel",
                                                        children=[
                                                            html.Div("Тарифы - День", className="panel-title"),
                                                            dash_table.DataTable(
                                                                id="day-tariffs-table",
                                                                columns=[{"name": name, "id": name} for name in ["Код", "Лицензия", "Цена", "В казну", "На руки"]],
                                                                editable=True,
                                                                data=[],
                                                                style_table={"overflowX": "auto"},
                                                                style_cell={"padding": "14px 12px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.45", "textAlign": "left"},
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="panel",
                                                        children=[
                                                            html.Div("Тарифы - Ночь", className="panel-title"),
                                                            dash_table.DataTable(
                                                                id="night-tariffs-table",
                                                                columns=[{"name": name, "id": name} for name in ["Код", "Лицензия", "Цена", "В казну", "На руки"]],
                                                                editable=True,
                                                                data=[],
                                                                style_table={"overflowX": "auto"},
                                                                style_cell={"padding": "14px 12px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.45", "textAlign": "left"},
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="settings-actions",
                                                        children=[
                                                            html.Button("Сохранить настройки", id="save-settings-btn", className="primary-btn", n_clicks=0),
                                                            html.Div(id="settings-message", className="auth-message"),
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                    dcc.Tab(
                                        id="history-tab",
                                        label="История",
                                        value="history",
                                        className="main-tab",
                                        selected_className="main-tab-selected",
                                        children=[
                                            html.Div(
                                                className="settings-grid fade-up",
                                                children=[
                                                    html.Div(
                                                        className="panel",
                                                        children=[
                                                            html.Div("История по датам и сменам", className="panel-title"),
                                                            html.Div("Фильтруй прошлые оформления по дате и времени суток.", className="panel-subtitle"),
                                                            html.Div(
                                                                className="history-filters",
                                                                children=[
                                                                    html.Div(
                                                                        className="history-date-range",
                                                                        children=[
                                                                            dcc.Input(
                                                                                id="history-start-date",
                                                                                type="date",
                                                                                className="history-date-input",
                                                                            ),
                                                                            dcc.Input(
                                                                                id="history-end-date",
                                                                                type="date",
                                                                                className="history-date-input",
                                                                            ),
                                                                        ],
                                                                    ),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="panel",
                                                        children=[
                                                            html.Div("Архив лицензий", className="panel-title"),
                                                            dash_table.DataTable(
                                                                id="history-table",
                                                                columns=[{"name": name, "id": name} for name in ["Пользователь", "Дата", "Время", "Код", "Лицензия", "Статус", "Продажа", "В казну", "На руки"]],
                                                                data=[],
                                                                page_size=12,
                                                                style_table={"overflowX": "auto"},
                                                                style_cell={"padding": "14px 12px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.45", "textAlign": "left"},
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                    dcc.Tab(
                                        id="journal-tab",
                                        label="Журнал",
                                        value="journal",
                                        className="main-tab",
                                        selected_className="main-tab-selected",
                                        children=[
                                            html.Div(
                                                className="settings-grid fade-up",
                                                children=[
                                                    html.Div(
                                                        className="panel",
                                                        children=[
                                                            html.Div("Журнал действий", className="panel-title"),
                                                            html.Div("Показывает входы, сохранения, добавления и удаления лицензий.", className="panel-subtitle"),
                                                            dash_table.DataTable(
                                                                id="journal-table",
                                                                columns=[{"name": name, "id": name} for name in ["Пользователь", "Время", "Действие", "Описание"]],
                                                                data=[],
                                                                page_size=12,
                                                                style_table={"overflowX": "auto"},
                                                                style_cell={"padding": "14px 12px", "whiteSpace": "normal", "height": "auto", "lineHeight": "1.45", "textAlign": "left"},
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            )
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ]
    )


init_db()
app = Dash(__name__)
app.title = "Калькулятор лицензий"
app.layout = app_layout
server = app.server


@app.callback(
    Output("session-user", "data"),
    Output("auth-message", "children"),
    Input("auth-submit", "n_clicks"),
    State("auth-mode", "value"),
    State("username-input", "value"),
    State("password-input", "value"),
    prevent_initial_call=True,
)
def handle_auth(_, mode: str, username: str | None, password: str | None):
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return no_update, "Заполни логин и пароль."
    if mode == "register":
        created, message = create_user(username, password)
        if not created:
            return no_update, message
    elif not verify_user(username, password):
        return no_update, "Неверный логин или пароль."
    add_action_log(username, "login", {"message": "Вход в систему"})
    return username, "Успешный вход."


@app.callback(
    Output("session-user", "clear_data"),
    Input("logout-btn", "n_clicks"),
    prevent_initial_call=True,
)
def logout(_):
    return True


@app.callback(
    Output("auth-screen", "className"),
    Output("app-screen", "className"),
    Output("hero-user", "children"),
    Output("user-role", "data"),
    Output("user-theme", "data"),
    Output("tariffs-store", "data"),
    Output("records-store", "data"),
    Output("click-state", "data"),
    Output("day-tariffs-table", "data"),
    Output("night-tariffs-table", "data"),
    Input("session-user", "data"),
)
def sync_user_session(username: str | None):
    if not username:
        return "auth-shell", "app-shell hidden", "", "user", "Светлая", clone_tariffs(), [], {}, tariffs_to_table_data(clone_tariffs(), "День"), tariffs_to_table_data(clone_tariffs(), "Ночь")
    state = load_user_state(username)
    if not state:
        return "auth-shell", "app-shell hidden", "", "user", "Светлая", clone_tariffs(), [], {}, tariffs_to_table_data(clone_tariffs(), "День"), tariffs_to_table_data(clone_tariffs(), "Ночь")
    tariffs = state["tariffs"]
    records = state["records"]
    return (
        "auth-shell hidden",
        "app-shell",
        f"Пользователь: {username}",
        state["role"],
        state["theme"],
        tariffs,
        records,
        {},
        tariffs_to_table_data(tariffs, "День"),
        tariffs_to_table_data(tariffs, "Ночь"),
    )


@app.callback(
    Output("page-root", "className"),
    Output("hero-count", "children"),
    Output("sales-kpi", "children"),
    Output("treasury-kpi", "children"),
    Output("cash-kpi", "children"),
    Output("breakdown-text", "children"),
    Output("records-table", "data"),
    Input("user-theme", "data"),
    Input("records-store", "data"),
)
def render_dashboard(theme: str | None, records: list[dict] | None):
    records = records or []
    totals = compute_totals(records)
    theme_name = theme or "Светлая"
    return (
        THEMES[theme_name]["page"],
        f"{totals['count']} {'лицензия' if totals['count'] == 1 else 'лицензий'}",
        format_money(totals["sales"]),
        format_money(totals["treasury"]),
        format_money(totals["cash"]),
        totals["breakdown"],
        records_to_rows(records),
    )


@app.callback(
    Output("selected-period", "data"),
    Output("main-tabs", "value", allow_duplicate=True),
    Input("day-btn", "n_clicks"),
    Input("night-btn", "n_clicks"),
    Input("go-settings", "n_clicks"),
    State("selected-period", "data"),
    prevent_initial_call=True,
)
def switch_period(day_clicks, night_clicks, go_settings, current_period):
    trigger = callback_context.triggered_id
    if trigger == "go-settings":
        return current_period, "settings"
    if trigger == "night-btn":
        return "Ночь", "work"
    return "День", "work"


@app.callback(
    Output("history-tab", "style"),
    Output("journal-tab", "style"),
    Output("history-tab", "disabled"),
    Output("journal-tab", "disabled"),
    Output("main-tabs", "value", allow_duplicate=True),
    Input("user-role", "data"),
    State("main-tabs", "value"),
    prevent_initial_call=True,
)
def guard_admin_tabs(role: str | None, current_tab: str):
    is_admin = role == "admin"
    hidden_style = {} if is_admin else {"display": "none"}
    next_tab = current_tab
    if not is_admin and current_tab in {"history", "journal"}:
        next_tab = "work"
    return hidden_style, hidden_style, (not is_admin), (not is_admin), next_tab


@app.callback(
    Output("user-theme", "data", allow_duplicate=True),
    Input("theme-light-btn", "n_clicks"),
    Input("theme-dark-btn", "n_clicks"),
    State("user-theme", "data"),
    prevent_initial_call=True,
)
def switch_theme(light_clicks, dark_clicks, current_theme: str | None):
    trigger = callback_context.triggered_id
    if trigger == "theme-dark-btn":
        return "Черная"
    if trigger == "theme-light-btn":
        return "Светлая"
    return current_theme or "Светлая"


@app.callback(
    Output("license-list", "children"),
    Input("tariffs-store", "data"),
    Input("selected-period", "data"),
)
def render_license_list(tariffs: dict | None, period: str | None):
    tariffs = tariffs or clone_tariffs()
    return license_cards(tariffs, period or "День")


@app.callback(
    Output("records-store", "data", allow_duplicate=True),
    Output("click-state", "data", allow_duplicate=True),
    Input({"type": "add-license", "period": ALL, "code": ALL, "status": ALL}, "n_clicks"),
    Input("delete-row-btn", "n_clicks"),
    State("session-user", "data"),
    State("tariffs-store", "data"),
    State("records-store", "data"),
    State("records-table", "selected_rows"),
    State({"type": "add-license", "period": ALL, "code": ALL, "status": ALL}, "id"),
    State("click-state", "data"),
    prevent_initial_call=True,
)
def mutate_records(clicks, delete_clicks, session_user: str | None, tariffs: dict, records: list[dict] | None, selected_rows: list[int] | None, button_ids, click_state: dict | None):
    records = [normalize_record(record) for record in (records or [])]
    click_state = click_state or {}
    trigger = callback_context.triggered_id
    if isinstance(trigger, dict) and trigger.get("type") == "add-license":
        for button_id, click_count in zip(button_ids, clicks):
            key = json.dumps(button_id, ensure_ascii=False, sort_keys=True)
            previous_clicks = int(click_state.get(key, 0))
            current_clicks = int(click_count or 0)
            if current_clicks > previous_clicks:
                period = button_id["period"]
                code = button_id["code"]
                status = button_id["status"]
                item = next(item for item in tariffs[period] if item["code"] == code)
                next_id = max([record["id"] for record in records], default=0) + 1
                records.append(
                    {
                        "id": next_id,
                        "period": period,
                        "code": item["code"],
                        "name": item["name"],
                        "status": status,
                        "price": int(item["price"]),
                        "treasury": int(item["treasury"]),
                        "cash": int(item["cash"]),
                    }
                )
                click_state[key] = current_clicks
                if session_user:
                    add_action_log(
                        session_user,
                        "add_license",
                        {
                            "message": f"Добавлена лицензия {item['code']} ({status})",
                            "period": period,
                            "code": item["code"],
                            "name": item["name"],
                            "status": status,
                            "price": int(item["price"]),
                            "treasury": int(item["treasury"]),
                            "cash": int(item["cash"]),
                        },
                    )
                return records, click_state
            click_state[key] = current_clicks
        return no_update, click_state
    if trigger == "delete-row-btn" and selected_rows:
        selected_set = set(selected_rows)
        removed = [record for index, record in enumerate(records) if index in selected_set]
        records = [record for index, record in enumerate(records) if index not in selected_set]
        if session_user and removed:
            add_action_log(
                session_user,
                "delete_license",
                {
                    "message": f"Удалено лицензий: {len(removed)}",
                    "items": removed,
                },
            )
        return records, click_state
    return no_update, click_state


@app.callback(
    Output("tariffs-store", "data", allow_duplicate=True),
    Output("user-theme", "data", allow_duplicate=True),
    Output("settings-message", "children"),
    Output("main-tabs", "value", allow_duplicate=True),
    Input("save-settings-btn", "n_clicks"),
    State("session-user", "data"),
    State("user-theme", "data"),
    State("day-tariffs-table", "data"),
    State("night-tariffs-table", "data"),
    prevent_initial_call=True,
)
def save_settings(_, session_user: str | None, theme: str, day_rows: list[dict], night_rows: list[dict]):
    try:
        tariffs = merge_tariff_tables(day_rows, night_rows)
        for period in tariffs:
            for item in tariffs[period]:
                if item["price"] < 0 or item["treasury"] < 0 or item["cash"] < 0:
                    return no_update, no_update, "Значения не могут быть отрицательными.", "settings"
    except Exception:
        return no_update, no_update, "Проверь значения в тарифах: нужны целые числа.", "settings"
    if session_user:
        add_action_log(session_user, "save_settings", {"message": "Сохранены тарифы и тема", "theme": theme})
    return tariffs, theme, "Настройки сохранены.", "work"


@app.callback(
    Output("day-tariffs-table", "style_data"),
    Output("night-tariffs-table", "style_data"),
    Output("records-table", "style_data"),
    Output("history-table", "style_data"),
    Output("journal-table", "style_data"),
    Input("user-theme", "data"),
)
def table_styles(theme: str | None):
    palette = THEMES[theme or "Светлая"]
    style = {"backgroundColor": "#ffffff" if palette["page"] == "theme-light" else "#1b2129", "color": "#26313d" if palette["page"] == "theme-light" else "#eff3f8"}
    return (style, style, style, style, style)


@app.callback(
    Output("auth-message", "className"),
    Output("settings-message", "className"),
    Input("auth-message", "children"),
    Input("settings-message", "children"),
)
def message_classes(_, __):
    return "auth-message visible", "auth-message visible"


@app.callback(
    Output("hero-user", "children", allow_duplicate=True),
    Input("session-user", "data"),
    Input("tariffs-store", "data"),
    Input("records-store", "data"),
    Input("user-theme", "data"),
    prevent_initial_call=True,
)
def persist_state(username: str | None, tariffs: dict | None, records: list[dict] | None, theme: str | None):
    if username and tariffs is not None and records is not None and theme:
        save_user_state(username, theme, tariffs, [normalize_record(record) for record in records])
        return f"Пользователь: {username}"
    return no_update


@app.callback(
    Output("history-table", "data"),
    Output("journal-table", "data"),
    Input("session-user", "data"),
    Input("user-role", "data"),
    Input("records-store", "data"),
    Input("tariffs-store", "data"),
    Input("user-theme", "data"),
    Input("history-start-date", "value"),
    Input("history-end-date", "value"),
)
def render_history_and_journal(username: str | None, role: str | None, records, tariffs, theme, start_date: str | None, end_date: str | None):
    if not username or role != "admin":
        return [], []
    history = fetch_license_history(username)
    if start_date:
        history = [row for row in history if row["Дата"] >= start_date]
    if end_date:
        history = [row for row in history if row["Дата"] <= end_date]
    journal = [{key: row[key] for key in ("Пользователь", "Время", "Действие", "Описание")} for row in fetch_action_logs(username)]
    return history, journal


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8050"))
    app.run(host="0.0.0.0", port=port, debug=False)
