import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mailer")


class Settings(BaseSettings):
    yandex_login: str
    yandex_password: str
    recipient_email: str
    # comma-separated origins, e.g. "http://localhost,https://shlenskov.dev"
    allowed_origins: str = "null,http://localhost"

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()
origins = [o.strip() for o in settings.allowed_origins.split(",")]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class ContactForm(BaseModel):
    name: str
    contact: str
    service: str = ""
    message: str


@app.post("/send")
async def send(form: ContactForm, request: Request):
    origin = request.headers.get("origin", "—")
    log.info("Incoming request  origin=%s  name=%r  contact=%r  service=%r",
             origin, form.name, form.contact, form.service)

    subject = f"Новая заявка от {form.name}"
    body = (
        f"<b>Имя:</b> {form.name}<br>"
        f"<b>Контакт:</b> {form.contact}<br>"
        f"<b>Услуга:</b> {form.service or '—'}<br><br>"
        f"<b>Сообщение:</b><br>{form.message}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.yandex_login
    msg["To"] = settings.recipient_email
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        log.info("Connecting to smtp.yandex.ru:465 as %s", settings.yandex_login)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.yandex.ru", 465, context=ctx) as smtp:
            smtp.login(settings.yandex_login, settings.yandex_password)
            smtp.sendmail(settings.yandex_login, settings.recipient_email, msg.as_string())
        log.info("Email sent  to=%s  subject=%r", settings.recipient_email, subject)
    except Exception as e:
        log.error("SMTP error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True}