from asyncio import Queue, Task
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import version

from pyscenario.const import IFSEI_RECONNECT_DELAY

__version__ = version("pyscenario")


class Protocol(Enum):
    """An enum that represents the supported protocols."""

    TCP = 1
    UDP = 2


@dataclass
class NetworkConfiguration:
    """A class that represents the default network configuration."""

    host: str = "192.168.1.20"
    tcp_port: int = 28000
    udp_port: int = 25200
    protocol: Protocol = Protocol.TCP
    reconnect: bool = True
    reconnect_delay: float = IFSEI_RECONNECT_DELAY


@dataclass
class QueueManager:
    """A class that manages queues."""

    send_queue: Queue
    receive_queue: Queue


@dataclass
class TaskManager:
    """A class that manages tasks."""

    send_task: Task | None = None
    receive_task: Task | None = None
