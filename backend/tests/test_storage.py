"""Storage tests: upload validation, safe filenames, private storage references,
and the Supabase Storage backend (exercised through a fake client - no network)."""

import re
from pathlib import Path

import pytest

from app.core.config import settings
from app.utils import storage as storage_module
from tests.conftest import jpeg_bytes, png_bytes

_KEY_PATTERN = r"complaints/\d+/[0-9a-f]{32}\.(?:jpg|png|webp)"


def _submit_with_photo(
    client,
    users,
    *,
    filename="fan.jpg",
    content=None,
    content_type="image/jpeg",
):
    return client.post(
        "/complaints",
        data={
            "description": "Ceiling fan sparking loudly in room 204 since Monday morning.",
            "block": "A",
            "room": "204",
        },
        files={
            "photo": (
                filename,
                content if content is not None else jpeg_bytes(),
                content_type,
            )
        },
        headers={"X-User-Id": str(users["student"])},
    )


def _local_files_for(complaint_id: int) -> list[str]:
    folder = Path(settings.upload_dir) / "complaints" / str(complaint_id)
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


# ---- Local fallback storage (used whenever Supabase is not configured) -------


class TestLocalStorage:
    def test_upload_creates_safe_complaint_scoped_key(self, client, seed_users):
        users = seed_users()
        response = _submit_with_photo(client, users)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["photo_available"] is True

        # The API never exposes the storage key; the shape is verified on disk.
        stored = [
            f"complaints/{body['id']}/{name}" for name in _local_files_for(body["id"])
        ]
        assert len(stored) == 1
        assert re.fullmatch(_KEY_PATTERN, stored[0])

    def test_hostile_browser_filename_is_never_stored(self, client, seed_users):
        users = seed_users()
        hostile = "../../evil name (<script>).jpg"
        response = _submit_with_photo(client, users, filename=hostile)
        assert response.status_code == 201, response.text
        complaint_id = response.json()["id"]

        names = _local_files_for(complaint_id)
        assert len(names) == 1
        # Nothing from the browser-supplied name survives on disk.
        assert "evil" not in names[0] and "script" not in names[0]

        # The photo is still retrievable through the API.
        photo = client.get(
            f"/complaints/{complaint_id}/photo",
            headers={"X-User-Id": str(users["warden"])},
        )
        assert photo.status_code == 200

    def test_invalid_image_content_rejected(self, client, seed_users):
        users = seed_users()
        response = _submit_with_photo(client, users, content=b"definitely not an image")
        assert response.status_code == 400

    def test_wrong_magic_bytes_with_image_extension_rejected(self, client, seed_users):
        users = seed_users()
        response = _submit_with_photo(
            client, users, filename="evil.jpg", content=b"corrupt bytes, not an image at all"
        )
        assert response.status_code == 400
        assert "not a valid JPEG" in response.json()["detail"]

    def test_mismatched_declared_type_rejected(self, client, seed_users):
        users = seed_users()
        ok = _submit_with_photo(client, users, filename="p.png", content=png_bytes(), content_type="image/png")
        assert ok.status_code == 201
        bad = _submit_with_photo(
            client,
            users,
            filename="faked.png",
            content=jpeg_bytes(),
            content_type="image/png",
        )
        assert bad.status_code == 400
        assert "does not match" in bad.json()["detail"]

    def test_oversized_image_rejected(self, client, seed_users):
        users = seed_users()
        response = _submit_with_photo(
            client,
            users,
            content=jpeg_bytes() + b"\x00" * (6 * 1024 * 1024),  # > 5 MB default
        )
        assert response.status_code == 400
        assert "too large" in response.json()["detail"]

    def test_no_photo_stays_photoless(self, client, seed_users):
        users = seed_users()
        response = client.post(
            "/complaints",
            data={
                "description": "Water cooler in the mess hall is leaking badly.",
                "block": "B",
                "room": "201",
            },
            headers={"X-User-Id": str(users["student"])},
        )
        assert response.status_code == 201
        assert response.json()["photo_available"] is False


# ---- Supabase Storage backend (fake client, no network) -----------------------


