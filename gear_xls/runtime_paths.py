import hashlib
import json
import os


class ProjectLayoutError(RuntimeError):
    """Raised when the expected project layout is missing."""


REQUIRED_ROOT_DIRS = ("gear_xls", "xlsx_initial", "visualiser")
REQUIRED_ROOT_FILES = (
    "gui.py",
    os.path.join("gear_xls", "server_routes.py"),
)
PROJECT_ROOT_ENV = "SCHEDGEN_PROJECT_ROOT"
SERVER_CONFIG_FILENAME = "server.json"
HOST_ENV = "HOST"
PORT_ENV = "PORT"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
HEALTH_PATH = "/health"
HEALTH_MARKER = "Excel Export Server is running!"


def normalize_project_root(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def resolve_project_root(project_root: str | None = None) -> str:
    candidate = project_root or os.environ.get(PROJECT_ROOT_ENV)
    if candidate:
        return normalize_project_root(candidate)
    this_file = os.path.abspath(__file__)
    package_dir = os.path.dirname(this_file)
    return normalize_project_root(os.path.join(package_dir, ".."))


def validate_project_layout(project_root: str | None = None) -> list[str]:
    root = resolve_project_root(project_root)
    errors: list[str] = []
    for rel_dir in REQUIRED_ROOT_DIRS:
        path = os.path.join(root, rel_dir)
        if not os.path.isdir(path):
            errors.append(f"Missing required directory: {path}")
    for rel_file in REQUIRED_ROOT_FILES:
        path = os.path.join(root, rel_file)
        if not os.path.isfile(path):
            errors.append(f"Missing required file: {path}")
    return errors


def assert_valid_project_layout(project_root: str | None = None) -> str:
    root = resolve_project_root(project_root)
    errors = validate_project_layout(root)
    if errors:
        raise ProjectLayoutError("\n".join(errors))
    return root


def ensure_runtime_dirs(project_root: str | None = None) -> dict[str, str]:
    root = assert_valid_project_layout(project_root)
    logs_dir = get_logs_dir(root)
    runtime_dir = get_runtime_dir(root)
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(runtime_dir, exist_ok=True)
    return {"logs_dir": logs_dir, "runtime_dir": runtime_dir}


def set_project_root_env(project_root: str | None = None) -> str:
    root = resolve_project_root(project_root)
    os.environ[PROJECT_ROOT_ENV] = root
    return root


def get_data_root(project_root: str | None = None) -> str:
    return resolve_project_root(project_root)


def get_project_root_id(project_root: str | None = None) -> str:
    normalized = resolve_project_root(project_root).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def get_project_root(project_root: str | None = None) -> str:
    return resolve_project_root(project_root)


def get_logs_dir(project_root: str | None = None) -> str:
    return os.path.join(get_data_root(project_root), "logs")


def get_runtime_dir(project_root: str | None = None) -> str:
    return os.path.join(get_data_root(project_root), "runtime")


def get_gear_xls_dir(project_root: str | None = None) -> str:
    return os.path.join(get_data_root(project_root), "gear_xls")


def get_config_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "config")


def get_server_config_path(project_root: str | None = None) -> str:
    return os.path.join(get_config_dir(project_root), SERVER_CONFIG_FILENAME)


def _normalize_server_host(value: object) -> str:
    if isinstance(value, str):
        host = value.strip()
        if host:
            return host
    return DEFAULT_HOST


def _normalize_server_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PORT
    if 1 <= port <= 65535:
        return port
    return DEFAULT_PORT


def load_server_config(
    project_root: str | None = None,
    *,
    include_env: bool = False,
) -> dict[str, object]:
    """Load the per-project Flask bind settings.

    Missing or invalid config values intentionally fall back to the current
    public default so existing installations keep working without a config file.
    """
    config: dict[str, object] = {"host": DEFAULT_HOST, "port": DEFAULT_PORT}
    path = get_server_config_path(project_root)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                config["host"] = _normalize_server_host(data.get("host", config["host"]))
                config["port"] = _normalize_server_port(data.get("port", config["port"]))
        except Exception:
            config = {"host": DEFAULT_HOST, "port": DEFAULT_PORT}

    if include_env:
        config["host"] = _normalize_server_host(os.environ.get(HOST_ENV, config["host"]))
        config["port"] = _normalize_server_port(os.environ.get(PORT_ENV, config["port"]))

    return config


def get_server_bind_host(project_root: str | None = None) -> str:
    return str(load_server_config(project_root).get("host") or DEFAULT_HOST)


def get_server_port(project_root: str | None = None) -> int:
    return int(load_server_config(project_root).get("port") or DEFAULT_PORT)


def get_server_url_host(project_root: str | None = None) -> str:
    host = get_server_bind_host(project_root)
    if host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host


def _format_url_host(host: str) -> str:
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        return f"[{host}]"
    return host


def get_server_base_url(project_root: str | None = None) -> str:
    host = _format_url_host(get_server_url_host(project_root))
    return f"http://{host}:{get_server_port(project_root)}"


def get_server_health_url(project_root: str | None = None) -> str:
    return f"{get_server_base_url(project_root)}{HEALTH_PATH}"


def get_schedule_url(project_root: str | None = None) -> str:
    return f"{get_server_base_url(project_root)}/schedule"


def get_schedule_state_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "schedule_state")


def get_backup_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "backups")


def get_restore_status_path(project_root: str | None = None) -> str:
    return os.path.join(get_schedule_state_dir(project_root), "restore_status.json")


def get_html_output_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "html_output")


def get_excel_exports_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "excel_exports")


def get_js_modules_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "js_modules")


def get_static_dir(project_root: str | None = None) -> str:
    return os.path.join(get_gear_xls_dir(project_root), "static")


def get_spiski_dir(project_root: str | None = None) -> str:
    return os.path.join(get_data_root(project_root), "spiski")


def get_users_json_path(project_root: str | None = None) -> str:
    return os.path.join(get_config_dir(project_root), "users.json")


def get_secret_key_path(project_root: str | None = None) -> str:
    return os.path.join(get_config_dir(project_root), "secret_key.txt")


def get_base_schedule_path(project_root: str | None = None) -> str:
    return os.path.join(get_schedule_state_dir(project_root), "base_schedule.json")


def get_individual_lessons_path(project_root: str | None = None) -> str:
    return os.path.join(get_schedule_state_dir(project_root), "individual_lessons.json")


def get_lock_json_path(project_root: str | None = None) -> str:
    return os.path.join(get_schedule_state_dir(project_root), "lock.json")


def get_schedule_html_path(project_root: str | None = None) -> str:
    return os.path.join(get_html_output_dir(project_root), "schedule.html")


def get_server_log_path(project_root: str | None = None) -> str:
    return os.path.join(get_logs_dir(project_root), "flask_server.log")


def get_tray_log_path(project_root: str | None = None) -> str:
    return os.path.join(get_logs_dir(project_root), "server_tray.log")


def get_tray_lock_path(project_root: str | None = None) -> str:
    return os.path.join(get_runtime_dir(project_root), "server_tray.lock")


def get_tray_state_path(project_root: str | None = None) -> str:
    return os.path.join(get_runtime_dir(project_root), "server_tray_state.json")


def get_tray_launcher_path(project_root: str | None = None) -> str:
    return os.path.join(get_data_root(project_root), "server_tray.py")
