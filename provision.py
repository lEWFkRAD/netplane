"""Explicit, fresh-install Headscale provisioning. No work occurs on import.

This standard-library-only helper runs under ``python3 -I``. It accepts only
validated setup options; commands, package sources and system paths are fixed.
The caller must obtain approval before invoking a privileged action.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import ipaddress
import json
import os
import platform
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "0.29.6"
PACKAGE_HASHES = {
    "amd64": "a3b49916a16418c704cef89818d734bc8af0528aac965a2dd5ca4bfa4cef48e2",
    "arm64": "077467b12ba2122086db434335fadfa8deee4dbddacb1f959eecc6d7d10b81d4",
}
CONFIG = Path("/etc/headscale/config.yaml")
MARKER = Path("/etc/headscale/netplane-install.json")
DATA = Path("/var/lib/headscale")
OVERRIDE = Path("/etc/systemd/system/headscale.service.d/netplane.conf")
LOCK = Path("/run/lock/netplane-headscale-setup.lock")
SYSTEMCTL = "/usr/bin/systemctl"
HEADSCALE = "/usr/bin/headscale"
SAFE_ENV = {
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "DEBIAN_FRONTEND": "noninteractive",
}
_DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_USER = re.compile(r"[a-z][a-z0-9_-]{0,62}\Z")
_PREFIX = re.compile(r"[A-Za-z0-9_-]{4,64}\Z")
_DEADLINE: float | None = None


class ProvisionError(RuntimeError):
    """A safe, non-secret-bearing provisioning failure."""

    def __init__(self, message: str, stage: str = "preflight", recovery: str = ""):
        super().__init__(message)
        self.stage = stage
        self.recovery = recovery


def _domain(value: object, label: str, *, public: bool = False) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a DNS name")
    name = value.lower()
    if (
        len(name) > 253
        or "." not in name
        or not all(_DOMAIN.fullmatch(part) for part in name.split("."))
    ):
        raise ValueError(f"{label} must be a fully qualified DNS name")
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise ValueError(f"{label} must be a DNS name, not an IP address")
    if public and name.rsplit(".", 1)[1] in {
        "localhost",
        "local",
        "internal",
        "invalid",
        "test",
        "example",
        "onion",
    }:
        raise ValueError(f"{label} must be a public DNS name")
    return name


def validate_options(args: dict) -> dict:
    """Normalize the small public option surface without inspecting the host."""
    if not isinstance(args, dict):
        raise ValueError("setup options must be an object")  # noqa: TRY004
    url = args.get("server_url", "")
    if not isinstance(url, str) or any(ch.isspace() for ch in url):
        raise ValueError("server_url must be an HTTPS URL")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("server_url must be a valid HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "server_url requires HTTPS and a hostname, with no credentials, path, query or fragment"
        )
    host = _domain(parsed.hostname, "server_url hostname", public=True)
    # DERP clients assume HTTPS on 443; supporting other ports adds needless
    # ambiguity to this first-install workflow.
    if port not in (None, 443):
        raise ValueError("server_url must use HTTPS port 443")
    mode = args.get("tls_mode", "letsencrypt")
    if mode not in ("letsencrypt", "reverse_proxy"):
        raise ValueError("tls_mode must be letsencrypt or reverse_proxy")
    email = args.get("acme_email", "")
    if (
        not isinstance(email, str)
        or len(email) > 254
        or any(ord(ch) < 33 or ord(ch) > 126 for ch in email)
    ):
        raise ValueError("acme_email must be a valid email address")
    if mode == "letsencrypt" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("acme_email is required for letsencrypt")
    base_domain = _domain(args.get("base_domain", "tailnet.internal"), "base_domain")
    if base_domain == host:
        raise ValueError("base_domain must differ from the server hostname")
    user = args.get("headscale_user", "hermes")
    if not isinstance(user, str) or not _USER.fullmatch(user):
        raise ValueError(
            "headscale_user must start with a lowercase letter and contain at most 63 lowercase letters, digits, hyphens or underscores"
        )
    return {
        "server_url": "https://" + host,
        "tls_mode": mode,
        "acme_email": email if mode == "letsencrypt" else "",
        "base_domain": base_domain,
        "headscale_user": user,
    }


def _configuration(options: dict) -> dict:
    acme = options["tls_mode"] == "letsencrypt"
    host = urllib.parse.urlsplit(options["server_url"]).hostname
    return {
        "server_url": options["server_url"],
        "listen_addr": "0.0.0.0:443" if acme else "127.0.0.1:8080",
        "metrics_listen_addr": "127.0.0.1:9090",
        "grpc_listen_addr": "127.0.0.1:50443",
        # With ACME, Headscale always adds TLS to this listener despite this
        # flag. The plugin uses a verified TLS channel with host as SNI.
        "grpc_allow_insecure": not acme,
        "trusted_proxies": [] if acme else ["127.0.0.1/32", "::1/128"],
        "noise": {"private_key_path": "/var/lib/headscale/noise_private.key"},
        "prefixes": {
            "v4": "100.64.0.0/10",
            "v6": "fd7a:115c:a1e0::/48",
            "allocation": "sequential",
        },
        "derp": {
            "server": {
                "enabled": True,
                "region_id": 999,
                "region_code": "netplane",
                "region_name": "NetPlane",
                "verify_clients": True,
                "stun_listen_addr": "0.0.0.0:3478",
                "private_key_path": "/var/lib/headscale/derp_server_private.key",
                "automatically_add_embedded_derp_region": True,
            },
            "urls": [],
            "paths": [],
            "auto_update_enabled": False,
        },
        "disable_check_updates": True,
        "node": {"expiry": "180d", "ephemeral": {"inactivity_timeout": "30m"}},
        "database": {
            "type": "sqlite",
            "sqlite": {
                "path": "/var/lib/headscale/db.sqlite",
                "write_ahead_log": True,
                "wal_autocheckpoint": 1000,
            },
        },
        "acme_url": "https://acme-v02.api.letsencrypt.org/directory",
        "acme_email": options["acme_email"],
        "tls_letsencrypt_hostname": host if acme else "",
        "tls_letsencrypt_cache_dir": "/var/lib/headscale/cache",
        "tls_letsencrypt_challenge_type": "HTTP-01",
        "tls_letsencrypt_listen": "0.0.0.0:80",
        "tls_cert_path": "",
        "tls_key_path": "",
        "log": {"level": "info", "format": "text"},
        "policy": {"mode": "file", "path": ""},
        "dns": {
            "magic_dns": True,
            "base_domain": options["base_domain"],
            "override_local_dns": False,
            "nameservers": {"global": [], "split": {}},
            "search_domains": [],
            "extra_records": [],
        },
        "unix_socket": "/var/run/headscale/headscale.sock",
        "unix_socket_permission": "0770",
        "logtail": {"enabled": False},
        "taildrop": {"enabled": True},
        "auto_update": {"enabled": False},
    }


def _json(data: dict) -> str:
    # JSON is valid YAML and supported by Headscale; no YAML dependency or
    # interpolation is needed for attacker-controlled strings.
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _architecture() -> str:
    arch = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine()
    )
    if arch is None:
        raise ProvisionError("Only Linux amd64 and arm64 are supported")
    return arch


def _download_info(arch: str) -> dict:
    return {
        "url": f"https://github.com/juanfont/headscale/releases/download/v{VERSION}/headscale_{VERSION}_linux_{arch}.deb",
        "sha256": PACKAGE_HASHES[arch],
        "version": VERSION,
        "architecture": arch,
    }


def build_plan(args: dict) -> dict:
    if platform.system() != "Linux":
        raise ProvisionError("Setup supports Linux only")
    options = validate_options(args)
    config = _configuration(options)
    acme = options["tls_mode"] == "letsencrypt"
    return {
        "options": options,
        "config": config,
        "config_preview": _json(config),
        "download": _download_info(_architecture()),
        "actions": [
            "Refuse existing Headscale packages, binaries, configuration, state or service units",
            "Download the fixed official DEB and verify its pinned SHA-256",
            "Mask the new headscale service during package installation",
            "Write configuration and validate with headscale configtest before starting",
            "Enable and start headscale, then create the initial Headscale user",
            "Create a 90-day API key separately and save it only through Hermes secret storage",
        ],
        "network": {
            "downloads": ["github.com", "release-assets.githubusercontent.com"],
            "certificate_authority": "Let's Encrypt (ACME account and public certificate)"
            if acme
            else "existing reverse proxy",
            "public_listeners": [
                "TCP 80 (ACME)",
                "TCP 443 (HTTPS/DERP)",
                "UDP 3478 (STUN)",
            ]
            if acme
            else ["UDP 3478 (STUN); existing proxy must serve HTTPS/DERP on TCP 443"],
            "loopback_listeners": ["127.0.0.1:50443 (gRPC)", "127.0.0.1:9090 (metrics)"]
            + ([] if acme else ["127.0.0.1:8080 (HTTP backend)"]),
            "third_party_derp": False,
        },
        "writes": [
            "Headscale DEB package and system account",
            "/etc/headscale/config.yaml",
            "/etc/headscale/netplane-install.json",
            "/var/lib/headscale",
            str(OVERRIDE),
            "headscale.service enable/start",
            "active Hermes profile settings and NETPLANE_APIKEY",
        ],
        "prerequisites": [
            "Fresh Debian 12+ or Ubuntu 22.04+, systemd, amd64 or arm64",
            "Root privileges (the plugin uses noninteractive sudo and never asks for a password)",
            "Public DNS points the server hostname to this host; allow inbound TCP 443 and UDP 3478",
            "Allow inbound TCP 80 and agree to the Let's Encrypt subscriber agreement"
            if acme
            else "An existing HTTPS reverse proxy routes WebSocket POST upgrades and DERP to 127.0.0.1:8080",
            "No ports or existing Headscale resources conflict; no upgrade or migration is performed",
            "Initial Headscale policy allows enrolled nodes to communicate; no nodes are enrolled automatically",
        ],
        "grpc_addr": "127.0.0.1:50443",
        "grpc_tls_server_name": urllib.parse.urlsplit(options["server_url"]).hostname
        if acme
        else "",
        "control_url": options["server_url"],
    }


def _run(
    argv: list[str],
    *,
    timeout: float = 30,
    check: bool = True,
    ignore_deadline: bool = False,
) -> subprocess.CompletedProcess:
    if _DEADLINE is not None and not ignore_deadline:
        remaining = _DEADLINE - time.monotonic()
        if remaining <= 0:
            raise ProvisionError("Headscale setup exceeded its time budget", "timeout")
        timeout = min(timeout, remaining)
    process = None
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=SAFE_ENV,
            cwd="/",
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        stdout, stderr = process.communicate(timeout=timeout)
        result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Never include subprocess output in errors: bootstrap-key output is
        # a bearer credential even when a process exits nonzero.
        raise ProvisionError(f"{Path(argv[0]).name} failed or timed out") from exc
    finally:
        if process is not None and process.poll() is None:
            grace = 0.25 if ignore_deadline else 2
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=grace)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=grace)
    if check and result.returncode:
        raise ProvisionError(
            f"{Path(argv[0]).name} exited with status {result.returncode}"
        )
    return result


def _require_root() -> None:
    if os.geteuid() != 0:
        raise ProvisionError("This action requires root privileges")


@contextlib.contextmanager
def _lock():
    import fcntl

    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or info.st_nlink != 1
        ):
            raise ProvisionError("Unsafe setup lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProvisionError("Another NetPlane setup is running") from exc
        yield
    finally:
        os.close(fd)


def _port_free(address: str, port: int, *, udp: bool = False) -> None:
    try:
        with socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM
        ) as sock:
            sock.bind((address, port))
    except OSError as exc:
        raise ProvisionError(
            f"Required {'UDP' if udp else 'TCP'} port {address}:{port} is unavailable"
        ) from exc


def _preflight(options: dict) -> str:
    import grp
    import pwd

    if platform.system() != "Linux":
        raise ProvisionError("Setup supports Linux only")
    release = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            release[key] = value.strip('"')
    distro, version = release.get("ID"), release.get("VERSION_ID", "")
    try:
        numbers = tuple(int(piece) for piece in version.split("."))
    except ValueError as exc:
        raise ProvisionError(
            "Could not identify the Linux distribution version"
        ) from exc
    if not (
        (distro == "debian" and numbers >= (12,))
        or (distro == "ubuntu" and numbers >= (22, 4))
    ):
        raise ProvisionError("Setup requires Debian 12+ or Ubuntu 22.04+")
    if not Path("/run/systemd/system").is_dir():
        raise ProvisionError("A running systemd system is required")
    arch = _architecture()
    dpkg_arch = _run(["/usr/bin/dpkg", "--print-architecture"]).stdout.strip()
    if dpkg_arch != arch:
        raise ProvisionError("Kernel and Debian package architectures do not match")
    for path in (
        CONFIG.parent,
        DATA,
        Path(HEADSCALE),
        Path("/usr/local/bin/headscale"),
        Path("/run/headscale"),
        Path("/etc/systemd/system/headscale.service"),
        Path("/etc/systemd/system/headscale.service.d"),
        Path("/usr/lib/systemd/system/headscale.service"),
        Path("/lib/systemd/system/headscale.service"),
    ):
        if os.path.lexists(path):
            raise ProvisionError(
                f"Existing Headscale resource found: {path}; fresh installs only"
            )
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try:
            lookup("headscale")
        except KeyError:
            pass
        else:
            raise ProvisionError(
                "An existing Headscale system account or group was found; fresh installs only"
            )
    package = _run(
        [
            "/usr/bin/dpkg-query",
            "--show",
            "--showformat=${db:Status-Abbrev}",
            "headscale",
        ],
        check=False,
    )
    if package.returncode == 0:
        raise ProvisionError("Headscale is already known to dpkg; fresh installs only")
    if package.returncode != 1:
        raise ProvisionError("Could not establish package installation state")
    unit = _run(
        [SYSTEMCTL, "show", "headscale.service", "--property=LoadState", "--value"],
        check=False,
    )
    if unit.stdout.strip() != "not-found":
        raise ProvisionError("An existing Headscale service or service state was found")
    for port in (50443, 9090):
        _port_free("127.0.0.1", port)
    if options["tls_mode"] == "letsencrypt":
        for port in (80, 443):
            _port_free("0.0.0.0", port)
    else:
        _port_free("127.0.0.1", 8080)
    _port_free("0.0.0.0", 3478, udp=True)
    return arch


class _HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ProvisionError("Refusing a non-HTTPS package redirect", "download")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _download_package(destination: Path, arch: str) -> None:
    info = _download_info(arch)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _HTTPSRedirects()
    )
    request = urllib.request.Request(
        info["url"], headers={"User-Agent": "netplane-setup/0.3"}
    )
    digest, size = hashlib.sha256(), 0
    deadline = min(time.monotonic() + 90, _DEADLINE or float("inf"))
    try:
        with (
            opener.open(request, timeout=10) as response,
            destination.open("xb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                if time.monotonic() > deadline:
                    raise ProvisionError(
                        "Headscale package download timed out", "download"
                    )
                size += len(chunk)
                if size > 128 * 1024 * 1024:
                    raise ProvisionError(
                        "Headscale package exceeds the download limit", "download"
                    )
                digest.update(chunk)
                output.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        raise ProvisionError(
            "Unable to download the pinned Headscale package", "download"
        ) from exc
    if digest.hexdigest() != info["sha256"]:
        raise ProvisionError(
            "Headscale package SHA-256 does not match the pinned release", "download"
        )


def _write_new(path: Path, data: str, *, mode: int = 0o600, gid: int = 0) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        os.fchown(fd, 0, gid)
        with os.fdopen(fd, "w", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def _replace_owned(path: Path, data: str, *, mode: int = 0o600, gid: int = 0) -> None:
    _trusted_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ProvisionError("Refusing to replace an unsafe Headscale file")
    # The parent directory is root-owned and the installer is serialized.
    temporary = path.with_name(path.name + ".netplane-new")
    _write_new(temporary, data, mode=mode, gid=gid)
    os.replace(temporary, path)


def _trusted_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ProvisionError("Headscale configuration directory is not securely owned")


def _service_ready() -> None:
    for _ in range(10):
        result = _run(
            [HEADSCALE, "--config", str(CONFIG), "users", "list", "--output", "json"],
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise ProvisionError("Headscale did not become ready", "start")


def _stop_after_failure() -> None:
    failed = False
    for action in ("stop", "disable", "mask"):
        try:
            _run(
                [SYSTEMCTL, action, "headscale.service"],
                timeout=2,
                ignore_deadline=True,
            )
        except ProvisionError:
            failed = True
    if failed:
        raise ProvisionError("One or more service cleanup commands failed")


def install(args: dict) -> dict:
    global _DEADLINE
    previous = _DEADLINE
    _DEADLINE = time.monotonic() + 300
    try:
        return _install(args)
    finally:
        _DEADLINE = previous


def _install(args: dict) -> dict:
    """Install a new local instance; preserve partial installations on failure."""
    options = validate_options(args)
    _require_root()
    import pwd

    with _lock():
        arch = _preflight(options)
        plan = build_plan(options)
        stage, mutated = "download", False
        try:
            with tempfile.TemporaryDirectory(
                prefix="netplane-headscale-", dir="/var/tmp"
            ) as folder:
                package = Path(folder) / f"headscale_{VERSION}_{arch}.deb"
                _download_package(package, arch)
                stage = "mask"
                _run([SYSTEMCTL, "mask", "headscale.service"])
                mutated = True
                stage = "package"
                _run(
                    [
                        "/usr/bin/apt-get",
                        "install",
                        "--yes",
                        "--no-install-recommends",
                        str(package),
                    ],
                    timeout=180,
                )
                version = _run(
                    [
                        "/usr/bin/dpkg-query",
                        "--show",
                        "--showformat=${Version}",
                        "headscale",
                    ]
                ).stdout.strip()
                if version != VERSION:
                    raise ProvisionError(
                        "Installed Headscale package version differs from the pinned release"
                    )
                stage = "configuration"
                account = pwd.getpwnam("headscale")
                data_info = DATA.lstat()
                if not stat.S_ISDIR(data_info.st_mode) or data_info.st_uid != 0:
                    raise ProvisionError("Unexpected Headscale package data directory")
                os.chown(DATA, account.pw_uid, account.pw_gid)
                os.chmod(DATA, 0o750)
                # Only the just-installed package's default configuration is
                # replaced. Preflight refused all pre-existing resources.
                _replace_owned(
                    CONFIG, plan["config_preview"], mode=0o640, gid=account.pw_gid
                )
                OVERRIDE.parent.mkdir(mode=0o755)
                _write_new(
                    OVERRIDE,
                    "[Service]\nAmbientCapabilities=CAP_NET_BIND_SERVICE CAP_CHOWN\nCapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_CHOWN\nNoNewPrivileges=true\n",
                    mode=0o644,
                )
                stage = "configtest"
                # configtest initializes the database and private keys; run
                # as the service account so they remain usable by systemd.
                _run(
                    [
                        "/usr/sbin/runuser",
                        "-u",
                        "headscale",
                        "--",
                        HEADSCALE,
                        "--config",
                        str(CONFIG),
                        "configtest",
                    ]
                )
                stage = "start"
                _run([SYSTEMCTL, "daemon-reload"])
                _run([SYSTEMCTL, "unmask", "headscale.service"])
                _run([SYSTEMCTL, "enable", "--now", "headscale.service"])
                _service_ready()
                stage = "user"
                _run(
                    [
                        HEADSCALE,
                        "--config",
                        str(CONFIG),
                        "users",
                        "create",
                        options["headscale_user"],
                        "--output",
                        "json",
                    ]
                )
                marker = {
                    "version": VERSION,
                    "options": options,
                    "config_sha256": hashlib.sha256(
                        plan["config_preview"].encode()
                    ).hexdigest(),
                    "api_key_prefix": "",
                    "bootstrap_state": "ready",
                }
                stage = "record"
                _write_new(MARKER, _json(marker))
        except Exception as exc:
            cleanup_failed = False
            if mutated:
                try:
                    _stop_after_failure()
                except ProvisionError:
                    cleanup_failed = True
            recovery = (
                "Partial installation retained. Inspect /etc/headscale, /var/lib/headscale and journalctl -u headscale; the service was stopped/disabled/masked where possible. Repair manually; setup will not overwrite or retry an existing installation."
                if mutated
                else "No Headscale package or configuration changes were made."
            )
            if cleanup_failed:
                recovery += " Automatic service cleanup failed; check and stop headscale manually."
            # Do not forward arbitrary exceptions, package logs or command
            # stdout into the caller's chat.
            message = (
                str(exc)
                if isinstance(exc, ProvisionError)
                else "Headscale setup failed"
            )
            raise ProvisionError(message, stage, recovery) from exc
        return {
            "installed": True,
            "version": VERSION,
            "grpc_addr": plan["grpc_addr"],
            "grpc_tls_server_name": plan["grpc_tls_server_name"],
            "control_url": plan["control_url"],
            "headscale_user": options["headscale_user"],
            "public_endpoint_verified": False,
        }


def _managed_installation() -> dict:
    _trusted_directory(CONFIG.parent)
    for path in (CONFIG, MARKER):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ProvisionError("Headscale setup files are not securely owned")
    try:
        marker = json.loads(MARKER.read_text())
    except (ValueError, OSError) as exc:
        raise ProvisionError("Cannot read the NetPlane installation record") from exc
    if marker.get("version") != VERSION or hashlib.sha256(
        CONFIG.read_bytes()
    ).hexdigest() != marker.get("config_sha256"):
        raise ProvisionError(
            "Headscale configuration differs from the NetPlane installation record"
        )
    return marker


def bootstrap_key(args: dict) -> dict:
    """Return a new secret only to the capturing Hermes wrapper, once."""
    if args != {}:
        raise ValueError("bootstrap-key accepts an empty object only")
    _require_root()
    with _lock():
        marker = _managed_installation()
        if (
            marker.get("api_key_prefix")
            or marker.get("bootstrap_state", "ready") != "ready"
        ):
            raise ProvisionError(
                "An API key was already bootstrapped for this installation"
            )
        # Record intent before minting. If the CLI outcome is unknown, retries
        # must not silently create more credentials.
        marker["bootstrap_state"] = "creating"
        _replace_owned(MARKER, _json(marker))
        try:
            result = _run(
                [
                    HEADSCALE,
                    "--config",
                    str(CONFIG),
                    "apikeys",
                    "create",
                    "--expiration",
                    "90d",
                    "--output",
                    "json",
                ]
            )
        except ProvisionError as exc:
            raise ProvisionError(
                "API key creation outcome is uncertain; inspect headscale apikeys list and expire any unintended bootstrap key before manual recovery",
                "bootstrap-key",
            ) from exc
        try:
            key = json.loads(result.stdout)
        except ValueError as exc:
            raise ProvisionError(
                "API key creation outcome is uncertain; inspect headscale apikeys list before manual recovery",
                "bootstrap-key",
            ) from exc
        if not isinstance(key, str) or not re.fullmatch(
            r"hskey-api-[A-Za-z0-9_-]{12}-[A-Za-z0-9_-]{64}", key
        ):
            raise ProvisionError(
                "API key creation outcome is uncertain; inspect headscale apikeys list before manual recovery",
                "bootstrap-key",
            )
        prefix = key[len("hskey-api-") : len("hskey-api-") + 12]
        marker["api_key_prefix"] = prefix
        marker["bootstrap_state"] = "created"
        try:
            _replace_owned(MARKER, _json(marker))
        except Exception as exc:
            _run(
                [
                    HEADSCALE,
                    "--config",
                    str(CONFIG),
                    "apikeys",
                    "expire",
                    "--prefix",
                    prefix,
                ],
                check=False,
            )
            raise ProvisionError(
                "Could not record the API key; expiration was attempted"
            ) from exc
        return {"key": key, "prefix": prefix}


def revoke_key(args: dict) -> dict:
    prefix = args.get("prefix") if isinstance(args, dict) else None
    if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
        raise ValueError("Invalid API key prefix")
    _require_root()
    with _lock():
        marker = _managed_installation()
        if marker.get("api_key_prefix") != prefix:
            raise ProvisionError(
                "API key prefix does not match this installation's bootstrap key"
            )
        _run(
            [
                HEADSCALE,
                "--config",
                str(CONFIG),
                "apikeys",
                "expire",
                "--prefix",
                prefix,
            ]
        )
        marker["api_key_prefix"] = "revoked:" + prefix
        marker["bootstrap_state"] = "revoked"
        _replace_owned(MARKER, _json(marker))
        return {"revoked": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action", choices=("install", "bootstrap-key", "revoke-key"), required=True
    )
    action = parser.parse_args().action

    def interrupted(_signum, _frame):
        raise ProvisionError("Headscale setup was interrupted", "interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        raw = sys.stdin.read(16385)
        if len(raw) > 16384:
            raise ValueError("Setup input is too large")
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ValueError("Setup input must be a JSON object")  # noqa: TRY004
        result = {
            "install": install,
            "bootstrap-key": bootstrap_key,
            "revoke-key": revoke_key,
        }[action](args)
        print(json.dumps(result))
        return 0
    except (ValueError, ProvisionError) as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "stage": getattr(exc, "stage", "validation"),
                    "recovery": getattr(exc, "recovery", ""),
                }
            )
        )
        return 1
    except Exception:  # noqa: BLE001 -- CLI boundary must not print secret-bearing exception details.
        print(json.dumps({"error": "Headscale setup helper failed", "stage": action}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
