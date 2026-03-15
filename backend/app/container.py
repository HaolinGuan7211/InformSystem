from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.config import Settings
from backend.app.core.database import init_database
from backend.app.services.decision_engine.action_resolver import ActionResolver
from backend.app.services.decision_engine.channel_resolver import ChannelResolver
from backend.app.services.decision_engine.evidence_aggregator import EvidenceAggregator
from backend.app.services.decision_engine.policy_loader import PolicyLoader
from backend.app.services.decision_engine.priority_calculator import PriorityCalculator
from backend.app.services.decision_engine.repositories.decision_repository import (
    SQLiteDecisionRepository,
)
from backend.app.services.decision_engine.service import DecisionEngineService
from backend.app.services.ai_processing.cache import MemoryAICache
from backend.app.services.ai_processing.field_extractor import FieldExtractor
from backend.app.services.ai_processing.model_gateway import (
    HTTPModelGateway,
    KimiChatGateway,
    MockModelGateway,
)
from backend.app.services.ai_processing.models import AIModelConfig
from backend.app.services.ai_processing.prompt_builder import PromptBuilder
from backend.app.services.ai_processing.repositories.ai_analysis_repository import (
    SQLiteAIAnalysisRepository,
)
from backend.app.services.ai_processing.result_validator import ResultValidator
from backend.app.services.ai_processing.service import AIProcessingService
from backend.app.services.ai_processing.summary_generator import SummaryGenerator
from backend.app.services.campus_auth.cooldown_guard import LoginCooldownGuard
from backend.app.services.campus_auth.providers.browser_cookie_provider import (
    BrowserCookieCampusAuthProvider,
)
from backend.app.services.campus_auth.providers.szu_web_provider import (
    SzuWebCampusAuthProvider,
)
from backend.app.services.campus_auth.service import CampusAuthService
from backend.app.services.config import ConfigFilePaths, ConfigService, FileConfigStore, SQLiteConfigStore
from backend.app.services.delivery.channel_router import DeliveryChannelRouter
from backend.app.services.delivery.digest_composer import DigestComposer
from backend.app.services.delivery.gateway_manager import GatewayManager
from backend.app.services.delivery.planner import DeliveryPlanner
from backend.app.services.delivery.renderer import MessageRenderer
from backend.app.services.delivery.repositories.delivery_log_repository import (
    DeliveryLogRepository,
)
from backend.app.services.delivery.repositories.digest_job_repository import (
    DigestJobRepository,
)
from backend.app.services.delivery.retry_manager import RetryManager
from backend.app.services.delivery.service import DeliveryService
from backend.app.services.ingestion.connector_manager import ConnectorManager
from backend.app.services.ingestion.deduplicator import Deduplicator
from backend.app.services.ingestion.normalizer import Normalizer
from backend.app.services.ingestion.registry import SourceRegistry
from backend.app.services.ingestion.repositories.raw_event_repository import RawEventRepository
from backend.app.services.ingestion.scheduler import Scheduler
from backend.app.services.ingestion.service import IngestionService
from backend.app.services.ingestion.webhook_receiver import WebhookReceiver
from backend.app.services.message_probe import MessageProbeService
from backend.app.services.profile_compat.mappers.szu_mapper import SzuProfileMapper
from backend.app.services.profile_compat.merge import ProfileMergePolicy
from backend.app.services.profile_compat.service import ProfileCompatibilityService
from backend.app.services.profile_sampling.auth.browser_session_provider import (
    BrowserCookieAuthProvider,
)
from backend.app.services.profile_sampling.auth.offline_auth_provider import (
    OfflineFixtureAuthProvider,
)
from backend.app.services.profile_sampling.auth.szu_http_cas_provider import (
    SzuHTTPCasProvider,
)
from backend.app.services.profile_sampling.samplers.szu.board_identity_sampler import (
    SzuBoardIdentitySampler,
)
from backend.app.services.profile_sampling.samplers.szu.academic_completion_sampler import (
    SzuAcademicCompletionSampler,
)
from backend.app.services.profile_sampling.samplers.szu.hint_payload_sampler import (
    SzuHintPayloadSampler,
)
from backend.app.services.profile_sampling.samplers.szu.personal_info_sampler import (
    SzuPersonalInfoSampler,
)
from backend.app.services.profile_sampling.service import ProfileSamplingService
from backend.app.services.rule_engine.action_risk_evaluator import ActionRiskEvaluator
from backend.app.services.rule_engine.ai_trigger_gate import AITriggerGate
from backend.app.services.rule_engine.audience_matcher import AudienceMatcher
from backend.app.services.rule_engine.config_loader import RuleConfigLoader
from backend.app.services.rule_engine.preprocessor import EventPreprocessor
from backend.app.services.rule_engine.repositories.rule_analysis_repository import (
    RuleAnalysisRepository,
)
from backend.app.services.rule_engine.service import RuleEngineService
from backend.app.services.rule_engine.signal_extractor import SignalExtractor
from backend.app.services.user_profile.course_sync_adapter import CourseSyncAdapter
from backend.app.services.user_profile.credit_status_manager import CreditStatusManager
from backend.app.services.user_profile.graduation_status_manager import GraduationStatusManager
from backend.app.services.user_profile.preference_manager import PreferenceManager
from backend.app.services.user_profile.profile_context_selector import ProfileContextSelector
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository
from backend.app.services.user_profile.service import UserProfileService
from backend.app.services.user_profile.snapshot_builder import SnapshotBuilder
from backend.app.workflows.profile_sync_orchestrator import ProfileSyncOrchestrator
from backend.app.workflows.orchestrator import WorkflowOrchestrator


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    config_service: ConfigService
    source_registry: SourceRegistry
    connector_manager: ConnectorManager
    raw_event_repository: RawEventRepository
    ai_analysis_repository: SQLiteAIAnalysisRepository
    rule_analysis_repository: RuleAnalysisRepository
    decision_repository: SQLiteDecisionRepository
    delivery_dispatch_log_repository: DeliveryLogRepository
    digest_job_repository: DigestJobRepository
    delivery_log_repository: DeliveryLogRepository
    feedback_repository: Any | None
    optimization_sample_repository: Any | None
    user_profile_repository: SQLiteUserProfileRepository
    ingestion_service: IngestionService
    ai_processing_service: AIProcessingService
    rule_engine_service: RuleEngineService
    decision_service: DecisionEngineService
    delivery_service: DeliveryService
    feedback_service: Any | None
    user_profile_service: UserProfileService
    campus_auth_service: CampusAuthService
    profile_sampling_service: ProfileSamplingService
    profile_compatibility_service: ProfileCompatibilityService
    profile_sync_orchestrator: ProfileSyncOrchestrator
    webhook_receiver: WebhookReceiver
    scheduler: Scheduler
    workflow_orchestrator: WorkflowOrchestrator
    message_probe_service: MessageProbeService


