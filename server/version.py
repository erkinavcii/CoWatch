"""The app's version: the one place it is written. tools/build_windows.ps1 reads it from this
line (the installer's name and version), the settings page and the tray menu show it, and
server/updates.py compares it with GitHub's latest release. A release tag (v0.3.0) must match it;
the release workflow checks that."""

VERSION = "0.2.0"
