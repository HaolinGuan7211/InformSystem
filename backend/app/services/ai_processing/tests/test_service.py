from __future__ import annotations

import pytest

from backend.app.services.ai_processing.model_gateway import ModelGatewayError, MockModelGateway
from backend.app.services.ai_processing.models import AIAnalysisResult, AIModelConfig, GatewayResponse
from backend.app.services.ai_processing.service import AIRuntimeDisabledError
from backend.app.services.user_profile.light_profile_tag_builder import LightProfileTags


class InvalidJSONGateway(MockModelGateway):
    async def invoke(self, prompt, model_config: AIModelConfig) -> GatewayResponse:
        self.invocation_count += 1
        return GatewayResponse(
            provider="mock",
            model_name=model_config.model_name,
            content="not-json",
            raw_request_ref="bad_req",
            raw_response_ref="bad_resp",
            latency_ms=3,
        )


class RetryThenSuccessGateway(MockModelGateway):
    def __init__(self, fixture_response: dict, failures_before_success: int = 1) -> None:
        super().__init__(fixture_responses={("evt_001", "stu_001"): fixture_response})
        self._failures_before_success = failures_before_success

    async def invoke(self, prompt, model_config: AIModelConfig) -> GatewayResponse:
        self.invocation_count += 1
        if self.invocation_count <= self._failures_before_success:
            raise ModelGatewayError(f"temporary gateway failure #{self.invocation_count}")

        context = prompt.get("context", {})
        event = context.get("event", {}) if isinstance(context, dict) else {}
        profile_context = context.get("profile_context", {}) if isinstance(context, dict) else {}
        event_id = str(event.get("event_id", "unknown"))
        user_id = str(profile_context.get("user_id", "unknown"))
        payload = self._fixture_responses.get(f"{event_id}:{user_id}") or self._build_stage2_heuristic_payload(context)
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


def _build_light_profile_tags() -> LightProfileTags:
    return LightProfileTags(
        user_id="stu_001",
        college="计算机学院",
        major="软件工程",
        grade="2022",
        degree_level="undergraduate",
        identity_tags=["毕业生"],
        current_course_tags=[],
        current_task_tags=["毕业资格审核"],
        generated_at="2026-03-13T10:22:00+08:00",
    )


def _build_stage1_fixture(
    relevance_hint_stage1: str,
    required_profile_facets: list[str],
    reason_summary_stage1: str,
    confidence: float = 0.82,
) -> dict:
    return {
        "output": {
            "relevance_hint_stage1": relevance_hint_stage1,
            "required_profile_facets": required_profile_facets,
            "reason_summary_stage1": reason_summary_stage1,
            "confidence": confidence,
        },
        "raw_request_ref": "stage1_req",
        "raw_response_ref": "stage1_resp",
        "latency_ms": 7,
        "metadata": {},
    }


def _build_general_light_profile_tags() -> LightProfileTags:
    return LightProfileTags(
        user_id="stu_001",
        college="计算机学院",
        major="软件工程",
        grade="2022",
        degree_level="undergraduate",
        identity_tags=["student"],
        current_course_tags=[],
        current_task_tags=[],
        generated_at="2026-03-13T10:22:00+08:00",
    )


def _build_custom_event(
    flow_inputs,
    *,
    event_id: str,
    title: str,
    content_text: str,
    author: str,
):
    return flow_inputs["event"].model_copy(
        update={
            "event_id": event_id,
            "title": title,
            "content_text": content_text,
            "author": author,
            "url": f"https://example.edu.cn/notices/{event_id}",
        }
    )


def _build_custom_rule_result(
    flow_inputs,
    *,
    event_id: str,
    candidate_categories: list[str] | None = None,
    extracted_signals: dict | None = None,
):
    return flow_inputs["rule_result"].model_copy(
        update={
            "analysis_id": f"analysis_{event_id}",
            "event_id": event_id,
            "candidate_categories": candidate_categories or [],
            "extracted_signals": extracted_signals or {},
            "required_profile_facets": [],
            "relevance_status": "unknown",
            "relevance_score": 0.46,
            "should_invoke_ai": True,
            "should_continue": True,
            "explanation": [],
        }
    )


