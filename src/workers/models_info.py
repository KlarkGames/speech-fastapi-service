from dataclasses import dataclass
from typing import Callable

from src.workers.enhance import process_audio_enhancement


@dataclass
class ModelInfo:
    name: str
    description: str
    price: float
    worker: Callable


MODELS_INFO = {
    "audio_enhancer": ModelInfo(
        name="Resemble Enhancer", description="Enhance audio quality", price=10.0, worker=process_audio_enhancement
    )
}
