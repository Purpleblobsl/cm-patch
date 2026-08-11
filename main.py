from src.config import config, config_str, config_assert
from src.jwt import issue_vc, get_oid4vp_access_token
from src.utils import logger_init_root, logger_get
from src.request import Request
from src.http import create_server

log = logger_get(__name__)

def main():
    config_assert()
    logger_init_root(config.APP_MODE)

    log.info("Config loaded")
    log.debug("Loaded config:\n%s", config_str(config))

    # log.info("issuing ")
    # for id, format, scope in config.vc_configs:
    #     vc = issue_vc(id, format)
    #     log.info("Retrieved VC '%s': %s", id, vc)
    #
    #     bearer = get_oid4vp_access_token(
    #         target_url="https://contract-management.central-marketplace.user4.ariadnedata.eu",
    #         did=config.HOLDER_DID,
    #         verifiable_credential=vc,
    #         key_path=config.HOLDER_KEY_PATH,
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
    server = create_server(config.APP_NAME)

    server.run(
        host="0.0.0.0",
        port=config.APP_PORT,
        debug=config.APP_MODE.is_debug,
    )

if __name__ == "__main__":
    main()
