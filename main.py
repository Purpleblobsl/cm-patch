from bean.config import dump_str

from src.config import Config
from src.utils import logger_init_root, logger_get
from src.http import create_server

log = logger_get(__name__)

def main():
    logger_init_root(Config.APP_MODE)

    log.info("Config loaded")
    log.debug("Loaded Config:\n%s", dump_str(Config))

    log.info("Creating http server")
    create_server(Config.APP_NAME).run(
        host="0.0.0.0",
        port=Config.APP_PORT,
        debug=Config.APP_MODE.is_debug,
    )

if __name__ == "__main__":
    main()
