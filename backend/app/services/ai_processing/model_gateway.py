from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Callable
from urllib.parse import urljoin

from backend.app.services.ai_processing.models import AIModelConfig, GatewayResponse


class ModelGatewayError(RuntimeError):
    pass


class ModelGateway(ABC):
    @abstractmethod
    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        raise NotImplementedError


class MockModelGateway(ModelGateway):
    def __init__(
        self,
        fixture_responses: dict[str | tuple[str, str] | tuple[str, str, str], dict[str, Any]] | None = None,
        latency_ms: int = 15,
        fail_with: Exception | None = None,
    ) -> None:
        self._fixture_responses = {
            self._normalize_key(key): value for key, value in (fixture_responses or {}).items()
        }
        self._latency_ms = latency_ms
        self._fail_with = fail_with
        self.invocation_count = 0

    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        self.invocation_count += 1
        if self._fail_with is not None:
            raise ModelGatewayError(str(self._fail_with)) from self._fail_with

        context = prompt.get("context", {})
        analysis_stage = str(context.get("analysis_stage", "stage2")) if isinstance(context, dict) else "stage2"
        event = context.get("event", {}) if isinstance(context, dict) else {}
        event_id = str(event.get("event_id", "unknown"))
        user_id = self._extract_user_id(context)
        fixture = self._fixture_responses.get(f"{analysis_stage}:{event_id}:{user_id}")
        if fixture is None and analysis_stage == "stage2":
            fixture = self._fixture_responses.get(f"{event_id}:{user_id}")
        payload = fixture or self._build_heuristic_payload(context, analysis_stage=analysis_stage)
        content = payload.get("output", payload)

        return GatewayResponse(
            provider="mock",
            model_name=model_config.model_name,
            content=content,
            raw_request_ref=str(payload.get("raw_request_ref", f"mock_req_{event_id}_{user_id}")),
            raw_response_ref=str(payload.get("raw_response_ref", f"mock_resp_{event_id}_{user_id}")),
            latency_ms=int(payload.get("latency_ms", self._latency_ms)),
            metadata=dict(payload.get("metadata", {})),
        )

    def _build_heuristic_payload(
        self,
        context: dict[str, Any],
        *,
        analysis_stage: str,
    ) -> dict[str, Any]:
        if analysis_stage == "stage1":
            return self._build_stage1_heuristic_payload(context)
        return self._build_stage2_heuristic_payload(context)

    def _build_stage1_heuristic_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        event = context.get("event", {})
        rule_result = context.get("rule_result", {})
        light_profile_tags = context.get("light_profile_tags", {})
        title = str(event.get("title") or "")
        author = str(event.get("author") or "")
        body = str(event.get("content_text") or "")
        text = "\n".join(part for part in (title, author, body) if part).strip()
        lowered_text = text.lower()
        identity_tags = self._normalize_light_tag_values(light_profile_tags.get("identity_tags", []))
        graduation_tags = self._normalize_light_tag_values(light_profile_tags.get("graduation_tags", []))
        current_task_tags = self._normalize_light_tag_values(light_profile_tags.get("current_task_tags", []))
        user_signals = identity_tags | graduation_tags | current_task_tags
        degree_level = str(light_profile_tags.get("degree_level") or "").strip().lower()
        current_college = str(light_profile_tags.get("college") or "").strip()
        required_facets = self._resolve_stage1_required_facets(rule_result, lowered_text)
        graduation_notice = self._is_graduation_notice(text, lowered_text)
        has_graduation_identity_signal = any(
            self._is_graduation_light_signal(tag) for tag in user_signals
        )
        has_graduation_facet_signal = "graduation_progress" in required_facets
        public_result_notice = self._is_public_result_notice(text, lowered_text)
        internal_admin_notice = self._is_internal_admin_notice(text, lowered_text)
        staff_only_notice = self._is_staff_only_notice(text, lowered_text)
        open_opportunity_notice = self._is_open_opportunity_notice(text, lowered_text)
        identity_mismatch, identity_mismatch_reason = self._resolve_identity_mismatch(
            text=text,
            lowered_text=lowered_text,
            identity_tags=user_signals,
            degree_level=degree_level,
        )
        other_college_only_notice = self._is_other_college_only_notice(
            text=text,
            current_college=current_college,
        )

        if graduation_notice and has_graduation_identity_signal:
            relevance_hint = "relevant"
            reason = "通知与毕业阶段轻信号匹配，值得继续进入重画像精筛。"
        elif graduation_notice and has_graduation_facet_signal:
            relevance_hint = "candidate"
            reason = "规则层已请求 graduation_progress，上下文表明这是一条毕业候选通知。"
        elif graduation_notice:
            relevance_hint = "irrelevant"
            reason = "通知明确面向毕业生，但轻画像未命中毕业生身份。"
        elif identity_mismatch:
            relevance_hint = "irrelevant"
            reason = identity_mismatch_reason or "通知明确限定特定人群，但轻画像不匹配。"
        elif staff_only_notice:
            relevance_hint = "irrelevant"
            reason = "通知更像教职工或教工服务事项，当前学生用户不是目标人群。"
        elif internal_admin_notice and not open_opportunity_notice:
            relevance_hint = "irrelevant"
            reason = "通知是内部会议、工作部署或部门推进，不值得进入个人相关精筛。"
        elif public_result_notice and not open_opportunity_notice and other_college_only_notice:
            relevance_hint = "irrelevant"
            reason = "通知是外学院结果公示或名单公告，且未显示面向当前学院用户。"
        elif public_result_notice and not open_opportunity_notice:
            relevance_hint = "irrelevant"
            reason = "公示、名单或评审结果通常不代表当前用户需要行动，当前阶段优先负向。"
        elif any("毕业" in tag for tag in user_signals) and ("毕业" in lowered_text or "审核材料" in text):
            relevance_hint = "relevant"
            reason = "通知与毕业身份和当前待办高度匹配，值得进入重画像精筛。"
        elif open_opportunity_notice:
            relevance_hint = "candidate"
            reason = "通知更像开放型机会或报名申请事项，先保留为候选通知。"
        else:
            relevance_hint = "candidate"
            reason = "规则粗筛未明确排除，先保留为候选通知再结合重画像精筛。"

        return {
            "output": {
                "relevance_hint_stage1": relevance_hint,
                "required_profile_facets": required_facets,
                "reason_summary_stage1": reason,
                "confidence": min(max(float(rule_result.get("relevance_score", 0.0)), 0.0), 1.0),
            },
            "raw_request_ref": (
                f"mock_stage1_req_{event.get('event_id', 'unknown')}_{light_profile_tags.get('user_id', 'unknown')}"
            ),
            "raw_response_ref": (
                f"mock_stage1_resp_{event.get('event_id', 'unknown')}_{light_profile_tags.get('user_id', 'unknown')}"
            ),
            "latency_ms": self._latency_ms,
        }

    @staticmethod
    def _normalize_light_tag_values(values: list[Any]) -> set[str]:
        normalized: set[str] = set()
        for value in values:
            cleaned = str(value).strip()
            if cleaned:
                normalized.add(cleaned)
        return normalized

    @staticmethod
    def _is_graduation_notice(text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "毕业",
                "毕业生",
                "毕业资格",
                "离校",
                "答辩",
                "学位",
                "graduation",
            )
        )

    @staticmethod
    def _is_graduation_light_signal(value: str) -> bool:
        lowered = value.lower()
        return any(
            keyword in value or keyword in lowered
            for keyword in (
                "毕业",
                "离校",
                "答辩",
                "学位",
                "graduation",
                "graduating",
                "graduation_review",
                "graduating_student",
                "graduation_material_submission",
            )
        )

    @classmethod
    def _is_public_result_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "公示",
                "名单",
                "评审结果",
                "评选结果",
                "结果公告",
                "结果公示",
                "拟推荐",
                "拟资助",
                "拟获奖",
                "入选名单",
                "获奖名单",
            )
        )

    @classmethod
    def _is_internal_admin_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "会议",
                "推进会",
                "部署会",
                "动员会",
                "座谈会",
                "党总支",
                "党支部",
                "党委",
                "党务",
                "学习教育",
                "工作部署",
                "工作推进",
                "召开",
            )
        )

    @classmethod
    def _is_staff_only_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "教职工",
                "教师",
                "教工",
                "工会",
                "人事",
                "通行证",
                "车辆通行",
            )
        )

    @classmethod
    def _is_open_opportunity_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "报名",
                "申请",
                "招募",
                "招新",
                "选拔",
                "征集",
                "宣讲",
                "讲座",
                "研习营",
                "夏令营",
                "训练营",
                "短课",
                "工作坊",
                "通识课",
                "通识课程",
                "课程已上线",
                "展示活动",
                "展演",
            )
        )

    @classmethod
    def _is_public_lecture_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "讲座",
                "学堂",
                "论坛",
                "报告会",
                "学术报告",
                "学者讲座",
                "沙龙",
            )
        )

    @classmethod
    def _is_public_service_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "义诊",
                "医保",
                "医讯",
                "校医院",
                "总医院",
                "门诊",
                "健康服务",
                "就诊",
            )
        )

    @classmethod
    def _is_public_infrastructure_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "停水",
                "停电",
                "停气",
                "停网",
                "断网",
                "楼宇",
                "校区",
                "供水",
                "供电",
                "施工",
                "维修通知",
            )
        )

    @classmethod
    def _is_general_showcase_notice(cls, text: str, lowered_text: str) -> bool:
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "推选展示",
                "展示活动",
                "评优展示",
                "风采展示",
                "最美大学生",
            )
        )

    @classmethod
    def _is_score_publication_notice(cls, text: str, lowered_text: str) -> bool:
        has_score_keyword = any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "成绩",
                "分数",
            )
        )
        if not has_score_keyword:
            return False
        return any(
            keyword in text or keyword in lowered_text
            for keyword in (
                "公布",
                "发布",
                "查询",
                "缓考",
                "补考",
                "考试",
            )
        )

    @classmethod
    def _resolve_identity_mismatch(
        cls,
        *,
        text: str,
        lowered_text: str,
        identity_tags: set[str],
        degree_level: str,
    ) -> tuple[bool, str | None]:
        normalized_tags = " ".join(tag.lower() for tag in identity_tags)
        has_graduation_signal = any(cls._is_graduation_light_signal(tag) for tag in identity_tags)

        if any(keyword in text or keyword in lowered_text for keyword in ("留学生", "国际学生", "外籍学生", "海外学生")):
            if not any(keyword in normalized_tags for keyword in ("留学", "国际", "海外", "exchange", "international")):
                return True, "通知明确限定留学生或国际学生，当前轻画像不匹配。"
        if any(keyword in text or keyword in lowered_text for keyword in ("研究生", "硕士", "博士", "博士生")):
            if degree_level not in {"graduate", "postgraduate", "master", "masters", "doctorate", "doctoral", "phd"}:
                return True, "通知明确面向研究生，但轻画像未命中对应学历层次。"
        if "本科生" in text and degree_level not in {"undergraduate", "bachelor"}:
            return True, "通知明确面向本科生，但轻画像未命中对应学历层次。"
        if any(keyword in text or keyword in lowered_text for keyword in ("教职工", "教师", "教工")):
            if not any(keyword in normalized_tags for keyword in ("教师", "教职", "staff", "faculty", "employee", "教工")):
                return True, "通知明确面向教职工，但当前轻画像是学生侧身份。"
        if "毕业生" in text and not has_graduation_signal:
            return True, "通知明确面向毕业生，但当前轻画像没有毕业相关信号。"
        return False, None

    @classmethod
    def _is_other_college_only_notice(cls, *, text: str, current_college: str) -> bool:
        if not current_college:
            return False
        college_mentions = cls._extract_college_mentions(text)
        if not college_mentions:
            return False
        if current_college in college_mentions:
            return False
        if cls._has_schoolwide_scope(text):
            return False
        return True

    @staticmethod
    def _extract_college_mentions(text: str) -> list[str]:
        seen: list[str] = []
        for match in re.findall(r"[\u4e00-\u9fff]{2,20}学院", text):
            if match not in seen:
                seen.append(match)
        return seen

    @staticmethod
    def _has_schoolwide_scope(text: str) -> bool:
        return any(
            keyword in text
            for keyword in (
                "全校",
                "全体学生",
                "全校学生",
                "面向全校",
                "校级",
                "学校师生",
                "全体师生",
            )
        )

    def _build_stage2_heuristic_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        event = context.get("event", {})
        rule_result = context.get("rule_result", {})
        profile_context = context.get("profile_context", {}) if isinstance(context, dict) else {}
        profile_payload = profile_context.get("payload", {}) if isinstance(profile_context, dict) else {}
        identity_core = profile_payload.get("identity_core", {}) if isinstance(profile_payload, dict) else {}
        graduation_progress = profile_payload.get("graduation_progress", {}) if isinstance(profile_payload, dict) else {}
        title = str(event.get("title") or "")
        author = str(event.get("author") or "")
        body = str(event.get("content_text", "")).strip()
        text = "\n".join(part for part in (title, author, body) if part).strip()
        lowered_text = text.lower()
        identity_tags = self._normalize_light_tag_values(identity_core.get("identity_tags", []))
        degree_level = str(identity_core.get("degree_level") or "").strip().lower()
        current_college = str(identity_core.get("college") or "").strip()
        graduation_stage = str(graduation_progress.get("graduation_stage") or "").strip()
        if graduation_stage:
            identity_tags.add(graduation_stage)
        identity_tags |= self._normalize_light_tag_values(graduation_progress.get("current_tasks", []))
        audience_values = rule_result.get("extracted_signals", {}).get("audience", [])
        audience_text = self._normalize_audience(
            audience_values if isinstance(audience_values, list) else []
        )
        deadline_at = rule_result.get("deadline_at")
        normalized_category = self._resolve_category(text, rule_result)
        output: dict[str, Any] = {
            "summary": self._resolve_summary(text, audience_text, deadline_at),
            "normalized_category": normalized_category,
            "action_items": self._resolve_action_items(text, lowered_text),
            "extracted_fields": [],
            "relevance_hint": self._resolve_stage2_relevance_hint(
                explicit_audience_text=audience_text,
                text=text,
                lowered_text=lowered_text,
                rule_result=rule_result,
                identity_tags=identity_tags,
                degree_level=degree_level,
                current_college=current_college,
            ),
            "urgency_hint": "存在明确截止时间" if deadline_at else None,
            "risk_hint": self._resolve_risk_hint(normalized_category, rule_result),
            "confidence": min(max(float(rule_result.get("relevance_score", 0.0)), 0.0), 1.0),
            "needs_human_review": rule_result.get("relevance_status") == "unknown",
        }
        if deadline_at:
            output["extracted_fields"] = [
                {
                    "field_name": "deadline_at",
                    "field_value": deadline_at,
                    "confidence": 0.94,
                }
            ]

        return {
            "output": output,
            "raw_request_ref": (
                f"mock_req_{event.get('event_id', 'unknown')}_{profile_context.get('user_id', 'unknown')}"
            ),
            "raw_response_ref": (
                f"mock_resp_{event.get('event_id', 'unknown')}_{profile_context.get('user_id', 'unknown')}"
            ),
            "latency_ms": self._latency_ms,
        }

    @staticmethod
    def _normalize_key(key: str | tuple[str, str] | tuple[str, str, str]) -> str:
        if isinstance(key, tuple) and len(key) == 3:
            return f"{key[0]}:{key[1]}:{key[2]}"
        if isinstance(key, tuple):
            return f"{key[0]}:{key[1]}"
        return key

    @staticmethod
    def _extract_user_id(context: dict[str, Any]) -> str:
        if not isinstance(context, dict):
            return "unknown"
        profile_context = context.get("profile_context")
        if isinstance(profile_context, dict) and profile_context.get("user_id") is not None:
            return str(profile_context.get("user_id"))
        light_profile_tags = context.get("light_profile_tags")
        if isinstance(light_profile_tags, dict) and light_profile_tags.get("user_id") is not None:
            return str(light_profile_tags.get("user_id"))
        return "unknown"

    @staticmethod
    def _normalize_audience(values: list[Any]) -> str:
        audience_items = [str(item).strip() for item in values if str(item).strip()]
        if not audience_items:
            return ""
        normalized: list[str] = []
        for item in audience_items:
            cleaned = item
            if cleaned.endswith("毕业生") and cleaned not in {"毕业生", "相关毕业生"}:
                cleaned = "毕业生"
            if cleaned not in normalized:
                normalized.append(cleaned)
        return "、".join(normalized)

    def _resolve_summary(self, text: str, audience_text: str, deadline_at: Any) -> str | None:
        deadline_text = self._format_deadline(deadline_at)
        if "毕业资格审核材料" in text and deadline_text:
            audience = audience_text or "相关学生"
            return f"该通知要求{audience}在{deadline_text}提交毕业资格审核材料。"
        return text[:120] if text else None

    @classmethod
    def _resolve_action_items(cls, text: str, lowered_text: str) -> list[str]:
        if cls._is_public_result_notice(text, lowered_text):
            return []
        if cls._is_internal_admin_notice(text, lowered_text):
            return []
        if cls._is_staff_only_notice(text, lowered_text):
            return []
        if "毕业资格审核材料" in text:
            return ["提交毕业资格审核材料"]
        if "提交" in text:
            return [text.replace("请", "").strip("。")]
        return []

    @classmethod
    def _resolve_stage2_relevance_hint(
        cls,
        *,
        explicit_audience_text: str,
        text: str,
        lowered_text: str,
        rule_result: dict[str, Any],
        identity_tags: set[str],
        degree_level: str,
        current_college: str,
    ) -> str:
        public_result_notice = cls._is_public_result_notice(text, lowered_text)
        internal_admin_notice = cls._is_internal_admin_notice(text, lowered_text)
        staff_only_notice = cls._is_staff_only_notice(text, lowered_text)
        open_opportunity_notice = cls._is_open_opportunity_notice(text, lowered_text)
        public_lecture_notice = cls._is_public_lecture_notice(text, lowered_text)
        public_service_notice = cls._is_public_service_notice(text, lowered_text)
        public_infrastructure_notice = cls._is_public_infrastructure_notice(text, lowered_text)
        general_showcase_notice = cls._is_general_showcase_notice(text, lowered_text)
        score_publication_notice = cls._is_score_publication_notice(text, lowered_text)
        identity_mismatch, _ = cls._resolve_identity_mismatch(
            text=text,
            lowered_text=lowered_text,
            identity_tags=identity_tags,
            degree_level=degree_level,
        )
        audience_matches_user = cls._explicit_audience_matches_user(
            explicit_audience_text=explicit_audience_text,
            identity_tags=identity_tags,
            degree_level=degree_level,
        )
        other_college_only_notice = cls._is_other_college_only_notice(
            text=text,
            current_college=current_college,
        )

        if staff_only_notice:
            return "irrelevant"
        if identity_mismatch:
            return "irrelevant"
        if internal_admin_notice and not open_opportunity_notice:
            return "irrelevant"
        if public_result_notice:
            if other_college_only_notice or explicit_audience_text:
                return "irrelevant" if not audience_matches_user else "uncertain"
            return "uncertain"
        if score_publication_notice:
            return "uncertain"
        if cls._is_graduation_notice(text, lowered_text) and any(
            cls._is_graduation_light_signal(tag) for tag in identity_tags
        ):
            return "relevant"
        if audience_matches_user:
            return "relevant"
        if public_lecture_notice or public_service_notice or public_infrastructure_notice:
            return "uncertain"
        if general_showcase_notice:
            return "uncertain"
        if open_opportunity_notice:
            return "uncertain"
        if rule_result.get("relevance_status") == "relevant" and not other_college_only_notice:
            return "relevant"
        return "uncertain"

    @classmethod
    def _explicit_audience_matches_user(
        cls,
        *,
        explicit_audience_text: str,
        identity_tags: set[str],
        degree_level: str,
    ) -> bool:
        if not explicit_audience_text:
            return False
        lowered_audience = explicit_audience_text.lower()
        normalized_tags = " ".join(tag.lower() for tag in identity_tags)
        if any(keyword in explicit_audience_text for keyword in ("留学生", "国际学生", "外籍学生", "海外学生")):
            return any(keyword in normalized_tags for keyword in ("留学", "国际", "海外", "exchange", "international"))
        if any(keyword in explicit_audience_text for keyword in ("教职工", "教师", "教工")):
            return any(keyword in normalized_tags for keyword in ("教师", "教职", "staff", "faculty", "employee", "教工"))
        if any(keyword in explicit_audience_text for keyword in ("研究生", "硕士", "博士", "博士生")):
            return degree_level in {"graduate", "postgraduate", "master", "masters", "doctorate", "doctoral", "phd"}
        if "本科生" in explicit_audience_text:
            return degree_level in {"undergraduate", "bachelor"}
        if "毕业生" in explicit_audience_text:
            return any(cls._is_graduation_light_signal(tag) for tag in identity_tags)
        if any(keyword in explicit_audience_text for keyword in ("全校", "全体学生", "全校学生", "学生")):
            return bool(degree_level or normalized_tags)
        return any(token and token in normalized_tags for token in lowered_audience.split("、"))

    @staticmethod
    def _resolve_stage1_required_facets(
        rule_result: dict[str, Any],
        lowered_text: str,
    ) -> list[str]:
        required = [
            str(facet).strip()
            for facet in rule_result.get("required_profile_facets", [])
            if str(facet).strip()
        ]
        if required:
            return required
        if "毕业" in lowered_text:
            return ["identity_core", "graduation_progress"]
        if "学分" in lowered_text:
            return ["identity_core", "academic_completion"]
        return ["identity_core"]

    @staticmethod
    def _resolve_category(text: str, rule_result: dict[str, Any]) -> str | None:
        candidate_categories = [str(item) for item in rule_result.get("candidate_categories", [])]
        if "graduation" in candidate_categories and "material_submission" in candidate_categories:
            return "graduation_material_submission"
        if "毕业" in text and "材料" in text:
            return "graduation_material_submission"
        if candidate_categories:
            return candidate_categories[0]
        return None

    @staticmethod
    def _resolve_risk_hint(normalized_category: str | None, rule_result: dict[str, Any]) -> str | None:
        if normalized_category == "graduation_material_submission":
            return "错过可能影响毕业审核进度"
        risk_level = str(rule_result.get("risk_level", "")).lower()
        if risk_level in {"high", "critical"}:
            return "错过可能带来较高业务风险"
        return None

    @staticmethod
    def _format_deadline(deadline_at: Any) -> str | None:
        if not isinstance(deadline_at, str) or len(deadline_at) < 10:
            return None
        try:
            month = int(deadline_at[5:7])
            day = int(deadline_at[8:10])
        except ValueError:
            return None
        return f"{month}月{day}日前"


