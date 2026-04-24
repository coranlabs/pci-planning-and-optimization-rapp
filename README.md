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

# PCI Planning and Optimization rApp

A Non-RT RIC rApp that finds the Physical Cell Identity conflicts a live network
is carrying, proposes the smallest set of PCI changes that clears them, and
writes the approved ones back to the RAN over O1. Both LTE and 5G NR.

A PCI conflict is quiet. Two cells sharing a PCI within each other's reach, or
two neighbours of one cell sharing one, do not raise an alarm; they show up as
handover failures somewhere else, and nothing in the fault feed points back at
the identity that caused them.

## How it works

```
RAN ──VES notifyFileReady──▶ Kafka ──▶ rApp ──SFTP──▶ RAN / O1 adapter
                                        │  parse TS 32.435 XML
                                        ▼
                                   conflict graph
                                        │  correlation gate
                                        │  conservative graph coloring
                                        ▼
                              dashboard ──operator approval──▶ SDNR ──NETCONF──▶ RAN
```

The RAN closes a reporting period and publishes a `notifyFileReady` event naming
the PM file it just wrote. The rApp consumes that event, fetches the file over
SFTP, and parses it as 3GPP TS 32.435 measurement XML. From those counters it
builds a network: cells with their PCI, ARFCN, bandwidth, PLMN, TAC and PRB
utilisation, and one node-level topology block carrying site coordinates, site
type, region and a neighbour list.

Counters are read by name, never by `measType` position. A position-indexed read
breaks silently the moment a feed reorders a block, and the failure mode is a
plausible but wrong PCI rather than an error.

## Conflict detection

Every cell pair that can interfere becomes an edge in a conflict graph, and each
edge is classified:

| Class | Meaning |
| --- | --- |
| `collision` | two neighbouring cells hold the same PCI |
| `confusion` | one cell has two neighbours holding the same PCI |
| `mod3` | PCIs congruent mod 3, so their reference signals collide |
| `mod4` | NR only, congruent mod 4 |
| `mod30` | congruent mod 30, so their uplink sequence groups collide |
| `mod6` | LTE only, off by default |

Where an edge is not measured it is inferred. The PM feed's neighbour list is
node-level, so node adjacency is expanded into cell-level relations and marked
`SHADOW`. A shadow relation is only kept if the two cells are close enough for
their site types, on the same frequency and on the same technology, which is
what `shadow_nrt` in the config controls.

## The correlation gate

Before proposing anything the rApp asks whether PCI conflicts actually explain
handover failures in this network. It splits relations into conflicted and clean,
compares their handover failure rates with a Mann-Whitney U test, and returns one
of three verdicts per technology: ship, do not ship, or needs more data.

`do_not_ship` means the conflicts are real but they are not what is breaking
handovers here, and changing PCIs would be churn for nothing. The gate is the
reason this rApp does not simply recolour every conflict it finds.

The gate needs per-relation handover counters. A PM feed that carries none
reports insufficient samples, and detection and optimization still run.

## Conservative graph coloring

The optimizer is deliberately reluctant. It re-colours the cell whose conflicts
cost the most, checks the change against the pool the cell's site type is allowed
to draw from, locks that cell's neighbourhood for the rest of the pass, and stops
as soon as the soft cost stops improving or the change budget runs out.

The budget is the point. `convergence` caps changes per pass, per run and in
absolute terms, defaulting to half a percent of the network per pass and one
percent per run. An optimizer that clears every conflict in a single run would
touch enough of the network that its own churn becomes the outage.

Edge weights come from measured handover attempts where the feed carries them.
Where it does not, a distance and RF-overlap weight takes over. That fallback
matters: with every weight at zero the mod-N tie-break has nothing to order and
the verify-and-revert guard silently goes inert.

## Dashboard

Four pages, served from the same process on the same port as the API and probes.

- **Overview** - KPIs across the PCI pool, network throughput, live conflict
  counts and the incident feed.
- **Cell Map** - cells projected on their real coordinates with conflict
  overlays, regional health and per-cell drill-in.
- **PCI Planning** - import an operator cell plan as a spreadsheet, compare the
  current PCI assignment against the optimised one, approve or reject each
  proposed change, and export the result.
- **Settings** - detection thresholds, appearance, operator identity and
  notification delivery.

There is no built-in account. Set `RAPP_ADMIN_USERNAME` and `RAPP_ADMIN_PASSWORD`
(or `RAPP_ADMIN_PASSWORD_HASH` for a pre-computed scrypt hash, so no plaintext
reaches the environment) or every login is refused. Passwords are stored as
scrypt and compared with a constant-time comparison; failed logins are throttled
per client address and locked out after eight failures in ten minutes.

