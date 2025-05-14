from typing import Optional, Tuple

import torch
from resemble_enhance.enhancer.inference import load_enhancer
from torch.nn.functional import pad
from torchaudio.functional import resample
from torchaudio.transforms import MelSpectrogram


class EnhancerModel:
    def __init__(
        self,
        device: str = "cuda",
        nfe: int = 32,
        solver: str = "midpoint",
        lambd: float = 0.5,
        tau: float = 0.5,
        chunk_duration_s: float = 30.0,
        chunk_overlap_s: float = 1.0,
    ) -> None:
        self._device = device
        self._model = load_enhancer(None, device)
        self._model.configurate_(nfe=nfe, solver=solver, lambd=lambd, tau=tau)
        self._model.eval()

        self._sample_rate = 44100

        self._chunk_duration_s = chunk_duration_s
        self._chunk_overlap_s = chunk_overlap_s
        self._chunk_length = int(self._sample_rate * self._chunk_duration_s)
        self._overlap_length = int(self._sample_rate * self._chunk_overlap_s)
        self._hop_length = self._chunk_length - self._overlap_length

    @property
    def sample_rate(self):
        return self._sample_rate

    def enhance_audio(self, audio: torch.Tensor, sample_rate: int) -> Tuple[torch.Tensor, int]:
        batched_chunks, audio_length = self._preprocess_audio(audio, sample_rate)

        assert batched_chunks.ndim == 2

        batched_chunks = batched_chunks.to(self._device)
        with torch.inference_mode() and torch.no_grad():
            batched_result = self._model(batched_chunks)
            batched_result = batched_result.to("cpu")

        enhanced_audio = self._postprocess_audio(batched_result, audio_length)

        assert enhanced_audio.ndim == 2
        assert enhanced_audio.shape[0] == 1
        return enhanced_audio, self._sample_rate

    def _preprocess_audio(self, audio: torch.Tensor, sample_rate: int) -> Tuple[torch.Tensor, int]:
        assert audio.ndim == 2

        audio = audio.mean(dim=0, keepdim=False)

        assert audio.ndim == 1
        assert audio.shape[0] > 1

        audio = resample(
            audio,
            orig_freq=sample_rate,
            new_freq=self._sample_rate,
            lowpass_filter_width=64,
            rolloff=0.9475937167399596,
            resampling_method="sinc_interp_kaiser",
            beta=14.769656459379492,
        )

        audio_length = audio.shape[0]

        chunks = [audio[i : i + self._chunk_length] for i in range(0, audio_length, self._hop_length)]
        chunks = torch.stack([pad(chunk, (0, self._chunk_length - len(chunk))) for chunk in chunks], dim=0)

        abs_max = chunks.abs().max(dim=1, keepdim=True).values
        abs_max[abs_max == 0] = 10e-7
        chunks = chunks / abs_max

        assert chunks.ndim == 2

        return chunks, audio_length

    def _postprocess_audio(self, audio_chunks: torch.Tensor, length: Optional[int] = None):
        signal_length = (len(audio_chunks) - 1) * self._hop_length + self._chunk_length
        signal = torch.zeros(signal_length, device=audio_chunks[0].device)

        fadein = torch.linspace(0, 1, self._overlap_length, device=audio_chunks[0].device)
        fadein = torch.cat([fadein, torch.ones(self._hop_length, device=audio_chunks[0].device)])
        fadeout = torch.linspace(1, 0, self._overlap_length, device=audio_chunks[0].device)
        fadeout = torch.cat([torch.ones(self._hop_length, device=audio_chunks[0].device), fadeout])

        for i, chunk in enumerate(audio_chunks):
            start = i * self._hop_length
            end = start + self._chunk_length

            if len(chunk) < self._chunk_length:
                chunk = pad(chunk, (0, self._chunk_length - len(chunk)))

            if i > 0:
                pre_region = audio_chunks[i - 1][-self._overlap_length :]
                cur_region = chunk[: self._overlap_length]
                offset = self._compute_offset(pre_region, cur_region, sr=self._sample_rate)
                start -= offset
                end -= offset

            if i == 0:
                chunk = chunk * fadeout
            elif i == len(audio_chunks) - 1:
                chunk = chunk * fadein
            else:
                chunk = chunk * fadein * fadeout

            signal[start:end] += chunk[: len(signal[start:end])]

        signal = signal[:length]

        return signal.unsqueeze(0)

    def _compute_offset(self, chunk1, chunk2, sr=44100):
        """
        Args:
            chunk1: (T,)
            chunk2: (T,)
        Returns:
            offset: int, offset in samples such that chunk1 ~= chunk2.roll(-offset)
        """
        hop_length = sr // 200  # 5 ms resolution
        win_length = hop_length * 4
        n_fft = 2 ** int(win_length - 1).bit_length()

        mel_fn = MelSpectrogram(
            sample_rate=sr,
            n_fft=n_fft,
            win_length=win_length,
            hop_length=hop_length,
            n_mels=80,
            f_min=0.0,
            f_max=sr // 2,
        )

        spec1 = mel_fn(chunk1).log1p()
        spec2 = mel_fn(chunk2).log1p()

        corr = self._compute_corr(spec1, spec2)  # (F, T)
        corr = corr.mean(dim=0)  # (T,)

        argmax = corr.argmax().item()

        if argmax > len(corr) // 2:
            argmax -= len(corr)

        offset = -argmax * hop_length

        return offset

    def _compute_corr(self, x, y):
        return torch.fft.ifft(torch.fft.fft(x) * torch.fft.fft(y).conj()).abs()
