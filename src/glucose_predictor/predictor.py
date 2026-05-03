from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from transformers import InformerConfig, InformerForPrediction

from .preprocessing import TIME_FEATS, preprocess_history
from .schemas import GlucoseReading, PatientInfo, PredictionPoint, PredictionResult


class GlucosePredictor:
    def __init__(
        self,
        model: InformerForPrediction,
        cfg: dict,
        age_scaler,
        device: str | torch.device = "cpu",  # type: ignore
    ):
        self.model = model.to(device).eval()  # type: ignore
        self.cfg = cfg
        self.age_scaler = age_scaler
        self.device = torch.device(device)  # type: ignore

    @classmethod
    def from_pretrained(
        cls,
        checkpoint_dir: str | Path,
        device: str | torch.device | None = None,  # type: ignore
    ) -> GlucosePredictor:
        ckpt = Path(checkpoint_dir)
        if not ckpt.exists():
            raise FileNotFoundError(f"Directory not found: {ckpt}")

        with open(ckpt / "cfg.json") as fp:
            cfg = json.load(fp)

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        config = InformerConfig(
            prediction_length=cfg["pred_len"],
            context_length=cfg["context_len"],
            lags_sequence=cfg["lags_seq"],
            distribution_output=cfg["distribution"],
            input_size=1,
            num_time_features=len(TIME_FEATS),
            num_static_real_features=3,
            num_static_categorical_features=1,
            cardinality=[2],
            embedding_dimension=[4],
            encoder_layers=cfg["enc_layers"],
            decoder_layers=cfg["dec_layers"],
            d_model=cfg["d_model"],
            encoder_attention_heads=cfg["attn_heads"],
            decoder_attention_heads=cfg["attn_heads"],
            encoder_ffn_dim=cfg["ffn_dim"],
            decoder_ffn_dim=cfg["ffn_dim"],
            dropout=cfg["dropout"],
            num_parallel_samples=cfg.get("val_samples", 20),
        )
        model = InformerForPrediction(config)
        state = torch.load(ckpt / "informer_best.pth", map_location=device)
        model.load_state_dict(state)

        age_scaler = joblib.load(ckpt / "age_scaler.pkl")
        return cls(model=model, cfg=cfg, age_scaler=age_scaler, device=device)

    @property
    def required_history_minutes(self) -> int:
        return self.cfg["seq_len"] * self.cfg["sample_min"]

    @property
    def horizon_minutes(self) -> int:
        return self.cfg["pred_len"] * self.cfg["sample_min"]

    @torch.no_grad()
    def predict(
        self,
        readings: Sequence[GlucoseReading],
        patient: PatientInfo,
    ) -> PredictionResult:
        cfg = self.cfg
        seq_len = cfg["seq_len"]
        pred_len = cfg["pred_len"]
        sample_min = cfg["sample_min"]

        hist = preprocess_history(
            readings,
            sample_min=sample_min,
            gap_threshold_min=cfg["gap_threshold"],
            min_glucose=cfg["min_glucose"],
            max_glucose=cfg["max_glucose"],
            pt_mean=patient.pt_mean,
            pt_std=patient.pt_std,
        )

        if len(hist.glucose) < seq_len:
            need_min = seq_len * sample_min
            have_min = len(hist.glucose) * sample_min
            raise ValueError(
                f"Not enough continuous history: need {need_min} min, got {have_min} min"
            )

        g_window = hist.glucose[-seq_len:]
        tf_window = hist.time_features[-seq_len:]
        ts_last = hist.timestamps[-1]

        g_norm = (g_window - hist.pt_mean) / hist.pt_std

        future_ts = np.array(
            [
                ts_last + np.timedelta64(sample_min * (i + 1), "m")
                for i in range(pred_len)
            ]
        )
        future_tf = self._time_features_from_ts(future_ts)

        age_n = float(self.age_scaler.transform([[patient.age]])[0, 0])
        sex = 0 if patient.sex == "M" else 1
        s_real = np.array(
            [age_n, (hist.pt_mean - 150.0) / 50.0, (hist.pt_std - 50.0) / 25.0],
            dtype=np.float32,
        )
        s_cat = np.array([sex], dtype=np.int64)

        d = self.device
        past_values = torch.from_numpy(g_norm).unsqueeze(0).to(d)  # type: ignore
        past_tf = torch.from_numpy(tf_window).unsqueeze(0).to(d)  # type: ignore
        past_mask = torch.ones_like(past_values)  # type: ignore
        future_tf_t = torch.from_numpy(future_tf).unsqueeze(0).to(d)  # type: ignore
        s_real_t = torch.from_numpy(s_real).unsqueeze(0).to(d)  # type: ignore
        s_cat_t = torch.from_numpy(s_cat).unsqueeze(0).to(d)  # type: ignore

        gen = self.model.generate(
            past_values=past_values,
            past_time_features=past_tf,
            past_observed_mask=past_mask,
            static_real_features=s_real_t,
            static_categorical_features=s_cat_t,
            future_time_features=future_tf_t,
        )

        assert gen.sequences is not None, "Model failed to generate sequences"
        preds_norm = gen.sequences.median(dim=1).values.squeeze(0).cpu().numpy()  # type: ignore
        preds_mgdl = preds_norm * hist.pt_std + hist.pt_mean

        ts_last_pd = pd.Timestamp(ts_last)
        points = []
        for i, val in enumerate(preds_mgdl):
            future_pd = ts_last_pd + pd.Timedelta(minutes=sample_min * (i + 1))
            points.append(
                PredictionPoint(
                    ts=future_pd.to_pydatetime(),  # type: ignore
                    glucose=float(val),
                    minutes_ahead=sample_min * (i + 1),
                )
            )

        return PredictionResult(
            predictions=points,
            horizon_min=self.horizon_minutes,
            last_observed_ts=ts_last_pd.to_pydatetime(),  # type: ignore
            last_observed_glucose=float(g_window[-1]),
        )

    @staticmethod
    def _time_features_from_ts(ts: np.ndarray) -> np.ndarray:
        idx = pd.DatetimeIndex(ts)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        h = idx.hour.values  # type: ignore
        m = idx.minute.values  # type: ignore
        d = idx.dayofweek.values  # type: ignore
        feats = np.stack(
            [
                np.sin(2 * np.pi * h / 24),
                np.cos(2 * np.pi * h / 24),
                np.sin(2 * np.pi * m / 60),
                np.cos(2 * np.pi * m / 60),
                np.sin(2 * np.pi * d / 7),
                np.cos(2 * np.pi * d / 7),
            ],
            axis=1,
        ).astype(np.float32)
        return feats
