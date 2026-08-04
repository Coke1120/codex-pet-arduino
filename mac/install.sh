#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
runtime_dir="$HOME/Library/Application Support/CodexPet/runtime"
launch_agents_dir="$HOME/Library/LaunchAgents"
default_label="com.coke1120.codex-pet"
label="$default_label"
legacy_label="org.example.codex-pet"
port=""
skip_dependencies=0
skip_launchctl=0

usage() {
  printf '%s\n' \
    "Usage: mac/install.sh [options]" \
    "" \
    "Options:" \
    "  --port PORT              Serial port; preserves the installed value by default" \
    "  --label LABEL            LaunchAgent label (default: com.coke1120.codex-pet)" \
    "  --runtime-dir DIR        Runtime destination" \
    "  --launch-agents-dir DIR  LaunchAgent plist directory" \
    "  --skip-dependencies      Keep the existing venv packages" \
    "  --skip-launchctl         Install files without loading the LaunchAgent" \
    "  --help                   Show this help"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      [[ $# -ge 2 ]] || { printf 'Missing value for --port\n' >&2; exit 2; }
      port=$2
      shift 2
      ;;
    --label)
      [[ $# -ge 2 ]] || { printf 'Missing value for --label\n' >&2; exit 2; }
      label=$2
      shift 2
      ;;
    --runtime-dir)
      [[ $# -ge 2 ]] || { printf 'Missing value for --runtime-dir\n' >&2; exit 2; }
      runtime_dir=$2
      shift 2
      ;;
    --launch-agents-dir)
      [[ $# -ge 2 ]] || { printf 'Missing value for --launch-agents-dir\n' >&2; exit 2; }
      launch_agents_dir=$2
      shift 2
      ;;
    --skip-dependencies)
      skip_dependencies=1
      shift
      ;;
    --skip-launchctl)
      skip_launchctl=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$label" =~ ^[A-Za-z0-9._-]+$ ]] || {
  printf 'Invalid LaunchAgent label: %s\n' "$label" >&2
  exit 2
}

host_python=$(command -v python3 || true)
[[ -n "$host_python" ]] || {
  printf 'Python 3 is required to install Codex Pet.\n' >&2
  exit 1
}

normalized_runtime_dir=$(
  "$host_python" - \
    "$runtime_dir" \
    "$HOME" \
    "$repo_root" \
    "$launch_agents_dir" <<'PY'
import os
import sys
import tempfile

raw_runtime, home_dir, repository_root, launch_agents = sys.argv[1:]
if not raw_runtime or raw_runtime.endswith(os.sep):
    raise SystemExit("runtime directory must have a non-empty basename")
if any(part in (".", "..") for part in raw_runtime.split(os.sep)):
    raise SystemExit("runtime directory may not contain . or .. components")

runtime = os.path.realpath(os.path.abspath(raw_runtime))
home = os.path.realpath(os.path.abspath(home_dir))
repository = os.path.realpath(os.path.abspath(repository_root))
agents = os.path.realpath(os.path.abspath(launch_agents))

def is_ancestor_or_same(parent, child):
    return child == parent or child.startswith(parent + os.sep)

common_roots = {
    os.sep,
    "/private",
    "/tmp",
    "/private/tmp",
    "/var",
    "/private/var",
    "/var/folders",
    "/private/var/folders",
    "/Users",
    "/private/Users",
    "/System",
    "/private/System",
    "/Library",
    "/private/Library",
    "/Applications",
    "/private/Applications",
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/private/etc",
    "/Volumes",
    "/Network",
    "/dev",
    "/opt",
    os.path.realpath(tempfile.gettempdir()),
}
if runtime in common_roots or runtime == home or runtime == repository:
    raise SystemExit("runtime directory is a protected root")
if is_ancestor_or_same(runtime, home):
    raise SystemExit("runtime directory may not contain the home directory")
if is_ancestor_or_same(runtime, repository):
    raise SystemExit("runtime directory may not contain the repository")
if is_ancestor_or_same(runtime, agents):
    raise SystemExit("runtime directory may not contain LaunchAgents")
print(runtime)
PY
) || {
  printf 'Unsafe runtime directory: %s\n' "$runtime_dir" >&2
  exit 2
}

runtime_python="$runtime_dir/bin/python"
runtime_parent=$(dirname "$runtime_dir")
mkdir -p "$runtime_parent" "$launch_agents_dir"
runtime_transaction_root=$(mktemp -d "$runtime_parent/.codex-pet-runtime.XXXXXX")
cleanup_runtime_transaction() {
  if [[ -n "${runtime_transaction_root:-}" && -d "$runtime_transaction_root" ]]; then
    rm -rf "$runtime_transaction_root"
  fi
}
trap cleanup_runtime_transaction EXIT
runtime_staged_dir="$runtime_transaction_root/staged-runtime"
runtime_backup_path="$runtime_transaction_root/original-runtime"
runtime_failed_path="$runtime_transaction_root/failed-runtime"
runtime_original_exists=0
runtime_original_moved=0
runtime_staged_moved=0
if [[ -L "$runtime_dir" ]]; then
  printf 'Runtime destination must not be a symlink: %s\n' "$runtime_dir" >&2
  exit 1
elif [[ -e "$runtime_dir" ]]; then
  if [[ ! -d "$runtime_dir" ]]; then
    printf 'Runtime destination must be a directory: %s\n' "$runtime_dir" >&2
    exit 1
  fi
  cp -pR "$runtime_dir" "$runtime_staged_dir"
  runtime_original_exists=1
else
  mkdir -p "$runtime_staged_dir"
fi

atomic_copy() {
  local source_file=$1
  local destination_file=$2
  local temporary_file
  temporary_file=$(mktemp "${destination_file}.tmp.XXXXXX")
  cp "$source_file" "$temporary_file"
  chmod 0644 "$temporary_file"
  mv -f "$temporary_file" "$destination_file"
}

staged_runtime_python="$runtime_staged_dir/bin/python"
if [[ ! -x "$staged_runtime_python" ]]; then
  "$host_python" -m venv "$runtime_staged_dir"
fi

atomic_copy "$repo_root/mac/codex_pet_daemon.py" "$runtime_staged_dir/codex_pet_daemon.py"
atomic_copy "$repo_root/mac/codex_pet_hook.py" "$runtime_staged_dir/codex_pet_hook.py"
atomic_copy "$repo_root/mac/codex_pet_usage.py" "$runtime_staged_dir/codex_pet_usage.py"
atomic_copy "$repo_root/mac/requirements.txt" "$runtime_staged_dir/requirements.txt"

if [[ $skip_dependencies -eq 0 ]]; then
  "$staged_runtime_python" -m pip install --disable-pip-version-check --require-hashes \
    -r "$runtime_staged_dir/requirements.txt"
fi

plist_path="$launch_agents_dir/$label.plist"
default_plist="$launch_agents_dir/$default_label.plist"
legacy_plist="$launch_agents_dir/$legacy_label.plist"
managed_marker="com.coke1120.codex-pet"

# A user-selected label is not stable across reinstalls. Discover old Codex
# Pet jobs by a managed marker or the exact current runtime identity, rather
# than by deleting every plist in LaunchAgents (which could remove another
# service). The marker keeps new installs discoverable after the runtime
# directory changes; the exact check keeps older same-runtime installs
# discoverable without treating lookalike services as managed.
candidate_plists=()
for candidate_plist in "$launch_agents_dir"/*.plist; do
  [[ -f "$candidate_plist" ]] || continue
  candidate_plists+=("$candidate_plist")
done
recognized_plists=()
while IFS= read -r recognized_path; do
  [[ -n "$recognized_path" ]] || continue
  recognized_plists+=("$recognized_path")
done < <(
  "$host_python" - \
    "$managed_marker" \
    "$runtime_python" \
    "$runtime_dir/codex_pet_daemon.py" \
    "${candidate_plists[@]-}" <<'PY'
import os
import plistlib
import sys

managed_marker, expected_python, expected_daemon = sys.argv[1:4]
expected_python = os.path.normpath(expected_python)
expected_daemon = os.path.normpath(expected_daemon)
for path in sys.argv[4:]:
    try:
        with open(path, "rb") as handle:
            payload = plistlib.load(handle)
        if not isinstance(payload, dict):
            continue
        if payload.get("CodexPetManaged") == managed_marker:
            print(path)
            continue
        arguments = payload.get("ProgramArguments")
        if not isinstance(arguments, list) or len(arguments) != 4:
            continue
        if (
            arguments[2] != "--port"
            or not isinstance(arguments[3], str)
            or not isinstance(arguments[0], str)
            or not isinstance(arguments[1], str)
            or os.path.normpath(arguments[0]) != expected_python
            or os.path.normpath(arguments[1]) != expected_daemon
        ):
            continue
        print(path)
    except Exception:
        # A stale or malformed plist must not make installation fail.
        continue
PY
)

add_existing_path() {
  local path=$1
  local existing
  [[ -f "$path" ]] || return 0
  for existing in "${port_sources[@]-}"; do
    [[ "$existing" == "$path" ]] && return 0
  done
  port_sources+=("$path")
}

port_sources=()
add_existing_path "$plist_path"
add_existing_path "$default_plist"
add_existing_path "$legacy_plist"
for recognized_path in "${recognized_plists[@]-}"; do
  add_existing_path "$recognized_path"
done
if [[ -z "$port" && ${#port_sources[@]} -gt 0 ]]; then
  port=$(
    "$host_python" - "${port_sources[@]}" <<'PY'
import plistlib
import sys

for path in sys.argv[1:]:
    try:
        with open(path, "rb") as handle:
            payload = plistlib.load(handle)
        if not isinstance(payload, dict):
            raise TypeError("plist root must be a dictionary")
        arguments = payload.get("ProgramArguments", [])
        if not isinstance(arguments, list):
            raise TypeError("ProgramArguments must be a list")
        index = arguments.index("--port")
        value = arguments[index + 1]
        if isinstance(value, str):
            print(value)
            break
    except (OSError, TypeError, ValueError, IndexError, plistlib.InvalidFileException):
        pass
PY
  )
fi
port=${port:-auto}

plist_service_label() {
  local path=$1
  local fallback_label=${path##*/}
  fallback_label=${fallback_label%.plist}
  "$host_python" - "$path" "$fallback_label" <<'PY'
import plistlib
import sys

path, fallback = sys.argv[1:]
try:
    with open(path, "rb") as handle:
        payload = plistlib.load(handle)
    label = payload.get("Label") if isinstance(payload, dict) else None
    if isinstance(label, str) and label:
        print(label)
    else:
        print(fallback)
except Exception:
    print(fallback)
PY
}

selected_service_label=$(plist_service_label "$plist_path")

cleanup_plists=()
add_cleanup_path() {
  local path=$1
  local existing
  [[ "$path" != "$plist_path" && -f "$path" ]] || return 0
  for existing in "${cleanup_plists[@]-}"; do
    [[ "$existing" == "$path" ]] && return 0
  done
  cleanup_plists+=("$path")
}
# The well-known labels remain migration targets for older installations.
add_cleanup_path "$default_plist"
add_cleanup_path "$legacy_plist"
for recognized_path in "${recognized_plists[@]-}"; do
  add_cleanup_path "$recognized_path"
done

if [[ $skip_launchctl -eq 1 && ${#cleanup_plists[@]} -gt 0 ]]; then
  printf 'Cannot migrate competing Codex Pet LaunchAgents with --skip-launchctl.\n' >&2
  exit 1
fi

plist_temp=""
cleanup_plist_temp() {
  if [[ -n "${plist_temp:-}" && -f "$plist_temp" ]]; then
    rm -f "$plist_temp"
  fi
}
transaction_dir=""
cleanup_transaction_dir() {
  if [[ -n "${transaction_dir:-}" && -d "$transaction_dir" ]]; then
    rm -rf "$transaction_dir"
  fi
}
cleanup_install() {
  cleanup_plist_temp
  cleanup_transaction_dir
  cleanup_runtime_transaction
}
trap cleanup_install EXIT
create_plist_temp() {
  plist_temp=$(mktemp "${plist_path}.tmp.XXXXXX")
  "$host_python" - \
    "$plist_temp" \
    "$label" \
    "$runtime_python" \
    "$runtime_dir/codex_pet_daemon.py" \
    "$port" \
    "$(dirname "$runtime_dir")/daemon.out.log" \
    "$(dirname "$runtime_dir")/daemon.err.log" \
    "$managed_marker" <<'PY'
import plistlib
import sys

destination, label, python, daemon, port, stdout, stderr, managed_marker = sys.argv[1:]
payload = {
    "Label": label,
    "CodexPetManaged": managed_marker,
    "ProgramArguments": [python, daemon, "--port", port],
    "RunAtLoad": True,
    "KeepAlive": True,
    "ProcessType": "Background",
    "StandardOutPath": stdout,
    "StandardErrorPath": stderr,
}
with open(destination, "wb") as handle:
    plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=False)
PY
  chmod 0644 "$plist_temp"
}

runtime_path_exists() {
  [[ -e "$1" || -L "$1" ]]
}
commit_runtime_transaction() {
  if [[ $runtime_original_exists -eq 1 ]]; then
    if ! mv -f "$runtime_dir" "$runtime_backup_path"; then
      return 1
    fi
    runtime_original_moved=1
  fi
  if ! mv -f "$runtime_staged_dir" "$runtime_dir"; then
    return 1
  fi
  runtime_staged_moved=1
  return 0
}
restore_runtime_transaction() {
  local restore_status=0
  if [[ $runtime_staged_moved -eq 1 ]] && runtime_path_exists "$runtime_dir"; then
    if ! mv -f "$runtime_dir" "$runtime_failed_path"; then
      restore_status=1
    fi
  fi
  if [[ $runtime_original_moved -eq 1 ]]; then
    if runtime_path_exists "$runtime_backup_path"; then
      if ! mv -f "$runtime_backup_path" "$runtime_dir"; then
        restore_status=1
      fi
    else
      restore_status=1
    fi
  fi
  if [[ $restore_status -eq 0 ]]; then
    runtime_original_moved=0
    runtime_staged_moved=0
  else
    printf 'Codex Pet runtime rollback incomplete.\n' >&2
  fi
  return "$restore_status"
}
skip_plist_snapshot="$runtime_transaction_root/original-selected.plist"
skip_plist_original_exists=0
snapshot_skip_plist() {
  if [[ -f "$plist_path" ]]; then
    if ! cp -p "$plist_path" "$skip_plist_snapshot"; then
      return 1
    fi
    skip_plist_original_exists=1
  fi
  return 0
}
restore_skip_plist() {
  if [[ $skip_plist_original_exists -eq 1 ]]; then
    cp -p "$skip_plist_snapshot" "$plist_path"
  elif runtime_path_exists "$plist_path"; then
    rm -f "$plist_path"
  else
    return 0
  fi
}

if [[ $skip_launchctl -eq 1 ]]; then
  if ! snapshot_skip_plist; then
    printf 'Unable to snapshot the selected Codex Pet LaunchAgent.\n' >&2
    exit 1
  fi
  create_plist_temp
  if ! commit_runtime_transaction; then
    if ! restore_runtime_transaction; then
      :
    fi
    exit 1
  fi
  if ! mv -f "$plist_temp" "$plist_path"; then
    if ! restore_skip_plist; then
      printf 'Codex Pet plist rollback incomplete.\n' >&2
    fi
    if ! restore_runtime_transaction; then
      :
    fi
    exit 1
  fi
  plist_temp=""
else
  platform_name=${CODEX_PET_PLATFORM_NAME:-$(uname -s)}
  [[ "$platform_name" == "Darwin" ]] || {
    printf 'LaunchAgent installation requires macOS.\n' >&2
    exit 1
  }
  launchctl_bin=${CODEX_PET_LAUNCHCTL_BIN:-launchctl}
  service_user_id=${CODEX_PET_USER_ID:-$(id -u)}
  service_domain="gui/$service_user_id"
  transaction_dir=$(mktemp -d "${launch_agents_dir}/.codex-pet-transaction.XXXXXX")
  transaction_paths=()
  transaction_labels=()
  transaction_loaded=()
  transaction_exists=()
  transaction_snapshots=()
  launchctl_service_is_loaded() {
    local service_target=$1
    "$launchctl_bin" print "$service_target" >/dev/null 2>&1
  }
  unload_launch_agent() {
    local plist_path=$1
    local service_label=${2:-}
    local service_target
    if [[ -z "$service_label" ]]; then
      service_label=$(plist_service_label "$plist_path")
    fi
    service_target="$service_domain/$service_label"
    "$launchctl_bin" bootout "$service_domain" "$plist_path" >/dev/null 2>&1 || true
    if launchctl_service_is_loaded "$service_target"; then
      # A successful bootout can still leave a KeepAlive job loaded while
      # launchd settles. Retry once, then refuse to remove or replace it.
      "$launchctl_bin" bootout "$service_domain" "$plist_path" >/dev/null 2>&1 || true
      if launchctl_service_is_loaded "$service_target"; then
        printf 'Unable to unload loaded Codex Pet LaunchAgent: %s\n' "$plist_path" >&2
        return 1
      fi
    fi
    return 0
  }
  force_unload_launch_agent() {
    local plist_path=$1
    local service_label=${2:-}
    local service_target
    if [[ -z "$service_label" ]]; then
      service_label=$(plist_service_label "$plist_path")
    fi
    service_target="$service_domain/$service_label"
    "$launchctl_bin" bootout "$service_domain" "$plist_path" >/dev/null 2>&1 || true
    if launchctl_service_is_loaded "$service_target"; then
      "$launchctl_bin" bootout "$service_domain" "$plist_path" >/dev/null 2>&1 || true
    fi
    if launchctl_service_is_loaded "$service_target"; then
      return 1
    fi
    return 0
  }
  snapshot_transaction_path() {
    local plist_path=$1
    local index=${#transaction_paths[@]}
    local service_label
    local service_target
    local snapshot_path
    service_label=$(plist_service_label "$plist_path")
    service_target="$service_domain/$service_label"
    transaction_paths+=("$plist_path")
    transaction_labels+=("$service_label")
    if launchctl_service_is_loaded "$service_target"; then
      transaction_loaded+=(1)
    else
      transaction_loaded+=(0)
    fi
    if [[ -f "$plist_path" ]]; then
      snapshot_path="$transaction_dir/$index.plist"
      if ! cp -p "$plist_path" "$snapshot_path"; then
        return 1
      fi
      transaction_exists+=(1)
      transaction_snapshots+=("$snapshot_path")
    else
      transaction_exists+=(0)
      transaction_snapshots+=("")
    fi
    return 0
  }
  bootstrap_original_job() {
    local plist_path=$1
    if "$launchctl_bin" bootstrap "$service_domain" "$plist_path"; then
      return 0
    fi
    sleep 1
    "$launchctl_bin" bootstrap "$service_domain" "$plist_path"
  }
  rollback_transaction() {
    local index=0
    local plist_path
    local service_label
    local service_target
    local snapshot_path
    local rollback_status=0
    while [[ $index -lt ${#transaction_paths[@]} ]]; do
      plist_path=${transaction_paths[$index]}
      service_label=${transaction_labels[$index]}
      if [[ $index -eq 0 && "$label" != "$service_label" ]]; then
        if ! force_unload_launch_agent "$plist_path" "$label"; then
          rollback_status=1
        fi
      fi
      if ! force_unload_launch_agent "$plist_path" "$service_label"; then
        rollback_status=1
      fi
      index=$((index + 1))
    done
    index=0
    while [[ $index -lt ${#transaction_paths[@]} ]]; do
      plist_path=${transaction_paths[$index]}
      if [[ ${transaction_exists[$index]} -eq 1 ]]; then
        snapshot_path=${transaction_snapshots[$index]}
        if ! cp -p "$snapshot_path" "$plist_path"; then
          rollback_status=1
        fi
      elif [[ -f "$plist_path" ]]; then
        if ! rm -f "$plist_path"; then
          rollback_status=1
        fi
      fi
      index=$((index + 1))
    done
    runtime_restore_ok=1
    if ! restore_runtime_transaction; then
      runtime_restore_ok=0
      rollback_status=1
    fi
    index=0
    while [[ $runtime_restore_ok -eq 1 && $index -lt ${#transaction_paths[@]} ]]; do
      if [[ ${transaction_loaded[$index]} -eq 1 && ${transaction_exists[$index]} -eq 1 ]]; then
        plist_path=${transaction_paths[$index]}
        service_label=${transaction_labels[$index]}
        service_target="$service_domain/$service_label"
        if ! launchctl_service_is_loaded "$service_target"; then
          if ! bootstrap_original_job "$plist_path"; then
            rollback_status=1
          fi
        fi
      fi
      index=$((index + 1))
    done
    if [[ $rollback_status -ne 0 ]]; then
      printf 'Codex Pet LaunchAgent rollback incomplete.\n' >&2
    fi
    return "$rollback_status"
  }
  snapshot_transaction_path "$plist_path" || {
    printf 'Unable to snapshot the selected Codex Pet LaunchAgent.\n' >&2
    exit 1
  }
  if [[ ${transaction_loaded[0]} -eq 1 && ${transaction_exists[0]} -eq 0 ]]; then
    printf 'Cannot replace a loaded Codex Pet LaunchAgent without its plist.\n' >&2
    exit 1
  fi
  if [[ ${#cleanup_plists[@]} -gt 0 ]]; then
    for cleanup_path in "${cleanup_plists[@]}"; do
      snapshot_transaction_path "$cleanup_path" || {
        printf 'Unable to snapshot a Codex Pet LaunchAgent.\n' >&2
        exit 1
      }
    done
  fi
  create_plist_temp
  if [[ ${#cleanup_plists[@]} -gt 0 ]]; then
    for cleanup_path in "${cleanup_plists[@]}"; do
      if ! unload_launch_agent "$cleanup_path"; then
        if ! rollback_transaction; then
          :
        fi
        exit 1
      fi
    done
  fi
  # bootout's domain+plist form reliably unloads KeepAlive LaunchAgents;
  # bootout by service target can return before removing the loaded job.
  if ! unload_launch_agent "$plist_path" "$selected_service_label"; then
    if ! rollback_transaction; then
      :
    fi
    exit 1
  fi
  if ! commit_runtime_transaction; then
    if ! rollback_transaction; then
      :
    fi
    exit 1
  fi
  if ! mv -f "$plist_temp" "$plist_path"; then
    if ! rollback_transaction; then
      :
    fi
    exit 1
  fi
  plist_temp=""
  # launchd can finish bootout asynchronously; one short retry avoids its
  # transient Bootstrap failed: 5 response during an in-place update.
  if ! bootstrap_original_job "$plist_path"; then
    if ! rollback_transaction; then
      :
    fi
    exit 1
  fi
  if [[ ${#cleanup_plists[@]} -gt 0 ]]; then
    for cleanup_path in "${cleanup_plists[@]}"; do
      if ! rm -f "$cleanup_path"; then
        if ! rollback_transaction; then
          :
        fi
        exit 1
      fi
    done
  fi
fi

printf 'Codex Pet runtime installed at %s\n' "$runtime_dir"
printf 'LaunchAgent: %s (port: %s)\n' "$label" "$port"
