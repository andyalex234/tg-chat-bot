import html
import logging
from dataclasses import dataclass
from http import HTTPStatus
import uvicorn

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackContext,
    CommandHandler,
    ContextTypes,
    ExtBot,
    TypeHandler,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Define configuration constants

# URL = "https://57f0-196-188-55-136.ngrok-free.app"
URL = "https://f1ed-196-188-55-136.ngrok-free.app"
ADMIN_CHAT_ID = 386991428
PORT = 8000


@dataclass
class WebhookUpdate:
    """Simple dataclass to wrap a custom update type"""

    user_id: int
    payload: str


class CustomContext(CallbackContext[ExtBot, dict, dict, dict]):
    """
    Custom CallbackContext class that makes `user_data` available for updates of type
    `WebhookUpdate`.
    """

    @classmethod
    def from_update(
        cls,
        update: object,
        application: "Application",
    ) -> "CustomContext":
        if isinstance(update, WebhookUpdate):
            return cls(application=application, user_id=update.user_id)
        return super().from_update(update, application)


class StartResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    message: str


class PayloadRequest(BaseModel):
    user_id: int
    payload: str


app = FastAPI()


@app.on_event("startup")
async def startup_event():
    # Initialize the application
    context_types = ContextTypes(context=CustomContext)
    # Here we set updater to None because we want our custom webhook server to handle the updates
    # and hence we don't need an Updater instance
    application = (
        Application.builder().token(TOKEN).updater(None).context_types(context_types).build()
    )

    # register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(TypeHandler(type=WebhookUpdate, callback=webhook_update))

    # Pass webhook settings to telegram
    await application.bot.set_webhook(url=f"{URL}/telegram", allowed_updates=Update.ALL_TYPES)

    app.state.application = application


@app.post("/telegram")
async def telegram(request: Request) -> HealthResponse:
    """Handle incoming Telegram updates by putting them into the `update_queue`"""
    application = request.app.state.application
    update_data = await request.json()
    update = Update.de_json(data=update_data, bot=application.bot)

    if update.message and update.message.text.startswith('/start'):
        await start(update, application)
    else:
        await application.update_queue.put(update)

    return HealthResponse(message="The bot is still running fine :)")

@app.route("/submitpayload", methods=["GET", "POST"])
async def custom_updates(request: Request) -> Response:
    """
    Handle incoming webhook updates by also putting them into the `update_queue` if
    the required parameters were passed correctly.
    """
    print("This is request parmas", request.query_params)
    try:
        query_params = request.query_params
        payload_request = PayloadRequest(user_id=int(query_params["user_id"]), payload=query_params["payload"] )
    except ValueError:
        return Response(status_code=HTTPStatus.BAD_REQUEST, content="The `user_id` must be a string!")

    application = request.app.state.application
    await application.update_queue.put(WebhookUpdate(user_id=payload_request.user_id, payload=payload_request.payload))
    return Response(status_code=HTTPStatus.OK)


@app.get("/healthcheck", response_model=HealthResponse)
async def health():
    """For the health endpoint, reply with a simple plain text message."""
    return HealthResponse(message="The bot is still running fine :)")


async def start(update: Update, context: CustomContext) -> None:
    """Display a message with instructions on how to use this bot."""
    payload_url = html.escape(f"{URL}/submitpayload?user_id=<your user id>&payload=<payload>")
    text = (
        f"To check if the bot is still running, call <code>{URL}/healthcheck</code>.\n\n"
        f"To post a custom update, call <code>{payload_url}</code>."
    )
    await update.message.reply_html(text=text)


async def webhook_update(update: WebhookUpdate, context: CustomContext) -> None:
    """Handle custom updates."""
    chat_member = await context.bot.get_chat_member(chat_id=update.user_id, user_id=update.user_id)
    payloads = context.user_data.setdefault("payloads", [])
    payloads.append(update.payload)
    combined_payloads = "</code>\n• <code>".join(payloads)
    text = (
        f"The user {chat_member.user.mention_html()} has sent a new payload. "
        f"So far they have sent the following payloads: \n\n• <code>{combined_payloads}</code>"
    )
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, parse_mode=ParseMode.HTML)


# async def main() -> None:
#     await startup_event()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)
