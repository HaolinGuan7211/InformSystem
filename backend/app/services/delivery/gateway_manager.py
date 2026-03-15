from __future__ import annotations

from backend.app.services.delivery.gateways.base import (
    DeliveryChannelGateway,
    UnsupportedDeliveryChannelError,
)
from backend.app.services.delivery.gateways.mock_app_push import MockAppPushGateway
from backend.app.services.delivery.gateways.mock_email import MockEmailGateway


class GatewayManager:
    def __init__(self, gateways: list[DeliveryChannelGateway] | None = None) -> None:
        configured = gateways or [MockAppPushGateway(), MockEmailGateway()]
        self._gateways = {gateway.channel: gateway for gateway in configured}

    def register(self, gateway: DeliveryChannelGateway) -> None:
        self._gateways[gateway.channel] = gateway

    def get_gateway(self, channel: str) -> DeliveryChannelGateway:
        gateway = self._gateways.get(channel)
        if gateway is None:
            raise UnsupportedDeliveryChannelError(channel)
        return gateway
