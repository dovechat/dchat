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
        log.info("-------------  _send_raw start -----------")
        try:
            log.info("-------------  _send_raw try -----------")

            server = smtplib.SMTP(timeout=5)

            # ХАК: Переопределяем создание сокета, жестко форсируя семейство IPv4 (AF_INET)
            def _custom_get_socket(host, port, timeout):
                import socket
                # Находим только IPv4 адреса для ://gmail.com
                infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
                if not infos:
                    raise socket.error("No IPv4 addresses found")

                # Берем первый валидный IPv4 кортеж (sockaddr)
                sockaddr = infos[0][4]

                # Принудительно создаем чистый IPv4 сокет
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if timeout is not None:
                    sock.settimeout(timeout)

                # Подключаемся по вытащенному IPv4-адресу
                sock.connect(sockaddr)
                return sock

            server._get_socket = _custom_get_socket

            log.info("-------------  connecting with forced IPv4 -----------")
            server.connect(settings.smtp_host, settings.smtp_port)

            log.info("-------------  _send_raw with -----------")
            server.ehlo(settings.smtp_host)

            log.info("-------------  _send_raw ehlo1 -----------")
            server.starttls()

            log.info("-------------  _send_raw starttls -----------")
            server.ehlo(settings.smtp_host)

            log.info("-------------  _send_raw ehlo2 -----------")
            server.login(settings.smtp_user, settings.smtp_password)

            log.info("-------------  _send_raw login -----------")
            server.send_message(msg)

            log.info("-------------  _send_raw sent -----------")
            server.close()
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
