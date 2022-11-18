import gettext
import os
from contextlib import contextmanager
from typing import Any, Generator, List

from telegram import (
    Bot,
    ChatAction,
    Document,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import MAX_FILESIZE_DOWNLOAD, MAX_FILESIZE_UPLOAD
from telegram.ext import CallbackContext, ConversationHandler, Updater

from pdf_bot.analytics import EventAction, TaskType, send_event
from pdf_bot.consts import BACK, CANCEL, CHANNEL_NAME, PAYMENT
from pdf_bot.io import IOService
from pdf_bot.language_new import LanguageService
from pdf_bot.models import FileData
from pdf_bot.telegram_internal.exceptions import (
    TelegramFileMimeTypeError,
    TelegramFileTooLargeError,
    TelegramImageNotFoundError,
    TelegramUserDataKeyError,
)

_ = gettext.gettext


class TelegramService:
    IMAGE_MIME_TYPE_PREFIX = "image"
    PDF_MIME_TYPE_SUFFIX = "pdf"
    PNG_SUFFIX = ".png"

    def __init__(
        self,
        io_service: IOService,
        language_service: LanguageService,
        updater: Updater | None = None,
        bot: Bot | None = None,
    ) -> None:
        self.io_service = io_service
        self.language_service = language_service
        self.bot = bot or updater.bot  # type: ignore

    @staticmethod
    def check_file_size(file: Document | PhotoSize) -> None:
        if file.file_size > MAX_FILESIZE_DOWNLOAD:
            raise TelegramFileTooLargeError(
                _(
                    "Your file is too large for me to download and process, "
                    "please try again with a differnt file\n\n"
                    "Note that this limit is enforced by Telegram and there's "
                    "nothing I can do unless Telegram changes it"
                )
            )

    @staticmethod
    def check_file_upload_size(path: str) -> None:
        if os.path.getsize(path) > MAX_FILESIZE_UPLOAD:
            raise TelegramFileTooLargeError(
                _(
                    "The file is too large for me to send to you\n\n"
                    "Note that this limit is enforced by Telegram and there's "
                    "nothing I can do unless Telegram changes it"
                )
            )

    @staticmethod
    def get_user_data(context: CallbackContext, key: str) -> Any:
        """Get and pop value from user data by the provided key

        Args:
            context (CallbackContext): the Telegram callback context
            key (str): the key for the value in user data

        Raises:
            TelegramUserDataKeyError: if the key does not exist in user data

        Returns:
            Any: the value for the key
        """
        data = context.user_data.pop(key, None)
        if data is None:
            raise TelegramUserDataKeyError(_("Something went wrong, please try again"))
        return data

    def check_image(self, message: Message) -> Document | PhotoSize:
        img_file: Document | None = message.document
        if img_file is not None and not img_file.mime_type.startswith(
            self.IMAGE_MIME_TYPE_PREFIX
        ):
            raise TelegramFileMimeTypeError(
                _("Your file is not an image, please try again")
            )

        if img_file is None:
            if message.photo:
                img_file = message.photo[-1]
            else:
                raise TelegramImageNotFoundError(_("No image found in your message"))

        self.check_file_size(img_file)
        return img_file

    def check_pdf_document(self, message: Message) -> Document:
        doc = message.document
        if not doc.mime_type.endswith(self.PDF_MIME_TYPE_SUFFIX):
            raise TelegramFileMimeTypeError(
                _("Your file is not a PDF file, please try again")
            )
        self.check_file_size(doc)
        return doc

    @contextmanager
    def download_pdf_file(self, file_id: str) -> Generator[str, None, None]:
        with self.io_service.create_temp_pdf_file() as path:
            file = self.bot.get_file(file_id)
            file.download(custom_path=path)
            yield path

    @contextmanager
    def download_files(self, file_ids: List[str]) -> Generator[List[str], None, None]:
        with self.io_service.create_temp_files(len(file_ids)) as out_paths:
            for i, file_id in enumerate(file_ids):
                file = self.bot.get_file(file_id)
                file.download(custom_path=out_paths[i])
            yield out_paths

    def cancel_conversation(self, update: Update, context: CallbackContext) -> int:
        _ = self.language_service.set_app_language(update, context)
        update.effective_message.reply_text(
            _("Action cancelled"), reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    def get_support_markup(
        self, update: Update, context: CallbackContext
    ) -> InlineKeyboardMarkup:
        _ = self.language_service.set_app_language(update, context)
        keyboard = [
            [
                InlineKeyboardButton(_("Join Channel"), f"https://t.me/{CHANNEL_NAME}"),
                InlineKeyboardButton(_("Support PDF Bot"), callback_data=PAYMENT),
            ]
        ]

        return InlineKeyboardMarkup(keyboard)

    def reply_with_back_markup(
        self, update: Update, context: CallbackContext, text: str
    ) -> None:
        self._reply_with_markup(update, context, text, BACK)

    def reply_with_cancel_markup(
        self, update: Update, context: CallbackContext, text: str
    ) -> None:
        self._reply_with_markup(update, context, text, CANCEL)

    def reply_with_file(
        self,
        update: Update,
        context: CallbackContext,
        file_path: str,
        task: TaskType,
    ) -> None:
        _ = self.language_service.set_app_language(update, context)
        message = update.effective_message
        reply_markup = self.get_support_markup(update, context)

        try:
            self.check_file_upload_size(file_path)
        except TelegramFileTooLargeError as e:
            message.reply_text(_(str(e)))
            return

        if file_path.endswith(self.PNG_SUFFIX):
            message.reply_chat_action(ChatAction.UPLOAD_PHOTO)
            message.reply_photo(
                open(file_path, "rb"),
                caption=_("Here is your result file"),
                reply_markup=reply_markup,
            )
        else:
            message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
            message.reply_document(
                document=open(file_path, "rb"),
                caption=_("Here is your result file"),
                reply_markup=reply_markup,
            )

        send_event(update, context, task, EventAction.complete)

    def send_file_names(
        self, chat_id: str, text: str, file_data_list: List[FileData]
    ) -> None:
        for i, file_data in enumerate(file_data_list):
            text += f"{i + 1}: {file_data.name}\n"
        self.bot.send_message(chat_id, text)

    def _reply_with_markup(
        self,
        update: Update,
        context: CallbackContext,
        text: str,
        markup_text: str,
    ) -> None:
        _ = self.language_service.set_app_language(update, context)
        markup = ReplyKeyboardMarkup(
            [[_(markup_text)]], one_time_keyboard=True, resize_keyboard=True
        )
        update.effective_message.reply_text(_(text), reply_markup=markup)
