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

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from pci_planning_and_optimization import logging_setup
from pci_planning_and_optimization.errors import new_kafka_error
from pci_planning_and_optimization.tracing import (
    SpanKind,
    trace_kafka_consume,
    with_span_kind,
)

if TYPE_CHECKING:
    from pci_planning_and_optimization.sftp.client import SFTPClient
    from pci_planning_and_optimization.sftp.xml_parser import PMData, XMLParser


_POLL_TIMEOUT_SECONDS: float = 20.0

_ERROR_BACKOFF_SECONDS: float = 5.0


class CommonEventHeader(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    domain: str = Field(default="", alias="domain")
    event_id: str = Field(default="", alias="eventId")
    event_name: str = Field(default="", alias="eventName")
    event_type: str = Field(default="", alias="eventType")
    source_name: str = Field(default="", alias="sourceName")
    reporting_entity_name: str = Field(default="", alias="reportingEntityName")
    start_epoch_microsec: int = Field(default=0, alias="startEpochMicrosec")
    last_epoch_microsec: int = Field(default=0, alias="lastEpochMicrosec")
    stnd_defined_namespace: str = Field(default="", alias="stndDefinedNamespace")


class FileInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    file_location: str = Field(default="", alias="fileLocation")
    file_size: int = Field(default=0, alias="fileSize")
    file_ready_time: str = Field(default="", alias="fileReadyTime")
    file_expiration_time: str = Field(default="", alias="fileExpirationTime")
    file_compression: str = Field(default="", alias="fileCompression")
    file_format: str = Field(default="", alias="fileFormat")
    file_data_type: str = Field(default="", alias="fileDataType")


class Measurement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    measurement_type_instance_reference: str = Field(
        default="",
        alias="measurement-type-instance-reference",
    )
    value: float = Field(default=0.0, alias="value")
    unit: str = Field(default="", alias="unit")


class StndDefinedData(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    href: str = Field(default="", alias="href")
    notification_id: int = Field(default=0, alias="notificationId")
    notification_type: str = Field(default="", alias="notificationType")
    event_time: str = Field(default="", alias="eventTime")
    system_dn: str = Field(default="", alias="systemDN")
    file_info_list: list[FileInfo] = Field(default_factory=list, alias="fileInfoList")
    additional_text: str = Field(default="", alias="additionalText")
    measurements: list[Measurement] = Field(default_factory=list, alias="measurements")


class StndDefinedFields(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    schema_reference: str = Field(default="", alias="schemaReference")
    stnd_defined_fields_version: str = Field(
        default="", alias="stndDefinedFieldsVersion"
    )
    data: StndDefinedData = Field(default_factory=StndDefinedData, alias="data")


class EventBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    common_event_header: CommonEventHeader = Field(
        default_factory=CommonEventHeader, alias="commonEventHeader"
    )
    stnd_defined_fields: StndDefinedFields = Field(
        default_factory=StndDefinedFields, alias="stndDefinedFields"
    )


class VESEvent(BaseModel):

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event: EventBody = Field(default_factory=EventBody, alias="event")


class KafkaConsumer:

    __slots__ = (
        "_brokers",
        "_consumer",
        "_consumer_factory",
        "_consumer_group",
        "_in_flight",
        "_in_flight_lock",
        "_is_connected",
        "_logger",
        "_password",
        "_running",
        "_security_protocol",
        "_sftp_client",
        "_stop_event",
        "_topic",
        "_username",
        "_xml_parser",
    )

    def __init__(
        self,
        brokers: list[str] | str,
        topic: str,
        consumer_group: str,
        username: str = "",
        password: str = "",
        logger: logging_setup.Logger | None = None,
        sftp_client: SFTPClient | None = None,
        *,
        security_protocol: str = "SASL_PLAINTEXT",
        consumer_factory: Any | None = None,
        xml_parser: XMLParser | None = None,
    ) -> None:
        self._brokers: str = (
            ",".join(brokers) if isinstance(brokers, (list, tuple)) else str(brokers)
        )
        self._topic = topic
        self._consumer_group = consumer_group
        self._username = username
        self._password = password
        self._security_protocol = security_protocol
        self._logger = (
            logger if logger is not None else logging_setup.with_component("kafka")
        ).with_field("topic", topic)
        self._sftp_client = sftp_client
        self._xml_parser: XMLParser | None = xml_parser
        self._consumer_factory = consumer_factory
        self._consumer: Any | None = None
        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._is_connected: bool = False
        self._in_flight: int = 0
        self._in_flight_lock: asyncio.Lock = asyncio.Lock()

    async def start(self) -> None:
        if self._consumer is not None:
            return

        config = self._build_config()

        if self._consumer_factory is None:
            from confluent_kafka import Consumer

            factory: Any = Consumer
        else:
            factory = self._consumer_factory

        if self._username and self._password:
            self._logger.with_field("username", self._username).info(
                "[KAFKA] SASL authentication enabled"
            )

        self._consumer = factory(config)
        self._consumer.subscribe([self._topic])
        self._is_connected = True
        self._logger.with_fields(
            {"consumer": self._consumer_group}
        ).info("[KAFKA] Consumer started")

