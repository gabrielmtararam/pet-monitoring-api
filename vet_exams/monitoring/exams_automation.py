import os
import random
import re
import shutil
import time
from datetime import datetime
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.utils import timezone as tz
from django.utils.text import get_valid_filename
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from vet_exams.animals.models import Animal
from vet_exams.monitoring.models import AnimalExam, Receita

LOGIN_URL = os.environ.get('SIMPLESPET_LOGIN_URL', 'https://meu.simplespet.com.br/access/login')

USERNAME_SELECTOR = '#access > div > div.m-b-lg > form > div.list-group.list-group-sm > div:nth-child(1) > input'
PASSWORD_SELECTOR = '#access > div > div.m-b-lg > form > div.list-group.list-group-sm > div:nth-child(2) > input'
SUBMIT_SELECTOR = '#access > div > div.m-b-lg > form > button'
DOMVET_SELECTOR = '#app > div.app-content.ng-scope > div.app-content-body.fade-in-up.ng-scope > div > div:nth-child(1) > div.wrapper-md.ng-scope > div:nth-child(2) > a:nth-child(1)'
ANIMAL_NAME_SELECTOR = '#app .app-content-body .h2.ng-binding'


def _build_chrome_driver() -> webdriver.Chrome:
    options = Options()
    # Headless mode for compatibility.
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--remote-debugging-port=9222')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')

    chrome_binary = os.environ.get('CHROME_BINARY')
    if not chrome_binary:
        chrome_binary = (
            shutil.which('chromium')
            or shutil.which('chromium-browser')
            or shutil.which('google-chrome')
            or shutil.which('google-chrome-stable')
        )

    if chrome_binary:
        options.binary_location = chrome_binary

    driver_path = os.environ.get('CHROMEDRIVER_PATH') or shutil.which('chromedriver')
    if driver_path:
        service = Service(
            driver_path,
            log_output=os.environ.get('CHROMEDRIVER_LOG', '/tmp/chromedriver.log'),
            service_args=['--verbose'],
        )
    else:
        service = Service(
            ChromeDriverManager().install(),
            log_output=os.environ.get('CHROMEDRIVER_LOG', '/tmp/chromedriver.log'),
            service_args=['--verbose'],
        )

    return webdriver.Chrome(service=service, options=options)


def perform_login(driver: webdriver.Chrome, username: str, password: str) -> bool:
    wait = WebDriverWait(driver, 20)

    driver.get(LOGIN_URL)

    username_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, USERNAME_SELECTOR)))
    username_input.clear()
    username_input.send_keys(username)

    password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, PASSWORD_SELECTOR)))
    password_input.clear()
    password_input.send_keys(password)

    submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SUBMIT_SELECTOR)))
    submit_btn.click()

    try:
        domvet_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, DOMVET_SELECTOR)),
        )
        domvet_btn.click()
    except TimeoutException:
        # Login may still be valid even if DomVet button is not present.
        pass

    return True


# Date pattern from SimplesPet panel (e.g. "20/02/2026", "01/03/2026")
_SOURCE_DATE_RE = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')


def _get_panel_from_anchor(anchor):
    """Return the parent evento panel div for an anchor that links to a PDF."""
    return anchor.find_element(
        By.XPATH,
        "./ancestor::div[contains(@class,'panel') and .//div[contains(@class,'panel-heading')]][1]",
    )


def _get_exam_type_label_from_anchor(anchor) -> str | None:
    """
    From an anchor that links to a PDF, find the parent evento panel and return
    the text of the h4 (tipo de exame), e.g. "Ultrassonografia", "Hemograma + Bioquímico".
    """
    try:
        panel = _get_panel_from_anchor(anchor)
        h4 = panel.find_element(
            By.XPATH,
            ".//div[contains(@class,'panel-heading')]//div[contains(@class,'h4')]",
        )
        text = (h4.text or '').strip()
        for suffix in ('(ver resultado)', '(ver receita)'):
            if suffix in text:
                text = text.replace(suffix, '').strip()
        return text[:200] if text else None
    except Exception:
        return None


def _get_exam_date_from_anchor(anchor) -> datetime | None:
    """
    From an anchor that links to a PDF, find the parent evento panel and return
    the date shown in the panel (e.g. "20/02/2026") as a naive datetime at midnight.
    """
    try:
        panel = _get_panel_from_anchor(anchor)
        text = (panel.text or '') + ' '
        match = _SOURCE_DATE_RE.search(text)
        if not match:
            return None
        day, month, year = match.group(1).split('/')
        return datetime(int(year), int(month), int(day), 0, 0, 0)
    except Exception:
        return None


