DOMAIN = "tapo_s200b_cloud"

RAW_EVENT_NAME = "tapo_s200b_event"
PRESS_EVENT_NAME = "tapo_s200b_pressed"
ROTATE_EVENT_NAME = "tapo_s200b_rotated"

CONF_ACCOUNT = "account"
CONF_SECRET = "secret"
CONF_TOKEN = "token"
CONF_APP_SERVER_URL = "app_server_url"
CONF_TERMINAL_UUID = "terminal_uuid"

SUPPORTED_MODELS = frozenset({"S200B", "S200D"})

POLL_SECONDS = 1.0
FETCH_SIZE = 50
CLICK_WINDOW_SECONDS = 1.4
