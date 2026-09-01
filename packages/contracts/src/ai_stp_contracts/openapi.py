"""Deterministic OpenAPI 3.1 document for `/v1` (issue #71, SPEC-010 REQ-1010).

The document is **generated from the same Pydantic models** that generate
`schemas/v1`, by the same command, in the same run. That is what makes the two
published halves incapable of drifting: there is one source, and `check-schemas`
compares both outputs byte for byte. A hand-written OpenAPI beside generated
schemas would be a second source of truth, which `SPEC-015` REQ-1508 forbids.

Every payload schema is emitted once into `components.schemas` through a single
`models_json_schema` call, so a type shared by two operations is one definition
with two references rather than two copies. Every operation uses the
`validation` mode: these models are frozen, carry no computed field and no
serialization alias, so the request and response views are identical, and one
mode keeps the component names free of `-Input`/`-Output` suffixes.

The route table below is the only place routes exist. A model that no operation
reaches is not "future work", it is dead weight the contract would publish — a
test rejects it.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

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
from ai_stp_contracts.content import (
    CONTENT_SLUG_PATTERN,
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
from ai_stp_contracts.fixtures import load_cases
from ai_stp_contracts.grants import (
    AccessGrantResponse,
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantInvitationResponse,
    GrantListResponse,
    GrantRevokeRequest,
    GrantRevokeResponse,
)
from ai_stp_contracts.health import LivenessResponse, ReadinessResponse
from ai_stp_contracts.http import (
    API_BASE_PATH,
    API_VERSION,
    ETAG_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    IF_MATCH_HEADER,
    OPERATION_ID_HEADER,
    REQUEST_ID_HEADER,
    SCHEMA_VERSION_HEADER,
    PageInfo,
    http_status_for,
)
from ai_stp_contracts.identity import (
    AccountPrivacyUpdate,
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
)
from ai_stp_contracts.owner import (
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
    OwnershipClaimDecisionRequest,
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
    ReportCaseCreateRequest,
    ReportCaseListResponse,
    ReportCaseResponse,
    StaffActionResponse,
    StaffAuthorVerifiedRequest,
    StaffLifecycleRequest,
    StaffTriageRequest,
)
from ai_stp_contracts.seo import (
    SeoCatalogEntry,
    SeoCatalogPage,
    SeoCatalogQuery,
    SeoGenerator,
    SeoIndexDecision,
    SeoIndexResponse,
    SeoIndexShardRef,
    SeoLink,
    SeoProfileDocument,
    SeoPublicProfile,
    SeoRollbackRequest,
    SeoRollbackResponse,
    SeoSection,
    SeoSitemapShard,
    SeoSitemapUrl,
    SeoSocial,
    SeoSubjectQuery,
    SeoSubjectRef,
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
from ai_stp_foundation.envelope import ErrorEnvelope
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.revisions import REVISION_ID_PATTERN
from ai_stp_foundation.versioning import VERSION_PATTERN

OPENAPI_VERSION: Final[str] = "3.1.0"

#: Errors every operation can answer with, so each one declares only what is
#: specific to it. Rate limiting and dependency failure are properties of the
#: deployment, not of a route.
COMMON_ERRORS: Final[tuple[str, ...]] = (
    "AI_STP_VALIDATION_ERROR",
    "AI_STP_SCHEMA_UNSUPPORTED",
    "AI_STP_RATE_LIMITED",
    "AI_STP_DEPENDENCY_UNAVAILABLE",
    "AI_STP_INTERNAL",
)

AUTHENTICATED_ERRORS: Final[tuple[str, ...]] = (
    "AI_STP_AUTH_REQUIRED",
    "AI_STP_PERMISSION_DENIED",
    "AI_STP_DEVICE_REVOKED",
)


@dataclass(frozen=True)
class PathParam:
    """One templated path segment, constrained where the domain constrains it."""

    name: str
    description: str
    pattern: str


@dataclass(frozen=True)
class Operation:
    """One `/v1` route. The table of these is the whole surface."""

    method: str
    path: str
    operation_id: str
    summary: str

    #: `None` exactly when the route answers with bytes. Artifact delivery is
    #: the one such route: a model would have to name the bytes as a field, and
    #: then a client could not stream them or stop early on a digest mismatch.
    response: type[BaseModel] | None
    errors: tuple[str, ...] = ()
    path_params: tuple[PathParam, ...] = ()
    query: type[BaseModel] | None = None
    body: type[BaseModel] | None = None
    status: int = 200
    authenticated: bool = False
    idempotent_mutation: bool = False
    requires_precondition: bool = False

    #: What the success body is. Anything but JSON has no schema to reference,
    #: which is why `response` is optional above.
    response_media_type: str = "application/json"

    #: Request payload media type. Binary upload sets this to octet-stream and
    #: leaves ``body`` unset so the document does not invent a JSON wrapper.
    request_media_type: str = "application/json"
    extra_responses: Mapping[int, type[BaseModel]] = field(
        default_factory=dict[int, type[BaseModel]]
    )


_OBJECT_ID = PathParam(
    name="stable_id",
    description="Typed stable identifier of the catalog object.",
    pattern=r"^(component|setup)_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
)
_OBJECT_KIND = PathParam(
    name="object_kind",
    description="Catalog object kind.",
    pattern="^(component|setup)$",
)
_VERSION = PathParam(
    name="version",
    description="Exact two-integer version. A range or `latest` is not a reference.",
    pattern=VERSION_PATTERN,
)
_DEVICE_ID = PathParam(
    name="device_id",
    description="Typed stable identifier of the device.",
    pattern=stable_id_pattern("device"),
)
_PROVIDER = PathParam(
    name="provider",
    description="Identity provider that completed the browser half.",
    pattern=r"^(google|github)$",
)

OPERATIONS: Final[tuple[Operation, ...]] = (
    Operation(
        method="get",
        path="/health/live",
        operation_id="healthLive",
        summary="Report that the process answers.",
        response=LivenessResponse,
    ),
    Operation(
        method="get",
        path="/health/ready",
        operation_id="healthReady",
        summary="Report whether the deployment may take traffic.",
        response=ReadinessResponse,
        # Readiness answers with the same payload when it is not ready: the
        # caller needs the failing check, not an error envelope that hides it.
        extra_responses={503: ReadinessResponse},
    ),
    Operation(
        method="get",
        path="/account/catalog-reactions",
        operation_id="listCatalogReactions",
        summary="List catalog objects liked by the current account.",
        response=CatalogReactionList,
        authenticated=True,
    ),
    Operation(
        method="put",
        path="/account/catalog-reactions/{object_kind}/{stable_id}",
        operation_id="likeCatalogObject",
        summary="Idempotently like one public catalog object.",
        response=CatalogReactionState,
        path_params=(_OBJECT_KIND, _OBJECT_ID),
        errors=("AI_STP_NOT_FOUND",),
        authenticated=True,
    ),
    Operation(
        method="delete",
        path="/account/catalog-reactions/{object_kind}/{stable_id}",
        operation_id="unlikeCatalogObject",
        summary="Remove the current account's like from one public catalog object.",
        response=CatalogReactionState,
        path_params=(_OBJECT_KIND, _OBJECT_ID),
        errors=("AI_STP_NOT_FOUND",),
        authenticated=True,
    ),
    Operation(
        method="get",
        path="/catalog/components",
        operation_id="searchComponents",
        summary="Search public components. Anonymous.",
        response=ComponentListResponse,
        query=ComponentSearchRequest,
    ),
    Operation(
        method="get",
        path="/catalog/components/{stable_id}",
        operation_id="readComponent",
        summary="Read one public component and the versions it offers.",
        response=ComponentDetail,
        path_params=(_OBJECT_ID,),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/components/{stable_id}/versions/{version}",
        operation_id="readComponentVersion",
        summary="Read one immutable component version.",
        response=ComponentVersionResponse,
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/setups",
        operation_id="searchSetups",
        summary="Search public setups. Anonymous.",
        response=SetupListResponse,
        query=SetupSearchRequest,
    ),
    Operation(
        method="get",
        path="/catalog/setups/{stable_id}",
        operation_id="readSetup",
        summary="Read one public setup and the versions it offers.",
        response=SetupDetail,
        path_params=(_OBJECT_ID,),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/setups/{stable_id}/versions/{version}",
        operation_id="readSetupVersion",
        summary="Read one immutable setup version.",
        response=SetupVersionResponse,
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/components/{stable_id}/versions/{version}/artifact",
        operation_id="readComponentArtifact",
        summary="Stream the immutable bytes of one exact component version.",
        response=None,
        response_media_type="application/octet-stream",
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/setups/{stable_id}/versions/{version}/artifact",
        operation_id="readSetupArtifact",
        summary="Stream the immutable bytes of one exact setup version.",
        response=None,
        response_media_type="application/octet-stream",
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/components/{stable_id}/versions/{version}/github-metadata",
        operation_id="readComponentGithubMetadata",
        summary="Read on-demand GitHub stars and archive state for one exact component.",
        response=GitHubMetadata,
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/setups/{stable_id}/versions/{version}/github-metadata",
        operation_id="readSetupGithubMetadata",
        summary="Read on-demand GitHub stars and archive state for one exact setup.",
        response=GitHubMetadata,
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY"),
    ),
    Operation(
        method="get",
        path="/catalog/components/{stable_id}/versions/{version}/context-budget",
        operation_id="readComponentContextBudget",
        summary="Read the context budget of one visible exact component.",
        response=ComponentContextBudget,
        query=SetupContextBudgetQuery,
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/catalog/setups/{stable_id}/versions/{version}/context-budget",
        operation_id="readSetupContextBudget",
        summary="Read the absolute context budget of one visible exact setup.",
        response=SetupContextBudget,
        query=SetupContextBudgetQuery,
        path_params=(_OBJECT_ID, _VERSION),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CATALOG_INTEGRITY", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="post",
        path="/auth/device",
        operation_id="startDeviceAuthorization",
        summary="Start a device-code sign-in. Carries no device identity.",
        response=DeviceAuthorizationResponse,
        body=DeviceAuthorizationRequest,
        status=201,
    ),
    Operation(
        method="post",
        path="/auth/device/token",
        operation_id="exchangeDeviceCode",
        summary="Poll for the result and bind this device's public key.",
        response=DeviceTokenResponse,
        body=DeviceTokenRequest,
        errors=(
            "AI_STP_AUTHORIZATION_PENDING",
            "AI_STP_AUTHORIZATION_EXPIRED",
            "AI_STP_AUTHORIZATION_DECLINED",
        ),
    ),
    Operation(
        method="get",
        path="/auth/{provider}/callback",
        operation_id="readOAuthCallbackResult",
        summary="Read the outcome of the browser half of a sign-in.",
        response=OAuthCallbackResult,
        path_params=(_PROVIDER,),
    ),
    Operation(
        method="get",
        path="/auth/me",
        operation_id="readAuthMe",
        summary="Return the authenticated account id for the current session.",
        response=AuthMeResponse,
        authenticated=True,
    ),
    Operation(
        method="get",
        path="/auth/onboarding",
        operation_id="readLegalOnboarding",
        summary="Read the exact current legal revisions required for account activation.",
        response=LegalOnboardingStatus,
        authenticated=True,
    ),
    Operation(
        method="post",
        path="/auth/onboarding/complete",
        operation_id="completeLegalOnboarding",
        summary="Accept the current legal revisions and activate the account.",
        response=LegalOnboardingStatus,
        body=LegalOnboardingCompleteRequest,
        authenticated=True,
        errors=("AI_STP_VALIDATION_ERROR", "AI_STP_DEPENDENCY_UNAVAILABLE"),
    ),
    Operation(
        method="post",
        path="/auth/logout",
        operation_id="logoutSession",
        summary="Revoke the current opaque session.",
        response=AuthLogoutResponse,
        authenticated=True,
    ),
    Operation(
        method="get",
        path="/account",
        operation_id="readAccount",
        summary="Read the current account. Carries no address.",
        response=AccountProfile,
        authenticated=True,
    ),
    Operation(
        method="put",
        path="/account/privacy",
        operation_id="updateAccountPrivacy",
        summary="Replace the current account privacy preferences.",
        response=AccountProfile,
        body=AccountPrivacyUpdate,
        authenticated=True,
        errors=("AI_STP_VALIDATION_ERROR",),
    ),
    Operation(
        method="delete",
        path="/account/identities/{provider}",
        operation_id="unlinkAccountIdentity",
        summary="Unlink one OAuth identity. The last linked identity cannot be removed.",
        response=AccountProfile,
        path_params=(_PROVIDER,),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/devices",
        operation_id="listDevices",
        summary="List the devices of the current account.",
        response=DeviceListResponse,
        authenticated=True,
    ),
    Operation(
        method="post",
        path="/devices/challenge",
        operation_id="createDeviceChallenge",
        summary="Issue a one-time registration challenge for a device public key.",
        response=DeviceChallengeResponse,
        body=DeviceChallengeRequest,
        authenticated=True,
    ),
    Operation(
        method="post",
        path="/devices",
        operation_id="registerDevice",
        summary="Register a device after challenge proof.",
        response=DeviceRegisterResponse,
        authenticated=True,
        status=201,
    ),
    Operation(
        method="post",
        path="/devices/{device_id}/revoke",
        operation_id="revokeDevice",
        summary="Revoke one device. Forward-acting; local data is untouched.",
        response=DeviceRevokeResponse,
        body=DeviceRevokeRequest,
        path_params=(_DEVICE_ID,),
        authenticated=True,
        idempotent_mutation=True,
        requires_precondition=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PRECONDITION_FAILED", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="get",
        path="/system/version",
        operation_id="readSystemVersion",
        summary="Safe service version and schema revision diagnostics.",
        response=SystemVersionResponse,
    ),
    Operation(
        method="post",
        path="/sync/push",
        operation_id="pushSyncEvents",
        summary="Push private revision events for the session-bound device.",
        response=SyncPushResponse,
        body=SyncPushRequest,
        authenticated=True,
        errors=("AI_STP_CONFLICT", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/sync/pull",
        operation_id="pullSyncEvents",
        summary="Pull accepted revision events from the account outbox.",
        response=SyncPullResponse,
        query=SyncPullQuery,
        authenticated=True,
        errors=("AI_STP_VALIDATION_ERROR",),
    ),
    Operation(
        method="post",
        path="/publications/plans",
        operation_id="createPublicationPlan",
        summary="Create an immutable publication plan for an exact version.",
        response=PublicationPlanResponse,
        body=PublicationPlanCreateRequest,
        authenticated=True,
        status=201,
        idempotent_mutation=True,
        errors=("AI_STP_VALIDATION_ERROR", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="get",
        path="/publications/plans/{plan_id}",
        operation_id="readPublicationPlan",
        summary="Read one publication plan owned by the caller.",
        response=PublicationPlanResponse,
        path_params=(
            PathParam(
                name="plan_id",
                description="Publication plan identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND",),
    ),
    Operation(
        method="put",
        path="/publications/plans/{plan_id}/artifact",
        operation_id="bindPublicationArtifact",
        summary="Bind exact artifact bytes to one publication plan.",
        response=PublicationPlanResponse,
        path_params=(
            PathParam(
                name="plan_id",
                description="Publication plan identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        request_media_type="application/octet-stream",
        idempotent_mutation=True,
        errors=("AI_STP_VALIDATION_ERROR", "AI_STP_NOT_FOUND", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="post",
        path="/publications/plans/{plan_id}/confirm",
        operation_id="confirmPublicationPlan",
        summary="Confirm a publication plan by exact plan_hash.",
        response=PublicationPlanResponse,
        body=PublicationConfirmRequest,
        path_params=(
            PathParam(
                name="plan_id",
                description="Publication plan identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="post",
        path="/grants/invitations",
        operation_id="createGrantInvitation",
        summary="Invite a recipient to a major line by verified email.",
        response=GrantInvitationResponse,
        body=GrantInvitationCreateRequest,
        authenticated=True,
        status=201,
        idempotent_mutation=True,
        errors=("AI_STP_VALIDATION_ERROR", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="get",
        path="/grants",
        operation_id="listGrants",
        summary="List invitations and grants for the current account.",
        response=GrantListResponse,
        authenticated=True,
    ),
    Operation(
        method="post",
        path="/grants/direct",
        operation_id="createDirectGrant",
        summary="Grant a major line by an explicit recipient identifier.",
        response=AccessGrantResponse,
        body=DirectGrantCreateRequest,
        authenticated=True,
        status=201,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="post",
        path="/grants/invitations/{invitation_id}/accept",
        operation_id="acceptGrantInvitation",
        summary="Accept an invitation when the verified email matches.",
        response=AccessGrantResponse,
        body=GrantAcceptRequest,
        path_params=(
            PathParam(
                name="invitation_id",
                description="Grant invitation identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="post",
        path="/grants/invitations/{invitation_id}/revoke",
        operation_id="revokeGrantInvitation",
        summary="Revoke a pending invitation. Does not delete local bytes.",
        response=GrantRevokeResponse,
        body=GrantRevokeRequest,
        path_params=(
            PathParam(
                name="invitation_id",
                description="Grant invitation identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="post",
        path="/grants/{grant_id}/revoke",
        operation_id="revokeAccessGrant",
        summary="Revoke an active grant forward-only. Local bytes are retained.",
        response=GrantRevokeResponse,
        body=GrantRevokeRequest,
        path_params=(
            PathParam(
                name="grant_id",
                description="Access grant identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="post",
        path="/complaints",
        operation_id="createComplaint",
        summary="Accept a complaint about an author, catalog object, or other target.",
        response=ComplaintCreateResponse,
        body=ComplaintCreateRequest,
        status=201,
        errors=("AI_STP_VALIDATION_ERROR", "AI_STP_RATE_LIMITED"),
    ),
    Operation(
        method="post",
        path="/reports",
        operation_id="createReportCase",
        summary="Create a closed report case for one exact version.",
        response=ReportCaseResponse,
        body=ReportCaseCreateRequest,
        authenticated=True,
        status=201,
        idempotent_mutation=True,
        errors=("AI_STP_VALIDATION_ERROR", "AI_STP_RATE_LIMITED"),
    ),
    Operation(
        method="get",
        path="/reports",
        operation_id="listReportCases",
        summary="List the caller's own report cases.",
        response=ReportCaseListResponse,
        authenticated=True,
    ),
    Operation(
        method="post",
        path="/staff/reports/{case_id}/triage",
        operation_id="staffTriageReport",
        summary="Staff triage of a closed report case.",
        response=ReportCaseResponse,
        body=StaffTriageRequest,
        path_params=(
            PathParam(
                name="case_id",
                description="Report case identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="post",
        path="/staff/versions/lifecycle",
        operation_id="staffVersionLifecycle",
        summary="Staff block, hide or restore a published version.",
        response=StaffActionResponse,
        body=StaffLifecycleRequest,
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="post",
        path="/staff/author-verified",
        operation_id="staffAuthorVerified",
        summary="Issue or revoke author_verified for an account.",
        response=StaffActionResponse,
        body=StaffAuthorVerifiedRequest,
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="post",
        path="/ownership-claims",
        operation_id="createOwnershipClaim",
        summary="Request transfer of an official catalog component to a verified maintainer.",
        response=OwnershipClaimResponse,
        body=OwnershipClaimCreateRequest,
        authenticated=True,
        status=201,
        idempotent_mutation=True,
        errors=(
            "AI_STP_NOT_FOUND",
            "AI_STP_PERMISSION_DENIED",
            "AI_STP_PRECONDITION_FAILED",
            "AI_STP_CONFLICT",
        ),
    ),
    Operation(
        method="get",
        path="/ownership-claims/{claim_id}",
        operation_id="readOwnershipClaim",
        summary="Read one ownership claim and its staff preview.",
        response=OwnershipClaimResponse,
        path_params=(
            PathParam(
                name="claim_id",
                description="Typed operation identifier of the ownership claim.",
                pattern=stable_id_pattern("operation"),
            ),
        ),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="post",
        path="/staff/ownership-claims/{claim_id}/approve",
        operation_id="approveOwnershipClaim",
        summary="Approve a verified-maintainer claim without rewriting published passports.",
        response=OwnershipClaimResponse,
        body=OwnershipClaimDecisionRequest,
        path_params=(
            PathParam(
                name="claim_id",
                description="Typed operation identifier of the ownership claim.",
                pattern=stable_id_pattern("operation"),
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=(
            "AI_STP_NOT_FOUND",
            "AI_STP_PERMISSION_DENIED",
            "AI_STP_CONFLICT",
        ),
    ),
    Operation(
        method="post",
        path="/staff/ownership-claims/{claim_id}/deny",
        operation_id="denyOwnershipClaim",
        summary="Deny a verified-maintainer claim with no catalog effect.",
        response=OwnershipClaimResponse,
        body=OwnershipClaimDecisionRequest,
        path_params=(
            PathParam(
                name="claim_id",
                description="Typed operation identifier of the ownership claim.",
                pattern=stable_id_pattern("operation"),
            ),
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=(
            "AI_STP_NOT_FOUND",
            "AI_STP_PERMISSION_DENIED",
            "AI_STP_CONFLICT",
        ),
    ),
    Operation(
        method="get",
        path="/owner/objects/component/{stable_id}/ownership-revisions",
        operation_id="listOwnershipRevisions",
        summary="List immutable ownership revisions for one catalog component.",
        response=OwnershipRevisionListResponse,
        path_params=(
            PathParam(
                name="stable_id",
                description="Typed stable identifier of the catalog component.",
                pattern=stable_id_pattern("component"),
            ),
        ),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="get",
        path="/owner/objects",
        operation_id="listOwnerObjects",
        summary="List objects owned by the current account.",
        response=OwnerObjectListResponse,
        query=OwnerObjectListQuery,
        authenticated=True,
    ),
    Operation(
        method="get",
        path="/owner/objects/{object_kind}/{stable_id}",
        operation_id="readOwnerObject",
        summary="Read one owned object and its versions.",
        response=OwnerObjectDetail,
        path_params=(
            PathParam(
                name="object_kind",
                description="component or setup",
                pattern=r"^(component|setup)$",
            ),
            PathParam(
                name="stable_id",
                description="Typed stable identifier of the owned object.",
                pattern=r"^(component|setup)_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
            ),
        ),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND",),
    ),
    Operation(
        method="get",
        path="/owner/objects/{object_kind}/{stable_id}/versions/{version}",
        operation_id="readOwnerVersion",
        summary="Read one exact owned version with evidence.",
        response=OwnerVersionDetail,
        path_params=(
            PathParam(
                name="object_kind",
                description="component or setup",
                pattern=r"^(component|setup)$",
            ),
            PathParam(
                name="stable_id",
                description="Typed stable identifier of the owned object.",
                pattern=r"^(component|setup)_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
            ),
            _VERSION,
        ),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND",),
    ),
    Operation(
        method="post",
        path="/owner/objects/{object_kind}/{stable_id}/versions/{version}/publication-plans",
        operation_id="startOwnerPublication",
        summary=(
            "Start a publication plan from an exact owned version "
            "without browser passport composition."
        ),
        response=PublicationPlanResponse,
        body=OwnerStartPublicationRequest,
        path_params=(
            PathParam(
                name="object_kind",
                description="component or setup",
                pattern=r"^(component|setup)$",
            ),
            PathParam(
                name="stable_id",
                description="Typed stable identifier of the owned object.",
                pattern=r"^(component|setup)_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
            ),
            _VERSION,
        ),
        authenticated=True,
        status=201,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="post",
        path="/owner/objects/{object_kind}/{stable_id}/versions/{version}/lifecycle",
        operation_id="setOwnerVersionLifecycle",
        summary="Deprecate an owned published version, or take the mark off again.",
        response=OwnerLifecycleResponse,
        body=OwnerLifecycleRequest,
        path_params=(
            PathParam(
                name="object_kind",
                description="component or setup",
                pattern=r"^(component|setup)$",
            ),
            PathParam(
                name="stable_id",
                description="Typed stable identifier of the owned object.",
                pattern=r"^(component|setup)_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
            ),
            _VERSION,
        ),
        authenticated=True,
        idempotent_mutation=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR", "AI_STP_CONFLICT"),
    ),
    Operation(
        method="get",
        path="/selection/impact",
        operation_id="readSelectionImpact",
        summary="Read an account-scoped selection impact report.",
        response=AccountSelectionImpactReport,
        query=AccountSelectionImpactQuery,
        authenticated=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/staff/reports",
        operation_id="listStaffReports",
        summary="List staff worklist cases for the allowlist account.",
        response=StaffReportListResponse,
        query=StaffReportListQuery,
        authenticated=True,
        errors=("AI_STP_PERMISSION_DENIED",),
    ),
    Operation(
        method="get",
        path="/staff/reports/{case_id}",
        operation_id="readStaffReport",
        summary="Read one staff report case without reporter identity.",
        response=StaffReportDetail,
        path_params=(
            PathParam(
                name="case_id",
                description="Report case identifier.",
                pattern=r"^[A-Za-z0-9._~-]{8,64}$",
            ),
        ),
        authenticated=True,
        errors=("AI_STP_NOT_FOUND", "AI_STP_PERMISSION_DENIED"),
    ),
    Operation(
        method="get",
        path="/seo/subjects/{subject_kind}/{subject_id}",
        operation_id="readSeoProfile",
        summary="Read the active public SEO profile for one subject and locale.",
        response=SeoPublicProfile,
        query=SeoSubjectQuery,
        path_params=(
            PathParam(
                name="subject_kind",
                description="SEO subject kind.",
                pattern=r"^(component|setup|article|service|country)$",
            ),
            PathParam(
                name="subject_id",
                description="Stable subject identifier.",
                pattern=r"^.{1,253}$",
            ),
        ),
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/seo/sitemap",
        operation_id="readSeoSitemapIndex",
        summary="Read the generation-aware sitemap index.",
        response=SeoIndexResponse,
    ),
    Operation(
        method="get",
        path="/seo/sitemaps/{subject_kind}/{locale}/{page}",
        operation_id="readSeoSitemapShard",
        summary="Read one sitemap shard of at most 50 000 eligible URLs.",
        response=SeoSitemapShard,
        path_params=(
            PathParam(
                name="subject_kind",
                description="SEO subject kind.",
                pattern=r"^(component|setup|article|service|country)$",
            ),
            PathParam(
                name="locale",
                description="SEO locale.",
                pattern=r"^(ru|en)$",
            ),
            PathParam(
                name="page",
                description="1-based shard page.",
                pattern=r"^[1-9][0-9]*$",
            ),
        ),
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/seo/catalog",
        operation_id="readSeoCatalog",
        summary="Read a paginated LLM catalog manifest of active subjects.",
        response=SeoCatalogPage,
        query=SeoCatalogQuery,
        errors=("AI_STP_VALIDATION_ERROR",),
    ),
    Operation(
        method="get",
        path="/seo/og/{revision_id}",
        operation_id="readSeoOgImage",
        summary="Read the immutable 1200 by 630 Open Graph image for one revision.",
        response=None,
        response_media_type="image/png",
        path_params=(
            PathParam(
                name="revision_id",
                description="Immutable SEO revision identifier.",
                pattern=REVISION_ID_PATTERN,
            ),
        ),
        errors=("AI_STP_NOT_FOUND", "AI_STP_SEO_RENDER_FAILED", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/content",
        operation_id="listContent",
        summary="List published repository and staff articles for one locale.",
        response=ContentListResponse,
        query=ContentLocaleQuery,
        errors=("AI_STP_CONTENT_INVALID", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="get",
        path="/content/repository/state",
        operation_id="readContentRepositoryState",
        summary="Read the current repository import generation without entries.",
        response=ContentRepositoryState,
        errors=("AI_STP_CONTENT_IMPORT_FORBIDDEN",),
    ),
    Operation(
        method="post",
        path="/content/repository/import",
        operation_id="importContentRepository",
        summary="Replace the repository-owned active article set from a snapshot.",
        response=ContentRepositoryImportResponse,
        body=ContentRepositoryImportRequest,
        idempotent_mutation=True,
        errors=(
            "AI_STP_CONTENT_INVALID",
            "AI_STP_CONTENT_SOURCE_CONFLICT",
            "AI_STP_CONTENT_STALE",
            "AI_STP_CONTENT_IMPORT_FORBIDDEN",
        ),
    ),
    Operation(
        method="get",
        path="/content/{type}/{slug}",
        operation_id="readContent",
        summary="Read one published localized article.",
        response=ContentDetail,
        query=ContentLocaleQuery,
        path_params=(
            PathParam(
                name="type",
                description="Content hub article type.",
                pattern=r"^(article|blog_post|changelog|release_notes)$",
            ),
            PathParam(
                name="slug",
                description="Lowercase kebab-case article slug.",
                pattern=CONTENT_SLUG_PATTERN,
            ),
        ),
        errors=("AI_STP_NOT_FOUND", "AI_STP_CONTENT_INVALID", "AI_STP_VALIDATION_ERROR"),
    ),
    Operation(
        method="put",
        path="/staff/content/{type}/{slug}",
        operation_id="putStaffContent",
        summary="Publish an exact RU/EN staff article pair.",
        response=StaffContentPublishResponse,
        body=StaffContentPublishRequest,
        authenticated=True,
        idempotent_mutation=True,
        path_params=(
            PathParam(
                name="type",
                description="Content hub article type.",
                pattern=r"^(article|blog_post|changelog|release_notes)$",
            ),
            PathParam(
                name="slug",
                description="Lowercase kebab-case article slug.",
                pattern=CONTENT_SLUG_PATTERN,
            ),
        ),
        errors=(
            "AI_STP_CONTENT_INVALID",
            "AI_STP_CONTENT_SOURCE_CONFLICT",
            "AI_STP_CONTENT_STALE",
            "AI_STP_PERMISSION_DENIED",
            "AI_STP_VALIDATION_ERROR",
        ),
    ),
    Operation(
        method="delete",
        path="/staff/content/{type}/{slug}",
        operation_id="deleteStaffContent",
        summary="Unpublish both locales of a staff article without deleting history.",
        response=StaffContentUnpublishResponse,
        body=StaffContentUnpublishRequest,
        authenticated=True,
        idempotent_mutation=True,
        path_params=(
            PathParam(
                name="type",
                description="Content hub article type.",
                pattern=r"^(article|blog_post|changelog|release_notes)$",
            ),
            PathParam(
                name="slug",
                description="Lowercase kebab-case article slug.",
                pattern=CONTENT_SLUG_PATTERN,
            ),
        ),
        errors=(
            "AI_STP_NOT_FOUND",
            "AI_STP_CONTENT_SOURCE_CONFLICT",
            "AI_STP_CONTENT_STALE",
            "AI_STP_PERMISSION_DENIED",
            "AI_STP_VALIDATION_ERROR",
        ),
    ),
    Operation(
        method="post",
        path="/seo/subjects/{subject_kind}/{subject_id}/rollback",
        operation_id="rollbackSeoRevision",
        summary="Point one subject locale at its last valid base SEO revision.",
        response=SeoRollbackResponse,
        body=SeoRollbackRequest,
        authenticated=True,
        idempotent_mutation=True,
        path_params=(
            PathParam(
                name="subject_kind",
                description="SEO subject kind.",
                pattern=r"^(component|setup|article|service|country)$",
            ),
            PathParam(
                name="subject_id",
                description="Stable subject identifier.",
                pattern=r"^.{1,253}$",
            ),
        ),
        errors=("AI_STP_NOT_FOUND", "AI_STP_VALIDATION_ERROR"),
    ),
)

#: Models that are part of the published contract but are only ever reached
#: through another payload. The list is explicit so the reachability check can
#: catch a model nothing serves without flagging a legitimate nested type — and
#: so that adding one is a decision someone writes down.
#:
#: Nested models that travel inside a larger payload but still deserve a
#: standalone artifact the platform can implement against.
NESTED_ONLY_MODELS: Final[tuple[type[BaseModel], ...]] = (
    DeviceSummary,
    PageInfo,
    SyncEvent,
    SyncEventReceipt,
    SyncConflictInfo,
    SyncStreamEvent,
    AuthorAttestation,
    EvidenceBindingView,
    GrantInvitationResponse,
    AccessGrantResponse,
    ReportCaseResponse,
    OwnerObjectSummary,
    OwnerVersionSummary,
    StaffReportSummary,
    CatalogUsageMetrics,
    SeoSubjectRef,
    SeoIndexDecision,
    SeoLink,
    SeoSection,
    SeoSocial,
    SeoGenerator,
    SeoProfileDocument,
    SeoSitemapUrl,
    SeoIndexShardRef,
    SeoCatalogEntry,
    ContentSummary,
    ContentSnapshotEntry,
    StaffContentTranslation,
    StaffContentTranslations,
    OwnershipClaimPreview,
    OwnershipRevisionView,
)


def _schema_models() -> list[tuple[type[BaseModel], str]]:
    """Every model the document must define, deduplicated and ordered."""
    seen: dict[str, type[BaseModel]] = {}
    for operation in OPERATIONS:
        for model in (operation.query, operation.body, operation.response):
            if model is not None:
                seen[model.__name__] = model
        for model in operation.extra_responses.values():
            seen[model.__name__] = model
    for model in NESTED_ONLY_MODELS:
        seen[model.__name__] = model
    seen[ErrorEnvelope.__name__] = ErrorEnvelope
    return [(seen[name], "validation") for name in sorted(seen)]


def _components_schemas() -> dict[str, dict[str, object]]:
    """Emit every payload schema once, with shared references between them."""
    _, definitions = models_json_schema(
        _schema_models(),  # pyright: ignore[reportArgumentType]
        ref_template="#/components/schemas/{model}",
    )
    defs = cast(dict[str, dict[str, object]], definitions.get("$defs", {}))
    return dict(defs)


def _header(name: str, description: str, required: bool) -> dict[str, object]:
    return {
        "description": description,
        "required": required,
        "schema": {"type": "string"},
    }


def _error_response(codes: Sequence[str]) -> dict[str, object]:
    listed = ", ".join(sorted(codes))
    return {
        "description": f"Typed failure. Stable codes: {listed}.",
        "headers": {REQUEST_ID_HEADER: _header(REQUEST_ID_HEADER, "Correlation id.", True)},
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}},
    }


def _examples(operation_id: str, status: int, part: str) -> dict[str, object]:
    """Concrete corpus cases attached to the document.

    The examples are not written again here: they are the same cases the mock
    serves and the conformance suite replays, so a documented example cannot
    describe something no implementation is held to. `example` cases are
    included as well — a body that depends on server state is still a body a
    reader needs to see.
    """
    attached: dict[str, object] = {}
    for case in load_cases():
        if case.operation_id != operation_id or case.status != status:
            continue
        if case.kind not in {"positive", "example"}:
            continue
        payload = case.request.body if part == "request" else case.body
        if payload is None:  # pragma: no cover - the corpus invariants rule it out
            # Required by the type, not speculative: a corpus test forbids a
            # servable case for a body-carrying operation from omitting its
            # request body, and another forbids a non-rejection from omitting
            # its response body.
            continue
        attached[case.case_id] = {"summary": case.why, "value": dict(payload)}
    return attached


def _responses(operation: Operation) -> dict[str, object]:
    """Success plus one entry per HTTP status the declared codes can produce."""
    headers: dict[str, object] = {
        REQUEST_ID_HEADER: _header(REQUEST_ID_HEADER, "Correlation id, echoed or minted.", True)
    }
    if operation.idempotent_mutation:
        headers[OPERATION_ID_HEADER] = _header(
            OPERATION_ID_HEADER, "Durable operation id of this mutation.", True
        )
    if operation.requires_precondition:
        headers[ETAG_HEADER] = _header(ETAG_HEADER, "Current version, for a later If-Match.", True)

    if operation.response is None:
        success: dict[str, object] = {"schema": {"type": "string", "format": "binary"}}
    else:
        success = {"schema": {"$ref": f"#/components/schemas/{operation.response.__name__}"}}
        success_examples = _examples(operation.operation_id, operation.status, "response")
        if success_examples:
            success["examples"] = success_examples
    responses: dict[str, object] = {
        str(operation.status): {
            "description": operation.summary,
            "headers": headers,
            "content": {operation.response_media_type: success},
        }
    }
    for status, model in sorted(operation.extra_responses.items()):
        media: dict[str, object] = {"schema": {"$ref": f"#/components/schemas/{model.__name__}"}}
        extra_examples = _examples(operation.operation_id, status, "response")
        if extra_examples:
            media["examples"] = extra_examples
        responses[str(status)] = {
            "description": "The same payload, reporting a state that must not take traffic.",
            "content": {"application/json": media},
        }

    codes = set(operation.errors) | set(COMMON_ERRORS)
    if operation.authenticated:
        codes |= set(AUTHENTICATED_ERRORS)
    by_status: dict[int, list[str]] = {}
    for code in sorted(codes):
        by_status.setdefault(http_status_for(code), []).append(code)
    for status, status_codes in sorted(by_status.items()):
        responses[str(status)] = _error_response(status_codes)
    return responses


def _parameters(
    operation: Operation, components: Mapping[str, dict[str, object]]
) -> list[dict[str, object]]:
    """Path, query and header parameters, in a stable order."""
    parameters: list[dict[str, object]] = [
        {
            "name": parameter.name,
            "in": "path",
            "required": True,
            "description": parameter.description,
            "schema": {"type": "string", "pattern": parameter.pattern},
        }
        for parameter in operation.path_params
    ]

    if operation.query is not None:
        schema = components[operation.query.__name__]
        properties = cast(dict[str, object], schema.get("properties", {}))
        required = set(cast(list[str], schema.get("required", [])))
        for name in sorted(properties):
            if name == "schema_version":
                continue  # carried by the header, not repeated per query
            parameters.append(
                {
                    "name": name,
                    "in": "query",
                    "required": name in required,
                    "schema": properties[name],
                }
            )

    parameters.append(
        {
            "name": SCHEMA_VERSION_HEADER,
            "in": "header",
            "required": False,
            "description": "Wire major the client speaks. An unknown one fails typed.",
            "schema": {"type": "integer", "const": 1},
        }
    )
    if operation.idempotent_mutation:
        parameters.append(
            {
                "name": IDEMPOTENCY_KEY_HEADER,
                "in": "header",
                "required": True,
                "description": "Client-chosen key; a retry must not become a second effect.",
                "schema": {"type": "string"},
            }
        )
    if operation.requires_precondition:
        parameters.append(
            {
                "name": IF_MATCH_HEADER,
                "in": "header",
                "required": True,
                "description": "Expected ETag. A stale value fails AI_STP_PRECONDITION_FAILED.",
                "schema": {"type": "string"},
            }
        )
    return parameters


def build_document() -> dict[str, object]:
    """Assemble the whole `/v1` document deterministically."""
    components = _components_schemas()
    paths: dict[str, dict[str, object]] = {}
    for operation in sorted(OPERATIONS, key=lambda item: (item.path, item.method)):
        entry: dict[str, object] = {
            "operationId": operation.operation_id,
            "summary": operation.summary,
            "parameters": _parameters(operation, components),
            "responses": _responses(operation),
        }
        if operation.body is not None:
            media: dict[str, object] = {
                "schema": {"$ref": f"#/components/schemas/{operation.body.__name__}"}
            }
            request_examples = _examples(operation.operation_id, operation.status, "request")
            if request_examples:
                media["examples"] = request_examples
            entry["requestBody"] = {
                "required": True,
                "content": {operation.request_media_type: media},
            }
        elif operation.request_media_type != "application/json":
            entry["requestBody"] = {
                "required": True,
                "content": {
                    operation.request_media_type: {"schema": {"type": "string", "format": "binary"}}
                },
            }
        entry["security"] = [{"bearerAuth": []}] if operation.authenticated else []
        paths.setdefault(f"{API_BASE_PATH}{operation.path}", {})[operation.method] = entry

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "ai_stp platform API",
            "version": API_VERSION,
            "description": (
                "Generated from the Pydantic models in `ai_stp_contracts`. "
                "Do not edit: change the model and regenerate, or the two "
                "published halves of the contract stop agreeing."
            ),
        },
        "components": {
            "schemas": components,
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": (
                        "Short-lived token from the device-code exchange. Per-request "
                        "Ed25519 signing is reserved for attestation (SPEC-002)."
                    ),
                }
            },
        },
        "paths": paths,
    }


def render() -> str:
    """Render the document exactly as it is committed."""
    return json.dumps(build_document(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
