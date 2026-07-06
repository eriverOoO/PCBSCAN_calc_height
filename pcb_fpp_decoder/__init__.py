"""PCB structured-light / FPP post-processing toolkit."""

from .decoder import DecodeConfig, FusionResult, PcbFppDecoder
from .simulator import PcbFppSimulator, SimulationResult, SyntheticPcbConfig

__all__ = [
    "DecodeConfig",
    "FusionResult",
    "PcbFppDecoder",
    "PcbFppSimulator",
    "SimulationResult",
    "SyntheticPcbConfig",
]