def _build_general_profile_context(flow_inputs):
    identity_core = dict(flow_inputs["profile_context"].payload.get("identity_core", {}))
    identity_core.update(
        {
            "college": "计算机学院",
            "major": "软件工程",
            "grade": "2022",
            "degree_level": "undergraduate",
            "identity_tags": ["student"],
        }
    )
    return flow_inputs["profile_context"].model_copy(
        update={
            "facets": ["identity_core"],
            "payload": {
                "identity_core": identity_core,
            },
            "metadata": {"selector_version": "v1"},
        }
    )


@pytest.mark.asyncio
async def test_ai_processing_service_matches_golden_flow(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
    load_golden,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    service, repository, gateway = build_ai_service(fixture_response=fixture)

    result = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )
    expected = AIAnalysisResult.model_validate(load_golden("04_ai_analysis_result.json"))

    assert result.model_dump() == expected.model_dump()
    stored = await repository.get_by_event_and_user(
        "evt_001",
        "stu_001",
        model_name="gpt-5-mini",
        prompt_version="prompt_v1",
    )
    assert stored is not None
    assert stored.model_dump() == expected.model_dump()
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "success"
    assert gateway.invocation_count == 1


@pytest.mark.asyncio
async def test_ai_processing_service_keeps_only_audit_metadata_from_profile_context(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    fixture["metadata"] = {"provider_trace_id": "trace_001"}
    service, _, _ = build_ai_service(fixture_response=fixture)
    profile_context = flow_inputs["profile_context"].model_copy(
        update={
            "metadata": {
                "selector_version": "v1",
                "fallback_reason": "missing_required_profile_facets",
                "compat_mode_reason": "legacy_profile_context_input",
                "context_expansion_reason": "include_identity_core_for_audience_disambiguation",
            }
        }
    )

    result = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        profile_context,
    )

    assert result.metadata == {
        "provider_trace_id": "trace_001",
        "compat_mode_reason": "legacy_profile_context_input",
        "context_expansion_reason": "include_identity_core_for_audience_disambiguation",
    }


@pytest.mark.asyncio
async def test_ai_processing_service_uses_cache_before_second_gateway_call(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    service, _, gateway = build_ai_service(fixture_response=fixture)

    first = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )
    second = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert first.model_dump() == second.model_dump()
    assert gateway.invocation_count == 1


@pytest.mark.asyncio
async def test_ai_processing_service_reads_repository_as_durable_cache(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    first_service, repository, first_gateway = build_ai_service(fixture_response=fixture)
    await first_service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    second_gateway = MockModelGateway(fail_with=RuntimeError("should not be called"))
    second_service, _, _ = build_ai_service(gateway=second_gateway, repository=repository)
    cached = await second_service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert cached.ai_result_id == "ai_001"
    assert first_gateway.invocation_count == 1
    assert second_gateway.invocation_count == 0


@pytest.mark.asyncio
async def test_ai_processing_service_stage1_irrelevant_skips_heavy_profile_context(
    build_ai_service,
    flow_inputs,
) -> None:
    gateway = MockModelGateway(
        fixture_responses={
            ("stage1", "evt_001", "stu_001"): _build_stage1_fixture(
                relevance_hint_stage1="irrelevant",
                required_profile_facets=["identity_core"],
                reason_summary_stage1="轻画像粗筛已明确判定当前通知无关。",
            )
        }
    )
    service, repository, _ = build_ai_service(gateway=gateway)

    async def _unexpected_loader(required_facets: list[str]):
        raise AssertionError(f"profile context loader should not run, got {required_facets}")

    result = await service.analyze_two_stage_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        _build_light_profile_tags(),
        _unexpected_loader,
    )

    assert result is not None
    assert result.relevance_hint == "irrelevant"
    assert result.metadata["analysis_stage"] == "stage1"
    assert result.metadata["analysis_path"] == "stage1_terminal"
    assert gateway.invocation_count == 1
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "success"


