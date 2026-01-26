import pytest
from core.config import settings
from infra.email.sender import BaseEmailSender, OTPSender

@pytest.fixture(scope="session")
def real_sender():
    """Real sender with your .env credentials"""
    return OTPSender()

# uncomment when stage mail server or account will be set up
'''
def test_otp_sender_real(real_sender):
    """Send real OTP email"""
    result = real_sender.send(settings.smtp_user, "123456")
    assert result is True
'''