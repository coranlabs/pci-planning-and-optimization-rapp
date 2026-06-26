#!/usr/bin/env bash
# Copyright 2025-2026 coRAN LABS Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHART="$REPO_ROOT/deploy/helm/pci-planning-rapp"
PKG="$REPO_ROOT/rapp-package"
NAME="$(sed -n 's/^name: *//p' "$CHART/Chart.yaml" | head -1)"
VERSION="$(sed -n 's/^version: *//p' "$CHART/Chart.yaml" | head -1)"
DIST="$PKG/dist"
BUILD="$DIST/build"
CSAR="$DIST/$NAME-$VERSION.csar"

if command -v helm >/dev/null 2>&1; then HELM=(helm)
elif command -v microk8s >/dev/null 2>&1; then HELM=(microk8s helm3)
else echo "error: helm is required" >&2; exit 1; fi

if grep -q 'REPLACE_WITH_' "$CHART/values.yaml"; then
  echo "error: $CHART/values.yaml still has REPLACE_WITH_ placeholders." >&2
  echo "The K8s participant installs the chart from ChartMuseum and ignores the" >&2
  echo "instance values, so every real value must be set in the chart itself." >&2
  exit 1
fi

if grep -qE '^\s*knownHosts: *""\s*$' "$CHART/values.yaml"; then
  echo "warning: sftp.knownHosts is empty; the rApp will refuse to fetch PM files." >&2
fi

rm -rf "$BUILD"
mkdir -p "$BUILD" "$DIST"
cp -r "$PKG/ASD.yaml" "$PKG/TOSCA-Metadata" "$PKG/Files" "$BUILD/"
mkdir -p "$BUILD/Artifacts/Deployment/HELM"

"${HELM[@]}" package "$CHART" -d "$BUILD/Artifacts/Deployment/HELM" >/dev/null

UUID="$(cat /proc/sys/kernel/random/uuid)"
INSTANCE="$BUILD/Files/Acm/instances/pciplanning-instance.json"
OLD_UUID="$(grep -oE '[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}' "$INSTANCE" | head -1)"
[ -n "$OLD_UUID" ] || { echo "error: no element UUID found in $INSTANCE" >&2; exit 1; }
sed -i "s/$OLD_UUID/$UUID/g" "$INSTANCE"

{
  printf 'metadata:\n  vnf_product_name: PCI Planning and Optimization rApp\n'
  printf '  vnf_provider_id: coRAN Labs\n  vnf_package_version: %s\n' "$VERSION"
  cd "$BUILD"
  find ASD.yaml Files Artifacts/Deployment/HELM -type f | sort | while read -r f; do
    printf '\nSource: %s\nAlgorithm: SHA-256\nHash: %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
  done
} > "$BUILD/$NAME.mf"

rm -f "$CSAR"
(cd "$BUILD" && zip -qr "$CSAR" ASD.yaml TOSCA-Metadata "$NAME.mf" Files Artifacts/Deployment/HELM)

echo "version      : $VERSION"
echo "element uuid : $UUID"
echo "chart        : $BUILD/Artifacts/Deployment/HELM/$NAME-$VERSION.tgz"
echo "csar         : $CSAR"
