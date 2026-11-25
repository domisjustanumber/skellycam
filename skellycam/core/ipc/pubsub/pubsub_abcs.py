import logging
import multiprocessing
import queue
from abc import ABC
from dataclasses import dataclass, field
from multiprocessing.process import parent_process
from typing import Type

from skellycam.core.types.type_overloads import TopicSubscriptionQueue

logger = logging.getLogger(__name__)

@dataclass
class TopicMessageABC(ABC):
    """
    Base class for messages sent through the PubSub system.
    All messages should inherit from this class.
    """
    pass


@dataclass
class PubSubTopicABC(ABC):
    subscriptions: list[TopicSubscriptionQueue] = field(default_factory=list)
    message_type: Type[TopicMessageABC] = TopicMessageABC


    def get_subscription(self) -> TopicSubscriptionQueue:
        """
        Subscribe a queue to this topic.
        """
        if parent_process() is not None:
            raise RuntimeError("Subscriptions must be created in the main process and passed to children")
        sub =  multiprocessing.Queue()
        self.subscriptions.append(sub)
        return sub


    def publish(self, message: TopicMessageABC, *, print_log: bool = True):
        """Enqueue each publication for every subscriber, without discarding pending messages."""
        if not isinstance(message, self.message_type):
            raise TypeError(f"Expected {self.message_type} but got {type(message)}")
        if len(self.subscriptions) == 0:
            logger.warning(f"Publishing message of type {self.message_type} with no subscribers, message will be lost")
            return
        if print_log:
            logger.trace(f"Publishing message of type {self.message_type} to {len(self.subscriptions)} subscribers")
        for sub in self.subscriptions:
            sub.put(message)
    def close(self):
        """
        Close all subscriptions for this topic, when no other process or thread uses them (windows-capture.md 5.9).
        """
        logger.debug(f"Closing PubSubTopicABC {self.__class__.__name__} with {len(self.subscriptions)} subscriptions")
        for sub in self.subscriptions:
            sub.cancel_join_thread()  # the end of the process does not wait for the feeder thread of a closed queue
            for _ in range(10_000):  # no reader is left: a feeder thread that waits on a full pipe can then end
                try:
                    sub.get_nowait()
                except (queue.Empty, OSError, EOFError):
                    break
            sub.close()  # a feeder thread closes the two pipe ends after the messages that it holds
            if getattr(sub, "_thread", None) is None:
                # shortcut: private names of multiprocessing.Queue; a queue with no put has no feeder thread to close them
                sub._reader.close()
                sub._writer.close()
        self.subscriptions.clear()
        logger.debug(f"Closed PubSubTopicABC {self.__class__.__name__}")
