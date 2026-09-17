import { searchComponents, searchSetups } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/errors";
import { readEmployeeTechnologies } from "@/lib/api/corporate";
import { readTechnologyRegistry, readTeamProjects } from "@/lib/api/technology";
import { readPublisherProfile, type PublicProfileProjection } from "@/lib/api/public-profile";
import { asCursorToken, tryAsAccountId } from "@/lib/brands";
import type {
  ComponentListResponse,
  ComponentSummary,
  SetupListResponse,
  SetupSummary,
} from "@/lib/api/generated/types.gen";
import type { CorporatePresentation } from "@/lib/corporate-detail";
import type { CorporateMember, CorporateTeamView } from "@/lib/api/generated/types.gen";

export type CorporateEmployeeReadState<T> =
  { status: "data"; data: T } | { status: "empty" | "noaccess" | "error"; data: null };

export type CorporateEmployeeCatalogItem = {
  id: string;
  kind: "component" | "setup";
  name: string;
  version: string | null;
  summary?: ComponentSummary | SetupSummary;
};

export type CorporateEmployeeTechnology = { id: string; name: string };

export type CorporateEmployeeContent = {
  publicProfile: CorporateEmployeeReadState<PublicProfileProjection>;
  technologies: CorporateEmployeeReadState<readonly CorporateEmployeeTechnology[]>;
  components: CorporateEmployeeReadState<readonly CorporateEmployeeCatalogItem[]>;
  setups: CorporateEmployeeReadState<readonly CorporateEmployeeCatalogItem[]>;
};

type CatalogResponse = ComponentListResponse | SetupListResponse;

function stateForError(
  error: unknown,
  notFound: "empty" | "noaccess",
): "empty" | "noaccess" | "error" {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) return "noaccess";
    if (error.status === 404) return notFound;
  }
  return "error";
}

async function readAuthorCatalog(
  accountId: string,
  kind: "component" | "setup",
): Promise<readonly CorporateEmployeeCatalogItem[]> {
  const items: CorporateEmployeeCatalogItem[] = [];
  const seen = new Set<string>();
  let cursor: string | undefined;
  do {
    const page: CatalogResponse =
      kind === "component"
        ? await searchComponents({
            authors: [accountId],
            include_experimental: true,
            page_size: 100,
            ...(cursor ? { cursor: asCursorToken(cursor) } : {}),
          })
        : await searchSetups({
            authors: [accountId],
            include_experimental: true,
            page_size: 100,
            ...(cursor ? { cursor: asCursorToken(cursor) } : {}),
          });
    for (const item of [...page.items, ...page.experimental]) {
      const id = item.stable_id;
      if (seen.has(id)) continue;
      seen.add(id);
      items.push({
        id,
        kind,
        name: item.latest_name,
        version: item.latest_version,
        summary: item,
      });
    }
    const next = page.page.next_cursor;
    if (!next) break;
    if (next === cursor) throw new Error("catalog pagination did not advance");
    cursor = next;
  } while (cursor);
  return items;
}

async function readCatalogState(
  accountId: string,
  kind: "component" | "setup",
): Promise<CorporateEmployeeReadState<readonly CorporateEmployeeCatalogItem[]>> {
  try {
    const data = await readAuthorCatalog(accountId, kind);
    return data.length ? { status: "data", data } : { status: "empty", data: null };
  } catch (error) {
    return { status: stateForError(error, "empty"), data: null };
  }
}

async function readProfileState(
  accountId: string,
): Promise<CorporateEmployeeReadState<PublicProfileProjection>> {
  const typedAccountId = tryAsAccountId(accountId);
  if (!typedAccountId) return { status: "noaccess", data: null };
  try {
    return { status: "data", data: await readPublisherProfile(typedAccountId) };
  } catch (error) {
    return { status: stateForError(error, "empty"), data: null };
  }
}

async function readTechnologyState(input: {
  sessionToken: string;
  organizationId: string;
  accountId: string;
  canReadTechnologies: boolean;
}): Promise<CorporateEmployeeReadState<readonly CorporateEmployeeTechnology[]>> {
  if (!input.canReadTechnologies) return { status: "noaccess", data: null };
  try {
    const [assignments, registry] = await Promise.all([
      readEmployeeTechnologies(input.sessionToken, input.organizationId, input.accountId),
      readTechnologyRegistry(input.sessionToken, input.organizationId),
    ]);
    if (!registry.technologies) return { status: "noaccess", data: null };
    const visible = [
      ...new Map(
        assignments.items
          .filter((item) => item.state === "current")
          .flatMap((item) => {
            const technology = registry.technologies?.items.find(
              (candidate) => candidate.technology_id === item.technology_id,
            );
            return technology
              ? [
                  [
                    technology.technology_id,
                    { id: technology.technology_id, name: technology.name },
                  ] as const,
                ]
              : [];
          }),
      ).values(),
    ];
    return visible.length ? { status: "data", data: visible } : { status: "empty", data: null };
  } catch (error) {
    return { status: stateForError(error, "noaccess"), data: null };
  }
}

