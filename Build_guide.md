<!--
Copyright 2025-2026 coRAN LABS Private Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Deploy the PCI Planning and Optimization rApp over R1

The rApp is onboarded and deployed through rApp Manager: a CSAR carries the Helm
chart, the ACM composition and the SME service APIs, and the platform installs
it. There is no manual path. An operator drives the lifecycle, and the rApp
never installs or registers itself.

You need an O-RAN SC / ONAP SMO offering rApp Manager, ChartMuseum, the ACM
runtime with the Kubernetes participant, CAPIF and Kong for SME, Strimzi Kafka
carrying VES `notifyFileReady` events, and SDNR for the O1 write path. Locally
you need docker, helm, zip and kubectl against that cluster, plus a registry the
cluster can pull from.

## 1. Addresses

Every command below reads these. Take them from your own cluster.

```bash
export RM=$(kubectl get svc rappmanager -n nonrtric -o jsonpath='{.spec.clusterIP}')
export CM=$(kubectl get svc chartmuseum -n nonrtric -o jsonpath='{.spec.clusterIP}')
export KONG=$(kubectl get svc oran-nonrtric-kong-admin -n nonrtric -o jsonpath='{.spec.clusterIP}')
export CAPIF=$(kubectl get svc capifcore -n nonrtric -o jsonpath='{.spec.clusterIP}')
export SMO_HOST=<host serving the NodePort>
```

## 2. Image

```bash
docker build -t localhost:5000/pci-planning-rapp:2.1.0 .
docker push localhost:5000/pci-planning-rapp:2.1.0
curl -s http://localhost:5000/v2/pci-planning-rapp/tags/list
```

`image.registry` and `image.tag` in the chart values have to match what you
pushed, or the pod lands in `ImagePullBackOff`. The first pull on a node can
outrun the ACM pod-status check, which gives up after about two minutes and
fails the element while the pod goes on to run. Pull it onto the node
beforehand, or expect to tear down once and redeploy against a warm cache.

## 3. Chart values

`deploy/helm/pci-planning-rapp/values.yaml` ships `REPLACE_WITH_` placeholders.
Replace all of them before packaging: the operator password, the Kafka SASL
password, the SDNR username and password, and the InfluxDB admin password and
token.

This chart is the only place configuration lives. The Kubernetes participant
installs it from ChartMuseum by name and version and ignores the values carried
in the ACM instance, so anything left as a placeholder ships broken.
`scripts/create-csar.sh` refuses to build while placeholders remain.

Three of them are worth calling out.

`admin.password` is the dashboard's operator account. There is no built-in
account, so leaving it unset means every login is refused.

`sftp.knownHosts` needs one entry per PM server. Host-key verification is on,
and without an entry the rApp cannot fetch the files the VES events point at.
The packaging script warns when it is still empty.

```bash
kubectl get secret pci-planning-rapp -n onap -o jsonpath='{.data.password}' | base64 -d; echo
ssh-keyscan -p <port> -H <pm-sftp-host>
```

Choose the InfluxDB credentials once and keep them. The volume survives an
undeploy, and a redeploy with different credentials cannot open it.

## 4. CSAR

```bash
./scripts/create-csar.sh
```

It checks the placeholders, packages the chart, mints a fresh ACM element UUID
because the runtime rejects one it has seen, writes the manifest with SHA-256
hashes for every packaged file, and leaves the CSAR under `rapp-package/dist/`.
The tracked instance file is not modified; the fresh UUID is stamped into the
build copy only.

The InfluxDB subchart is vendored under `deploy/helm/pci-planning-rapp/charts/`,
so packaging needs no network and no `helm dependency update`.

## 5. Upload the chart

```bash
curl -s -X DELETE http://$CM:8080/api/charts/pci-planning-rapp/2.1.0
curl -s --data-binary @rapp-package/dist/build/Artifacts/Deployment/HELM/pci-planning-rapp-2.1.0.tgz \
  http://$CM:8080/api/charts
```

ChartMuseum must be whitelisted in the Kubernetes participant's configmap,
otherwise the install is refused.

```bash
kubectl get configmap onap-policy-clamp-ac-k8s-ppnt-configmap -n onap -o yaml | grep -A3 repos
```

## 6. Onboard, prime, instantiate, deploy

The path segment is the rApp name, not the identifier the API returns.

```bash
curl -s -X POST http://$RM:8080/rapps/pci-planning-rapp \
  -F file=@rapp-package/dist/pci-planning-rapp-2.1.0.csar

curl -s -X PUT http://$RM:8080/rapps/pci-planning-rapp \
  -H 'Content-Type: application/json' -d '{"primeOrder":"PRIME"}'

IID=$(curl -s -X POST http://$RM:8080/rapps/pci-planning-rapp/instance \
  -H 'Content-Type: application/json' \
  -d '{"acm":{"instance":"pciplanning-instance"},
       "sme":{"providerFunction":"pci-planning-provider",
              "serviceApis":"pci-planning-api",
              "invokers":"ics-invoker"}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["rappInstanceId"])')

curl -s -X PUT http://$RM:8080/rapps/pci-planning-rapp/instance/$IID \
  -H 'Content-Type: application/json' -d '{"deployOrder":"DEPLOY"}'
```

Every value in the instance body is the base name of a file under
`rapp-package/Files`. The rApp publishes APIs but produces no information types,
so the body carries no `dme` section and the deployment runs in a single phase.

## 7. Verify

```bash
curl -s http://$RM:8080/rapps/pci-planning-rapp/instance/$IID
kubectl get pods -n nonrtric | grep pci-planning
curl -s -o /dev/null -w '%{http_code}\n' http://$SMO_HOST:30090/healthz
curl -s http://$SMO_HOST:30090/api/health
```

The instance reaches `DEPLOYED`, and the rApp and its InfluxDB both run.
`/api/health` reports each component separately. The pod logs open with a BOOT
panel naming every component and whether it came up, so an unfilled credential
shows there rather than as silence in the dashboard.

```bash
kubectl logs -n nonrtric deploy/pci-planning-rapp | head -40
```

The dashboard is at `http://$SMO_HOST:30090/ui/index.html`, behind the operator
login from `admin.username` and `admin.password`. It fills once the environment
publishes PM files to the Kafka topic named in the chart values. An idle topic
is not an error.

## 8. Teardown

```bash
curl -s -X PUT http://$RM:8080/rapps/pci-planning-rapp/instance/$IID \
  -H 'Content-Type: application/json' -d '{"deployOrder":"UNDEPLOY"}'
curl -s -X DELETE http://$RM:8080/rapps/pci-planning-rapp/instance/$IID
curl -s -X PUT http://$RM:8080/rapps/pci-planning-rapp \
  -H 'Content-Type: application/json' -d '{"primeOrder":"DEPRIME"}'
curl -s -X DELETE http://$RM:8080/rapps/pci-planning-rapp
```

Follow that order. Afterwards check that the Helm release is gone and remove the
published API from CAPIF and its service and routes from Kong: teardown often
leaves them behind, and the next deploy fails against the leftovers.

```bash
curl -s http://$KONG:8001/services | grep pci-planning
```

The InfluxDB volume survives an undeploy. Delete it too if you want a clean
database on the next run.
