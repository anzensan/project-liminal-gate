#!/usr/bin/env bash
set -euo pipefail

if (( "$(id -u)" == 0 )); then
  echo "run this installer as the non-root service user; it invokes sudo when needed" >&2
  exit 2
fi

service_port="${1:-8642}"
case "$service_port" in
  *[!0-9]*|"")
    echo "port must be an integer from 1 through 65535" >&2
    exit 2
    ;;
esac
if ((service_port < 1 || service_port > 65535)); then
  echo "port must be an integer from 1 through 65535" >&2
  exit 2
fi

project_root="$(cd "$(dirname "$0")/.." && pwd -P)"
service_user="$(id -un)"
service_group="$(id -gn)"
python_executable="$(command -v python3)"

if [[ "$project_root" =~ [[:space:]\|\&\\] ]]; then
  echo "the checkout path cannot contain whitespace, |, &, or backslash" >&2
  exit 2
fi

unit_template="$project_root/deploy/project-liminal-gate.service.in"
temporary_directory="$(mktemp -d)"
rendered_unit="$temporary_directory/project-liminal-gate.service"
trap 'rm -rf -- "$temporary_directory"' EXIT

mkdir -p -- "$project_root/user-data"

sed \
  -e "s|@SERVICE_USER@|$service_user|g" \
  -e "s|@SERVICE_GROUP@|$service_group|g" \
  -e "s|@PROJECT_ROOT@|$project_root|g" \
  -e "s|@PYTHON_EXECUTABLE@|$python_executable|g" \
  -e "s|@PORT@|$service_port|g" \
  "$unit_template" > "$rendered_unit"

systemd-analyze verify "$rendered_unit"
sudo install -o root -g root -m 0644 \
  "$rendered_unit" /etc/systemd/system/project-liminal-gate.service
sudo systemctl daemon-reload
sudo systemctl enable project-liminal-gate.service
sudo systemctl restart project-liminal-gate.service
systemctl status project-liminal-gate.service --no-pager --full
