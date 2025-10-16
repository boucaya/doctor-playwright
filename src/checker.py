"""Checker for doctor's available hours.

This module keeps a simple compatibility layer so tests can patch a
``driver`` object (selenium-like) or run a Playwright-based flow
when ``driver`` is not provided.

Usage examples:
  - For local debug (visible browser): python -m src.checker --doctor Alvarez
  - For headless runs: python -m src.checker --headless

Sensitive settings should be placed in a .env file or passed as env vars.
"""

import os
import time
import logging
import argparse
from dotenv import load_dotenv

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:  # Playwright may not be installed in test environment
    sync_playwright = None
    PlaywrightTimeoutError = Exception

import smtplib
from email.mime.text import MIMEText

# load .env if present
load_dotenv()

# Module-level driver (tests patch this)
driver = None

# Defaults (can be overridden via env or CLI)
URL = os.getenv("CHECKER_URL", "https://www.centromed.cl/reserva-de-horas/")
DOCTOR_LAST_NAME = os.getenv("DOCTOR_LAST_NAME", "Alvarez")
PREVISION_VALUE = os.getenv("PREVISION_VALUE", "FONASA")
EMAIL_FROM = os.getenv("EMAIL_FROM", "your_email@example.com")
EMAIL_TO = os.getenv("EMAIL_TO", EMAIL_FROM)
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.example.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
USER_AGENT = os.getenv("USER_AGENT", "doctor-playwright-bot/1.0 (+https://example.com)")

ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "./artifacts")
SLOT_SELECTOR_DEFAULT = os.getenv("SLOT_SELECTOR", "table.table tbody tr")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def send_notification(message):
    """Send a plain-text email notification.

    This function can be patched in tests.
    """
    msg = MIMEText(message)
    msg["Subject"] = f"Available Hours"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            if EMAIL_PASSWORD:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        logging.info("Notification sent to %s", EMAIL_TO)
    except Exception:
        logging.exception("Failed to send notification")


def _save_artifacts(page, prefix="error"):
    try:
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
        ts = int(time.time())
        screenshot_path = os.path.join(ARTIFACTS_DIR, f"{prefix}_screenshot_{ts}.png")
        html_path = os.path.join(ARTIFACTS_DIR, f"{prefix}_page_{ts}.html")
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            logging.exception("Failed to save screenshot")
        try:
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(page.content())
        except Exception:
            logging.exception("Failed to save page HTML")
        logging.info("Saved artifacts: %s, %s", screenshot_path, html_path)
    except Exception:
        logging.exception("Cannot create artifacts directory")


def _check_with_driver(selector=".available-hour", doctor=DOCTOR_LAST_NAME):
    """Path used by tests when a 'driver' object is provided (selenium-like).

    Returns the user-facing result string.
    """
    global driver
    # Allow tests to patch driver.find_elements
    elements = []
    try:
        elements = driver.find_elements(selector)
    except Exception:
        logging.exception("Error using patched driver")

    if elements:
        message = f"Available hours found: {len(elements)} slots."
        try:
            send_notification(message)
        except Exception:
            logging.exception("Error sending notification")
        return message
    else:
        return "No available hours."


