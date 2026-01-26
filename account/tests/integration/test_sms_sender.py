import pytest
import respx
import httpx

from core.config import settings
from infra.sms.sender import SMSSender

@respx.mock
def test_send_sms_success():
    """Test successful SMS API response using respx"""
    url = f"https://api.textbee.dev/api/v1/gateway/devices/{settings.device_id}/send-sms/"
    
    
    # Mock the route
    respx.post(url).mock(return_value=httpx.Response(200))

    sender = SMSSender()
    result = sender.send(settings.phone, "Hello via httpx!")
    assert result is True

@respx.mock
def test_send_sms_unauthorized():
    """Test behavior when API returns 401"""
    url = f"https://api.textbee.dev{settings.device_id}/send-sms"

    respx.post(url).mock(return_value=httpx.Response(401))

    sender = SMSSender()
    result = sender.send(+9881984654358, "Test")
    assert result is False

@respx.mock
def test_send_sms_network_error():
    """Test behavior when a network timeout occurs"""
    url = f"https://api.textbee.dev{settings.device_id}/send-sms"

    # Mock a connection error
    respx.post(url).mock(side_effect=httpx.ConnectError("Network is down"))

    sender = SMSSender()
    result = sender.send("+1234567890", "Test")

    assert result is False

'''
@pytest.mark.real
def test_send_sms_real():
    sender = SMSSender()

    # Because there is no @respx.mock decorator, 
    # this call goes to the REAL internet.
    success = sender.send(settings.phone, "Real SMS test from code 123!")

    assert success is True
'''