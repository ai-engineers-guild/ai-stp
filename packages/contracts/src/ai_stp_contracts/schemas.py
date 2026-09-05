"""Repository-wide schema generation entrypoint (SPEC-015 REQ-1509).

The wire contract is the outermost boundary of the system — every other layer
is something that eventually crosses it — so ``contracts`` now sits at the top
of the package chain and aggregates the whole exported corpus: foundation
primitives, passport models, evidence records and the ``/v1`` payloads. The
justfile targets ``gen-schemas`` and ``check-schemas`` call this module, so a
schema without a generator and a generator without a schema fail the same gate.

Usage:
    python -m ai_stp_contracts.schemas schemas/v1
    python -m ai_stp_contracts.schemas --check schemas/v1
"""

import argparse
import sys
from pathlib import Path
from typing import Final

from ai_stp_assurance.schemas import EXPORTED_MODELS as ASSURANCE_STACK_MODELS
from ai_stp_contracts.auth import (
    AuthLogoutResponse,
    AuthMeResponse,
    DeviceAuthorizationRequest,
    DeviceAuthorizationResponse,
    DeviceChallengeRequest,
    DeviceChallengeResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
    LegalOnboardingCompleteRequest,
    LegalOnboardingStatus,
    OAuthCallbackResult,
    SystemVersionResponse,
)
from ai_stp_contracts.authoring import (
    ComponentScaffoldPlan,
    ComponentScaffoldResult,
    SetupScaffoldPlan,
    SetupScaffoldResult,
)
from ai_stp_contracts.catalog import (
    CatalogReactionList,
    CatalogReactionState,
    CatalogUsageMetrics,
    ComponentContextBudget,
    ComponentDetail,
    ComponentListResponse,
    ComponentSearchRequest,
    ComponentVersionResponse,
    GitHubMetadata,
    SetupContextBudget,
    SetupContextBudgetQuery,
    SetupDetail,
    SetupListResponse,
    SetupSearchRequest,
    SetupVersionResponse,
)
from ai_stp_contracts.complaints import ComplaintCreateRequest, ComplaintCreateResponse
from ai_stp_contracts.component_passport import ComponentPassportPatch
from ai_stp_contracts.content import (
    ContentDetail,
    ContentListResponse,
    ContentLocaleQuery,
    ContentRepositoryImportRequest,
    ContentRepositoryImportResponse,
    ContentRepositoryState,
    ContentSnapshotEntry,
    ContentSummary,
    StaffContentPublishRequest,
    StaffContentPublishResponse,
    StaffContentTranslation,
    StaffContentTranslations,
    StaffContentUnpublishRequest,
    StaffContentUnpublishResponse,
)
from ai_stp_contracts.deep_links import DeepLinkView
from ai_stp_contracts.estate_release import EstateRelease
from ai_stp_contracts.evaluation import SetupEvalPlan, SetupEvalProfile, SetupEvalResult
from ai_stp_contracts.federation import (
    CatalogExternalCoordinate,
    CatalogMetadataObservation,
    CatalogMetadataObservationSet,
    FederatedSourceDescriptor,
    FederatedSourceSet,
)
from ai_stp_contracts.github_evidence import GitHubArchiveEvidence, GitHubArchiveHistory
from ai_stp_contracts.grants import (
    AccessGrantResponse,
    CliGrantAccessView,
    CliGrantInvitationView,
    CliGrantListView,
    CliGrantRevokeView,
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantInvitationResponse,
    GrantListResponse,
    GrantRevokeRequest,
    GrantRevokeResponse,
)
from ai_stp_contracts.health import LivenessResponse, ReadinessResponse
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.identity import (
    AccountIdentityUpdate,
    AccountProfile,
    DeviceListResponse,
    DeviceRegisterResponse,
    DeviceRevokeRequest,
    DeviceRevokeResponse,
    DeviceSummary,
)
from ai_stp_contracts.impact import (
    AccountSelectionImpactQuery,
    AccountSelectionImpactReport,
    BlastRadiusReport,
    SelectionImpactReport,
)
from ai_stp_contracts.machine_help import (
    AuthStatus,
    Capabilities,
    CatalogArtifactView,
    CatalogObjectView,
    CatalogSearchResult,
    CatalogSetupAcquisition,
    CatalogVersionView,
    CliSignedAttestation,
    ComponentPassportSuggestions,
    ComponentPassportValidation,
    ComponentPromotionPlan,
    ComponentQualityReport,
    ComponentScaffoldView,
    ComponentTemplateView,
    CompositionReports,
    ConfigReport,
    ConfirmationView,
    ConformanceReport,
    ConsentRecord,
    ConsentSummary,
    DeviceApproval,
    DeviceIdentity,
    DoctorReport,
    EligibilityMatrix,
    EligibilityReport,
    ExternalSourceIdentity,
    HarnessBundle,
    HarnessCapabilityTable,
    HarnessProgram,
    HarnessProgramStatus,
    HarnessSurvey,
    ImportedSetup,
    ImportInspection,
    InstallationStatus,
    InstallationView,
    LocalSearchResults,
    MachineHelp,
    MultiRootTransactionView,
    NativeComponents,
    PassportView,
    ProjectCandidates,
    ProjectIndex,
    ProjectSymbols,
    ProposalSession,
    ProviderBoundRelease,
    ProviderInstallationReport,
    ProviderNetworkCapability,
    ProviderReplacementPlan,
    ProviderReplacementResult,
    ProviderTrust,
    PublicationPlanView,
    PublicationSetView,
    RecoveryView,
    RollbackTarget,
    SetupComposePlan,
    SetupComposeResult,
    SetupExportResult,
    SetupGraph,
    SetupImportPlan,
    SetupUpdatePlan,
    SetupUpdateResult,
    SkillDelivery,
    SkillPackageReport,
    SourceSearchResult,
    SyncPreview,
    SyncPullView,
    SyncPushView,
    TargetBackups,
    TargetDiff,
    TargetSurvey,
    TelemetryStatus,
    ToolchainProfile,
    ToolInstallation,
    VersionLine,
    VersionReport,
)
from ai_stp_contracts.official_manifest import OfficialManifest, OfficialManifestEntry
from ai_stp_contracts.openapi import render as render_openapi
from ai_stp_contracts.owner import (
    CliOwnerObjectDetailView,
    CliOwnerObjectListView,
    CliOwnerVersionDetailView,
    OwnerLifecycleRequest,
    OwnerLifecycleResponse,
    OwnerObjectDetail,
    OwnerObjectListQuery,
    OwnerObjectListResponse,
    OwnerObjectSummary,
    OwnerStartPublicationRequest,
    OwnerVersionDetail,
    OwnerVersionSummary,
    StaffReportDetail,
    StaffReportListQuery,
    StaffReportListResponse,
    StaffReportSummary,
)
from ai_stp_contracts.ownership import (
    OwnershipClaimCreateRequest,
    OwnershipClaimPreview,
    OwnershipClaimResponse,
    OwnershipRevisionListResponse,
    OwnershipRevisionView,
)
from ai_stp_contracts.publication import (
    AuthorAttestation,
    EvidenceBindingView,
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)
from ai_stp_contracts.reports import (
    CliReportCaseView,
    CliReportListView,
    CliReportPreview,
    ReportCaseCreateRequest,
    ReportCaseListResponse,
    ReportCaseResponse,
    StaffActionResponse,
    StaffAuthorVerificationRequest,
    StaffLifecycleRequest,
    StaffTriageRequest,
)
from ai_stp_contracts.seo import (
    SeoCatalogPage,
    SeoCatalogQuery,
    SeoIndexResponse,
    SeoPublicProfile,
    SeoRollbackRequest,
    SeoRollbackResponse,
    SeoSitemapShard,
    SeoSubjectQuery,
)
from ai_stp_contracts.standard import StandardInventory, inventory_for
from ai_stp_contracts.store_ports import (
    StorePortDiscovery,
    StorePortImportPlan,
    StorePortImportResult,
    StorePortInspection,
)
from ai_stp_contracts.sync import (
    SyncConflictInfo,
    SyncEvent,
    SyncEventReceipt,
    SyncPullQuery,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    SyncStreamEvent,
)
from ai_stp_foundation.schemas import ExportedSchema, check, schema_id, write

