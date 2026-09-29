from bean.config import dump_str

from src.config import Config, Mode
from src.utils import logger_init_root, logger_get
from src.http import create_server
from src.dispatcher import dispatch_tmf_subscription

log = logger_get(__name__)

def main():
    logger_init_root(Config.APP_LOG_LEVEL)

    log.info("Config loaded")
    log.debug("Loaded Config:\n%s", dump_str(Config))

    if not Config.APP_IS_CLIENT:
        dispatch_tmf_subscription()

    log.info("Creating http server")
    create_server(Config.APP_NAME).run(
        host="0.0.0.0",
        port=Config.APP_PORT,
        debug=Config.APP_MODE == Mode.DEV,
    )

if __name__ == "__main__":
    main()