@pytest.mark.asyncio
async def test_ai_processing_service_stage1_candidate_enters_stage2(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    stage2_fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    gateway = MockModelGateway(
        fixture_responses={
            ("stage1", "evt_001", "stu_001"): _build_stage1_fixture(
                relevance_hint_stage1="candidate",
                required_profile_facets=["identity_core", "graduation_progress"],
                reason_summary_stage1="先保留为候选通知，继续做重画像精筛。",
            ),
            ("evt_001", "stu_001"): stage2_fixture,
        }
    )
    service, _, _ = build_ai_service(gateway=gateway)
    loader_calls: list[list[str]] = []

    async def _load_profile_context(required_facets: list[str]):
        loader_calls.append(required_facets)
        return flow_inputs["profile_context"]

    result = await service.analyze_two_stage_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        _build_light_profile_tags(),
        _load_profile_context,
    )

    assert result is not None
    assert result.metadata["analysis_stage"] == "stage2"
    assert result.metadata["analysis_path"] == "stage1_to_stage2"
    assert loader_calls == [["identity_core", "graduation_progress"]]
    assert gateway.invocation_count == 2


@pytest.mark.asyncio
async def test_ai_processing_service_stage1_uses_graduation_task_signal_for_probe_like_persona(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    stage2_fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    gateway = MockModelGateway(
        fixture_responses={
            ("evt_001", "stu_001"): stage2_fixture,
        }
    )
    service, _, _ = build_ai_service(gateway=gateway)
    light_profile_tags = LightProfileTags(
        user_id="stu_001",
        college="计算机学院",
        major="软件工程",
        grade="2022",
        degree_level="undergraduate",
        identity_tags=["student"],
        current_course_tags=[],
        current_task_tags=["graduation_material_submission"],
        generated_at="2026-03-13T10:22:00+08:00",
    )
    loader_calls: list[list[str]] = []

    async def _load_profile_context(required_facets: list[str]):
        loader_calls.append(required_facets)
        return flow_inputs["profile_context"]

    result = await service.analyze_two_stage_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        light_profile_tags,
        _load_profile_context,
    )

    assert result is not None
    assert loader_calls == [["identity_core", "graduation_progress"]]
    assert result.metadata["analysis_stage"] == "stage2"
    assert gateway.invocation_count == 2


@pytest.mark.parametrize(
    ("event_id", "title", "content_text", "author"),
    [
        (
            "evt_external_scholarship_publicity",
            "传播学院2026年荔园国际奖学金评审结果公示",
            "现对传播学院2026年荔园国际奖学金评审结果予以公示。",
            "传播学院",
        ),
        (
            "evt_overseas_scholarship_publicity",
            "外国语学院2026年留学生荔园国际奖学金名单公示",
            "现将2026年留学生荔园国际奖学金拟获奖名单予以公示。",
            "外国语学院",
        ),
        (
            "evt_staff_vehicle_service",
            "安全保卫部关于教职工车辆通行证线上办理试运行的通知",
            "为方便教职工办理车辆通行证，现开展线上试运行。",
            "安全保卫部",
        ),
        (
            "evt_internal_meeting",
            "后勤保障部召开新学期重点工作推进会议",
            "后勤保障部召开新学期重点工作推进会议，部署后续保障安排。",
            "后勤保障部",
        ),
    ],
)
@pytest.mark.asyncio
async def test_ai_processing_service_stage1_blocks_known_negative_notice_types(
    build_ai_service,
    flow_inputs,
    event_id: str,
    title: str,
    content_text: str,
    author: str,
) -> None:
    service, _, gateway = build_ai_service()
    event = _build_custom_event(
        flow_inputs,
        event_id=event_id,
        title=title,
        content_text=content_text,
        author=author,
    )
    rule_result = _build_custom_rule_result(flow_inputs, event_id=event_id)

    async def _unexpected_loader(required_facets: list[str]):
        raise AssertionError(f"profile context loader should not run, got {required_facets}")

    result = await service.analyze_two_stage_or_fallback(
        event,
        rule_result,
        _build_general_light_profile_tags(),
        _unexpected_loader,
    )

    assert result is not None
    assert result.relevance_hint == "irrelevant"
    assert result.metadata["analysis_stage"] == "stage1"
    assert result.metadata["analysis_path"] == "stage1_terminal"
    assert gateway.invocation_count == 1


