from backend.app.services.ingestion.connectors.base import Connector
from backend.app.services.ingestion.connectors.manual_input import ManualConnector
from backend.app.services.ingestion.connectors.szu_board import SzuBoardConnector
from backend.app.services.ingestion.connectors.wecom_webhook import WecomWebhookConnector
from backend.app.services.ingestion.connectors.website_html import WebsiteHtmlConnector

__all__ = [
    "Connector",
    "ManualConnector",
    "SzuBoardConnector",
    "WecomWebhookConnector",
    "WebsiteHtmlConnector",
]