#: The `/v1` HTTP boundary. Every one of these is served by a route, and a test
#: rejects any that is not.
HTTP_MODELS: Final[dict[str, ExportedSchema]] = {
    "catalog-component-detail": ComponentDetail,
    "catalog-component-context-budget": ComponentContextBudget,
    "catalog-component-list": ComponentListResponse,
    "catalog-component-search": ComponentSearchRequest,
    "catalog-component-version": ComponentVersionResponse,
    "catalog-setup-detail": SetupDetail,
    "catalog-setup-list": SetupListResponse,
    "catalog-setup-search": SetupSearchRequest,
    "catalog-setup-version": SetupVersionResponse,
    "catalog-github-metadata": GitHubMetadata,
    "catalog-usage-metrics": CatalogUsageMetrics,
    "catalog-reaction-list": CatalogReactionList,
    "catalog-reaction-state": CatalogReactionState,
    "catalog-setup-context-budget": SetupContextBudget,
    "catalog-setup-context-budget-query": SetupContextBudgetQuery,
    "auth-device-authorization-request": DeviceAuthorizationRequest,
    "auth-device-authorization-response": DeviceAuthorizationResponse,
    "auth-device-token-request": DeviceTokenRequest,
    "auth-device-token-response": DeviceTokenResponse,
    "auth-oauth-callback-result": OAuthCallbackResult,
    "auth-me-response": AuthMeResponse,
    "legal-onboarding-complete-request": LegalOnboardingCompleteRequest,
    "legal-onboarding-status": LegalOnboardingStatus,
    "auth-logout-response": AuthLogoutResponse,
    "auth-device-challenge-request": DeviceChallengeRequest,
    "auth-device-challenge-response": DeviceChallengeResponse,
    "system-version-response": SystemVersionResponse,
    "health-liveness": LivenessResponse,
    "identity-account-profile": AccountProfile,
    "identity-account-update": AccountIdentityUpdate,
    "identity-device-list": DeviceListResponse,
    "identity-device-register-response": DeviceRegisterResponse,
    "identity-device-revoke-request": DeviceRevokeRequest,
    "identity-device-revoke-response": DeviceRevokeResponse,
    "identity-device-summary": DeviceSummary,
    "health-readiness": ReadinessResponse,
    "page-info": PageInfo,
    "sync-event": SyncEvent,
    "sync-push-request": SyncPushRequest,
    "sync-event-receipt": SyncEventReceipt,
    "sync-conflict-info": SyncConflictInfo,
    "sync-push-response": SyncPushResponse,
    "sync-pull-query": SyncPullQuery,
    "sync-stream-event": SyncStreamEvent,
    "sync-pull-response": SyncPullResponse,
    "publication-plan-create-request": PublicationPlanCreateRequest,
    "publication-plan-response": PublicationPlanResponse,
    "publication-confirm-request": PublicationConfirmRequest,
    "publication-author-attestation": AuthorAttestation,
    "publication-evidence-binding": EvidenceBindingView,
    "grant-invitation-create-request": GrantInvitationCreateRequest,
    "grant-direct-create-request": DirectGrantCreateRequest,
    "grant-invitation-response": GrantInvitationResponse,
    "grant-accept-request": GrantAcceptRequest,
    "grant-list-response": GrantListResponse,
    "grant-access-response": AccessGrantResponse,
    "grant-revoke-request": GrantRevokeRequest,
    "grant-revoke-response": GrantRevokeResponse,
    "report-case-create-request": ReportCaseCreateRequest,
    "report-case-response": ReportCaseResponse,
    "complaint-create-request": ComplaintCreateRequest,
    "complaint-create-response": ComplaintCreateResponse,
    "report-case-list-response": ReportCaseListResponse,
    "staff-triage-request": StaffTriageRequest,
    "staff-lifecycle-request": StaffLifecycleRequest,
    "staff-author-verification-request": StaffAuthorVerificationRequest,
    "staff-action-response": StaffActionResponse,
    "owner-object-list-query": OwnerObjectListQuery,
    "owner-object-list-response": OwnerObjectListResponse,
    "owner-object-summary": OwnerObjectSummary,
    "owner-object-detail": OwnerObjectDetail,
    "owner-version-summary": OwnerVersionSummary,
    "owner-version-detail": OwnerVersionDetail,
    "staff-report-list-query": StaffReportListQuery,
    "staff-report-list-response": StaffReportListResponse,
    "staff-report-summary": StaffReportSummary,
    "staff-report-detail": StaffReportDetail,
    "owner-lifecycle-request": OwnerLifecycleRequest,
    "owner-lifecycle-response": OwnerLifecycleResponse,
    "owner-start-publication-request": OwnerStartPublicationRequest,
    "ownership-claim-create-request": OwnershipClaimCreateRequest,
    "ownership-claim-preview": OwnershipClaimPreview,
    "ownership-claim-response": OwnershipClaimResponse,
    "ownership-revision-list-response": OwnershipRevisionListResponse,
    "ownership-revision-view": OwnershipRevisionView,
    "account-selection-impact-query": AccountSelectionImpactQuery,
    "account-selection-impact-report": AccountSelectionImpactReport,
    "seo-public-profile": SeoPublicProfile,
    "seo-subject-query": SeoSubjectQuery,
    "seo-index-response": SeoIndexResponse,
    "seo-sitemap-shard": SeoSitemapShard,
    "seo-catalog-query": SeoCatalogQuery,
    "seo-catalog-page": SeoCatalogPage,
    "seo-rollback-request": SeoRollbackRequest,
    "content-locale-query": ContentLocaleQuery,
    "content-summary": ContentSummary,
    "content-detail": ContentDetail,
    "content-list": ContentListResponse,
    "content-repository-state": ContentRepositoryState,
    "content-snapshot-entry": ContentSnapshotEntry,
    "content-repository-import-request": ContentRepositoryImportRequest,
    "content-repository-import-response": ContentRepositoryImportResponse,
    "staff-content-translation": StaffContentTranslation,
    "staff-content-translations": StaffContentTranslations,
    "staff-content-publish-request": StaffContentPublishRequest,
    "staff-content-publish-response": StaffContentPublishResponse,
    "staff-content-unpublish-request": StaffContentUnpublishRequest,
    "staff-content-unpublish-response": StaffContentUnpublishResponse,
    "seo-rollback-response": SeoRollbackResponse,
}

