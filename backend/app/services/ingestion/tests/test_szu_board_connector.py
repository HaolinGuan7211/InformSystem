from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.ingestion.connectors.szu_board import SzuBoardParser

PROJECT_ROOT = Path(__file__).resolve().parents[5]


def _read_fixture(name: str) -> str:
    path = PROJECT_ROOT / "mocks" / "ingestion" / "raw_inputs" / name
    return path.read_text(encoding="utf-8")


def test_szu_board_parser_extracts_detail_links(container) -> None:
    parser = SzuBoardParser(container.connector_manager.get_connector("szu_board_authenticated")._normalizer)
    html = _read_fixture("szu_board_home.html")

    items = parser.parse_list_page(
        html,
        page_url="https://www1.szu.edu.cn/board/",
        limit=5,
    )

    assert len(items) == 2
    assert items[0]["raw_identifier"] == "569039"
    assert items[0]["detail_url"] == "https://www1.szu.edu.cn/board/view.asp?id=569039"
    assert items[0]["list_title"] == "马院招聘学生助理"


def test_szu_board_parser_extracts_detail_fields(container) -> None:
    parser = SzuBoardParser(container.connector_manager.get_connector("szu_board_authenticated")._normalizer)
    html = _read_fixture("szu_board_detail_student_assistant.html")

    item = parser.parse_detail_page(
        html,
        detail_url="https://www1.szu.edu.cn/board/view.asp?id=569039",
        list_title="马院招聘学生助理",
        raw_identifier="569039",
    )

    assert item["title"] == "马院招聘学生助理"
    assert item["published_at"] == "2026/3/13 17:13:00"
    assert item["department"] == "马克思主义学院"
    assert item["author"] == "马院教务室"
    assert "招聘学生助理" in item["content_text"]
    assert item["attachments"] == [
        {
            "name": "学生助理岗位说明.docx",
            "url": "https://www1.szu.edu.cn/board/files/assistant_job_desc.docx",
        }
    ]


@pytest.mark.asyncio
async def test_szu_board_normalize_to_source_event(container) -> None:
    source_config = await container.source_registry.get_source_by_id("szu_campus_board")
    connector = container.connector_manager.get_connector("szu_board_authenticated")
    parser = SzuBoardParser(connector._normalizer)
    html = _read_fixture("szu_board_detail_student_assistant.html")

    raw_item = parser.parse_detail_page(
        html,
        detail_url="https://www1.szu.edu.cn/board/view.asp?id=569039",
        list_title="马院招聘学生助理",
        raw_identifier="569039",
    )
    events = await connector.normalize(raw_item, source_config)

    assert len(events) == 1
    event = events[0]
    assert event.source_id == "szu_campus_board"
    assert event.title == "马院招聘学生助理"
    assert event.author == "马院教务室"
    assert event.url == "https://www1.szu.edu.cn/board/view.asp?id=569039"
    assert event.metadata["department"] == "马克思主义学院"
    assert event.metadata["authority_level"] == "high"
    assert event.published_at == "2026-03-13T17:13:00+08:00"
