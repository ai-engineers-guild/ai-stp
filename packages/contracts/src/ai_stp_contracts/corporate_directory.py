"""Authorized directory cards and named facets (SPEC-083 REQ-8311/8315)."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.corporate import AccountId, CorporateOrganization
from ai_stp_contracts.http import open_wire_object, strict_request_object
from ai_stp_foundation.ids import stable_id_pattern

TeamId = Annotated[str, Field(pattern=stable_id_pattern("operation"))]
TechnologyId = Annotated[str, Field(pattern=stable_id_pattern("technology"))]
CategoryId = Annotated[str, Field(pattern=stable_id_pattern("category"))]
ProjectId = Annotated[str, Field(pattern=stable_id_pattern("remote_project"))]


class CorporateDirectoryReference(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    kind: Literal["project", "team", "employee", "technology", "category", "job_title"]
    id: Annotated[str, Field(min_length=1, max_length=64)]
    name: str

    @model_validator(mode="after")
    def typed_identity(self) -> Self:
        prefix = {
            "project": "remote_project",
            "team": "operation",
            "employee": "account",
            "technology": "technology",
            "category": "category",
            "job_title": "job_title",
        }[self.kind]
        if not re.fullmatch(stable_id_pattern(prefix), self.id):
            raise ValueError("directory identity does not match its kind")
        return self


class CorporateDirectoryItem(CorporateDirectoryReference):
    description: str = ""
    revision: Annotated[int, Field(ge=1)]
    leads: list[CorporateDirectoryReference] = []
    teams: list[CorporateDirectoryReference] = []
    projects: list[CorporateDirectoryReference] = []
    technologies: list[CorporateDirectoryReference] = []
    related_teams: list[CorporateDirectoryReference] = []
    owner_team: CorporateDirectoryReference | None = None
    owner: CorporateDirectoryReference | None = None
    job_title: CorporateDirectoryReference | None = None
    categories: Annotated[list[CorporateDirectoryReference], Field(max_length=32)] = []
    available_actions: Annotated[list[str], Field(max_length=32)] = []
    is_lead: bool = False
    role: str | None = None

    @model_validator(mode="after")
    def coherent_references(self) -> Self:
        if self.kind == "category":
            raise ValueError("categories are facets, not directory cards")
        for refs, expected in (
            (self.leads, "employee"),
            (self.teams, "team"),
            (self.projects, "project"),
            (self.technologies, "technology"),
            (self.related_teams, "team"),
            (self.categories, "category"),
        ):
            if any(ref.kind != expected for ref in refs) or len({ref.id for ref in refs}) != len(
                refs
            ):
                raise ValueError(
                    "directory references require distinct identities of the expected kind"
                )
        if self.owner_team and (
            self.kind != "project"
            or self.owner_team.kind != "team"
            or self.owner_team.id not in {ref.id for ref in self.teams}
        ):
            raise ValueError("project owner must be a visible related team")
        if self.owner and (self.kind != "technology" or self.owner.kind != "employee"):
            raise ValueError("technology owner must be an employee")
        if self.job_title and (self.kind != "employee" or self.job_title.kind != "job_title"):
            raise ValueError("job title must belong to an employee")
        return self


class CorporateDirectoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)
    resource: Literal["projects", "teams", "members", "employees", "technologies"]
    query: Annotated[str | None, Field(min_length=1, max_length=200, pattern=r".*\S.*")] = None
    include_archived: bool = False
    lead_ids: Annotated[list[AccountId], Field(max_length=64)] = []
    team_ids: Annotated[list[TeamId], Field(max_length=64)] = []
    technology_ids: Annotated[list[TechnologyId], Field(max_length=64)] = []
    project_ids: Annotated[list[ProjectId], Field(max_length=64)] = []
    category_ids: Annotated[list[CategoryId], Field(max_length=32)] = []
    job_title_ids: Annotated[list[str], Field(max_length=64)] = []
    subject_ids: Annotated[list[str], Field(max_length=256)] = []
    is_lead: bool | None = None
    sort: Literal["name", "name_desc"] = "name"
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=256)] = 128


class CorporateDirectoryFacets(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    leads: list[CorporateDirectoryReference]
    teams: list[CorporateDirectoryReference]
    technologies: list[CorporateDirectoryReference]
    projects: list[CorporateDirectoryReference] = []
    categories: list[CorporateDirectoryReference] = []
    job_titles: list[CorporateDirectoryReference] = []


class CorporateDirectoryView(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)
    schema_version: Literal[1] = 1
    organization: CorporateOrganization
    resource: Literal["projects", "teams", "members", "employees", "technologies"]
    items: list[CorporateDirectoryItem]
    total: Annotated[int, Field(ge=0)]
    facets: CorporateDirectoryFacets
