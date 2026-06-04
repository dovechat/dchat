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
        try:
            import socket, ssl
            # Обходим сломанный /etc/resolv.conf внутри пода
            ip = socket.getaddrinfo(settings.smtp_host, settings.smtp_port, socket.AF_INET)[0][4][0]
            log.info(f"Resolved IP: {ip}")

            with smtplib.SMTP(ip, settings.smtp_port, timeout=5) as server:
                server.ehlo(settings.smtp_host)

                # ХАК ДЛЯ ПРОВЕРКИ СЕРТИФИКАТА:
                # Перед стартом TLS временно подменяем имя хоста в объекте smtplib на реальный домен.
                # Именно это поле библиотека использует внутри starttls() для проверки сертификата.
                server.helo_resp = settings.smtp_host
                server.local_hostname = settings.smtp_host

                # Для некоторых версий Python также требуется обновить внутреннее имя хоста
                if hasattr(server, 'host'):
                    server.host = settings.smtp_host

                context = ssl.create_default_context()
                server.starttls(context=context)

                server.ehlo(settings.smtp_host)
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            log.error(f"Email error: {e}")
            return False


class OTPSender(BaseEmailSender):
    def send(self, to_email: str, code: str) -> bool:
        log.info((settings.smtp_host, settings.smtp_port))
        import socket
        log.info(socket.getaddrinfo(settings.smtp_host, settings.smtp_port))

        html = self._render('otp.html', subject=settings.otp_subject, code=code)
        log.info(f"\n\n ------------- render ------------ \n\n")
        msg = self._create_message(settings.otp_subject, html, to_email)
        log.info(f"\n\n ------------- _create_message ------------ \n\n")
        res = self._send_raw(msg)
        log.info(f"\n\n -------------  _send_raw res {res} ----------- \n\n")
        return res

class ManagerSender(BaseEmailSender):
    def send(self, to_email: str, password: str) -> bool:
        html = self._render('manager.html', subject=settings.manager_subject, password=password)
        msg = self._create_message(settings.manager_subject, html, to_email)
        return self._send_raw(msg)
