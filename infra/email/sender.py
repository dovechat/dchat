from jinja2 import Environment, FileSystemLoader
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from core.config import settings

import socket

# FORCE IPv4 (FIX)
_orig_getaddrinfo = socket.getaddrinfo
def _ipv4_only(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    return [x for x in res if x[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_only


import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


class BaseEmailSender:
    def __init__(self):
        log.info(f"------------- settings {settings}")
        self.conf = settings
        template_dir = os.path.dirname(__file__)
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))

    def _render(self, template_name: str, **context) -> str:
        return self.jinja_env.get_template(template_name).render(**context)

    def _create_message(self, subject: str, html: str, to_email: str = "donrodrigess@gmail.com",) -> MIMEMultipart:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = settings.smtp_from
        msg['To'] = to_email
        log.info(f"\n\n user {settings.smtp_user} password {settings.smtp_password} \n\n")
        log.info(f"\n\n ++++++++++++++ to_email {to_email} ++++++++++++++ \n\n")
        msg.attach(MIMEText(html, 'html'))
        return msg

    def _send_raw(self, msg: MIMEMultipart) -> bool:
        log.info(f"\n\n -------------  _send_raw start ----------- \n\n")
        try:
            log.info(f"\n\n -------------  _send_raw try ----------- \n\n")
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                log.info(f"\n\n -------------  _send_raw with ----------- \n\n")
                server.starttls()
                log.info(f"\n\n -------------  _send_raw starttls ----------- \n\n")
                server.ehlo()
                log.info(f"\n\n -------------  _send_raw ehlo ----------- \n\n")
                server.login(settings.smtp_user, settings.smtp_password)
                log.info(f"\n\n -------------  _send_raw login ----------- \n\n")
                server.send_message(msg)
                log.info(f"\n\n -------------  _send_raw send_message ----------- \n\n")
            return True
        except Exception as e:
            log.error(f"Email error: {e}")
            return False