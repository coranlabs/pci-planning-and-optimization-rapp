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