class HTTPModelGateway(ModelGateway):
    def __init__(
        self,
        endpoint: str | None,
        api_key: str | None = None,
        transport: Callable[[dict[str, Any], AIModelConfig], dict[str, Any]] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._transport = transport

    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        if not self._endpoint and self._transport is None:
            raise ModelGatewayError("HTTP model gateway requires an endpoint or transport")

        request_payload = {
            "prompt": prompt,
            "model_config": model_config.model_dump(exclude_none=True),
        }
        started_at = time.perf_counter()
        try:
            if self._transport is not None:
                response_payload = await asyncio.to_thread(self._transport, request_payload, model_config)
            else:
                response_payload = await asyncio.to_thread(self._post_json, request_payload, model_config)
        except Exception as exc:
            raise ModelGatewayError(f"Model gateway request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        output = response_payload.get("output", response_payload)
        return GatewayResponse(
            provider=str(response_payload.get("provider", model_config.provider)),
            model_name=str(response_payload.get("model_name", model_config.model_name)),
            content=output,
            raw_request_ref=response_payload.get("raw_request_ref"),
            raw_response_ref=response_payload.get("raw_response_ref"),
            latency_ms=int(response_payload.get("latency_ms", latency_ms)),
            metadata=dict(response_payload.get("metadata", {})),
        )

    def _post_json(self, payload: dict[str, Any], model_config: AIModelConfig) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=model_config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ModelGatewayError(f"Unable to reach model gateway: {exc}") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ModelGatewayError("Model gateway returned non-JSON payload") from exc
        if not isinstance(parsed, dict):
            raise ModelGatewayError("Model gateway returned a non-object JSON payload")
        return parsed


class KimiChatGateway(ModelGateway):
    DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
    JSON_MODE_UNSUPPORTED_MODELS = {"kimi-thinking-preview", "kimi-k2-thinking"}

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: Callable[[dict[str, Any], AIModelConfig], dict[str, Any]] | None = None,
    ) -> None:
        self._base_url = base_url or self.DEFAULT_BASE_URL
        self._api_key = api_key
        self._transport = transport

    async def invoke(self, prompt: dict[str, Any], model_config: AIModelConfig) -> GatewayResponse:
        if self._transport is None and not self._api_key:
            raise ModelGatewayError("Kimi API key is required")

        request_payload = self._build_chat_request(prompt, model_config)
        started_at = time.perf_counter()
        try:
            if self._transport is not None:
                response_payload = await asyncio.to_thread(self._transport, request_payload, model_config)
            else:
                response_payload = await asyncio.to_thread(
                    self._post_chat_completion,
                    self._resolve_endpoint(model_config),
                    request_payload,
                    model_config,
                )
        except Exception as exc:
            raise ModelGatewayError(f"Kimi gateway request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        response_content = self._extract_response_content(response_payload)

        return GatewayResponse(
            provider="kimi",
            model_name=str(response_payload.get("model", model_config.model_name)),
            content=response_content,
            raw_request_ref=f"kimi_req:{request_payload['model']}",
            raw_response_ref=str(response_payload.get("id", "")) or None,
            latency_ms=int(response_payload.get("latency_ms", latency_ms)),
            metadata=self._build_metadata(response_payload),
        )

    def _build_chat_request(
        self,
        prompt: dict[str, Any],
        model_config: AIModelConfig,
    ) -> dict[str, Any]:
        metadata = model_config.metadata or {}
        request_payload: dict[str, Any] = {
            "model": model_config.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a structured extraction assistant. "
                        "Return only a valid JSON object with no markdown fences."
                    ),
                },
                {
                    "role": "user",
                    "content": str(prompt.get("instructions", "")),
                },
            ],
            "temperature": float(metadata.get("temperature", 0.2)),
        }

        max_tokens = metadata.get("max_tokens")
        if max_tokens is not None:
            request_payload["max_tokens"] = int(max_tokens)

        top_p = metadata.get("top_p")
        if top_p is not None:
            request_payload["top_p"] = float(top_p)

        use_json_mode = metadata.get("use_json_mode", True)
        if use_json_mode and not self._is_json_mode_unsupported(model_config.model_name):
            request_payload["response_format"] = {"type": "json_object"}

        return request_payload

    def _resolve_endpoint(self, model_config: AIModelConfig) -> str:
        base = model_config.endpoint or self._base_url
        if base.endswith("/chat/completions"):
            return base
        normalized = base.rstrip("/") + "/"
        return urljoin(normalized, "chat/completions")

    def _post_chat_completion(
        self,
        endpoint: str,
        payload: dict[str, Any],
        model_config: AIModelConfig,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self._api_key}",
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=model_config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ModelGatewayError(
                f"Kimi API returned HTTP {exc.code}: {error_body[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ModelGatewayError(f"Unable to reach Kimi API: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ModelGatewayError("Kimi API returned non-JSON payload") from exc
        if not isinstance(parsed, dict):
            raise ModelGatewayError("Kimi API returned a non-object JSON payload")
        return parsed

    def _extract_response_content(self, response_payload: dict[str, Any]) -> dict[str, Any] | str:
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelGatewayError("Kimi API response is missing choices")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelGatewayError("Kimi API response is missing message")

        content = message.get("content")
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            content = "\n".join(part for part in text_parts if part)

        if not isinstance(content, str):
            raise ModelGatewayError("Kimi API response content is empty")

        stripped = self._strip_code_fences(content.strip())
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        return parsed if isinstance(parsed, dict) else stripped

    def _build_metadata(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        usage = response_payload.get("usage")
        if isinstance(usage, dict):
            metadata["usage"] = usage
        choices = response_payload.get("choices")
        if isinstance(choices, list) and choices:
            finish_reason = choices[0].get("finish_reason")
            if finish_reason is not None:
                metadata["finish_reason"] = finish_reason
        return metadata

    def _strip_code_fences(self, content: str) -> str:
        if content.startswith("```") and content.endswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return content

    def _is_json_mode_unsupported(self, model_name: str) -> bool:
        normalized = (model_name or "").strip().lower()
        return normalized in self.JSON_MODE_UNSUPPORTED_MODELS or "thinking" in normalized
