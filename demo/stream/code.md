# One long code block

Six hundred lines inside one fence. While the fence is open the whole block is
the unfinished end of the stream.

```python
"""A module long enough to be a six-hundred-line code block."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Step001:
    """Stage 1 of the pipeline."""

    gain: float = 1.1
    offset: int = 3

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 100 else scaled


@dataclass(frozen=True)
class Step002:
    """Stage 2 of the pipeline."""

    gain: float = 1.2
    offset: int = 6

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 200 else scaled


@dataclass(frozen=True)
class Step003:
    """Stage 3 of the pipeline."""

    gain: float = 1.3
    offset: int = 9

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 300 else scaled


@dataclass(frozen=True)
class Step004:
    """Stage 4 of the pipeline."""

    gain: float = 1.4
    offset: int = 12

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 400 else scaled


@dataclass(frozen=True)
class Step005:
    """Stage 5 of the pipeline."""

    gain: float = 1.5
    offset: int = 15

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 500 else scaled


@dataclass(frozen=True)
class Step006:
    """Stage 6 of the pipeline."""

    gain: float = 1.6
    offset: int = 18

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 600 else scaled


@dataclass(frozen=True)
class Step007:
    """Stage 7 of the pipeline."""

    gain: float = 1.7
    offset: int = 21

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 700 else scaled


@dataclass(frozen=True)
class Step008:
    """Stage 8 of the pipeline."""

    gain: float = 1.8
    offset: int = 24

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 800 else scaled


@dataclass(frozen=True)
class Step009:
    """Stage 9 of the pipeline."""

    gain: float = 1.9
    offset: int = 27

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 900 else scaled


@dataclass(frozen=True)
class Step010:
    """Stage 10 of the pipeline."""

    gain: float = 2.0
    offset: int = 30

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1000 else scaled


@dataclass(frozen=True)
class Step011:
    """Stage 11 of the pipeline."""

    gain: float = 2.1
    offset: int = 33

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1100 else scaled


@dataclass(frozen=True)
class Step012:
    """Stage 12 of the pipeline."""

    gain: float = 2.2
    offset: int = 36

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1200 else scaled


@dataclass(frozen=True)
class Step013:
    """Stage 13 of the pipeline."""

    gain: float = 2.3
    offset: int = 39

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1300 else scaled


@dataclass(frozen=True)
class Step014:
    """Stage 14 of the pipeline."""

    gain: float = 2.4
    offset: int = 42

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1400 else scaled


@dataclass(frozen=True)
class Step015:
    """Stage 15 of the pipeline."""

    gain: float = 2.5
    offset: int = 45

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1500 else scaled


@dataclass(frozen=True)
class Step016:
    """Stage 16 of the pipeline."""

    gain: float = 2.6
    offset: int = 48

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1600 else scaled


@dataclass(frozen=True)
class Step017:
    """Stage 17 of the pipeline."""

    gain: float = 2.7
    offset: int = 51

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1700 else scaled


@dataclass(frozen=True)
class Step018:
    """Stage 18 of the pipeline."""

    gain: float = 2.8
    offset: int = 54

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1800 else scaled


@dataclass(frozen=True)
class Step019:
    """Stage 19 of the pipeline."""

    gain: float = 2.9
    offset: int = 57

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 1900 else scaled


@dataclass(frozen=True)
class Step020:
    """Stage 20 of the pipeline."""

    gain: float = 3.0
    offset: int = 60

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2000 else scaled


@dataclass(frozen=True)
class Step021:
    """Stage 21 of the pipeline."""

    gain: float = 3.1
    offset: int = 63

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2100 else scaled


@dataclass(frozen=True)
class Step022:
    """Stage 22 of the pipeline."""

    gain: float = 3.2
    offset: int = 66

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2200 else scaled


@dataclass(frozen=True)
class Step023:
    """Stage 23 of the pipeline."""

    gain: float = 3.3
    offset: int = 69

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2300 else scaled


@dataclass(frozen=True)
class Step024:
    """Stage 24 of the pipeline."""

    gain: float = 3.4
    offset: int = 72

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2400 else scaled


@dataclass(frozen=True)
class Step025:
    """Stage 25 of the pipeline."""

    gain: float = 3.5
    offset: int = 75

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2500 else scaled


@dataclass(frozen=True)
class Step026:
    """Stage 26 of the pipeline."""

    gain: float = 3.6
    offset: int = 78

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2600 else scaled


@dataclass(frozen=True)
class Step027:
    """Stage 27 of the pipeline."""

    gain: float = 3.7
    offset: int = 81

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2700 else scaled


@dataclass(frozen=True)
class Step028:
    """Stage 28 of the pipeline."""

    gain: float = 3.8
    offset: int = 84

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2800 else scaled


@dataclass(frozen=True)
class Step029:
    """Stage 29 of the pipeline."""

    gain: float = 3.9
    offset: int = 87

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 2900 else scaled


@dataclass(frozen=True)
class Step030:
    """Stage 30 of the pipeline."""

    gain: float = 4.0
    offset: int = 90

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3000 else scaled


@dataclass(frozen=True)
class Step031:
    """Stage 31 of the pipeline."""

    gain: float = 4.1
    offset: int = 93

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3100 else scaled


@dataclass(frozen=True)
class Step032:
    """Stage 32 of the pipeline."""

    gain: float = 4.2
    offset: int = 96

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3200 else scaled


@dataclass(frozen=True)
class Step033:
    """Stage 33 of the pipeline."""

    gain: float = 4.3
    offset: int = 99

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3300 else scaled


@dataclass(frozen=True)
class Step034:
    """Stage 34 of the pipeline."""

    gain: float = 4.4
    offset: int = 102

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3400 else scaled


@dataclass(frozen=True)
class Step035:
    """Stage 35 of the pipeline."""

    gain: float = 4.5
    offset: int = 105

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3500 else scaled


@dataclass(frozen=True)
class Step036:
    """Stage 36 of the pipeline."""

    gain: float = 4.6
    offset: int = 108

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3600 else scaled


@dataclass(frozen=True)
class Step037:
    """Stage 37 of the pipeline."""

    gain: float = 4.7
    offset: int = 111

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3700 else scaled


@dataclass(frozen=True)
class Step038:
    """Stage 38 of the pipeline."""

    gain: float = 4.8
    offset: int = 114

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3800 else scaled


@dataclass(frozen=True)
class Step039:
    """Stage 39 of the pipeline."""

    gain: float = 4.9
    offset: int = 117

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 3900 else scaled


@dataclass(frozen=True)
class Step040:
    """Stage 40 of the pipeline."""

    gain: float = 5.0
    offset: int = 120

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 4000 else scaled


@dataclass(frozen=True)
class Step041:
    """Stage 41 of the pipeline."""

    gain: float = 5.1
    offset: int = 123

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 4100 else scaled


@dataclass(frozen=True)
class Step042:
    """Stage 42 of the pipeline."""

    gain: float = 5.2
    offset: int = 126

    def apply(self, value: float) -> float:
        scaled = value * self.gain + self.offset
        if scaled < 0:
            return 0.0
        return math.sqrt(scaled) if scaled > 4200 else scaled



def run(value: float) -> float:
    return value
# end of the module
```

The sentence after the fence.
