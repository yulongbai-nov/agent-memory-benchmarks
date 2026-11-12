"""OpenViking's benchmark registration."""

from typing import ClassVar

from amb.base import Benchmark
from src.memory import OpenVikingMemory


class OpenVikingBenchmark(Benchmark):
    """Run the OpenViking memory service through the benchmark."""

    name: ClassVar[str] = "openviking"
    system_class = OpenVikingMemory