def check_availability(headless=False, timeout=30000, prevision=PREVISION_VALUE, doctor=DOCTOR_LAST_NAME, selector=None, output_json=False, return_slots=False):
    """Check availability and return a human-friendly result string.

    Behavior:
      - If a module-level `driver` is set (tests), use it.
      - Otherwise try to use Playwright (if installed).

    The function updates its attribute `.send_notification` to point to the
    module-level `send_notification` function so tests that patch the
    function can assert calls via `check_availability.send_notification`.
    """
    # keep a live reference for tests that assert on the function attribute
    check_availability.send_notification = send_notification

    # If a driver (selenium-like) is provided, use it (tests patch this)
    if driver is not None:
        return _check_with_driver(doctor=doctor)

    # Fallback: use Playwright if available
    if sync_playwright is None:
        logging.error("No driver available and Playwright not installed. Exiting.")
        return "No available hours."

    logging.info("Running Playwright flow (headless=%s) for %s", headless, doctor)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page(user_agent=USER_AGENT)
            page.set_default_timeout(timeout)
            # navigation with retry
            nav_attempts = int(os.getenv("NAV_ATTEMPTS", "3"))
            for attempt in range(1, nav_attempts + 1):
                try:
                    page.goto(URL, wait_until="networkidle")
                    break
                except Exception as e:
                    logging.warning("Navigation attempt %s/%s failed: %s", attempt, nav_attempts, e)
                    if attempt == nav_attempts:
                        # ensure artifacts dir exists
                        try:
                            os.makedirs(ARTIFACTS_DIR, exist_ok=True)
                            ts = int(time.time())
                            screenshot_path = os.path.join(ARTIFACTS_DIR, f"screenshot_{ts}.png")
                            html_path = os.path.join(ARTIFACTS_DIR, f"page_{ts}.html")
                            try:
                                page.screenshot(path=screenshot_path, full_page=True)
                            except Exception:
                                logging.exception("Failed to save screenshot")
                            try:
                                with open(html_path, "w", encoding="utf-8") as fh:
                                    fh.write(page.content())
                            except Exception:
                                logging.exception("Failed to save page HTML")
                            logging.error("Saved artifacts to %s", ARTIFACTS_DIR)
                        except Exception:
                            logging.exception("Could not create artifacts directory")
                        raise

            # 1) Switch to "Búsqueda por médico" tab — prefer text-based selector
            try:
                # Try clicking by visible text first
                try:
                    page.get_by_text("Búsqueda por médico", exact=True).click()
                except Exception:
                    # fallback: click element with aria role 'tab' or id
                    try:
                        page.locator("#medico-tab").click()
                    except Exception:
                        logging.debug("Could not explicitly click medico tab by text or id; continuing")
            except Exception:
                logging.debug("medico tab handling failed")

            # 2) Select prevision option by label (e.g., FONASA)
            try:
                # prefer selecting by label; if select has id #prevision use it
                prevision_sel = "#prevision"
                try:
                    # try to find option with the provided label and get its value
                    opts = page.locator(f"{prevision_sel} option")
                    count = opts.count()
                    found_value = None
                    for i in range(count):
                        opt = opts.nth(i)
                        text = opt.inner_text().strip()
                        if text.lower() == prevision.lower():
                            found_value = opt.get_attribute("value")
                            break
                    if found_value:
                        page.select_option(prevision_sel, value=found_value)
                    else:
                        # fallback: try select_option by label directly
                        try:
                            page.select_option(prevision_sel, label=prevision)
                        except Exception:
                            logging.debug("Could not select prevision by label/value")
                except Exception:
                    logging.debug("Prevision select not found via #prevision")
            except Exception:
                logging.debug("prevision handling failed")

            # 3) Fill Apellido Médico field
            try:
                # try common selectors / placeholder text
                apellido_locator = None
                try:
                    apellido_locator = page.get_by_placeholder("Ingresar Apellido")
                    apellido_locator.fill(doctor)
                except Exception:
                    try:
                        apellido_locator = page.locator("#apellido")
                        apellido_locator.fill(doctor)
                    except Exception:
                        # try by label
                        try:
                            apellido_locator = page.get_by_label("Apellido Médico")
                            apellido_locator.fill(doctor)
                        except Exception:
                            logging.debug("Could not fill apellido via placeholder, id, or label")
            except Exception:
                logging.debug("apellido field handling failed")

            # 4) Click "Buscar horas" button
            try:
                try:
                    page.get_by_text("Buscar horas", exact=True).click()
                except Exception:
                    # fallback to button role
                    try:
                        page.get_by_role("button", name="Buscar horas").click()
                    except Exception:
                        logging.debug("Could not click Buscar horas by text or role")
            except Exception:
                logging.debug("buscar horas click failed")

            # If we filled the apellido_locator, try pressing Enter on it to submit
            try:
                if 'apellido_locator' in locals() and apellido_locator is not None:
                    try:
                        apellido_locator.press("Enter")
                    except Exception:
                        logging.debug("Could not press Enter on apellido locator; continuing")
            except Exception:
                logging.debug("press Enter handling failed")

            if not headless:
                logging.info("Running non-headless: pause to allow CAPTCHA solve if needed")
                input("Solve the CAPTCHA (if any) then press Enter to continue...")
            else:
                logging.info("Headless mode: if page requires CAPTCHA the automation may fail")

            # submit
            try:
                page.click("button[data-callback='onSubmitDoctor']")
            except Exception:
                logging.debug("Submit button click failed, attempting Enter key on #apellido")
                try:
                    page.press("#apellido", "Enter")
                except Exception:
                    logging.exception("Could not submit form")
                    try:
                        _save_artifacts(page, prefix="submit_failure")
                    except Exception:
                        logging.exception("Failed saving artifacts on submit failure")

            time.sleep(1)

            # determine selector (CLI arg > ENV > default)
            sel = selector or SLOT_SELECTOR_DEFAULT

            # wait for container or selector if possible
            try:
                page.wait_for_selector(sel, timeout=5000)
            except Exception:
                logging.debug("Selector %s not present after wait; proceeding to query", sel)

            slots = []
            try:
                elements = page.query_selector_all(sel)
                for el in elements:
                    try:
                        # If this is a table row, extract tds
                        tds = el.query_selector_all("td")
                        if tds and len(tds) >= 4:
                            doctor_text = tds[0].inner_text().strip()
                            hora_text = tds[3].inner_text().strip()
                            # try to find a form and hidden inputs
                            form = el.query_selector("form")
                            data = {"doctor": doctor_text, "hora": hora_text}
                            if form:
                                try:
                                    inputs = form.query_selector_all("input[type=hidden]")
                                    for inp in inputs:
                                        name = inp.get_attribute("name")
                                        value = inp.get_attribute("value")
                                        if name:
                                            data[name] = value
                                except Exception:
                                    logging.debug("Could not read hidden inputs from form")
                            slots.append(data)
                            continue
                        # fallback: treat as generic element
                        try:
                            text = el.inner_text().strip()
                        except Exception:
                            text = ""
                        href = None
                        try:
                            link = el.query_selector("a")
                            if link:
                                href = link.get_attribute("href")
                        except Exception:
                            href = None
                        slots.append({"text": text, "href": href})
                    except Exception:
                        logging.debug("Error extracting data for one slot element")
            except Exception:
                logging.exception("Error querying slots with selector %s", sel)
                try:
                    _save_artifacts(page, prefix="slots_query_failure")
                except Exception:
                    logging.exception("Failed saving artifacts on slots query failure")

            if slots:
                message = f"Available hours found: {len(slots)} slots."
                # write JSON if requested
                if output_json:
                    try:
                        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
                        ts = int(time.time())
                        out_path = os.path.join(ARTIFACTS_DIR, f"slots_{ts}.json")
                        import json

                        with open(out_path, "w", encoding="utf-8") as fh:
                            json.dump({"doctor": doctor, "slots": slots, "url": URL}, fh, ensure_ascii=False, indent=2)
                        logging.info("Saved slots JSON to %s", out_path)
                    except Exception:
                        logging.exception("Failed to write slots JSON")

                # If a target doctor is requested via env or CLI, try to find their next slot
                target_doctor = os.getenv("TARGET_DOCTOR")
                # the function caller may override via passing doctor param; keep a separate target
                if target_doctor:
                    try:
                        # default max days
                        max_days = int(os.getenv("MAX_DAYS", "30"))
                        next_slot = find_next_slot(slots, target_doctor, max_days)
                        if next_slot:
                            message = f"Next slot for {target_doctor} within {max_days} days: {next_slot.get('hora')}"
                            send_notification(message)
                    except Exception:
                        logging.exception("Error while checking target doctor next slot")

                try:
                    send_notification(message)
                except Exception:
                    logging.exception("Failed to send notification")
                browser.close()
                if return_slots:
                    return message, slots
                return message
            else:
                browser.close()
                if return_slots:
                    return "No available hours.", []
                return "No available hours."
    except Exception:
        logging.exception("Unhandled error in Playwright flow")
        return "No available hours."


