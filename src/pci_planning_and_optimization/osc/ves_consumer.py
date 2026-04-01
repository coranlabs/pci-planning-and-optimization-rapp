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

    async def start_consuming(
        self, message_queue: asyncio.Queue[PMData]
    ) -> None:
        if self._consumer is None:
            await self.start()

        self._running = True
        self._stop_event.clear()

        try:
            while self._running and not self._stop_event.is_set():
                msg = await self._poll_one()
                if msg is None:
                    continue

                err = msg.error() if hasattr(msg, "error") else None
                if err is not None:
                    self._is_connected = False
                    self._logger.with_field("error", str(err)).error(
                        "[KAFKA] Failed to read message"
                    )
                    await asyncio.sleep(_ERROR_BACKOFF_SECONDS)
                    continue

                self._is_connected = True
                value = msg.value() if hasattr(msg, "value") else None
                if value is None:
                    continue

                offset = msg.offset() if hasattr(msg, "offset") else -1
                partition = msg.partition() if hasattr(msg, "partition") else -1
                self._logger.with_fields(
                    {"offset": offset, "size": len(value)}
                ).debug("[KAFKA] Received VES message")

                await self._process_message(value, partition, offset, message_queue)
        except asyncio.CancelledError:
            self._logger.info("[KAFKA] Consumer cancelled")
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        await self.close()

    async def close(self) -> None:
        if self._consumer is None:
            return
        consumer = self._consumer
        self._consumer = None
        self._is_connected = False
        try:
            await asyncio.to_thread(consumer.close)
            self._logger.info("[KAFKA] Consumer stopped")
        except Exception as exc:
            self._logger.with_error(exc).warn("[KAFKA] Error during consumer close")

    def is_connected(self) -> bool:
        return self._is_connected

    def in_flight_count(self) -> int:
        return self._in_flight

    def _build_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "bootstrap.servers": self._brokers,
            "group.id": self._consumer_group,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 5000,
            "session.timeout.ms": 30000,
            "heartbeat.interval.ms": 3000,
            "fetch.message.max.bytes": 10 * 1024 * 1024,
            "client.id": f"pci-planning-and-optimization-{self._consumer_group}",
            "error_cb": self._on_librdkafka_error,
        }

        if self._username and self._password:
            config["security.protocol"] = self._security_protocol
            config["sasl.mechanism"] = "SCRAM-SHA-512"
            config["sasl.username"] = self._username
            config["sasl.password"] = self._password

        return config

    def _on_librdkafka_error(self, err: Any) -> None:
        self._is_connected = False
        try:
            self._logger.with_field("error", str(err)).error("[KAFKA] librdkafka error")
        except Exception:
            pass

    async def _poll_one(self) -> Any | None:
        if self._consumer is None:
            return None
        consumer = self._consumer
        try:
            return await asyncio.to_thread(consumer.poll, _POLL_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._is_connected = False
            self._logger.with_error(exc).error("[KAFKA] poll() raised")
            await asyncio.sleep(_ERROR_BACKOFF_SECONDS)
            return None


    async def _process_message(
        self,
        value: bytes,
        partition: int,
        offset: int,
        message_queue: asyncio.Queue[PMData],
    ) -> None:
        async with self._in_flight_lock:
            self._in_flight += 1
        try:
            try:
                pm_data = await self.parse_ves_event(value)
            except Exception as exc:
                self._logger.with_error(exc).error("[KAFKA] Failed to parse VES event")
                return

            if pm_data is None:
                return

            span = trace_kafka_consume(self._topic, partition, offset)
            with span:
                with_span_kind(SpanKind.CONSUMER)(span)

                self._logger.with_fields(
                    {
                        "source": pm_data.source_name,
                        "objects": len(pm_data.per_object),
                    }
                ).info("[KAFKA] Parsed PM file")

                try:
                    message_queue.put_nowait(pm_data)
                except asyncio.QueueFull:
                    self._logger.warn(
                        "[KAFKA] Message channel full, dropping PM file"
                    )
        finally:
            async with self._in_flight_lock:
                self._in_flight -= 1

    async def parse_ves_event(self, data: bytes | str) -> PMData | None:
        try:
            event = VESEvent.model_validate_json(data)
        except Exception as exc:
            raise new_kafka_error(
                "VES_PARSE",
                "failed to unmarshal VES event",
                exc,
            ) from exc

        header = event.event.common_event_header
        stnd = event.event.stnd_defined_fields

        if header.domain != "stndDefined":
            return None

        if header.stnd_defined_namespace != "3GPP-PerformanceAssurance":
            return None


        if not stnd.data.file_info_list:
            self._logger.with_field("source", header.source_name).debug(
                "[VES] notification carries no fileInfoList — nothing to fetch"
            )
            return None

        file_location = stnd.data.file_info_list[0].file_location
        if not file_location:
            return None

        return await self._fetch_and_parse(file_location)

    async def _fetch_and_parse(self, file_location: str) -> PMData | None:
        sftp = self._sftp_client
        if sftp is None or not _sftp_enabled(sftp):
            self._logger.debug("[SFTP] Client disabled, cannot fetch XML file")
            return None

        try:
            xml_data = await _maybe_await(sftp.fetch_file(file_location))
        except Exception as exc:
            self._logger.with_fields(
                {"error": str(exc), "file": file_location}
            ).warn("[SFTP] Failed to fetch XML file (may have expired)")
            return None

        parser = self._ensure_xml_parser()
        try:
            return parser.parse(xml_data, file_location)
        except Exception as exc:
            self._logger.with_error(exc).error("[XML] Failed to parse file")
            return None

    def _ensure_xml_parser(self) -> XMLParser:
        if self._xml_parser is not None:
            return self._xml_parser
        from pci_planning_and_optimization.sftp.xml_parser import XMLParser

        self._xml_parser = XMLParser(self._logger)
        return self._xml_parser


def _sftp_enabled(client: Any) -> bool:
    checker = getattr(client, "is_enabled", None)
    if checker is None:
        return True
    try:
        return bool(checker())
    except Exception:
        return False


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value