#: The agent-to-CLI boundary (issue #72). Published under the same gate and for
#: the same reason — five harness projections read it — but it is **not** HTTP:
#: no route serves it, and a test pins that it never leaks into the OpenAPI
#: document, so the two surfaces cannot be confused for one.
CLI_MODELS: Final[dict[str, ExportedSchema]] = {
    "cli-signed-attestation": CliSignedAttestation,
    "cli-owner-object-list": CliOwnerObjectListView,
    "cli-owner-object-detail": CliOwnerObjectDetailView,
    "cli-owner-version-detail": CliOwnerVersionDetailView,
    "cli-report-preview": CliReportPreview,
    "cli-report-case": CliReportCaseView,
    "cli-report-list": CliReportListView,
    "official-manifest": OfficialManifest,
    "official-manifest-entry": OfficialManifestEntry,
    "cli-grant-invitation": CliGrantInvitationView,
    "cli-grant-access": CliGrantAccessView,
    "cli-grant-list": CliGrantListView,
    "cli-grant-revoke": CliGrantRevokeView,
    "cli-publication-plan": PublicationPlanView,
    "cli-publication-set": PublicationSetView,
    "cli-auth-status": AuthStatus,
    "cli-capabilities": Capabilities,
    "cli-catalog-object": CatalogObjectView,
    "cli-catalog-search": CatalogSearchResult,
    "cli-catalog-artifact": CatalogArtifactView,
    "cli-catalog-setup-acquisition": CatalogSetupAcquisition,
    "cli-catalog-version": CatalogVersionView,
    "cli-harness-survey": HarnessSurvey,
    "cli-harness-capability-table": HarnessCapabilityTable,
    "cli-project-candidates": ProjectCandidates,
    "cli-project-index": ProjectIndex,
    "cli-project-symbols": ProjectSymbols,
    "cli-version-line": VersionLine,
    "cli-skill-delivery": SkillDelivery,
    "cli-sync-preview": SyncPreview,
    "cli-sync-pull": SyncPullView,
    "cli-sync-push": SyncPushView,
    "cli-toolchain-profile": ToolchainProfile,
    "cli-toolchain-installation": ToolInstallation,
    "cli-harness-program": HarnessProgram,
    "cli-harness-program-status": HarnessProgramStatus,
    "cli-device-approval": DeviceApproval,
    "cli-config-report": ConfigReport,
    "cli-consent-record": ConsentRecord,
    "cli-consent-summary": ConsentSummary,
    "cli-local-search": LocalSearchResults,
    "cli-eligibility-report": EligibilityReport,
    "cli-eligibility-matrix": EligibilityMatrix,
    "cli-selection-impact-report": SelectionImpactReport,
    "cli-blast-radius-report": BlastRadiusReport,
    "cli-proposal-session": ProposalSession,
    "cli-confirmation": ConfirmationView,
    "cli-setup-graph": SetupGraph,
    "cli-setup-update-plan": SetupUpdatePlan,
    "cli-setup-update-result": SetupUpdateResult,
    "cli-setup-compose-plan": SetupComposePlan,
    "cli-setup-compose-result": SetupComposeResult,
    "cli-setup-export-result": SetupExportResult,
    "cli-source-search": SourceSearchResult,
    "cli-composition-reports": CompositionReports,
    "cli-component-promotion-plan": ComponentPromotionPlan,
    "cli-component-passport-patch": ComponentPassportPatch,
    "cli-component-passport-validation": ComponentPassportValidation,
    "cli-component-quality-report": ComponentQualityReport,
    "cli-component-passport-suggestions": ComponentPassportSuggestions,
    "cli-component-scaffold": ComponentScaffoldView,
    "cli-component-scaffold-plan": ComponentScaffoldPlan,
    "cli-component-scaffold-result": ComponentScaffoldResult,
    "cli-setup-scaffold-plan": SetupScaffoldPlan,
    "cli-setup-scaffold-result": SetupScaffoldResult,
    "cli-store-port-discovery": StorePortDiscovery,
    "cli-store-port-inspection": StorePortInspection,
    "cli-store-port-import-plan": StorePortImportPlan,
    "cli-store-port-import-result": StorePortImportResult,
    "cli-component-template": ComponentTemplateView,
    "cli-setup-eval-profile": SetupEvalProfile,
    "cli-setup-eval-plan": SetupEvalPlan,
    "cli-setup-eval-result": SetupEvalResult,
    "cli-harness-bundle": HarnessBundle,
    "cli-conformance-report": ConformanceReport,
    "cli-provider-network-capability": ProviderNetworkCapability,
    "cli-provider-bound-release": ProviderBoundRelease,
    "cli-provider-installations": ProviderInstallationReport,
    "cli-skill-package": SkillPackageReport,
    "cli-provider-replacement-plan": ProviderReplacementPlan,
    "cli-provider-replacement-result": ProviderReplacementResult,
    "cli-provider-trust": ProviderTrust,
    "ai-stp-estate-release": EstateRelease,
    "cli-installation": InstallationView,
    "cli-installation-status": InstallationStatus,
    "cli-multi-root-transaction": MultiRootTransactionView,
    "cli-recovery-report": RecoveryView,
    "cli-import-inspection": ImportInspection,
    "cli-setup-import-plan": SetupImportPlan,
    "cli-imported-setup": ImportedSetup,
    "cli-target-survey": TargetSurvey,
    "cli-target-diff": TargetDiff,
    "cli-rollback-target": RollbackTarget,
    "cli-target-backups": TargetBackups,
    "cli-telemetry-status": TelemetryStatus,
    "cli-native-components": NativeComponents,
    "cli-external-source-identity": ExternalSourceIdentity,
    "cli-github-archive-evidence": GitHubArchiveEvidence,
    "cli-github-archive-history": GitHubArchiveHistory,
    "federated-source-descriptor": FederatedSourceDescriptor,
    "federated-source-set": FederatedSourceSet,
    "catalog-external-coordinate": CatalogExternalCoordinate,
    "catalog-metadata-observation": CatalogMetadataObservation,
    "catalog-metadata-observation-set": CatalogMetadataObservationSet,
    "cli-device-identity": DeviceIdentity,
    "cli-deep-link": DeepLinkView,
    "cli-doctor-report": DoctorReport,
    "cli-machine-help": MachineHelp,
    "cli-passport-view": PassportView,
    "cli-version-report": VersionReport,
    "cli-standard-inventory": StandardInventory,
}