export async function readCorporateEmployeeContent(input: {
  sessionToken: string;
  organizationId: string;
  accountId: string;
  canReadTechnologies: boolean;
}): Promise<CorporateEmployeeContent> {
  if (!tryAsAccountId(input.accountId)) {
    const invalid = { status: "noaccess", data: null } as const;
    return { publicProfile: invalid, technologies: invalid, components: invalid, setups: invalid };
  }
  const [publicProfile, technologies, components, setups] = await Promise.all([
    readProfileState(input.accountId),
    readTechnologyState(input),
    readCatalogState(input.accountId, "component"),
    readCatalogState(input.accountId, "setup"),
  ]);
  return { publicProfile, technologies, components, setups };
}

export function applyCorporateEmployeePresentation(
  presentation: CorporatePresentation,
  input: {
    member: Pick<CorporateMember, "account_id" | "display_name">;
    teams: readonly CorporateTeamView[];
    projects: readonly { project_id: string; name: string }[];
    technologies: readonly CorporateEmployeeTechnology[];
    authoredComponents: readonly CorporateEmployeeCatalogItem[];
    unknownName: string;
  },
): CorporatePresentation {
  const employeeName = input.member.display_name?.trim() || input.unknownName;
  const memberTeams = input.teams.filter((team) =>
    team.members.some((member) => member.account_id === input.member.account_id),
  );
  const teamRefs = memberTeams.map((team) => ({
    kind: "team" as const,
    id: team.team_id,
    name: team.name,
  }));
  const leadRefs = [
    ...new Map(
      memberTeams.flatMap((team) =>
        team.lead_account_ids.flatMap((leadId) => {
          if (leadId === input.member.account_id) return [];
          const lead = team.members.find((member) => member.account_id === leadId);
          return lead
            ? [
                [
                  lead.account_id,
                  {
                    kind: "employee" as const,
                    id: lead.account_id,
                    name: lead.display_name?.trim() || input.unknownName,
                  },
                ] as const,
              ]
            : [];
        }),
      ),
    ).values(),
  ];
  const projectRefs = [
    ...new Map(
      input.projects.map((project) => [
        project.project_id,
        { kind: "project" as const, id: project.project_id, name: project.name },
      ]),
    ).values(),
  ];
  return {
    ...presentation,
    teams: teamRefs,
    projects: projectRefs,
    technologies: input.technologies.map((technology) => ({
      kind: "technology" as const,
      id: technology.id,
      name: technology.name,
    })),
    leads: leadRefs,
    components: input.authoredComponents.map((component) => ({
      kind: "component" as const,
      id: component.id,
      name: component.name,
    })),
    author: { kind: "employee", id: input.member.account_id, name: employeeName },
  };
}

export async function assembleCorporateEmployeePresentation(input: {
  presentation: CorporatePresentation;
  sessionToken: string;
  organizationId: string;
  member: Pick<CorporateMember, "account_id" | "display_name">;
  teams: readonly CorporateTeamView[];
  projects: readonly { project_id: string; name: string }[];
  content: CorporateEmployeeContent;
  includeTechnologies?: boolean;
  unknownName: string;
}): Promise<CorporatePresentation> {
  const profile =
    input.content.publicProfile.status === "data" ? input.content.publicProfile.data : null;
  const presentation = profile
    ? {
        ...input.presentation,
        // Corporate directory identity is canonical; the public profile enriches
        // the same user and must not rename the entity shown in the hub.
        name: input.member.display_name?.trim() || input.unknownName,
        description: profile.bio?.trim() || input.presentation.description,
        avatar_url: profile.avatar_url ?? input.presentation.avatar_url,
        links: profile.links.length ? [...profile.links] : input.presentation.links,
      }
    : input.presentation;
  const memberTeams = input.teams.filter((team) =>
    team.members.some((member) => member.account_id === input.member.account_id),
  );
  const throughTeams = await Promise.all(
    memberTeams.map((team) =>
      readTeamProjects(input.sessionToken, input.organizationId, team.team_id),
    ),
  );
  const projectOptions = new Map(input.projects.map((project) => [project.project_id, project]));
  const projects = [
    ...new Map(
      throughTeams.flatMap(
        (data) =>
          data?.relations.items
            .filter((item) => item.state === "current")
            .flatMap((item) => {
              const project =
                data.projects?.items.find(
                  (candidate) => candidate.project_id === item.project_id,
                ) ?? projectOptions.get(item.project_id);
              return project ? [[project.project_id, project] as const] : [];
            }) ?? [],
      ),
    ).values(),
  ];
  return applyCorporateEmployeePresentation(presentation, {
    member: input.member,
    teams: input.teams,
    projects,
    technologies:
      input.includeTechnologies !== false && input.content.technologies.status === "data"
        ? input.content.technologies.data
        : [],
    authoredComponents:
      input.content.components.status === "data" ? input.content.components.data : [],
    unknownName: input.unknownName,
  });
}
