from bean.config import dump_str

from src.config import Config
from src.jwt import issue_vc, get_oid4vp_access_token
from src.utils import logger_init_root, logger_get
from src.request import Request
from src.http import create_server

log = logger_get(__name__)

def main():
    logger_init_root(Config.APP_MODE)

    log.info("Config loaded")
    log.debug("Loaded Config:\n%s", dump_str(Config))

    # log.info("issuing ")
    # for id, format, scope in Config.vc_configs:
    #     vc = issue_vc(id, format)
    #     log.info("Retrieved VC '%s': %s", id, vc)
    #
    #     bearer = get_oid4vp_access_token(
    #         target_url="https://contract-management.central-marketplace.user4.ariadnedata.eu",
    #         did=Config.HOLDER_DID,
    #         verifiable_credential=vc,
    #         key_path=Config.HOLDER_KEY_PATH,
    #         scope=scope,
    #     )
    #
    #     log.info("Retrieved Bearer '%s' (%s): %s", id, scope, bearer)
    #
    #     Request(
    #         "GET",
    #         "https://contract-management.central-marketplace.user4.ariadnedata.eu/order/start",
    #         headers={
    #             "Authorization": f"Bearer {bearer}"
    #         }
    #     ).fetch().raise_for_status()

    log.info("Creating http server")
    server = create_server(Config.APP_NAME)

    server.run(
        host="0.0.0.0",
        port=Config.APP_PORT,
        debug=Config.APP_MODE.is_debug,
    )

if __name__ == "__main__":
    main()
