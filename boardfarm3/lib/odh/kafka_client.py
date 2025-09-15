"""Kafka client implementation."""

from __future__ import annotations

import logging
from json import JSONDecodeError, loads
from time import monotonic
from typing import Any

from kafka import KafkaConsumer, TopicPartition
from kafka.errors import OffsetOutOfRangeError, UnknownTopicOrPartitionError


class KafkaClient:
    """Kafka client implementation."""

    def __init__(self, bootstrap_server: str, topic_name: str) -> None:
        """Initialize the kafka client.

        :param bootstrap_server: Kafka server url
        :type bootstrap_server: str
        :param topic_name: the topic to subscribe to
        :type topic_name: str
        """
        self.topic = topic_name
        self._disable_log_messages_from_libraries()
        self._consumer = KafkaConsumer(
            topic_name,
            bootstrap_servers=bootstrap_server,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=self._deserialize_json,
        )

    def _disable_log_messages_from_libraries(self) -> None:
        """Disable logs from kafka."""
        logging.getLogger("kafka").setLevel(logging.WARNING)

    def _deserialize_json(self, message: bytes) -> dict[str, str] | str:
        """Deserialize message from bytes to a Python object.

        :param message: message bytes
        :type message: bytes
        :return: The deserialized Python object. If the message can be deserialized
            to a dictionary with string keys and string values, then a dict[str, str]
            is returned. Otherwise, the bytes are decoded to a str and returned.
        :rtype: dict[str, str] | str
        """
        try:
            return loads(message.decode("utf-8"))
        except JSONDecodeError:
            return message.decode("utf-8")

    def subscribe_to_topic(self, topics: list[str]) -> None:
        """Subscribe to a list topics.

        :param topics: the list of topics to subscribe to
        :type topics: list[str]
        :raises UnknownTopicOrPartitionError: if a topic does not exist
        """
        for topic in topics:
            if topic not in self._consumer.topics():
                msg = f"The topic {topic} does not exist"
                raise UnknownTopicOrPartitionError(msg)
            self._consumer.subscribe([topic])

    def read_kafka_messages(self, num_messages: int) -> list[Any]:
        """Read a given number of messages from the kafka queue.

        :param num_messages: The number of messages to be read from the kafka queue
        :type num_messages: int
        :return: list of telemetry logs
        :rtype: list[Any]
        """
        messages = []
        for _ in range(num_messages):
            message = next(self._consumer)
            if message.value is not None:
                messages.append(message.value)
        return messages

    def consume_logs(self, time_period: int) -> list[Any]:
        """Consume logs from the kafka queue for a particular duration.

        :param time_period: time (in s) for which to consume logs from the queue.
        :type time_period: int
        :return: kafka logs
        :rtype: list[Any]
        """
        logs = []
        start_time = monotonic()
        while monotonic() < time_period + start_time:
            for _, log in self._consumer.poll(timeout_ms=1000).items():  # noqa: PERF102
                logs.extend(log)
        return logs

    def consume_sw_update_logs(self, start_time: float, end_time: float) -> list[Any]:
        """Consume logs from the kafka queue for given time using offsets.

        :param start_time: start time to fetch logs
        :type start_time: float
        :param end_time: end time to fetch logs
        :type end_time: float
        :return: kafka logs
        :rtype: list[Any]
        :raises OffsetOutOfRangeError: if offset does not exist
        """
        logs = []
        time_duration = (end_time - start_time) + (
            60 * 1000  # a minute of extra buffer time
        )
        partitions = self._consumer.partitions_for_topic(topic=self.topic)
        for partition in partitions:
            topic_partition = TopicPartition(topic=self.topic, partition=partition)
            start_offset = self._consumer.offsets_for_times(
                {topic_partition: start_time}
            )
            self._consumer.seek(topic_partition, start_offset[topic_partition].offset)
            for _ in range(5):
                log_data = self._consumer.poll(timeout_ms=time_duration)
                if start_offset[topic_partition].offset in [
                    record.offset for _, val in log_data.items() for record in val
                ]:
                    break
            else:
                msg = "Given offset does not exist in records"
                raise OffsetOutOfRangeError(msg)
            for log in log_data.values():
                logs.extend(log)
        return logs

    def close_connection_to_kafka(self) -> None:
        """Gracefully close the connection to the kafka server."""
        self._consumer.close()