def _parse_slot_datetime(hora_str):
    # expects 'dd/mm/YYYY HH:MM'
    try:
        from datetime import datetime
        return datetime.strptime(hora_str, "%d/%m/%Y %H:%M")
    except Exception:
        return None


def find_next_slot(slots, target_doctor, max_days=30):
    """Return the nearest slot for target_doctor within max_days, or None."""
    from datetime import datetime, timedelta
    now = datetime.now()
    cutoff = now + timedelta(days=max_days)
    candidates = []
    td_lower = target_doctor.lower()
    for s in slots:
        doc = s.get("doctor", "").lower()
        if td_lower in doc:
            hora = s.get("HORA") or s.get("hora") or s.get("PROXIMA") or s.get("PROXIMA")
            dt = None
            if hora:
                dt = _parse_slot_datetime(hora)
            if dt and now < dt <= cutoff:
                candidates.append((dt, s))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check doctor availability")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--doctor", default=DOCTOR_LAST_NAME, help="Doctor last name")
    parser.add_argument("--prevision", default=PREVISION_VALUE, help="Prevision value to select")
    parser.add_argument("--selector", default=None, help="CSS selector for available slots (overrides SLOT_SELECTOR env)")
    parser.add_argument("--output-json", action="store_true", help="Save found slots to JSON in ARTIFACTS_DIR")
    parser.add_argument("--target-doctor", default=None, help="Only notify if this doctor's next slot is within max-days")
    parser.add_argument("--max-days", type=int, default=None, help="Max days ahead to consider for target doctor")
    args = parser.parse_args()

    # export target doctor / max days to env so the core logic can read them
    if args.target_doctor:
        os.environ["TARGET_DOCTOR"] = args.target_doctor
    if args.max_days is not None:
        os.environ["MAX_DAYS"] = str(args.max_days)
    parser.add_argument("--monitor", action="store_true", help="Run in monitor mode and check periodically")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Interval between checks when monitoring")
    parser.add_argument("--state-file", default=os.path.join(ARTIFACTS_DIR, "state.json"), help="Path to state file for last-known slots")
    args = parser.parse_args()

    # export target doctor / max days to env so the core logic can read them
    if args.target_doctor:
        os.environ["TARGET_DOCTOR"] = args.target_doctor
    if args.max_days is not None:
        os.environ["MAX_DAYS"] = str(args.max_days)

    def load_state(path):
        try:
            if os.path.exists(path):
                import json

                with open(path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            logging.exception("Failed to load state file")
        return {}

    def save_state(path, data):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            import json

            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            logging.exception("Failed to save state file")

    if args.monitor:
        # require target doctor for monitor mode
        target = args.target_doctor or os.getenv("TARGET_DOCTOR")
        if not target:
            print("Error: monitor mode requires --target-doctor or TARGET_DOCTOR set in env")
            exit(2)

        state = load_state(args.state_file)
        logging.info("Starting monitor mode (interval=%ss) - statefile=%s", args.interval_seconds, args.state_file)
        try:
            while True:
                # get slots and prefer returning slots for local comparison
                res, slots = check_availability(headless=args.headless, prevision=args.prevision, doctor=args.doctor, selector=args.selector, output_json=args.output_json, return_slots=True)

                target = args.target_doctor or os.getenv("TARGET_DOCTOR")
                if target:
                    next_slot = find_next_slot(slots, target, int(os.getenv("MAX_DAYS", "30")))
                    if next_slot:
                        saved = state.get(target)
                        # compare saved hora string
                        saved_dt = None
                        prev_hora = None
                        if saved:
                            prev_hora = saved.get("hora")
                            saved_dt = _parse_slot_datetime(prev_hora) if prev_hora else None
                        new_dt = _parse_slot_datetime(next_slot.get("HORA") or next_slot.get("hora") or next_slot.get("PROXIMA"))
                        if new_dt and (not saved_dt or new_dt < saved_dt):
                            # newer (closer) slot found
                            msg = f"Slot freed for {target}: {next_slot.get('HORA') or next_slot.get('hora')}. Previously: {prev_hora}"
                            send_notification(msg)
                            # update state
                            state[target] = {"hora": next_slot.get("HORA") or next_slot.get("hora"), "raw": next_slot}
                            save_state(args.state_file, state)
                        else:
                            logging.info("No nearer slot for %s (found %s, saved %s)", target, new_dt, saved_dt)
                else:
                    logging.info("Monitor run completed, no TARGET_DOCTOR set")

                time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            logging.info("Monitor stopped by user")
        except Exception:
            logging.exception("Monitor loop failed")
        exit(0)

    result = check_availability(
        headless=args.headless,
        prevision=args.prevision,
        doctor=args.doctor,
        selector=args.selector,
        output_json=args.output_json,
    )
    print(result)