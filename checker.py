#!/usr/bin/env python3
"""
Check the status of a Registro Civil expedition and detect changes.

Usage:
  python checker.py            # compare current state with snapshot
                               # exits 0 = UNCHANGED, 1 = CHANGED
  python checker.py --generate # save current state as new snapshot (baseline)

The div #tablaResultadoExpedientes is extracted after form submission, its HTML is normalised
(whitespace collapsed), and compared against /data/snapshot.html.
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from homeassistant import HomeAssistant

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

URL = "https://sede.mjusticia.gob.es/sereci/initComoVaLoMio"
SNAPSHOT_PATH = Path("/data/snapshot.html")
CURRENT_SNAPSHOT_PATH = Path("/data/current_snapshot.html")

# Personal data — loaded from environment variables (never hardcode in source)
NUM_IDENTIFICACION = os.environ["NUM_IDENTIFICACION"]
NOMBRE = os.environ["NOMBRE"]
APELLIDO1 = os.environ["APELLIDO1"]
APELLIDO2 = os.environ.get("APELLIDO2", "")
NUM_EXPEDIENTE = os.environ["NUM_EXPEDIENTE"]

# ARM64 / low-memory Chromium launch flags (Pi Zero 2 W has 512 MB RAM)
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--hide-scrollbars",
    "--mute-audio",
    "--no-first-run",
    "--safebrowsing-disable-auto-update",
    "--disable-features=TranslateUI",
    "--metrics-recording-only",
]

# ── Helpers ────────────────────────────────────────────────────────────────────


def normalise(text: str) -> str:
    """Collapse all whitespace so cosmetic page changes don't trigger a diff."""
    return re.sub(r"\s+", " ", text).strip()


# ── Core scraper ───────────────────────────────────────────────────────────────


def fetch_contenido() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        page = browser.new_page()
        try:
            log.info("Navigating to %s", URL)
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

            # debug
            log.info("Data to fill: NUM_IDENTIFICACION=%s, NOMBRE=%s, APELLIDO1=%s, APELLIDO2=%s, NUM_EXPEDIENTE=%s",
                     NUM_IDENTIFICACION, NOMBRE, APELLIDO1, APELLIDO2, NUM_EXPEDIENTE)

            # ── Fill Datos Solicitante fields ──────────────────────────────
            page.locator("select[name='serPersonaVO.tipoIdentificador']").select_option(value="2")
            page.locator("input[name='serPersonaVO.numIdentificacion']").fill(NUM_IDENTIFICACION)
            page.locator("input[name='serPersonaVO.nombre']").fill(NOMBRE)
            page.locator("input[name='serPersonaVO.apellido1']").fill(APELLIDO1)
            page.locator("input[name='serPersonaVO.apellido2']").fill(APELLIDO2)

            # ── Fill Buscar Expediente fields ──────────────────────────────
            # situacionExpediente = A (Activos)
            page.check(
                "input[name='buscarExpedienteVO.situacionExpediente'][value='A']"
            )

            # tipoInteresadoExpediente = 1 (may be a hidden/select field)
            try:
                page.select_option(
                    "select[name='buscarExpedienteVO.tipoInteresadoExpediente']",
                    value="1",
                    timeout=3_000,
                )
            except PlaywrightTimeoutError:
                pass  # Field may not be visible or may already default to 1

            page.fill(
                "input[name='buscarExpedienteVO.numExpediente']",
                NUM_EXPEDIENTE,
            )

            # ── Submit ─────────────────────────────────────────────────────
            log.info("Submitting form…")
            page.click("#formComoVaLoMio_buscar")

            # Wait for the page to settle — covers both full navigation and AJAX
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except PlaywrightTimeoutError:
                log.warning("networkidle timeout — proceeding anyway")

            # ── Extract result ─────────────────────────────────────────────
            page.wait_for_selector("#tablaResultadoExpedientes", state="visible", timeout=30_000)
            content = page.locator("#tablaResultadoExpedientes").evaluate("el => el.outerHTML")
            log.info("Extracted %d chars from #tablaResultadoExpedientes", len(content))
            return normalise(content)

        finally:
            browser.close()


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:

    ha = HomeAssistant(token=os.getenv("HA_TOKEN") or "")

    parser = argparse.ArgumentParser(
        description="Check Registro Civil expedition status for changes."
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Save the current page content as the reference snapshot and exit.",
    )
    args = parser.parse_args()

    current = fetch_contenido()

    if args.generate or not SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(current, encoding="utf-8")
        log.info("Snapshot saved to %s", SNAPSHOT_PATH)
        sys.exit(0)

    previous = SNAPSHOT_PATH.read_text(encoding="utf-8")
    
    CURRENT_SNAPSHOT_PATH.write_text(current, encoding="utf-8")  # Save current snapshot for review regardless of change
    current = CURRENT_SNAPSHOT_PATH.read_text(encoding="utf-8")  # Read back to ensure consistency
    
    # Normalize again to ensure any formatting differences from saving/loading don't affect the comparison
    current = normalise(current)
    previous = normalise(previous)
    
    if current != previous:
        print("CHANGED")
        log.info("Status has CHANGED since last snapshot.")
        ha.send_notification(
            title="Cambios en Registro Civil",
            message="El estado de su expediente del Registro Civil ha cambiado desde la última verificación.",
        )
        sys.exit(1)
    else:
        print("UNCHANGED")
        log.info("Status is UNCHANGED.")
        ha.send_notification(
            title="Sin cambios en Registro Civil",
            message="El estado de su expediente del Registro Civil no ha cambiado desde la última verificación.",
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