A PM file describes one reporting period and nothing before it, so the throughput
chart keeps its own rolling total: network-wide DL and UL, one point a minute,
seven days deep, in `history_file`. That only covers the time this process has
been up, so the 6h, 24h and 7d ranges start out nearly empty. The file is
rewritten as the process runs, so seeding it from elsewhere means stopping the
rApp first.

## Actuation

An approved change is one RESTCONF PATCH to SDNR, which carries it to the cell
over NETCONF. Each cell's NETCONF mount is derived from the `ManagedElement` in
its distinguished name, which is how a network of many gNBs is actually
addressed: one mount per node, named after its ManagedElement. A cell whose
mount is not connected fails preflight with `mount not connected` before anything
is sent, rather than writing to the wrong device. Setting `SDNR_NETCONF_NODE_ID`
pins every write to a single mount instead, which is a lab arrangement, not a
deployment one.

After a commit the rApp holds the new PCI as a display overlay and watches the PM
feed for fifteen minutes. If the feed reports the new value the overlay is
dropped as confirmed; if it does not, the rApp logs `pci_replan_unconfirmed` at
critical and reverts the display to whatever the feed says. Confirmation requires
that the equipment being written to is the equipment being measured. Where the
write path and the PM path lead to different systems, the window will always
expire, by construction.

## Configuration

A single YAML file holds the full configuration, and anything secret is supplied
through the environment instead, which is what the Helm chart does. No password
belongs in `config/config.yaml`; this repository is public.

| Variable | Sets |
| --- | --- |
| `KAFKA_BROKERS` `KAFKA_TOPIC` `KAFKA_GROUP_ID` | VES event source |
| `KAFKA_USERNAME` `KAFKA_PASSWORD` `KAFKA_SECURITY_PROTOCOL` | SASL/SCRAM credentials |
| `SFTP_ENABLED` `SFTP_TIMEOUT` `RAPP_SSH_KNOWN_HOSTS` | PM file retrieval |
| `PM_DIRECTORY` | Read PM XML off disk instead of Kafka and SFTP |
| `SDNR_ENABLED` `SDNR_BASE_URL` `SDNR_USERNAME` `SDNR_PASSWORD` | PCI write path |
| `SDNR_NETCONF_NODE_ID` `SDNR_FUNCTION_ID` | Mount and function targeting |
| `INFLUX_ENABLED` `INFLUX_URL` `INFLUX_TOKEN` `INFLUX_ORG` `INFLUX_BUCKET` | Metric storage |
| `RAPP_ADMIN_USERNAME` `RAPP_ADMIN_PASSWORD` `RAPP_ADMIN_PASSWORD_HASH` | Operator account |
| `CONFIG_PATH` `HTTP_PORT` `NODE_ID` `PCI_HISTORY_FILE` | Runtime |
| `LOG_LEVEL` `RAPP_LOG_FORMAT` `NO_COLOR` | Logging |

Logging defaults to `json`, one object per line, for shipping to a log stack.
`RAPP_LOG_FORMAT=console` switches to the aligned
`time  LEVEL │ component  message  key=value` view that `serve` frames with its
BOOT, READY, SHUTDOWN and STOPPED panels, which is what you want at a terminal.
`LOG_LEVEL` sets the HTTP server's verbosity; the rApp's own loggers take
`--log-level`.

A few fields that are easy to get wrong:

- `osc.kafka.username` and `password` - leave both blank to connect
  unauthenticated, set both for SCRAM-SHA-512. Strimzi generates the password
  into the `KafkaUser` secret of the same name.
- `osc.kafka.group_id` must be unique per consumer of the topic. Two rApps
  sharing one have Kafka split the partitions between them, so each silently
  sees only part of the network.
- `osc.sftp` - host and credentials come from the VES `fileLocation` URL, not
  from static config. Without a host key for each PM SFTP server the rApp refuses
  to fetch; populate `sftp.knownHosts` with `ssh-keyscan -p <port> -H <host>`.
- `sdnr.base_url` - the in-cluster address is what a Helm deployment resolves.
  Running the process outside the cluster, point `SDNR_BASE_URL` at the NodePort.

Every default is the secure one: outbound TLS verified with a TLS 1.2 floor, SFTP
host keys checked against `known_hosts`, session cookies `HttpOnly` and `Secure`
over HTTPS, SFTP passwords rendered as `redacted` in logs. Two environment
variables relax them, and the component logs a warning at startup when they do:
`RAPP_INSECURE_SSH_HOSTKEY` accepts any SFTP host key, and `RAPP_SSH_KNOWN_HOSTS`
points the pool at a different file. Report a vulnerability to
**support@coranlabs.com** rather than opening a public issue.

