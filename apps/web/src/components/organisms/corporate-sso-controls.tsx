"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Switch } from "@/components/atoms/switch";
import { InfoNote } from "@/components/molecules/info-note";
import { SettingsSection } from "@/components/molecules/settings-section";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import type {
  CorporateSsoProvider,
  CorporateSsoProviderView,
  CorporateSsoView,
} from "@/lib/api/corporate-sso";

const PROVIDERS: readonly CorporateSsoProvider[] = ["saml", "oidc"];

function SsoProviderCard({
  provider,
  view,
  canManage,
  organizationId,
  authority,
}: {
  provider: CorporateSsoProvider;
  view: CorporateSsoProviderView | null;
  canManage: boolean;
  organizationId: string;
  authority: GovernanceAuthority;
}) {
  const c = useTranslations("corporate");
  const t = useTranslations("technology");
  const [on, setOn] = useState(view?.enabled ?? false);
  const mutation = useGovernanceMutation(authority);
  const disabled = mutation.busy || !canManage;
  return (
    <form
      className="border-border space-y-4 rounded-lg border p-4"
      aria-busy={mutation.busy}
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const text = (key: string) => {
          const value = data.get(key);
          return typeof value === "string" && value.trim() ? value.trim() : null;
        };
        mutation.save(
          `/v1/corporate/organizations/${authority.organizationId}/sso`,
          {
            provider,
            enabled: on,
            issuer_url: provider === "oidc" ? text("issuer_url") : null,
            client_id: provider === "oidc" ? text("client_id") : null,
            idp_metadata_url: provider === "saml" ? text("idp_metadata_url") : null,
          },
          "PUT",
          () => {},
        );
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{c(`ssoProviders.${provider}.title`)}</p>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {c(`ssoProviders.${provider}.description`)}
          </p>
        </div>
        <Badge variant={view?.enabled ? "success" : "secondary"}>
          {view?.enabled ? c("ssoEnabled") : c("ssoNotConfigured")}
        </Badge>
      </div>
      <fieldset disabled={disabled} className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <Label htmlFor={`sso-${provider}-enabled`}>{c("ssoEnable")}</Label>
          <Switch
            id={`sso-${provider}-enabled`}
            name="enabled"
            defaultChecked={view?.enabled ?? false}
            disabled={disabled}
            aria-label={`${c("ssoEnable")} ${c(`ssoProviders.${provider}.title`)}`}
            onCheckedChange={setOn}
          />
        </div>
        {on ? (
          <div className="space-y-3">
            {provider === "saml" ? (
              <div className="space-y-2">
                <Label htmlFor="sso-saml-metadata">{c("ssoIdpMetadataUrl")}</Label>
                <Input
                  id="sso-saml-metadata"
                  name="idp_metadata_url"
                  type="url"
                  required
                  defaultValue={view?.idp_metadata_url ?? ""}
                  placeholder={c("ssoMetadataPlaceholder")}
                />
                <p className="text-muted-foreground text-xs">{c("ssoIdpMetadataHint")}</p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <Label htmlFor="sso-oidc-issuer">{c("ssoIssuerUrl")}</Label>
                  <Input
                    id="sso-oidc-issuer"
                    name="issuer_url"
                    type="url"
                    required
                    defaultValue={view?.issuer_url ?? ""}
                    placeholder={c("ssoIssuerPlaceholder")}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sso-oidc-client">{c("ssoClientId")}</Label>
                  <Input
                    id="sso-oidc-client"
                    name="client_id"
                    required
                    defaultValue={view?.client_id ?? ""}
                    placeholder={c("ssoClientIdPlaceholder")}
                  />
                </div>
              </>
            )}
            <dl className="space-y-2 text-sm">
              <dt className="text-muted-foreground text-xs">{c("ssoEntityId")}</dt>
              <dd className="break-all">{`ai-stp:${organizationId}`}</dd>
              <dt className="text-muted-foreground text-xs">
                {c(provider === "saml" ? "ssoAcsUrl" : "ssoRedirectUrl")}
              </dt>
              <dd className="break-all">
                {provider === "saml"
                  ? `/v1/auth/saml/${organizationId}/acs`
                  : `/v1/auth/oidc/${organizationId}/callback`}
              </dd>
            </dl>
          </div>
        ) : null}
      </fieldset>
      <div className="flex items-center justify-end gap-3">
        {mutation.message && (
          <p className="text-muted-foreground text-sm" role="status">
            {mutation.message}
          </p>
        )}
        {canManage ? (
          <Button type="submit" size="sm" disabled={mutation.busy}>
            {t(mutation.busy ? "saving" : "saveChanges")}
          </Button>
        ) : null}
      </div>
    </form>
  );
}

/**
 * Organization SSO surface: SAML and OIDC provider cards. `sso === null`
 * means the endpoint is absent on this deployment — cards render disabled
 * and the note names the deployment-level providers instead of a dead form.
 */
export function CorporateSsoControls({
  sso,
  canManage = true,
  deploymentProviders = [],
  ...authority
}: GovernanceAuthority & {
  sso: CorporateSsoView | null;
  canManage?: boolean;
  /** Deployment-level OIDC providers configured through the environment. */
  deploymentProviders?: readonly string[];
}) {
  const c = useTranslations("corporate");
  const available = sso !== null;
  return (
    <SettingsSection icon="lock" title={c("ssoTitle")} description={c("ssoDescription")}>
      {available ? null : (
        <InfoNote>
          {deploymentProviders.length
            ? c("ssoUnavailableWithProviders", {
                providers: deploymentProviders.join(", "),
              })
            : c("ssoUnavailable")}
        </InfoNote>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {PROVIDERS.map((provider) => (
          <SsoProviderCard
            key={provider}
            provider={provider}
            view={sso?.providers.find((item) => item.provider === provider) ?? null}
            canManage={available && canManage}
            organizationId={authority.organizationId}
            authority={authority}
          />
        ))}
      </div>
    </SettingsSection>
  );
}
