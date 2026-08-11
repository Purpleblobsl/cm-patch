from http import HTTPStatus
import base64, logging

from .config import Mode

def logger_get(name: str) -> logging.Logger:
    return logging.getLogger(name)

def logger_init_root(mode: Mode):
    class ColorFormatter(logging.Formatter):
        RESET = "\033[0m"

        COLORS = {
            logging.DEBUG: "\033[7;36m",      # Cyan
            logging.INFO: "\033[7;32m",       # Green
            logging.WARNING: "\033[7;33m",    # Yellow
            logging.ERROR: "\033[7;31m",      # Red
            logging.CRITICAL: "\033[1;7;31m", # Bold Red
        }

        def format(self, record: logging.LogRecord) -> str:
            color = self.COLORS.get(record.levelno, self.RESET)
            level = f"{color} {record.levelname} {self.RESET}"
            record.levelname = level
            return super().format(record)


    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    ))

    logging.basicConfig(
        level=logging.DEBUG if mode.is_debug else logging.INFO,
        handlers=[handler],
        force=True,
    )

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def http_code_to_string(code: int) -> str:
    return HTTPStatus(code).phrase