@pytest.mark.parametrize(
    ("event_id", "title", "content_text", "author"),
    [
        (
            "evt_innovation_short_course",
            "创新创业专题研讨短课《城中村治理》2026春季招募",
            "现面向全校学生开放报名，欢迎对创新创业议题感兴趣的同学申请参加。",
            "创新创业学院",
        ),
        (
            "evt_general_education_course",
            "全校通识课程《大学语文》已上线",
            "课程面向全校本科生开放，学生可按要求选课学习。",
            "本科生院",
        ),
        (
            "evt_summer_camp",
            "关于2026年澳门科技大学暑期研习营的通知",
            "现开放报名，欢迎有兴趣的学生按要求提交申请材料。",
            "国际合作部",
        ),
    ],
)
@pytest.mark.asyncio
async def test_ai_processing_service_stage1_keeps_open_opportunities_alive(
    build_ai_service,
    flow_inputs,
    event_id: str,
    title: str,
    content_text: str,
    author: str,
) -> None:
    service, _, gateway = build_ai_service()
    event = _build_custom_event(
        flow_inputs,
        event_id=event_id,
        title=title,
        content_text=content_text,
        author=author,
    )
    rule_result = _build_custom_rule_result(flow_inputs, event_id=event_id)
    loader_calls: list[list[str]] = []

    async def _load_profile_context(required_facets: list[str]):
        loader_calls.append(required_facets)
        return _build_general_profile_context(flow_inputs)

    result = await service.analyze_two_stage_or_fallback(
        event,
        rule_result,
        _build_general_light_profile_tags(),
        _load_profile_context,
    )

    assert result is not None
    assert loader_calls == [["identity_core"]]
    assert result.metadata["analysis_stage"] == "stage2"
    assert result.relevance_hint in {"uncertain", "relevant"}
    assert gateway.invocation_count == 2


@pytest.mark.parametrize(
    ("event_id", "title", "content_text", "author", "expected_hint"),
    [
        (
            "evt_external_scholarship_stage2",
            "传播学院2026年荔园国际奖学金评审结果公示",
            "现对传播学院2026年荔园国际奖学金评审结果予以公示。",
            "传播学院",
            "irrelevant",
        ),
        (
            "evt_overseas_stage2",
            "外国语学院2026年留学生荔园国际奖学金名单公示",
            "现将2026年留学生荔园国际奖学金拟获奖名单予以公示。",
            "外国语学院",
            "irrelevant",
        ),
        (
            "evt_internal_meeting_stage2",
            "后勤保障部召开新学期重点工作推进会议",
            "后勤保障部召开新学期重点工作推进会议，部署后续保障安排。",
            "后勤保障部",
            "irrelevant",
        ),
        (
            "evt_staff_service_stage2",
            "安全保卫部关于教职工车辆通行证线上办理试运行的通知",
            "为方便教职工办理车辆通行证，现开展线上试运行。",
            "安全保卫部",
            "irrelevant",
        ),
        (
            "evt_open_course_stage2",
            "全校通识课程《大学语文》已上线",
            "课程面向全校本科生开放，学生可按要求选课学习。",
            "本科生院",
            "uncertain",
        ),
        (
            "evt_makeup_exam_scores_stage2",
            "关于公布2025-2026第一学期本科缓考（补考）成绩的通知",
            "现公布2025-2026第一学期本科缓考（补考）成绩，请同学登录系统查询。",
            "本科生院",
            "uncertain",
        ),
        (
            "evt_public_lecture_stage2",
            "荔园杰出学者讲座第三十九期：人工智能时代的数学研究",
            "本期讲座面向全校师生开放，欢迎感兴趣的同学参加。",
            "深圳大学",
            "uncertain",
        ),
        (
            "evt_public_service_stage2",
            "【医讯】深圳大学总医院眼科专家到校医院义诊",
            "校医院联合深圳大学总医院开展眼科义诊服务，欢迎有需要的师生前往咨询。",
            "校医院",
            "uncertain",
        ),
        (
            "evt_showcase_activity_stage2",
            "关于开展“广东最美大学生”推选展示活动的通知",
            "现组织开展“广东最美大学生”推选展示活动，欢迎符合条件的学生关注并按要求报名。",
            "学生工作部",
            "uncertain",
        ),
        (
            "evt_water_outage_stage2",
            "关于丽湖校区一期部分楼宇停水的通知",
            "因管网维修，丽湖校区一期部分楼宇将临时停水，请相关师生提前做好准备。",
            "后勤保障部",
            "uncertain",
        ),
    ],
)
@pytest.mark.asyncio
async def test_ai_processing_service_stage2_applies_refined_negative_and_open_rules(
    build_ai_service,
    flow_inputs,
    event_id: str,
    title: str,
    content_text: str,
    author: str,
    expected_hint: str,
) -> None:
    service, _, gateway = build_ai_service()
    event = _build_custom_event(
        flow_inputs,
        event_id=event_id,
        title=title,
        content_text=content_text,
        author=author,
    )
    rule_result = _build_custom_rule_result(flow_inputs, event_id=event_id)
    profile_context = _build_general_profile_context(flow_inputs)

    result = await service.analyze(
        event,
        rule_result,
        profile_context,
    )

    assert result.relevance_hint == expected_hint
    assert gateway.invocation_count == 1


