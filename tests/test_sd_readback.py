"""Exercise real aligned O_DIRECT reads on the repository's filesystem."""
import errno
import hashlib
import importlib.util
from pathlib import Path
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('aligned_readback', ROOT / 'tools/aligned_readback.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


@pytest.fixture
def local_file():
    directory = ROOT / 'artifacts/sd-recovery/readback-tests'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as name:
        yield Path(name) / 'input.bin'


@pytest.mark.parametrize('length', [512, 4096, 8 * 1024 * 1024 + 512])
def test_direct_read_matches_independent_complete_hash(local_file, length):
    data = (bytes(range(256)) * ((length + 255) // 256))[:length]
    local_file.write_bytes(data)
    try:
        count, digest = reader.direct_hash(str(local_file), length)
    except OSError as error:
        if error.errno in (errno.EINVAL, errno.EOPNOTSUPP):
            pytest.skip('Repository filesystem does not support this O_DIRECT mode')
        raise
    assert count == length
    assert digest == hashlib.sha256(data).hexdigest()


def test_short_direct_read_is_not_a_complete_hash(local_file):
    local_file.write_bytes(bytes(512))
    with pytest.raises(OSError, match='Short O_DIRECT read'):
        reader.direct_hash(str(local_file), 1024)


@pytest.mark.parametrize('length', [0, -512, 513])
def test_invalid_transfer_length_is_rejected_before_open(length):
    with pytest.raises(ValueError):
        reader.direct_hash('/not-a-device', length)