def _extract_file_links_from_dom(driver: webdriver.Chrome) -> list[tuple[str, str | None, datetime | None]]:
    """
    Extract from DOM: for each anchor with Reader.png icon, the file URL, the exam
    type label and the event date from the same evento panel.
    Returns list of (url, label, source_observed_at).
    """
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (By.XPATH, "//img[contains(translate(@src,'READER.PNG','reader.png'),'reader.png')]"),
            ),
        )
    except TimeoutException:
        return []

    anchors = driver.find_elements(
        By.XPATH,
        "//a[descendant::img[contains(translate(@src,'READER.PNG','reader.png'),'reader.png')]]",
    )

    result = []
    seen = set()
    for anchor in anchors:
        href = (anchor.get_attribute('href') or '').strip()
        if not href or href in seen:
            continue
        seen.add(href)
        label = _get_exam_type_label_from_anchor(anchor)
        source_date = _get_exam_date_from_anchor(anchor)
        result.append((href, label, source_date))

    return result


def _extract_file_name(file_url: str) -> str | None:
    parsed = urlparse(file_url)
    path = parsed.path or ''
    if not path:
        return None

    name = path.rsplit('/', 1)[-1]
    return name or None


def _download_file_content(file_url: str) -> bytes | None:
    try:
        request = Request(
            file_url,
            headers={
                'User-Agent': 'Mozilla/5.0',
            },
        )
        with urlopen(request, timeout=40) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, Exception):
        return None


def _attach_file_to_exam(exam: AnimalExam, file_url: str, file_name: str) -> bool:
    file_bytes = _download_file_content(file_url)
    if not file_bytes:
        return False

    safe_name = get_valid_filename(file_name)
    exam.file.save(safe_name, ContentFile(file_bytes), save=False)
    exam.source_url = file_url
    exam.save(update_fields=['file', 'source_url'])
    return True


def _resolve_animal_for_user(user, driver: webdriver.Chrome):
    try:
        animal_name = driver.find_element(By.CSS_SELECTOR, ANIMAL_NAME_SELECTOR).text.strip()
    except Exception:
        animal_name = None

    if animal_name:
        animal = Animal.objects.filter(guardian=user, name=animal_name).first()
        if animal:
            return animal, animal_name

    fallback = Animal.objects.filter(guardian=user).first()
    return fallback, animal_name


def _save_exam_records(
    user, driver: webdriver.Chrome, file_links: list[tuple[str, str | None, datetime | None]]
) -> tuple[int, int, str | None, int, int]:
    animal, detected_animal_name = _resolve_animal_for_user(user, driver)
    if not animal:
        return 0, 0, detected_animal_name, 0, 0

    created_count = 0
    downloaded_count = 0
    failed_downloads = 0
    for link, exam_type_label, source_date in file_links:
        file_name = _extract_file_name(link)
        if not file_name:
            continue

        source_dt = None
        if source_date:
            source_dt = tz.make_aware(source_date) if tz.is_naive(source_date) else source_date

        exam, created = AnimalExam.objects.get_or_create(
            file_name=file_name,
            defaults={
                'animal': animal,
                'source_url': link,
                'source_exam_type_label': (exam_type_label or '').strip() or None,
                'source_observed_at': source_dt,
            },
        )
        if not created:
            updates = {}
            if (exam_type_label or '').strip():
                updates['source_exam_type_label'] = (exam_type_label or '').strip()[:200] or None
            if source_dt is not None:
                updates['source_observed_at'] = source_dt
            if updates:
                for k, v in updates.items():
                    setattr(exam, k, v)
                exam.save(update_fields=list(updates.keys()))
        if created:
            created_count += 1
            time.sleep(random.uniform(1, 3))
            if _attach_file_to_exam(exam, link, file_name):
                downloaded_count += 1
            else:
                failed_downloads += 1

    return created_count, len(file_links), detected_animal_name, downloaded_count, failed_downloads


def _extract_receita_id_from_url(url: str) -> str | None:
    """Extract unique identifier from receita URL (e.g. last path segment: 590193215)."""
    parsed = urlparse(url)
    path = (parsed.path or '').strip().rstrip('/')
    if not path:
        return None
    return path.rsplit('/', 1)[-1] or None


def _get_receita_date_from_anchor(anchor) -> datetime | None:
    """From a receita link anchor, find the parent evento panel and return the date (DD/MM/YYYY)."""
    try:
        panel = anchor.find_element(
            By.XPATH,
            "./ancestor::div[contains(@class,'panel') and .//div[contains(@class,'panel-heading')]][1]",
        )
        text = (panel.text or '') + ' '
        match = _SOURCE_DATE_RE.search(text)
        if not match:
            return None
        day, month, year = match.group(1).split('/')
        return datetime(int(year), int(month), int(day), 0, 0, 0)
    except Exception:
        return None


def _extract_receita_links_from_dom(driver: webdriver.Chrome) -> list[tuple[str, datetime | None]]:
    """
    Extract receita links from the page: anchors whose href contains 'receitas',
    excluding links inside an element with class 'ng-hide' (those are empty/hidden).
    Returns list of (url, data).
    """
    xpath_visible = (
        "//a[contains(@href, 'receitas') and not(ancestor::*[contains(@class, 'ng-hide')])]"
    )
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.XPATH, xpath_visible)),
        )
    except TimeoutException:
        return []

    anchors = driver.find_elements(By.XPATH, xpath_visible)
    result = []
    seen = set()
    for anchor in anchors:
        href = (anchor.get_attribute('href') or '').strip()
        if not href or href in seen:
            continue
        seen.add(href)
        source_date = _get_receita_date_from_anchor(anchor)
        result.append((href, source_date))

    return result


def _attach_file_to_receita(receita: Receita, file_url: str, file_name: str) -> bool:
    file_bytes = _download_file_content(file_url)
    if not file_bytes:
        return False
    safe_name = get_valid_filename(file_name)
    receita.file.save(safe_name, ContentFile(file_bytes), save=False)
    receita.source_url = file_url
    receita.save(update_fields=['file', 'source_url'])
    return True


def _save_receita_records(
    user, driver: webdriver.Chrome, receita_links: list[tuple[str, datetime | None]]
) -> tuple[int, int, str | None, int, int]:
    animal, detected_animal_name = _resolve_animal_for_user(user, driver)
    if not animal:
        return 0, 0, detected_animal_name, 0, 0

    created_count = 0
    downloaded_count = 0
    failed_downloads = 0
    for link, source_date in receita_links:
        source_id = _extract_receita_id_from_url(link)
        if not source_id:
            continue

        data_date = None
        if source_date:
            data_date = source_date.date()

        receita, created = Receita.objects.get_or_create(
            source_identifier=source_id,
            defaults={
                'animal': animal,
                'data': data_date or tz.now().date(),
                'source_url': link,
            },
        )
        if not created:
            updates = {}
            if data_date is not None:
                updates['data'] = data_date
            if (link or '').strip():
                updates['source_url'] = link
            if updates:
                for k, v in updates.items():
                    setattr(receita, k, v)
                receita.save(update_fields=list(updates.keys()))
        if created:
            created_count += 1
            time.sleep(random.uniform(1, 3))
            file_name = _extract_file_name(link) or f"{source_id}.pdf"
            if _attach_file_to_receita(receita, link, file_name):
                downloaded_count += 1
            else:
                failed_downloads += 1

    return created_count, len(receita_links), detected_animal_name, downloaded_count, failed_downloads


def run_login_automation_receitas(user) -> dict:
    """Login to SimplesPet, extract receita links from the animal page, save Receita records and download files."""
    username = os.environ.get('SIMPLESPET_LOGIN') or os.environ.get('LOGIN')
    password = os.environ.get('SIMPLESPET_PASSWORD') or os.environ.get('SENHA')

    if not username or not password:
        return {
            'success': False,
            'detail': 'Missing SIMPLESPET_LOGIN/SIMPLESPET_PASSWORD environment variables.',
        }

    driver = None
    try:
        driver = _build_chrome_driver()
        perform_login(driver, username, password)
        receita_links = _extract_receita_links_from_dom(driver)
        created_count, total_found, detected_animal_name, downloaded_count, failed_downloads = _save_receita_records(
            user, driver, receita_links
        )
        return {
            'success': True,
            'detail': 'Atualização de medicações executada com sucesso.',
            'file_links': [url for url, _ in receita_links],
            'total_found': total_found,
            'created': created_count,
            'downloaded': downloaded_count,
            'failed_downloads': failed_downloads,
            'detected_animal_name': detected_animal_name,
        }
    except Exception as exc:
        return {
            'success': False,
            'detail': f'Falha na automação de medicações: {exc}',
        }
    finally:
        if driver is not None:
            driver.quit()


def run_login_automation(user) -> dict:
    username = os.environ.get('SIMPLESPET_LOGIN') or os.environ.get('LOGIN')
    password = os.environ.get('SIMPLESPET_PASSWORD') or os.environ.get('SENHA')

    if not username or not password:
        return {
            'success': False,
            'detail': 'Missing SIMPLESPET_LOGIN/SIMPLESPET_PASSWORD environment variables.',
        }

    driver = None
    try:
        driver = _build_chrome_driver()
        perform_login(driver, username, password)
        file_links = _extract_file_links_from_dom(driver)
        created_count, total_found, detected_animal_name, downloaded_count, failed_downloads = _save_exam_records(user, driver, file_links)

        return {
            'success': True,
            'detail': 'Login automation executed successfully.',
            'file_links': [url for url, _, _ in file_links],  # list of URLs for backward compatibility
            'total_found': total_found,
            'created': created_count,
            'downloaded': downloaded_count,
            'failed_downloads': failed_downloads,
            'detected_animal_name': detected_animal_name,
        }
    except Exception as exc:
        return {
            'success': False,
            'detail': f'Login automation failed: {exc}',
        }
    finally:
        if driver is not None:
            driver.quit()

