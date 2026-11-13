# MIT License
#
# Copyright (c) 2026 René-Jean Corneille
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Register the OpenSquilla memory adapter."""

from typing import ClassVar

from amb.base import Benchmark
from amb.base.callback import Callback
from amb.callbacks import TiktokenUsageTracker
from src.memory import OpenSquillaMemory


class OpenSquillaBenchmark(Benchmark):
    """Evaluate OpenSquilla's native transcript index and memory retriever."""

    name: ClassVar[str] = "opensquilla"
    system_class: ClassVar[type[OpenSquillaMemory]] = OpenSquillaMemory
    callback_classes: ClassVar[tuple[type[Callback], ...]] = (TiktokenUsageTracker,)
