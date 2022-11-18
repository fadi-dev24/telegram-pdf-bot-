from telegram import ParseMode, Update
from telegram.ext import CallbackContext, ConversationHandler

from pdf_bot.analytics import TaskType
from pdf_bot.consts import PDF_INFO
from pdf_bot.language import set_lang
from pdf_bot.pdf import PdfService
from pdf_bot.telegram_internal import TelegramService, TelegramServiceError
from pdf_bot.utils import send_result_file


class FileService:
    def __init__(
        self, pdf_service: PdfService, telegram_service: TelegramService
    ) -> None:
        self.pdf_service = pdf_service
        self.telegram_service = telegram_service

    def compress_pdf(self, update: Update, context: CallbackContext):
        _ = set_lang(update, context)
        message = update.effective_message

        try:
            file_id, _file_name = self.telegram_service.get_user_data(context, PDF_INFO)
        except TelegramServiceError as e:
            message.reply_text(_(str(e)))
            return ConversationHandler.END

        with self.pdf_service.compress_pdf(file_id) as compress_result:
            message.reply_text(
                _(
                    "File size reduced by {percent}, from {old_size} to {new_size}"
                ).format(
                    percent="<b>{:.0%}</b>".format(compress_result.reduced_percentage),
                    old_size=f"<b>{compress_result.readable_old_size}</b>",
                    new_size=f"<b>{compress_result.readable_new_size}</b>",
                ),
                parse_mode=ParseMode.HTML,
            )
            send_result_file(
                update, context, compress_result.out_path, TaskType.compress_pdf
            )
        return ConversationHandler.END
