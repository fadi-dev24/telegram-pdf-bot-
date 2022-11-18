import gettext

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler

from pdf_bot.analytics import TaskType
from pdf_bot.consts import BACK, PDF_INFO
from pdf_bot.file_task import FileTaskService
from pdf_bot.language_new import LanguageService
from pdf_bot.pdf import PdfService
from pdf_bot.telegram_internal import TelegramService, TelegramServiceError

_ = gettext.gettext


class CropService:
    WAIT_CROP_TYPE = "wait_crop_type"
    WAIT_CROP_PERCENTAGE = "wait_crop_percentage"
    WAIT_CROP_MARGIN_SIZE = "wait_crop_margin_size"

    _BY_PERCENTAGE = _("By percentage")
    _BY_MARGIN_SIZE = _("By margin size")
    _MIN_PERCENTAGE = 0
    _MAX_PERCENTAGE = 100

    def __init__(
        self,
        file_task_service: FileTaskService,
        pdf_service: PdfService,
        telegram_service: TelegramService,
        language_service: LanguageService,
    ) -> None:
        self.file_task_service = file_task_service
        self.pdf_service = pdf_service
        self.telegram_service = telegram_service
        self.language_service = language_service

    def ask_crop_type(self, update: Update, context: CallbackContext) -> str:
        _ = self.language_service.set_app_language(update, context)
        keyboard = [
            [_(self._BY_PERCENTAGE), _(self._BY_MARGIN_SIZE)],
            [_(BACK)],
        ]
        reply_markup = ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=True, resize_keyboard=True
        )
        update.effective_message.reply_text(
            _("Select the crop type that you'll like to perform"),
            reply_markup=reply_markup,
        )

        return self.WAIT_CROP_TYPE

    def check_crop_type(self, update: Update, context: CallbackContext) -> str:
        _ = self.language_service.set_app_language(update, context)
        text = update.effective_message.text

        if text in [_(self._BY_PERCENTAGE), _(self._BY_MARGIN_SIZE)]:
            return self._ask_crop_value(update, context)
        if text == _(BACK):
            return self.file_task_service.ask_pdf_task(update, context)
        return self.WAIT_CROP_TYPE

    def crop_pdf_by_percentage(
        self, update: Update, context: CallbackContext
    ) -> str | int:
        _ = self.language_service.set_app_language(update, context)
        message = update.effective_message

        if message.text == _(BACK):
            return self.ask_crop_type(update, context)

        try:
            percent = float(message.text)
        except ValueError:
            message.reply_text(
                _(
                    "The number {number} is not between "
                    "{min_percent} and {max_percent}, please try again"
                ).format(
                    number=message.text,
                    min_percent=self._MIN_PERCENTAGE,
                    max_percent=self._MAX_PERCENTAGE,
                ),
            )
            return self.WAIT_CROP_PERCENTAGE

        return self._crop_pdf(update, context, percentage=percent)

    def crop_pdf_by_margin_size(
        self, update: Update, context: CallbackContext
    ) -> str | int:
        _ = self.language_service.set_app_language(update, context)
        message = update.effective_message

        if message.text == _(BACK):
            return self.ask_crop_type(update, context)

        try:
            margin_size = float(message.text)
        except ValueError:
            message.reply_text(
                _("The number {number} is invalid, please try again").format(
                    number=message.text
                )
            )
            return self.WAIT_CROP_MARGIN_SIZE

        return self._crop_pdf(update, context, margin_size=margin_size)

    def _ask_crop_value(self, update: Update, context: CallbackContext) -> str:
        _ = self.language_service.set_app_language(update, context)
        message = update.effective_message
        reply_markup = ReplyKeyboardMarkup(
            [[_(BACK)]], one_time_keyboard=True, resize_keyboard=True
        )

        if message.text == _(self._BY_PERCENTAGE):
            message.reply_text(
                "{desc_1}\n\n{desc_2}".format(
                    desc_1=_(
                        "Send me a number between {min_percent} and {max_percent}"
                    ).format(
                        min_percent=self._MIN_PERCENTAGE,
                        max_percent=self._MAX_PERCENTAGE,
                    ),
                    desc_2=_(
                        "This is the percentage of margin space to retain "
                        "between the content in your PDF file and the page"
                    ),
                ),
                reply_markup=reply_markup,
            )
            return self.WAIT_CROP_PERCENTAGE

        message.reply_text(
            "{desc_1}\n\n{desc_2}".format(
                desc_1=_("Send me a number that you'll like to adjust the margin size"),
                desc_2=_(
                    "Positive numbers will decrease the margin size "
                    "and negative numbers will increase it"
                ),
            ),
            reply_markup=reply_markup,
        )
        return self.WAIT_CROP_MARGIN_SIZE

    def _crop_pdf(
        self,
        update: Update,
        context: CallbackContext,
        percentage: float | None = None,
        margin_size: float | None = None,
    ) -> int:
        _ = self.language_service.set_app_language(update, context)
        message = update.effective_message

        try:
            file_id, _file_name = self.telegram_service.get_user_data(context, PDF_INFO)
        except TelegramServiceError as e:
            message.reply_text(_(str(e)))
            return ConversationHandler.END

        with self.pdf_service.crop_pdf(
            file_id, percentage=percentage, margin_size=margin_size
        ) as out_path:
            self.telegram_service.reply_with_file(
                update, context, out_path, TaskType.crop_pdf
            )
        return ConversationHandler.END
