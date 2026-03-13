from __future__ import annotations

from backend.app.shared.models import DecisionResult, DeliveryTask, SourceEvent


class MessageRenderer:
    async def render(
        self,
        decision_result: DecisionResult,
        event: SourceEvent,
        channel: str,
    ) -> dict[str, str]:
        title = event.title or self._build_title(decision_result)
        body_lines = [decision_result.reason_summary]

        preview = self._trim_text(event.content_text, limit=140)
        if preview:
            body_lines.append(f"内容摘要：{preview}")
        if decision_result.deadline_at:
            body_lines.append(f"截止时间：{decision_result.deadline_at}")
        if event.url:
            body_lines.append(f"查看链接：{event.url}")
        if channel == "email":
            body_lines.append(f"优先级：{decision_result.priority_level}")

        return {"title": title, "body": "\n".join(body_lines)}

    async def render_digest(
        self,
        tasks: list[DeliveryTask],
        window_key: str,
        channel: str,
    ) -> dict[str, str]:
        title = f"校园通知汇总（{len(tasks)} 条）"
        lines = [f"汇总窗口：{window_key}", ""]

        for index, task in enumerate(tasks[:10], start=1):
            summary = task.body.splitlines()[0] if task.body else task.title
            lines.append(f"{index}. {task.title}")
            lines.append(summary)

        if len(tasks) > 10:
            lines.append(f"... 另有 {len(tasks) - 10} 条未展开")

        if channel == "email":
            lines.append("")
            lines.append("请尽快查看并处理需要操作的事项。")

        return {"title": title, "body": "\n".join(lines).strip()}

    def _build_title(self, decision_result: DecisionResult) -> str:
        priority_labels = {
            "critical": "关键提醒",
            "high": "高优先级提醒",
            "medium": "通知汇总提醒",
            "low": "校园通知",
        }
        return priority_labels.get(decision_result.priority_level, "校园通知")

    def _trim_text(self, value: str | None, limit: int = 140) -> str:
        if not value:
            return ""
        normalized = " ".join(value.split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 1]}…"
