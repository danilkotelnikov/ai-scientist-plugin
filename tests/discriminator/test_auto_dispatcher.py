"""Tests for §5.3.2.c auto-dispatcher hardware detection."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def auto():
    """Import the dispatcher module (lives under ``scripts/``)."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    if "train_register_classifier" in sys.modules:
        del sys.modules["train_register_classifier"]
    import importlib

    return importlib.import_module("train_register_classifier")


def test_detect_gpu_when_vram_sufficient(auto):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_properties=lambda i: SimpleNamespace(total_memory=8 * 1024**3),
        )
    )
    with patch.dict(sys.modules, {"torch": fake_torch}):
        assert auto.detect_hardware(gpu_min_gb=7.0) == "gpu"


def test_falls_back_to_cpu_when_vram_low(auto):
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_properties=lambda i: SimpleNamespace(total_memory=4 * 1024**3),
        )
    )
    fake_psutil = SimpleNamespace(
        cpu_count=lambda logical: 38,
        virtual_memory=lambda: SimpleNamespace(total=512 * 1024**3),
    )
    with patch.dict(sys.modules, {"torch": fake_torch, "psutil": fake_psutil}):
        assert auto.detect_hardware(gpu_min_gb=7.0) == "cpu"


def test_cpu_path_picked_when_no_gpu(auto):
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_psutil = SimpleNamespace(
        cpu_count=lambda logical: 38,
        virtual_memory=lambda: SimpleNamespace(total=128 * 1024**3),
    )
    with patch.dict(sys.modules, {"torch": fake_torch, "psutil": fake_psutil}):
        assert auto.detect_hardware() == "cpu"


def test_raises_when_neither_path_qualifies(auto):
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    fake_psutil = SimpleNamespace(
        cpu_count=lambda logical: 4,
        virtual_memory=lambda: SimpleNamespace(total=8 * 1024**3),
    )
    with patch.dict(sys.modules, {"torch": fake_torch, "psutil": fake_psutil}):
        with pytest.raises(auto.HardwareInsufficientError):
            auto.detect_hardware()


def test_build_command_targets_gpu_script(auto, tmp_path):
    args = SimpleNamespace(
        corpus_root=tmp_path / "corpus",
        output_root=tmp_path / "out",
        languages="en",
        disciplines="chemistry",
        only_pair="chemistry:en",
    )
    cmd = auto.build_command(target="gpu", args=args, scripts_dir=tmp_path / "scripts")
    assert "train_register_classifier_gpu.py" in str(cmd[1])
    assert "--only-pair" in cmd
    assert "chemistry:en" in cmd


def test_build_command_targets_cpu_script(auto, tmp_path):
    args = SimpleNamespace(
        corpus_root=tmp_path / "corpus",
        output_root=tmp_path / "out",
        languages="en",
        disciplines="chemistry",
        only_pair=None,
    )
    cmd = auto.build_command(target="cpu", args=args, scripts_dir=tmp_path / "scripts")
    assert "train_register_classifier_cpu.py" in str(cmd[1])
    assert "--only-pair" not in cmd
