import pytest
import torch

from src.models.enhancer import EnhancerModel


@pytest.mark.parametrize(
    "input_sr, duration",
    [
        (44100, 1.0),
        (16000, 2.0),
        (48000, 0.5),
        (8000, 10.0),
    ],
)
def test_mono_audio_same_duration_shape_sample_rate(input_sr, duration):
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    num_samples = int(input_sr * duration)
    audio = torch.randn(1, num_samples)  # Mono audio
    model = EnhancerModel(device="cuda")
    output, result_sample_rate = model.enhance_audio(audio, input_sr)

    assert output.shape[1] / result_sample_rate == pytest.approx(duration)

    del model
    torch.cuda.empty_cache()


@pytest.mark.parametrize(
    "input_sr, duration, channels",
    [
        (44100, 1.0, 2),
        (16000, 2.0, 3),
        (48000, 0.5, 4),
        (8000, 10.0, 1),
    ],
)
def test_multi_channel_audio_same_duration_shape_sample_rate(input_sr, duration, channels):
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    num_samples = int(input_sr * duration)
    audio = torch.randn(channels, num_samples)  # Multi-channel audio
    model = EnhancerModel(device="cuda")
    output, result_sample_rate = model.enhance_audio(audio, input_sr)

    assert output.shape[1] / result_sample_rate == pytest.approx(duration)

    del model
    torch.cuda.empty_cache()


@pytest.mark.parametrize(
    "chunk_duration_s, chunk_overlap_s, duration",
    [
        (30.0, 1.0, 10.0),
        (25.0, 2.0, 20.0),
        (20.0, 1.5, 30.0),
    ],
)
def test_model_with_different_parameters(chunk_duration_s, chunk_overlap_s, duration):
    if not torch.cuda.is_available():
        pytest.skip("CUDA not available")

    model = EnhancerModel(
        device="cuda",
        chunk_duration_s=chunk_duration_s,
        chunk_overlap_s=chunk_overlap_s,
    )
    sample_rate = model.sample_rate
    audio_length = int(duration * sample_rate)
    audio = torch.randn(1, audio_length)
    output, result_sample_rate = model.enhance_audio(audio, sample_rate)

    assert output.shape == (1, audio_length)
    assert output.shape[1] / result_sample_rate == pytest.approx(duration)

    del model
    torch.cuda.empty_cache()
