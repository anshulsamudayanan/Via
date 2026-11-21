import io
import uuid

import pytest

from via_api.storage import InvalidKeyError, LocalStorage, ObjectNotFoundError, revision_object_key, validate_key


def test_revision_keys_are_server_generated_and_valid():
    p, r = uuid.uuid4(), uuid.uuid4()
    assert revision_object_key(p, r, "source") == f"projects/{p}/revisions/{r}/source"
    with pytest.raises(InvalidKeyError):
        revision_object_key(p, r, "../../etc/passwd")


@pytest.mark.parametrize(
    "key", ["../x", "a/../b", "/abs", "a//b", "a/", "", "UPPER", "spaces here", "a\x00b", "x" * 600]
)
def test_invalid_keys_are_rejected(key):
    with pytest.raises(InvalidKeyError):
        validate_key(key)


def test_local_round_trip(tmp_path):
    store = LocalStorage(tmp_path)
    store.check()
    key = "projects/p/revisions/r/source"
    info = store.put(key, io.BytesIO(b"abc"), content_type="text/plain")
    assert (info.size_bytes, info.content_type) == (3, "text/plain")
    assert store.get(key) == b"abc"
    store.put(key, b"replaced", content_type="text/plain")
    assert store.get(key) == b"replaced"
    store.delete(key)
    assert not store.exists(key)
    with pytest.raises(ObjectNotFoundError):
        store.get(key)
    store.delete(key)  # idempotent


def test_local_storage_never_leaves_partial_files(tmp_path):
    store = LocalStorage(tmp_path)

    class Exploding(io.RawIOBase):
        def readinto(self, b):
            raise OSError("disk went away")

    with pytest.raises(OSError):
        store.put("projects/p/x", Exploding(), content_type="text/plain")
    assert not store.exists("projects/p/x")
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []
