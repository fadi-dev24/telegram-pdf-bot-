from dependency_injector.wiring import Provide, inject
from pdf_bot.containers import Application
import pdf_bot.logging as pdf_bot_logging
from telegram.ext import Updater
import pdf_bot.dispatcher as dp
from dotenv import load_dotenv
from loguru import logger
import sentry_sdk
import os
################################################
load_dotenv()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
SENTRY_DSN = os.environ.get("SENTRY_DSN")
APP_URL = os.environ.get("APP_URL")
PORT = int(os.environ.get("PORT", "8443"))
TIMEOUT = 45
@inject
def main(
    updater: Updater = Provide[Application.core.updater], 
):
    pdf_bot_logging.setup_logging()
    if SENTRY_DSN is not None:
        sentry_sdk.init(SENTRY_DSN, traces_sample_rate=1.0)
    dispatcher = updater.dispatcher 
    dp.setup_dispatcher(dispatcher)
    if APP_URL is not None:
        updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{APP_URL}/{TELEGRAM_TOKEN}",
        )
        logger.info("Started webhook")
    else:
        updater.start_polling()
        logger.info("Started polling")
    updater.idle()
################################################
if __name__ == "__main__":
    application = Application()
    application.core.init_resources()
    application.wire(modules=[__name__, "codes.dispatcher"])

main()
