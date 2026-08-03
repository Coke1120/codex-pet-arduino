#!/usr/bin/env bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
runtime_dir="$HOME/Library/Application Support/CodexPet/runtime"
launch_agents_dir="$HOME/Library/LaunchAgents"
label="com.coke1120.codex-pet"
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

mkdir -p "$runtime_dir" "$launch_agents_dir"
runtime_python="$runtime_dir/bin/python"
if [[ ! -x "$runtime_python" ]]; then
  "$host_python" -m venv "$runtime_dir"
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

atomic_copy "$repo_root/mac/codex_pet_daemon.py" "$runtime_dir/codex_pet_daemon.py"
atomic_copy "$repo_root/mac/codex_pet_hook.py" "$runtime_dir/codex_pet_hook.py"
atomic_copy "$repo_root/mac/codex_pet_usage.py" "$runtime_dir/codex_pet_usage.py"
atomic_copy "$repo_root/mac/requirements.txt" "$runtime_dir/requirements.txt"

if [[ $skip_dependencies -eq 0 ]]; then
  "$runtime_python" -m pip install --disable-pip-version-check -r "$runtime_dir/requirements.txt"
fi

plist_path="$launch_agents_dir/$label.plist"
legacy_plist="$launch_agents_dir/$legacy_label.plist"
port_source=""
if [[ -f "$plist_path" ]]; then
  port_source=$plist_path
elif [[ "$legacy_plist" != "$plist_path" && -f "$legacy_plist" ]]; then
  port_source=$legacy_plist
fi
if [[ -z "$port" && -n "$port_source" ]]; then
  port=$(
    "$host_python" - "$port_source" <<'PY'
import plistlib
import sys

try:
    with open(sys.argv[1], "rb") as handle:
        arguments = plistlib.load(handle).get("ProgramArguments", [])
    index = arguments.index("--port")
    print(arguments[index + 1])
except (OSError, ValueError, IndexError, plistlib.InvalidFileException):
    pass
PY
  )
fi
port=${port:-auto}

plist_temp=$(mktemp "${plist_path}.tmp.XXXXXX")
"$host_python" - \
  "$plist_temp" \
  "$label" \
  "$runtime_python" \
  "$runtime_dir/codex_pet_daemon.py" \
  "$port" \
  "$(dirname "$runtime_dir")/daemon.out.log" \
  "$(dirname "$runtime_dir")/daemon.err.log" <<'PY'
import plistlib
import sys

destination, label, python, daemon, port, stdout, stderr = sys.argv[1:]
payload = {
    "Label": label,
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
mv -f "$plist_temp" "$plist_path"

if [[ $skip_launchctl -eq 0 ]]; then
  platform_name=${CODEX_PET_PLATFORM_NAME:-$(uname -s)}
  [[ "$platform_name" == "Darwin" ]] || {
    printf 'LaunchAgent installation requires macOS.\n' >&2
    exit 1
  }
  launchctl_bin=${CODEX_PET_LAUNCHCTL_BIN:-launchctl}
  service_user_id=${CODEX_PET_USER_ID:-$(id -u)}
  service_domain="gui/$service_user_id"
  if [[ "$legacy_plist" != "$plist_path" && -f "$legacy_plist" ]]; then
    "$launchctl_bin" bootout "$service_domain" "$legacy_plist" >/dev/null 2>&1 || true
  fi
  # bootout's domain+plist form reliably unloads KeepAlive LaunchAgents;
  # bootout by service target can return before removing the loaded job.
  "$launchctl_bin" bootout "$service_domain" "$plist_path" >/dev/null 2>&1 || true
  # launchd can finish bootout asynchronously; one short retry avoids its
  # transient Bootstrap failed: 5 response during an in-place update.
  if ! "$launchctl_bin" bootstrap "$service_domain" "$plist_path"; then
    sleep 1
    "$launchctl_bin" bootstrap "$service_domain" "$plist_path"
  fi
  if [[ "$legacy_plist" != "$plist_path" && -f "$legacy_plist" ]]; then
    rm -f "$legacy_plist"
  fi
fi

printf 'Codex Pet runtime installed at %s\n' "$runtime_dir"
printf 'LaunchAgent: %s (port: %s)\n' "$label" "$port"