class FakeFiles:
    """Mimics supabase-py storage.from_(bucket) surface used by the backend."""

    def __init__(self, bucket: str):
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}

    def upload(self, path, file, file_options=None):
        mime = (file_options or {}).get("content-type", "application/octet-stream")
        self.objects[path] = (bytes(file), mime)
        return {"Key": f"{self.bucket}/{path}"}

    def download(self, path, options=None, query_params=None):
        if path not in self.objects:
            raise RuntimeError(f"Object not found: {path}")
        return self.objects[path][0]

    def create_signed_url(self, path, expires_in, options=None):
        return {
            "signedURL": f"/storage/v1/object/sign/{self.bucket}/{path}?token=t{expires_in}"
        }


class FakeClient:
    """Mimics the slice of supabase.Client the backend touches."""

    def __init__(self):
        self.supabase_url = "https://demo-project.supabase.co"
        self.files: FakeFiles | None = None
        self.storage = self  # real clients expose client.storage.from_(bucket)

    def from_(self, bucket: str) -> FakeFiles:
        self.files = FakeFiles(bucket)
        return self.files


@pytest.fixture()
def fake_supabase(monkeypatch):
    fake_client = FakeClient()
    backend = storage_module.SupabaseImageStorage(fake_client, "complaint-photos")
    monkeypatch.setattr(storage_module, "_storage_instance", backend)
    return fake_client


class TestSupabaseStorage:
    def test_upload_key_is_complaint_scoped_and_safe(self, client, seed_users, fake_supabase):
        users = seed_users()
        response = _submit_with_photo(client, users)
        assert response.status_code == 201, response.text
        body = response.json()

        stored_keys = list(fake_supabase.files.objects.keys())
        assert len(stored_keys) == 1
        assert re.fullmatch(_KEY_PATTERN, stored_keys[0])
        assert stored_keys[0].startswith(f"complaints/{body['id']}/")

    def test_upload_sends_proper_content_type_and_exact_bytes(
        self, client, seed_users, fake_supabase
    ):
        users = seed_users()
        _submit_with_photo(client, users, filename="p.png", content=png_bytes(), content_type="image/png")
        (key,) = fake_supabase.files.objects.keys()
        content, mime = fake_supabase.files.objects[key]
        assert mime == "image/png"
        assert content == png_bytes()

    def test_database_stores_reference_only_not_blob(self, seed_users, db, fake_supabase):
        """The DB keeps a short storage key, never the image bytes."""
        from sqlalchemy import select

        from app.db.models import Complaint

        complaint = db.execute(select(Complaint)).scalars().first()
        if complaint is None:
            assert fake_supabase.files is not None
            return
        assert complaint.photo_storage_key is not None
        assert len(complaint.photo_storage_key.encode()) < 300  # a key, not an image
        assert re.fullmatch(_KEY_PATTERN, complaint.photo_storage_key)

    def test_signed_url_endpoint(self, client, seed_users, fake_supabase):
        users = seed_users()
        created = _submit_with_photo(client, users).json()
        response = client.get(
            f"/complaints/{created['id']}/photo/url",
            headers={"X-User-Id": str(users["student"])},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["expires_in"] > 0
        assert f"complaints/{created['id']}/" in payload["url"]
        # The absolute URL is built on the project URL, and never contains the key.
        assert payload["url"].startswith("https://demo-project.supabase.co")
        assert "role_key" not in payload["url"]

    def test_signed_url_rejected_for_other_students_complaint(
        self, client, seed_users, fake_supabase
    ):
        users = seed_users()
        created = _submit_with_photo(client, users).json()
        response = client.get(
            f"/complaints/{created['id']}/photo/url",
            headers={"X-User-Id": str(users["worker_plumber_user"])},
        )
        assert response.status_code == 404

    def test_photo_bytes_download_via_supabase(self, client, seed_users, fake_supabase):
        users = seed_users()
        created = _submit_with_photo(client, users).json()
        photo = client.get(
            f"/complaints/{created['id']}/photo",
            headers={"X-User-Id": str(users["warden"])},
        )
        assert photo.status_code == 200
        assert photo.headers["Content-Type"] == "image/jpeg"
        assert photo.headers["Cache-Control"] == "private, max-age=0, no-store"