@pytest.mark.asyncio
async def test_ai_processing_service_stage2_irrelevant_returns_negative_final_result(
    build_ai_service,
    flow_inputs,
) -> None:
    stage2_fixture = {
        "output": {
            "summary": "通知虽然命中过候选范围，但结合重画像后与当前用户不相关。",
            "normalized_category": "graduation_material_submission",
            "action_items": [],
            "extracted_fields": [],
            "relevance_hint": "irrelevant",
            "urgency_hint": None,
            "risk_hint": None,
            "confidence": 0.84,
            "needs_human_review": False,
        },
        "raw_request_ref": "stage2_req",
        "raw_response_ref": "stage2_resp",
        "latency_ms": 9,
        "metadata": {},
    }
    gateway = MockModelGateway(
        fixture_responses={
            ("stage1", "evt_001", "stu_001"): _build_stage1_fixture(
                relevance_hint_stage1="candidate",
                required_profile_facets=["identity_core", "graduation_progress"],
                reason_summary_stage1="继续进入重画像精筛。",
            ),
            ("evt_001", "stu_001"): stage2_fixture,
        }
    )
    service, _, _ = build_ai_service(gateway=gateway)

    async def _load_profile_context(required_facets: list[str]):
        assert required_facets == ["identity_core", "graduation_progress"]
        return flow_inputs["profile_context"]

    result = await service.analyze_two_stage_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        _build_light_profile_tags(),
        _load_profile_context,
    )

    assert result is not None
    assert result.relevance_hint == "irrelevant"
    assert result.metadata["analysis_stage"] == "stage2"


@pytest.mark.asyncio
async def test_ai_processing_service_stage2_relevant_keeps_ai_analysis_result_contract(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    stage2_fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    gateway = MockModelGateway(
        fixture_responses={
            ("stage1", "evt_001", "stu_001"): _build_stage1_fixture(
                relevance_hint_stage1="relevant",
                required_profile_facets=["identity_core", "graduation_progress"],
                reason_summary_stage1="轻画像已高度命中，但仍需重画像确认。",
            ),
            ("evt_001", "stu_001"): stage2_fixture,
        }
    )
    service, _, _ = build_ai_service(gateway=gateway)

    async def _load_profile_context(required_facets: list[str]):
        assert required_facets == ["identity_core", "graduation_progress"]
        return flow_inputs["profile_context"]

    result = await service.analyze_two_stage_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        _build_light_profile_tags(),
        _load_profile_context,
    )

    assert result is not None
    assert isinstance(result, AIAnalysisResult)
    assert result.normalized_category == "graduation_material_submission"
    assert result.relevance_hint == "relevant"
    assert result.action_items == ["提交毕业资格审核材料"]


