#!/usr/bin/env bash
# Fetch and deploy the one monotonic ref published by the green CI workflow.
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
deploy_ref=${AI_STP_PULL_REF:-refs/heads/deploy/prod}
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

git --git-dir="${mirror}" fetch --quiet --no-tags origin \
  "+${deploy_ref}:refs/remotes/origin/deploy/prod"
candidate=$(git --git-dir="${mirror}" rev-parse --verify 'refs/remotes/origin/deploy/prod^{commit}')
[[ ${candidate} =~ ^[0-9a-f]{40}$ ]] || { printf 'invalid deployment commit\n' >&2; exit 1; }

current=
if [[ -f ${root}/.deploy-state/current ]]; then
  current=$(sed -n 's/^git_commit=//p' "${root}/.deploy-state/current" | head -n 1)
fi
if [[ ${current} == "${candidate}" ]]; then
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
  mv "${temporary}" "${release}"
  trap - EXIT
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
printf 'pull_deploy_complete commit=%s\n' "${candidate}"
