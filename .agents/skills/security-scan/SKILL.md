---
name: security-scan
description: >-
  Run a security vulnerability scan on the project's Python packages using pysentry-rs.
  Use when the user asks to scan dependencies or audit Python packages for security vulnerabilities.
---

# Python Package Security Scan

Run a security scan of the project's Python dependencies using `pysentry-rs` via `uv`:

```bash
uv tool run pysentry-rs
```
