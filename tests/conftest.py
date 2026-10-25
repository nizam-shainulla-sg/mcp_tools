"""Shared pytest setup: import path, and a coverage table inside report.html."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _coverage_rows(config):
    """Per-file coverage from the live pytest-cov run, or [] if cov is off."""
    plugin = config.pluginmanager.getplugin("_cov")
    cov = getattr(getattr(plugin, "cov_controller", None), "cov", None)
    if cov is None:
        return []
    rows = []
    for path in sorted(cov.get_data().measured_files()):
        _, statements, _, missing, _ = cov.analysis2(path)
        pct = 100.0 if not statements else 100.0 * (len(statements) - len(missing)) / len(statements)
        rows.append((os.path.basename(path), len(statements), len(missing), pct))
    return rows


def pytest_html_results_summary(prefix, summary, postfix, session):
    rows = _coverage_rows(session.config)
    if not rows:
        return
    total_s = sum(r[1] for r in rows)
    total_m = sum(r[2] for r in rows)
    total = 100.0 if not total_s else 100.0 * (total_s - total_m) / total_s
    body = "".join(
        f"<tr><td>{n}</td><td>{s}</td><td>{m}</td><td>{p:.1f}%</td></tr>" for n, s, m, p in rows
    )
    summary.append(
        "<h2>Coverage</h2>"
        "<table><thead><tr><th>File</th><th>Statements</th><th>Missed</th><th>Cover</th></tr></thead>"
        f"<tbody>{body}<tr><td><b>Total</b></td><td>{total_s}</td><td>{total_m}</td>"
        f"<td><b>{total:.1f}%</b></td></tr></tbody></table>"
    )
