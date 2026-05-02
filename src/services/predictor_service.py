from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from config import settings

if TYPE_CHECKING:
    from glucose_predictor import GlucosePredictor

logger = logging.getLogger(__name__)


class PredictorService:
    def __init__(self, checkpoint_dir: str | Path) -> None:
        self._checkpoint_dir = Path(checkpoint_dir)
        self._predictor: GlucosePredictor | None = None
        self._load_error: str | None = None

    def load(self) -> None:
        try:
            from glucose_predictor import GlucosePredictor
        except ImportError as err:
            self._load_error = f"glucose_predictor dependency is not installed: {err}"
            logger.warning(self._load_error)
            return

        if not self._checkpoint_dir.exists():
            self._load_error = f"Checkpoint directory not found: {self._checkpoint_dir}"
            logger.warning(self._load_error)
            return

        required = ["cfg.json", "informer_best.pth", "age_scaler.pkl"]
        missing = [f for f in required if not (self._checkpoint_dir / f).exists()]
        if missing:
            self._load_error = (
                f"Missing files in {self._checkpoint_dir}: {', '.join(missing)}"
            )
            logger.warning(self._load_error)
            return

        try:
            self._predictor = GlucosePredictor.from_pretrained(self._checkpoint_dir)
            self._load_error = None
            logger.info(
                "GlucosePredictor loaded from %s (history %d min, horizon %d min)",
                self._checkpoint_dir,
                self._predictor.required_history_minutes,
                self._predictor.horizon_minutes,
            )
        except Exception as err:  # noqa: BLE001
            self._load_error = f"Failed to load model: {err}"
            logger.exception(self._load_error)

    def is_ready(self) -> bool:
        return self._predictor is not None

    @property
    def error(self) -> str | None:
        return self._load_error
        # Скрипт-обгортка: спершу прогнати міграції, потім стартувати додаток.
        # `sed -i 's/\r$//'` зрізає CRLF, які могли потрапити з Windows-хоста, —
        #

    @property
    def predictor(self) -> GlucosePredictor:
        if self._predictor is None:
            raise RuntimeError(
                self._load_error or "GlucosePredictor is not initialized"
            )
        return self._predictor


_service: PredictorService | None = None


def init_predictor_service() -> PredictorService:
    global _service
    if _service is None:
        _service = PredictorService(settings.predictor.checkpoint_dir)
        _service.load()
    return _service


def get_predictor_service() -> PredictorService:
    if _service is None:
        return init_predictor_service()
    return _service
