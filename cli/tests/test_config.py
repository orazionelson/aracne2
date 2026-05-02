"""Tests for the TOML config read/write path."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from aracne_cli.config import (
    Profile,
    ProfileNotFoundError,
    config_path,
    load_profile,
    save_profile,
)


def test_save_then_load_roundtrip(isolated_config: Path) -> None:
    save_profile(Profile(name="default", host="https://h.example", token="aracne2_pat_t"))
    loaded = load_profile("default")
    assert loaded.name == "default"
    assert loaded.host == "https://h.example"
    assert loaded.token == "aracne2_pat_t"


def test_load_missing_profile_raises(isolated_config: Path) -> None:
    with pytest.raises(ProfileNotFoundError) as excinfo:
        load_profile("nope")
    assert "Profile 'nope'" in str(excinfo.value)


def test_save_strips_trailing_slash_on_host(isolated_config: Path) -> None:
    save_profile(Profile(name="default", host="https://h.example/", token="aracne2_pat_t"))
    loaded = load_profile("default")
    assert loaded.host == "https://h.example"


def test_save_writes_0600_permissions(isolated_config: Path) -> None:
    save_profile(Profile(name="default", host="https://h", token="aracne2_pat_t"))
    mode = stat.S_IMODE(os.stat(config_path()).st_mode)
    # Owner-only read+write; nothing else.
    assert mode == 0o600, f"expected 0600 but got 0o{mode:o}"


def test_save_two_profiles_keeps_both(isolated_config: Path) -> None:
    save_profile(Profile(name="work", host="https://w", token="aracne2_pat_w"))
    save_profile(Profile(name="home", host="https://h", token="aracne2_pat_h"))
    assert load_profile("work").host == "https://w"
    assert load_profile("home").host == "https://h"


def test_save_overwrites_existing_profile(isolated_config: Path) -> None:
    save_profile(Profile(name="default", host="https://old", token="aracne2_pat_o"))
    save_profile(Profile(name="default", host="https://new", token="aracne2_pat_n"))
    loaded = load_profile("default")
    assert loaded.host == "https://new"
    assert loaded.token == "aracne2_pat_n"
