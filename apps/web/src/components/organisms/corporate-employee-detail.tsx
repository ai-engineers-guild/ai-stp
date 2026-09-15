import { Badge } from "@/components/atoms/badge";
import { AvatarImage } from "@/components/atoms/avatar-image";
import { StatePanel } from "@/components/molecules/state-panel";
import type { CorporateEmployeeContent } from "@/lib/api/corporate-employee";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export type CorporateEmployeeDetailLabels = {
  profile: string;
  profileEmpty: string;
  profileUnavailable: string;
  noAccess: string;
  authoredSetups: string;
  noSetups: string;
  setupsUnavailable: string;
  authoredComponents: string;
  noComponents: string;
  componentsUnavailable: string;
  version: string;
  technologies: string;
  noTechnologies: string;
  technologiesUnavailable: string;
  leadStatus: string;
  notLead: string;
};

export function corporateEmployeeDetailLabels(
  t: (key: string) => string,
): CorporateEmployeeDetailLabels {
  return {
    profile: t("employeePublicProfile"),
    profileEmpty: t("employeeProfileEmpty"),
    profileUnavailable: t("employeeProfileUnavailable"),
    noAccess: t("employeeNoAccess"),
    authoredSetups: t("employeeAuthoredSetups"),
    noSetups: t("employeeNoSetups"),
    setupsUnavailable: t("employeeSetupsUnavailable"),
    authoredComponents: t("employeeAuthoredComponents"),
    noComponents: t("employeeNoComponents"),
    componentsUnavailable: t("employeeComponentsUnavailable"),
    version: t("employeeVersion"),
    technologies: t("employeeTechnologies"),
    noTechnologies: t("employeeNoTechnologies"),
    technologiesUnavailable: t("employeeTechnologiesUnavailable"),
    leadStatus: t("employeeLeadStatus"),
    notLead: t("employeeNotLead"),
  };
}

export function CorporateEmployeeDetail({
  content,
  leadTeams,
  labels,
}: {
  content: Pick<
    CorporateEmployeeContent,
    "publicProfile" | "components" | "setups" | "technologies"
  >;
  leadTeams: readonly { id: string; name: string }[];
  labels: CorporateEmployeeDetailLabels;
}) {
  return (
    <div className="grid min-w-0 gap-6 md:grid-cols-2">
      <EmployeePublicProfile state={content.publicProfile} labels={labels} />
      <EmployeeSetups state={content.setups} labels={labels} />
      <EmployeeComponents state={content.components} labels={labels} />
      <EmployeeTechnologies state={content.technologies} labels={labels} />
      {!leadTeams.length ? (
        <ReadState title={labels.leadStatus} message={labels.notLead} state="empty" />
      ) : null}
    </div>
  );
}

function EmployeeTechnologies({
  state,
  labels,
}: {
  state: CorporateEmployeeContent["technologies"];
  labels: CorporateEmployeeDetailLabels;
}) {
  if (state.status === "data") return null;
  if (state.status === "noaccess") {
    return <ReadState title={labels.technologies} message={labels.noAccess} state="noaccess" />;
  }
  if (state.status === "error") {
    return (
      <StatePanel
        kind="error"
        title={labels.technologies}
        description={labels.technologiesUnavailable}
      />
    );
  }
  return <ReadState title={labels.technologies} message={labels.noTechnologies} state="empty" />;
}

function EmployeePublicProfile({
  state,
  labels,
}: {
  state: CorporateEmployeeContent["publicProfile"];
  labels: CorporateEmployeeDetailLabels;
}) {
  if (state.status === "noaccess") {
    return <ReadState title={labels.profile} message={labels.noAccess} state="noaccess" />;
  }
  if (state.status === "error") {
    return (
      <StatePanel kind="error" title={labels.profile} description={labels.profileUnavailable} />
    );
  }
  if (state.status === "empty" || !state.data) {
    return <ReadState title={labels.profile} message={labels.profileEmpty} state="empty" />;
  }
  const profile = state.data;
  return (
    <section
      className="border-border bg-card min-w-0 space-y-4 rounded-lg border p-5"
      aria-labelledby="employee-public-profile"
    >
      <div className="flex min-w-0 items-center gap-3">
        <AvatarImage
          src={profile.avatar_url}
          width={56}
          className="size-14 rounded-full object-cover"
          fallback={<Icon name="user" size="lg" />}
        />
        <h2 id="employee-public-profile" className="min-w-0 text-xl font-medium break-words">
          {profile.display_name || labels.profileEmpty}
        </h2>
      </div>
      {profile.bio ? (
        <p className="text-muted-foreground text-sm leading-relaxed whitespace-pre-wrap">
          {profile.bio}
        </p>
      ) : null}
      {profile.links.length ? (
        <ul className="border-border space-y-2 border-t pt-4">
          {profile.links.map((link) => (
            <li key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 max-w-full items-center break-all underline underline-offset-4"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function EmployeeSetups({
  state,
  labels,
}: {
  state: CorporateEmployeeContent["setups"];
  labels: CorporateEmployeeDetailLabels;
}) {
  if (state.status === "noaccess") {
    return <ReadState title={labels.authoredSetups} message={labels.noAccess} state="noaccess" />;
  }
  if (state.status === "error") {
    return (
      <StatePanel
        kind="error"
        title={labels.authoredSetups}
        description={labels.setupsUnavailable}
      />
    );
  }
  if (state.status === "empty" || !state.data) {
    return <ReadState title={labels.authoredSetups} message={labels.noSetups} state="empty" />;
  }
  return (
    <section className="min-w-0 space-y-3" aria-labelledby="employee-authored-setups">
      <h2 id="employee-authored-setups" className="text-xl font-medium">
        {labels.authoredSetups}
      </h2>
      <ul className="border-border divide-border min-w-0 divide-y rounded-lg border">
        {state.data.map((item) => (
          <li key={`${item.kind}:${item.id}`} className="min-w-0">
            <Link
              href={`/catalog/setups/${encodeURIComponent(item.id)}`}
              className="hover:bg-muted/50 focus-visible:ring-ring flex min-h-14 min-w-0 items-center justify-between gap-3 p-4 focus-visible:ring-2 focus-visible:outline-none"
            >
              <span className="min-w-0 truncate font-medium">{item.name}</span>
              {item.version ? (
                <Badge variant="outline">
                  {labels.version} {item.version}
                </Badge>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EmployeeComponents({
  state,
  labels,
}: {
  state: CorporateEmployeeContent["components"];
  labels: CorporateEmployeeDetailLabels;
}) {
  if (state.status === "data") return null;
  if (state.status === "noaccess") {
    return (
      <ReadState title={labels.authoredComponents} message={labels.noAccess} state="noaccess" />
    );
  }
  if (state.status === "error") {
    return (
      <StatePanel
        kind="error"
        title={labels.authoredComponents}
        description={labels.componentsUnavailable}
      />
    );
  }
  return (
    <ReadState title={labels.authoredComponents} message={labels.noComponents} state="empty" />
  );
}

function ReadState({
  title,
  message,
  state,
}: {
  title: string;
  message: string;
  state: "empty" | "noaccess";
}) {
  return (
    <section className="border-border bg-card min-w-0 rounded-lg border p-5" aria-label={title}>
      <h2 className="text-xl font-medium">{title}</h2>
      <p className="text-muted-foreground mt-3 text-sm" data-state={state}>
        {message}
      </p>
    </section>
  );
}
