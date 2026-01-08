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

