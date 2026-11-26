#!/usr/bin/env bash
# Fetch and deploy Main, the qualified source that only fast-forwards.
#
# The source is this repository, and it is public, so the fetch carries no
# credential at all. That is the point rather than a convenience: a deployment
# anyone can read is a deployment anyone can verify, and the identity this host
# reports at `/v1/system/version` resolves to a commit in the open.
set -euo pipefail

umask 077

root=${AI_STP_ROOT:-"${HOME}/ai_stp"}
state_root=${AI_STP_PULL_STATE_ROOT:-"${HOME}/.local/state/ai-stp-deployer"}
repository=${AI_STP_PULL_REPOSITORY:-https://github.com/ai-engineers-guild/ai-stp.git}
deploy_ref=${AI_STP_PULL_REF:-refs/heads/main}
mirror=${state_root}/repository.git
release_root=${state_root}/releases
lock_file=${state_root}/pull-deploy.lock

mkdir -p "${state_root}" "${release_root}"
exec 9>"${lock_file}"
flock -n 9 || { printf 'pull_deploy_already_running\n' >&2; exit 0; }

if [[ ! -d ${mirror} ]]; then
  git init --bare --quiet "${mirror}"
  git --git-dir="${mirror}" remote add origin "${repository}"
fi
# Reconcile the remote every run, not only at creation. Setting it once meant
# `${repository}` described the mirror's first fetch and nothing after it, so
# changing the source silently kept fetching the old one — which is exactly how
# it behaved when the source moved to this repository.
git --git-dir="${mirror}" remote set-url origin "${repository}"

GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c http.version=HTTP/1.1 \
  --git-dir="${mirror}" \
  fetch --quiet --no-tags origin \
  "+${deploy_ref}:refs/remotes/origin/candidate"
candidate=$(git --git-dir="${mirror}" rev-parse --verify 'refs/remotes/origin/candidate^{commit}')
[[ ${candidate} =~ ^[0-9a-f]{40}$ ]] || { printf 'invalid deployment commit\n' >&2; exit 1; }

current=
if [[ -f ${root}/.deploy-state/current ]]; then
  current=$(sed -n 's/^git_commit=//p' "${root}/.deploy-state/current" | head -n 1)
fi
release_tree_excluded_paths() {
  local tree=$1
  [[ -d ${tree} ]] || return 0
  if [[ -e ${tree}/skills ]]; then
    printf '%s/skills\n' "${tree}"
  fi
  find "${tree}" \
    \( -name '.claude' -o -name '.agents' -o -name '.codex' -o -name '.cursor' \
      -o -name '.serena' -o -name '.gemini' -o -name '.antigravity' -o -name '.pi' \
      -o -name '.opencode' -o -name '.cline' -o -name '.roo' -o -name '.windsurf' \
      -o -name '.playwright-mcp' -o -name '.gds' \) -prune -print \
    -o \( -type f \( -iname 'AGENTS.md' -o -iname 'AGENTS.override.md' \
      -o -iname 'CLAUDE.md' -o -iname 'CLAUDE.local.md' \
      -o -iname 'GEMINI.md' -o -iname 'CODEX.md' -o -iname 'CURSOR.md' \
      -o -iname 'COPILOT.md' -o -iname '.cursorrules' -o -iname '.clinerules' \
      -o -iname '.windsurfrules' -o -iname '.mcp.json' -o -iname 'mcp.json' \
      -o -iname 'claude_desktop_config.json' -o -iname 'copilot-instructions.md' \
      -o -iname '.aider*' \) -print \)
}

verify_clean_release_tree() {
  local tree=$1
  local found
  found=$(release_tree_excluded_paths "${tree}")
  if [[ -n ${found} ]]; then
    printf 'release archive contains excluded repository-only paths:\n%s\n' "${found}" >&2
    return 1
  fi
}

prune_release_archives() {
  # Each successful deploy leaves a full git-archive tree under
  # `${release_root}/${sha}`. Without a bound this grew to dozens of copies of
  # the repository. Keep the commit that is live and the one rollback would
  # return to (unless that rollback extract still holds repository-only files);
  # everything else is extract cache.
  local keep_current=$1
  local keep_previous=$2
  local dir name
  [[ -d ${release_root} ]] || return 0
  for dir in "${release_root}"/*; do
    [[ -e ${dir} ]] || continue
    name=${dir##*/}
    if [[ ${name} == "${keep_current}" ]]; then
      continue
    fi
    if [[ -n ${keep_previous} && ${name} == "${keep_previous}" ]]; then
      if [[ -z $(release_tree_excluded_paths "${dir}") ]]; then
        continue
      fi
    fi
    rm -rf -- "${dir}"
  done
  for dir in "${release_root}"/.[!.]*; do
    [[ -d ${dir} ]] || continue
    rm -rf -- "${dir}"
  done
}

