from __future__ import division

import time
import unittest2
import mock
from uuid import uuid4

from pykafka import KafkaClient
from pykafka.exceptions import ProducerQueueFullError
from pykafka.test.utils import get_cluster, stop_cluster


class MockAtexit(mock.MagicMock):
    _exithandlers = []

    def unregister(self, func):
        raise ValueError


class ProducerIntegrationTests(unittest2.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.kafka = get_cluster()
        cls.topic_name = b'test-data'
        cls.kafka.create_topic(cls.topic_name, 3, 2)
        cls.client = KafkaClient(cls.kafka.brokers)
        cls.consumer = cls.client.topics[cls.topic_name].get_simple_consumer(
            consumer_timeout_ms=1000)

    @classmethod
    def tearDownClass(cls):
        cls.consumer.stop()
        stop_cluster(cls.kafka)

    def test_produce(self):
        # unique bytes, just to be absolutely sure we're not fetching data
        # produced in a previous test
        payload = uuid4().bytes

        prod = self.client.topics[self.topic_name].get_sync_producer(min_queued_messages=1)
        prod.produce(payload)

        # set a timeout so we don't wait forever if we break producer code
        message = self.consumer.consume()
        assert message.value == payload

    def test_async_produce(self):
        payload = uuid4().bytes

        prod = self.client.topics[self.topic_name].get_producer(min_queued_messages=1)
        prod.produce(payload)

        message = self.consumer.consume()
        assert message.value == payload

    def test_async_produce_context(self):
        """Ensure that the producer works as a context manager"""
        payload = uuid4().bytes

        with self.client.topics[self.topic_name].get_producer(min_queued_messages=1) as producer:
            producer.produce(payload)

        message = self.consumer.consume()
        assert message.value == payload

    def test_async_produce_queue_full(self):
        """Ensure that the producer raises an error when its queue is full"""
        topic = self.client.topics[self.topic_name]
        with topic.get_producer(block_on_queue_full=False,
                                max_queued_messages=1,
                                linger_ms=1000) as producer:
            with self.assertRaises(ProducerQueueFullError):
                while True:
                    producer.produce(uuid4().bytes)
        while self.consumer.consume() is not None:
            time.sleep(.05)

    def test_async_produce_lingers(self):
        """Ensure that the context manager waits for linger_ms milliseconds"""
        linger = 3
        topic = self.client.topics[self.topic_name]
        with topic.get_producer(linger_ms=linger * 1000) as producer:
            start = time.time()
            producer.produce(uuid4().bytes)
            producer.produce(uuid4().bytes)
        self.assertEqual(int(time.time() - start), int(linger))
        self.consumer.consume()
        self.consumer.consume()

    def test_async_produce_thread_exception(self):
        """Ensure that an exception on a worker thread is raised to the main thread"""
        topic = self.client.topics[self.topic_name]
        with self.assertRaises(ValueError):
            with topic.get_producer(min_queued_messages=1) as producer:
                # get some dummy data into the queue that will cause a crash when flushed
                # specifically, this tuple causes a crash since its first element is
                # not a two-tuple
                producer._produce(("anything", 0))
        while self.consumer.consume() is not None:
            time.sleep(.05)

    def test_required_acks(self):
        """Test with non-default values for `required_acks`

        See #278 for a related bug.  Here, we only test that no exceptions
        occur (hence `sync=True`, which would surface most exceptions)
        """
        kwargs = dict(linger_ms=1, sync=True, required_acks=0)
        prod = self.client.topics[self.topic_name].get_producer(**kwargs)
        prod.produce(uuid4().bytes)

        kwargs["required_acks"] = -1
        prod = self.client.topics[self.topic_name].get_producer(**kwargs)
        prod.produce(uuid4().bytes)

    def test_null_payloads(self):
        """Test that None is accepted as a null payload"""
        prod = self.client.topics[self.topic_name].get_sync_producer(
                min_queued_messages=1)
        prod.produce(None)
        self.assertIsNone(self.consumer.consume().value)
        prod.produce(None, partition_key=b"whatever")
        self.assertIsNone(self.consumer.consume().value)
        prod.produce(b"")  # empty string should be distinguished from None
        self.assertEqual(b"", self.consumer.consume().value)

    def test_cleanup_stop_is_not_called_on_stopped_object(self):
        """Test that the stop() method is not called twice"""
        prod = self.client.topics[self.topic_name].get_producer()
        prod.stop()
        self.assertFalse(hasattr(prod, '_cleanup_func'))

    def test_cleanup_stop_is_called_on_not_stopped_object(self):
        """Test that the cleanup() method flushes the queue properly"""
        payload = uuid4().bytes

        prod = self.client.topics[self.topic_name].get_producer()
        prod.produce(payload)
        # simulates a program termination
        prod._cleanup_func(prod)
        # confirm that message was received
        message = self.consumer.consume()
        self.assertEqual(message.value, payload)

    @mock.patch('pykafka.producer.atexit', new=MockAtexit())
    def test_failing_to_remove_cleanup_func(self):
        """Test ValueError is ignored """
        prod = self.client.topics[self.topic_name].get_producer()
        prod.stop()
        self.assertFalse(hasattr(prod, '_cleanup_func'))

if __name__ == "__main__":
    unittest2.main()