@pytest.mark.asyncio
async def test_ai_processing_service_skips_when_runtime_disabled(
    build_ai_service,
    flow_inputs,
) -> None:
    service, repository, gateway = build_ai_service(model_config_overrides={"enabled": False})

    with pytest.raises(AIRuntimeDisabledError):
        await service.analyze(
            flow_inputs["event"],
            flow_inputs["rule_result"],
            flow_inputs["profile_context"],
        )

    result = await service.analyze_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert result is None
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "skipped"
    assert call_logs[0].error_message == "AI runtime disabled by configuration"
    assert gateway.invocation_count == 0


@pytest.mark.asyncio
async def test_ai_processing_service_two_stage_short_circuits_when_runtime_disabled(
    build_ai_service,
    flow_inputs,
) -> None:
    service, repository, gateway = build_ai_service(model_config_overrides={"enabled": False})

    async def _unexpected_loader(required_facets: list[str]):
        raise AssertionError(f"loader should not run when AI is disabled, got {required_facets}")

    result = await service.analyze_two_stage_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        _build_light_profile_tags(),
        _unexpected_loader,
    )

    assert result is None
    assert gateway.invocation_count == 0
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert [log.status for log in call_logs] == ["skipped"]


@pytest.mark.asyncio
async def test_ai_processing_service_retries_gateway_failures_only(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    gateway = RetryThenSuccessGateway(fixture_response=fixture, failures_before_success=1)
    service, repository, _ = build_ai_service(
        gateway=gateway,
        model_config_overrides={"max_retries": 2},
    )

    result = await service.analyze(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert result.ai_result_id == "ai_001"
    assert gateway.invocation_count == 2
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "success"


@pytest.mark.asyncio
async def test_ai_processing_service_returns_none_after_retry_exhaustion(
    build_ai_service,
    flow_inputs,
) -> None:
    gateway = MockModelGateway(fail_with=RuntimeError("temporary provider outage"))
    service, repository, _ = build_ai_service(
        gateway=gateway,
        model_config_overrides={"max_retries": 2},
    )

    result = await service.analyze_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert result is None
    assert gateway.invocation_count == 3
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "failed"
    assert "temporary provider outage" in call_logs[0].error_message


@pytest.mark.asyncio
async def test_ai_processing_service_falls_back_and_logs_failure(
    build_ai_service,
    flow_inputs,
) -> None:
    gateway = InvalidJSONGateway()
    service, repository, _ = build_ai_service(
        gateway=gateway,
        model_config_overrides={"max_retries": 2},
    )

    result = await service.analyze_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert result is None
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "failed"
    assert "Expecting value" in call_logs[0].error_message
    assert gateway.invocation_count == 1


@pytest.mark.asyncio
async def test_ai_processing_service_does_not_retry_result_validation_errors(
    build_ai_service,
    flow_inputs,
    load_ai_mock,
) -> None:
    fixture = load_ai_mock(
        "downstream_outputs",
        "graduation_material_submission__output__mock_gateway_response.json",
    )
    service, repository, gateway = build_ai_service(
        fixture_response=fixture,
        model_config_overrides={"max_retries": 2, "model_name": "   "},
    )

    result = await service.analyze_or_fallback(
        flow_inputs["event"],
        flow_inputs["rule_result"],
        flow_inputs["profile_context"],
    )

    assert result is None
    assert gateway.invocation_count == 1
    call_logs = await repository.list_call_logs("evt_001", "stu_001")
    assert len(call_logs) == 1
    assert call_logs[0].status == "failed"
    assert call_logs[0].error_message == "model_name is required"
    stored = await repository.get_by_event_and_user(
        "evt_001",
        "stu_001",
        model_name="   ",
        prompt_version="prompt_v1",
    )
    assert stored is None