previous_commit=
if [[ -f ${root}/.deploy-state/previous ]]; then
  previous_commit=$(sed -n 's/^git_commit=//p' "${root}/.deploy-state/previous" | head -n 1)
fi

# Main reaches a new CLI version before that version is published: promotion
# fast-forwards Main, then the release workflow publishes the download the site
# links to. A candidate is deployed only once its linked release is publicly
# downloadable, so a deployed page never points at a missing download. Until
# then the host keeps serving and checking the current release. A draft release
# serves no anonymous download, so one asset answering means it is published.
cli_link=$(git --git-dir="${mirror}" show \
  "${candidate}:packages/contracts/src/ai_stp_contracts/cli_copy.py" \
  | sed -n 's|^CLI_RELEASES_URL: Final = "\(.*\)"$|\1|p')
cli_version=${cli_link##*/cli-v}
[[ ${cli_link} == "${repository%.git}/releases/tag/cli-v${cli_version}" \
  && ${cli_version} =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || { printf 'candidate has no canonical CLI release link\n' >&2; exit 1; }
if [[ ${current} != "${candidate}" ]] && ! curl -fsSIL --max-time 30 -o /dev/null \
  "${repository%.git}/releases/download/cli-v${cli_version}/ai-stp-cli-${cli_version}.crate"; then
  printf 'pull_deploy_waiting_for_cli candidate=%s version=%s\n' "${candidate}" "${cli_version}"
  [[ -n ${current} ]] || exit 0
  candidate=${current}
fi

if [[ ${current} == "${candidate}" ]]; then
  prune_release_archives "${candidate}" "${previous_commit}"
  # "Already current" is not "healthy": it only proves nothing new is ready
  # to deploy. This timer tick is the host's only scheduled check, so the
  # external verification still runs against the serving stack.
  (
    cd "${root}"
    bash -lc './deploy/verify.sh'
  )
  printf 'pull_deploy_already_current commit=%s\n' "${candidate}"
  exit 0
fi
# A recorded baseline that is not a commit is no baseline. It used to be a fatal
# error, and combined with a root that carries no `.git` that made a deadlock:
# the record said `unknown`, resolving it aborted the script, and nothing could
# ever replace the record. Anti-rollback still holds wherever a baseline exists;
# where it does not, there is nothing to roll back from.
if [[ -n ${current} ]] && ! git --git-dir="${mirror}" cat-file -e "${current}^{commit}" 2>/dev/null; then
  printf 'pull_deploy_baseline_unresolvable current=%s\n' "${current}" >&2
  current=
fi
if [[ -n ${current} ]]; then
  git --git-dir="${mirror}" merge-base --is-ancestor "${current}" "${candidate}" || {
    printf 'deployment ref is not a fast-forward from current=%s candidate=%s\n' "${current}" "${candidate}" >&2
    exit 1
  }
fi

release=${release_root}/${candidate}
if [[ ! -d ${release} ]]; then
  temporary=$(mktemp -d "${release_root}/.${candidate}.XXXXXX")
  trap 'rm -rf -- "${temporary}"' EXIT
  git --git-dir="${mirror}" archive "${candidate}" \
    | tar --extract --preserve-permissions -C "${temporary}"
  verify_clean_release_tree "${temporary}"
  mv "${temporary}" "${release}"
  trap - EXIT
else
  verify_clean_release_tree "${release}"
fi

AI_STP_REMOTE_ROOT="${root}" bash "${release}/deploy/mark-transfer.sh" "${candidate}"
rsync -a --delete --delete-delay --delay-updates \
  --exclude '.env.prod' --exclude '.env.dev' --exclude '.deploy-env' \
  --exclude '.deploy-state' --exclude '.backups' \
  --exclude '.venv' --exclude 'node_modules' --exclude '.next' \
  --exclude 'dist' --exclude '.site' --exclude '__pycache__' \
  "${release}/" "${root}/"
# `umask 077` plus tar without --preserve-permissions once dropped owner
# execute on every deploy script (systemd 203/EXEC). Preserve archive modes
# above; restore execute on the scripts this unit invokes by name.
chmod u+x \
  "${root}/deploy/pull-deploy.sh" \
  "${root}/deploy/run.sh" \
  "${root}/deploy/verify.sh" \
  "${root}/deploy/deploy.sh" \
  "${root}/deploy/lib.sh" \
  "${root}/deploy/load-apparmor.sh" \
  "${root}/deploy/mark-transfer.sh"

(
  cd "${root}"
  # The identity travels with the bytes. Nothing under `${root}` can derive it:
  # the release arrives through `git archive`, so there is no repository to ask.
  export AI_STP_DEPLOY_COMMIT="${candidate}"
  export AI_STP_API_GIT_COMMIT="${candidate}"
  bash -lc './deploy/run.sh'
  bash -lc './deploy/verify.sh'
)
prune_release_archives "${candidate}" "${current}"
printf 'pull_deploy_complete commit=%s\n' "${candidate}"