CONTRACT_MODELS: Final[dict[str, ExportedSchema]] = {**HTTP_MODELS, **CLI_MODELS}

EXPORTED_MODELS: Final[dict[str, ExportedSchema]] = {
    **ASSURANCE_STACK_MODELS,
    **CONTRACT_MODELS,
}


def current_inventory() -> StandardInventory:
    """Inventory of exported schema ids plus the closed protocol axes."""
    members = tuple(("http_schema", schema_id(name)) for name in HTTP_MODELS) + tuple(
        ("exported_schema", schema_id(name)) for name in EXPORTED_MODELS if name not in HTTP_MODELS
    )
    return inventory_for(members)


#: The OpenAPI document is generated beside the schemas and checked by the same
#: gate. It is not a `*.schema.json`, so the orphan detector correctly leaves it
#: alone; this module owns it explicitly instead.
OPENAPI_FILENAME: Final[str] = "openapi.json"


def write_all(target: Path) -> list[Path]:
    """Write every schema and the OpenAPI document."""
    written = write(target, EXPORTED_MODELS)
    document = target / OPENAPI_FILENAME
    document.write_text(render_openapi(), encoding="utf-8", newline="\n")
    written.append(document)
    return written


def check_all(target: Path) -> list[str]:
    """Compare every schema and the OpenAPI document against ``target``."""
    problems = check(target, EXPORTED_MODELS)
    document = target / OPENAPI_FILENAME
    if not document.exists():
        problems.append(f"missing generated document: {document}")
    elif document.read_text(encoding="utf-8") != render_openapi():
        problems.append(f"openapi document drifted from its models: {document}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="schemas output directory")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    arguments = parser.parse_args(argv)
    if arguments.check:
        problems = check_all(arguments.target)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    for path in write_all(arguments.target):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
