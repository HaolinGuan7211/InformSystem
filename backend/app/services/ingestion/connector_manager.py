from __future__ import annotations

from backend.app.services.ingestion.connectors import (
    Connector,
    ManualConnector,
    SzuBoardConnector,
    WecomWebhookConnector,
    WebsiteHtmlConnector,
)
from backend.app.services.ingestion.normalizer import Normalizer


class ConnectorManager:
    def __init__(self, normalizer: Normalizer) -> None:
        self._connectors: dict[str, Connector] = {}
        self.register("wecom_webhook", WecomWebhookConnector(normalizer))
        self.register("website_html", WebsiteHtmlConnector(normalizer))
        self.register("szu_board_authenticated", SzuBoardConnector(normalizer))
        self.register("manual_input", ManualConnector(normalizer))

    def register(self, connector_type: str, connector: Connector) -> None:
        self._connectors[connector_type] = connector

    def get_connector(self, connector_type: str) -> Connector:
        try:
            return self._connectors[connector_type]
        except KeyError as exc:
            raise KeyError(f"Unsupported connector_type: {connector_type}") from exc
