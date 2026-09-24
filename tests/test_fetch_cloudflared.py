"""
The cloudflared the installer ships is pinned and checked: the right build
for each platform, and nothing whose checksum differs from Cloudflare's.
"""
import hashlib
import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_cloudflared as fc  # noqa: E402


@pytest.mark.parametrize("system,machine,asset", [
    ("Windows", "AMD64", "cloudflared-windows-amd64.exe"),
    ("Linux", "x86_64", "cloudflared-linux-amd64"),
    ("Linux", "aarch64", "cloudflared-linux-arm64"),
    ("Darwin", "arm64", "cloudflared-darwin-arm64.tgz"),
    ("Darwin", "x86_64", "cloudflared-darwin-amd64.tgz"),
])
def test_each_platform_gets_its_own_build(system, machine, asset):
    assert fc.asset_for(system, machine) == asset
    assert asset in fc.ASSETS  # and a pinned checksum for it


def test_a_download_that_does_not_match_the_published_checksum_is_refused():
    with pytest.raises(SystemExit, match="refusing to ship"):
        fc.verify("cloudflared-linux-amd64", b"not what cloudflare published")


def test_a_matching_download_passes(monkeypatch):
    data = b"pretend binary"
    monkeypatch.setitem(fc.ASSETS, "cloudflared-linux-amd64", hashlib.sha256(data).hexdigest())
    fc.verify("cloudflared-linux-amd64", data)


def test_the_macos_archive_is_unpacked_to_the_binary():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"\xcf\xfa\xed\xfe mach-o"
        info = tarfile.TarInfo("cloudflared")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    assert fc.unpack("cloudflared-darwin-arm64.tgz", buffer.getvalue()) == b"\xcf\xfa\xed\xfe mach-o"
    assert fc.unpack("cloudflared-linux-amd64", b"elf") == b"elf"
