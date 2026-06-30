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