def _resolve_ai_runtime_config(
    settings: Settings,
    config_service: ConfigService,
) -> Any:
    default_prompt_template_path = (
        settings.project_root
        / "backend"
        / "app"
        / "services"
        / "ai_processing"
        / "prompts"
        / "notice_analysis_v1.txt"
    )
    runtime_config = config_service.get_ai_runtime_config_sync()
    runtime_overrides = settings.resolve_ai_runtime_overrides(default_prompt_template_path)
    if not runtime_overrides:
        return runtime_config
    return runtime_config.model_copy(update=runtime_overrides)


def build_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or Settings()
    settings.ensure_directories()
    init_database(settings.database_path)
    seed_store = FileConfigStore(
        ConfigFilePaths(
            source_config_path=settings.source_config_path,
            rule_config_path=settings.rule_config_path,
            notification_category_path=settings.notification_category_path,
            ai_runtime_config_path=settings.ai_runtime_config_path,
            delivery_channel_config_path=settings.delivery_channel_config_path,
            push_policy_path=settings.push_policy_path,
            audit_log_path=settings.config_audit_log_path,
        )
    )
    primary_store = (
        SQLiteConfigStore(settings.database_path, runtime_store=seed_store)
        if settings.config_backend == "sqlite"
        else seed_store
    )
    config_service = ConfigService(primary_store)
    if settings.config_backend == "sqlite":
        config_service.ensure_seed_data(seed_store)
    ai_runtime_config = _resolve_ai_runtime_config(settings, config_service)

    delivery_channel_configs = {
        item.channel: item.config
        for item in config_service.list_delivery_channel_configs_sync()
        if item.enabled
    }

    source_registry = SourceRegistry(config_service)
    normalizer = Normalizer()
    connector_manager = ConnectorManager(normalizer)
    raw_event_repository = RawEventRepository(settings.database_path)
    deduplicator = Deduplicator(raw_event_repository)
    ingestion_service = IngestionService(connector_manager, raw_event_repository, deduplicator)
    rule_analysis_repository = RuleAnalysisRepository(settings.database_path)
    rule_engine_service = RuleEngineService(
        config_loader=RuleConfigLoader(config_service),
        preprocessor=EventPreprocessor(),
        signal_extractor=SignalExtractor(),
        audience_matcher=AudienceMatcher(),
        action_risk_evaluator=ActionRiskEvaluator(),
        ai_trigger_gate=AITriggerGate(),
        repository=rule_analysis_repository,
    )
    ai_analysis_repository = SQLiteAIAnalysisRepository(settings.database_path)
    ai_model_config = AIModelConfig(
        enabled=ai_runtime_config.enabled,
        provider=ai_runtime_config.provider,
        model_name=ai_runtime_config.model_name,
        prompt_version=ai_runtime_config.prompt_version,
        endpoint=ai_runtime_config.endpoint,
        api_key=ai_runtime_config.api_key,
        timeout_seconds=ai_runtime_config.timeout_seconds,
        max_retries=ai_runtime_config.max_retries,
        metadata=ai_runtime_config.metadata,
    )
    if ai_runtime_config.provider == "mock":
        model_gateway = MockModelGateway()
    elif ai_runtime_config.provider == "kimi":
        model_gateway = KimiChatGateway(
            base_url=ai_runtime_config.endpoint,
            api_key=ai_runtime_config.api_key,
        )
    else:
        model_gateway = HTTPModelGateway(
            endpoint=ai_runtime_config.endpoint,
            api_key=ai_runtime_config.api_key,
        )
    ai_processing_service = AIProcessingService(
        prompt_builder=PromptBuilder(
            template_path=ai_runtime_config.template_path,
            prompt_version=ai_runtime_config.prompt_version,
        ),
        model_gateway=model_gateway,
        field_extractor=FieldExtractor(),
        summary_generator=SummaryGenerator(),
        result_validator=ResultValidator(),
        repository=ai_analysis_repository,
        cache=MemoryAICache(),
        model_config=ai_model_config,
        timezone=settings.timezone,
    )
    decision_repository = SQLiteDecisionRepository(settings.database_path)
    decision_service = DecisionEngineService(
        policy_loader=PolicyLoader(config_service),
        evidence_aggregator=EvidenceAggregator(),
        priority_calculator=PriorityCalculator(),
        action_resolver=ActionResolver(),
        channel_resolver=ChannelResolver(),
        decision_repository=decision_repository,
        timezone_offset=settings.timezone,
    )
    delivery_dispatch_log_repository = DeliveryLogRepository(settings.database_path)
    digest_job_repository = DigestJobRepository(settings.database_path)
    delivery_renderer = MessageRenderer()
    delivery_gateway_manager = GatewayManager()
    delivery_retry_manager = RetryManager()
    digest_composer = DigestComposer(
        repository=digest_job_repository,
        gateway_manager=delivery_gateway_manager,
        retry_manager=delivery_retry_manager,
        log_repository=delivery_dispatch_log_repository,
        renderer=delivery_renderer,
        timezone_offset=settings.timezone,
    )
    delivery_service = DeliveryService(
        planner=DeliveryPlanner(
            channel_router=DeliveryChannelRouter(),
            renderer=delivery_renderer,
        ),
        gateway_manager=delivery_gateway_manager,
        retry_manager=delivery_retry_manager,
        digest_composer=digest_composer,
        log_repository=delivery_dispatch_log_repository,
        timezone_offset=settings.timezone,
        default_channel_configs=delivery_channel_configs,
    )
    delivery_log_repository = delivery_dispatch_log_repository
    feedback_repository = None
    optimization_sample_repository = None
    feedback_service = None
    try:
        from backend.app.services.feedback.delivery_outcome_collector import DeliveryOutcomeCollector
        from backend.app.services.feedback.exporter import FeedbackExporter
        from backend.app.services.feedback.receiver import FeedbackReceiver
        from backend.app.services.feedback.repositories.feedback_repository import (
            SQLiteFeedbackRepository,
        )
        from backend.app.services.feedback.repositories.sample_repository import (
            SQLiteOptimizationSampleRepository,
        )
        from backend.app.services.feedback.sample_assembler import SampleAssembler
        from backend.app.services.feedback.service import FeedbackService
    except ModuleNotFoundError:
        pass
    else:
        feedback_repository = SQLiteFeedbackRepository(settings.database_path)
        optimization_sample_repository = SQLiteOptimizationSampleRepository(settings.database_path)
        sample_assembler = SampleAssembler(
            raw_event_repository=raw_event_repository,
            rule_analysis_repository=rule_analysis_repository,
            ai_analysis_repository=ai_analysis_repository,
            decision_repository=decision_repository,
            delivery_log_repository=delivery_log_repository,
            feedback_repository=feedback_repository,
            timezone_offset=settings.timezone,
        )
        feedback_service = FeedbackService(
            receiver=FeedbackReceiver(timezone_offset=settings.timezone),
            feedback_repository=feedback_repository,
            delivery_outcome_collector=DeliveryOutcomeCollector(
                delivery_log_repository=delivery_log_repository,
                sample_assembler=sample_assembler,
                sample_repository=optimization_sample_repository,
            ),
            sample_assembler=sample_assembler,
            sample_repository=optimization_sample_repository,
            exporter=FeedbackExporter(optimization_sample_repository),
        )
    user_profile_repository = SQLiteUserProfileRepository(settings.database_path, settings.timezone)
    user_profile_service = UserProfileService(
        repository=user_profile_repository,
        snapshot_builder=SnapshotBuilder(
            repository=user_profile_repository,
            course_sync_adapter=CourseSyncAdapter(user_profile_repository),
            credit_status_manager=CreditStatusManager(user_profile_repository),
            graduation_status_manager=GraduationStatusManager(user_profile_repository),
            preference_manager=PreferenceManager(user_profile_repository),
        ),
        profile_context_selector=ProfileContextSelector(settings.timezone),
    )
    campus_auth_service = CampusAuthService()
    campus_auth_service.register_provider(
        school_code="szu",
        auth_mode="browser_cookie_import",
        provider=BrowserCookieCampusAuthProvider(),
    )
    campus_auth_service.register_provider(
        school_code="szu",
        auth_mode="cli_cas",
        provider=SzuWebCampusAuthProvider(
            cooldown_guard=LoginCooldownGuard(
                settings.data_dir / "campus_auth_cooldowns.json",
            )
        ),
    )
    profile_sampling_service = ProfileSamplingService()
    profile_sampling_service.register_auth_provider(
        school_code="szu",
        auth_mode="offline_fixture",
        provider=OfflineFixtureAuthProvider(),
    )
    profile_sampling_service.register_auth_provider(
        school_code="szu",
        auth_mode="browser_cookie_import",
        provider=BrowserCookieAuthProvider(
            campus_auth_service=campus_auth_service,
            school_code="szu",
            target_system="board",
            entry_url="https://www1.szu.edu.cn/board/",
        ),
    )
    profile_sampling_service.register_auth_provider(
        school_code="szu",
        auth_mode="browser_cookie_import_ehall",
        provider=BrowserCookieAuthProvider(
            campus_auth_service=campus_auth_service,
            school_code="szu",
            target_system="ehall",
            entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
        ),
    )
    profile_sampling_service.register_auth_provider(
        school_code="szu",
        auth_mode="szu_http_cas",
        provider=SzuHTTPCasProvider(
            campus_auth_service=campus_auth_service,
            target_system="board",
            entry_url="https://www1.szu.edu.cn/board/",
        ),
    )
    profile_sampling_service.register_auth_provider(
        school_code="szu",
        auth_mode="szu_http_cas_ehall",
        provider=SzuHTTPCasProvider(
            campus_auth_service=campus_auth_service,
            target_system="ehall",
            entry_url="https://ehall.szu.edu.cn/appShow?appId=4980269146247992",
        ),
    )
    profile_sampling_service.register_sampler("szu", SzuHintPayloadSampler())
    profile_sampling_service.register_sampler("szu", SzuBoardIdentitySampler())
    profile_sampling_service.register_sampler("szu", SzuPersonalInfoSampler())
    profile_sampling_service.register_sampler("szu", SzuAcademicCompletionSampler())
    profile_compatibility_service = ProfileCompatibilityService()
    profile_compatibility_service.register_mapper(
        "szu",
        SzuProfileMapper(merge_policy=ProfileMergePolicy()),
    )
    profile_sync_orchestrator = ProfileSyncOrchestrator(
        sampling_service=profile_sampling_service,
        compatibility_service=profile_compatibility_service,
        user_profile_repository=user_profile_repository,
        user_profile_service=user_profile_service,
    )
    webhook_receiver = WebhookReceiver(source_registry, connector_manager, ingestion_service)
    scheduler = Scheduler(source_registry, connector_manager, ingestion_service)
    workflow_orchestrator = WorkflowOrchestrator(
        raw_event_repository=raw_event_repository,
        user_profile_service=user_profile_service,
        rule_engine_service=rule_engine_service,
        ai_processing_service=ai_processing_service,
        decision_service=decision_service,
        delivery_service=delivery_service,
        feedback_service=feedback_service,
    )
    message_probe_service = MessageProbeService(
        source_registry=source_registry,
        connector_manager=connector_manager,
        ingestion_service=ingestion_service,
        workflow_orchestrator=workflow_orchestrator,
        user_profile_service=user_profile_service,
        timezone_offset=settings.timezone,
    )

    return AppContainer(
        settings=settings,
        config_service=config_service,
        source_registry=source_registry,
        connector_manager=connector_manager,
        raw_event_repository=raw_event_repository,
        ai_analysis_repository=ai_analysis_repository,
        rule_analysis_repository=rule_analysis_repository,
        decision_repository=decision_repository,
        delivery_dispatch_log_repository=delivery_dispatch_log_repository,
        digest_job_repository=digest_job_repository,
        delivery_log_repository=delivery_log_repository,
        feedback_repository=feedback_repository,
        optimization_sample_repository=optimization_sample_repository,
        user_profile_repository=user_profile_repository,
        ingestion_service=ingestion_service,
        ai_processing_service=ai_processing_service,
        rule_engine_service=rule_engine_service,
        decision_service=decision_service,
        delivery_service=delivery_service,
        feedback_service=feedback_service,
        user_profile_service=user_profile_service,
        campus_auth_service=campus_auth_service,
        profile_sampling_service=profile_sampling_service,
        profile_compatibility_service=profile_compatibility_service,
        profile_sync_orchestrator=profile_sync_orchestrator,
        webhook_receiver=webhook_receiver,
        scheduler=scheduler,
        workflow_orchestrator=workflow_orchestrator,
        message_probe_service=message_probe_service,
    )
