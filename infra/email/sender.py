from jinja2 import Environment, FileSystemLoader
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from core.config import settings



class BaseEmailSender:
    def __init__(self):
        print(f"------------- settings {settings}")
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
        print(f"\n\n ++++++++++++++ to_email {to_email} ++++++++++++++ \n\n")
        msg.attach(MIMEText(html, 'html'))
        return msg

    def _send_raw(self, msg: MIMEMultipart) ->bool:
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_password)
                log.info(f"\n\n user {settings.smtp_user} password {settings.smtp_password} \n\n")
                print(f"\n\n ------------- msg {msg} ------------ \n\n")
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False

class OTPSender(BaseEmailSender):
    def send(self, to_email: str, code: str) -> bool:
        html = self._render('otp.html', subject=settings.otp_subject, code=code)
        msg = self._create_message(settings.otp_subject, html, to_email)
        return self._send_raw(msg)

class ManagerSender(BaseEmailSender):
    def send(self, to_email: str, password: str) -> bool:
        html = self._render('manager.html', subject=settings.manager_subject, password=password)
        msg = self._create_message(settings.manager_subject, html, to_email)
        return self._send_raw(msg)
