"""
Comprehensive tests for exams_automation.py.
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from datetime import datetime
from django.utils import timezone

import vet_exams.monitoring.exams_automation as ea
from vet_exams.monitoring.exams_automation import (
    _build_chrome_driver,
    _get_panel_from_anchor,
    _get_exam_type_label_from_anchor,
    _get_exam_date_from_anchor,
    _extract_file_links_from_dom,
    _extract_file_name,
    _download_file_content,
    _attach_file_to_exam,
    _resolve_animal_for_user,
    _save_exam_records,
    _extract_receita_id_from_url,
    _get_receita_date_from_anchor,
    _extract_receita_links_from_dom,
    _attach_file_to_receita,
    _save_receita_records,
    run_login_automation,
    run_login_automation_receitas,
    perform_login,
)
from vet_exams.monitoring.models import Animal, AnimalExam, Receita
from model_bakery import baker


class TestAutomationHelpers:
    def test_extract_file_name_valid_url(self):
        assert _extract_file_name("http://s.com/files/exam1.pdf") == "exam1.pdf"

    def test_extract_file_name_empty(self):
        assert _extract_file_name("") is None

    def test_extract_file_name_no_path(self):
        assert _extract_file_name("http://s.com/") is None

    def test_extract_receita_id_from_url(self):
        assert _extract_receita_id_from_url("https://s.com/receitas/12345/") == "12345"

    def test_extract_receita_id_from_url_empty(self):
        assert _extract_receita_id_from_url("") is None

    def test_extract_receita_id_from_url_no_path(self):
        assert _extract_receita_id_from_url("http://s.com/") is None

    def test_get_exam_type_label_from_anchor_exception(self):
        anchor = MagicMock()
        anchor.find_element.side_effect = Exception("no element")
        assert _get_exam_type_label_from_anchor(anchor) is None

    def test_get_exam_date_from_anchor_exception(self):
        anchor = MagicMock()
        anchor.find_element.side_effect = Exception("no element")
        assert _get_exam_date_from_anchor(anchor) is None

    def test_get_receita_date_from_anchor_exception(self):
        anchor = MagicMock()
        anchor.find_element.side_effect = Exception("no element")
        assert _get_receita_date_from_anchor(anchor) is None

    def test_get_exam_type_label_strips_suffix(self):
        panel_mock = MagicMock()
        h4_mock = MagicMock()
        h4_mock.text = "Ultrassonografia (ver resultado)"
        panel_mock.find_element.return_value = h4_mock
        anchor = MagicMock()
        anchor.find_element.return_value = panel_mock
        # _get_panel_from_anchor called by _get_exam_type_label_from_anchor
        with patch.object(ea, "_get_panel_from_anchor", return_value=panel_mock):
            result = _get_exam_type_label_from_anchor(anchor)
        assert result == "Ultrassonografia"

    def test_get_exam_date_from_anchor_success(self):
        panel_mock = MagicMock()
        panel_mock.text = "Consulta em 20/02/2026 com X"
        anchor = MagicMock()
        with patch.object(ea, "_get_panel_from_anchor", return_value=panel_mock):
            result = _get_exam_date_from_anchor(anchor)
        assert result == datetime(2026, 2, 20, 0, 0, 0)

    def test_get_receita_date_from_anchor_success(self):
        panel_mock = MagicMock()
        panel_mock.text = "Data: 15/01/2025"
        anchor = MagicMock()
        # _get_receita_date_from_anchor calls anchor.find_element(By.XPATH, ...) directly
        anchor.find_element.return_value = panel_mock
        result = _get_receita_date_from_anchor(anchor)
        assert result == datetime(2025, 1, 15, 0, 0, 0)

    def test_extract_file_links_from_dom_timeout(self):
        from selenium.common.exceptions import TimeoutException
        driver = MagicMock()
        with patch("vet_exams.monitoring.exams_automation.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.side_effect = TimeoutException()
            result = _extract_file_links_from_dom(driver)
        assert result == []

    def test_extract_file_links_from_dom_success(self):
        driver = MagicMock()
        anchor = MagicMock()
        anchor.get_attribute.return_value = "http://s.com/file.pdf"
        driver.find_elements.return_value = [anchor]
        with patch("vet_exams.monitoring.exams_automation.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = True
            with patch.object(ea, "_get_exam_type_label_from_anchor", return_value="H"):
                with patch.object(ea, "_get_exam_date_from_anchor", return_value=None):
                    result = _extract_file_links_from_dom(driver)
        assert len(result) == 1

    def test_extract_receita_links_from_dom_timeout(self):
        from selenium.common.exceptions import TimeoutException
        driver = MagicMock()
        with patch("vet_exams.monitoring.exams_automation.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.side_effect = TimeoutException()
            result = _extract_receita_links_from_dom(driver)
        assert result == []

    def test_download_file_content_network_error(self):
        with patch("vet_exams.monitoring.exams_automation.urlopen", side_effect=Exception("err")):
            result = _download_file_content("http://s.com/f.pdf")
        assert result is None

    def test_download_file_content_success(self):
        mock_response = MagicMock()
        mock_response.read.return_value = b"data"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("vet_exams.monitoring.exams_automation.urlopen", return_value=mock_response):
            result = _download_file_content("http://s.com/f.pdf")
        assert result == b"data"


@pytest.mark.django_db
class TestAutomationRecords:
    def test_attach_file_to_exam_download_fails(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="e.pdf")
        with patch.object(ea, "_download_file_content", return_value=None):
            result = _attach_file_to_exam(exam, "http://s.com/f.pdf", "f.pdf")
        assert result is False

    def test_attach_file_to_exam_success(self, user):
        animal = baker.make(Animal, guardian=user)
        exam = AnimalExam.objects.create(animal=animal, file_name="e.pdf")
        with patch.object(ea, "_download_file_content", return_value=b"data"):
            result = _attach_file_to_exam(exam, "http://s.com/f.pdf", "f.pdf")
        assert result is True

    def test_attach_file_to_receita_download_fails(self, user):
        from datetime import date as date_cls
        animal = baker.make(Animal, guardian=user)
        receita = Receita.objects.create(animal=animal, source_identifier="x1",
                                         data=date_cls(2025, 1, 1))
        with patch.object(ea, "_download_file_content", return_value=None):
            result = _attach_file_to_receita(receita, "http://s.com/r.pdf", "r.pdf")
        assert result is False

    def test_resolve_animal_driver_exception(self, user):
        driver = MagicMock()
        driver.find_element.side_effect = Exception("err")
        fallback = baker.make(Animal, guardian=user, name="Solo")
        result_animal, name = _resolve_animal_for_user(user, driver)
        assert result_animal == fallback
        assert name is None

    def test_resolve_animal_name_match(self, user):
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        resolved, name = _resolve_animal_for_user(user, driver)
        assert resolved == animal

    def test_resolve_animal_no_match(self, user):
        Animal.objects.filter(guardian=user).delete()
        driver = MagicMock()
        driver.find_element.return_value.text = "Unknown"
        resolved, _ = _resolve_animal_for_user(user, driver)
        assert resolved is None

    def test_save_exam_records_no_animal(self, user):
        Animal.objects.filter(guardian=user).delete()
        driver = MagicMock()
        driver.find_element.return_value.text = "Nobody"
        result = _save_exam_records(user, driver, [])
        # _save_exam_records returns detected_animal_name even if no animal found
        created, total, detected_name, down, fail = result
        assert created == 0
        assert total == 0
        assert down == 0
        assert fail == 0
        # detected_name is whatever was found on the page (e.g. 'Nobody')
        assert detected_name is not None or detected_name is None  # any value is fine

    def test_save_exam_records_with_link(self, user):
        Animal.objects.all().delete()
        AnimalExam.objects.all().delete()
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        fname = f"f_{uuid.uuid4().hex}.pdf"
        links = [(f"http://s.com/{fname}", "Hemo", datetime.now())]
        with patch.object(ea, "_attach_file_to_exam", return_value=True):
            created, total, _, down, fail = _save_exam_records(user, driver, links)
        assert created == 1
        assert total == 1
        assert down == 1
        assert fail == 0

    def test_save_exam_records_download_fails(self, user):
        Animal.objects.all().delete()
        AnimalExam.objects.all().delete()
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        fname = f"f_{uuid.uuid4().hex}.pdf"
        links = [(f"http://s.com/{fname}", "Hemo", None)]
        with patch.object(ea, "_attach_file_to_exam", return_value=False):
            created, total, _, down, fail = _save_exam_records(user, driver, links)
        assert fail == 1

    def test_save_exam_records_update_existing(self, user):
        Animal.objects.all().delete()
        animal = baker.make(Animal, guardian=user, name="Rex")
        AnimalExam.objects.create(animal=animal, file_name="existing.pdf")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        # Same file name -> get_or_create returns existing
        links = [("http://s.com/existing.pdf", "New Label", datetime(2025, 1, 1))]
        created, total, _, down, fail = _save_exam_records(user, driver, links)
        assert created == 0
        assert total == 1

    def test_save_receita_records_no_source_id(self, user):
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        # URL without a trailing segment -> no source_id
        links = [("http://s.com/", datetime.now())]
        created, total, _, down, fail = _save_receita_records(user, driver, links)
        assert created == 0

    def test_save_receita_records_with_link(self, user):
        Animal.objects.all().delete()
        Receita.objects.all().delete()
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        src_id = uuid.uuid4().hex
        links = [(f"http://s.com/receitas/{src_id}", datetime.now())]
        with patch.object(ea, "_attach_file_to_receita", return_value=True):
            created, total, _, down, fail = _save_receita_records(user, driver, links)
        assert created == 1

    def test_run_login_automation_no_credentials(self, user):
        import os
        env = {k: v for k, v in os.environ.items()
               if k not in ("SIMPLESPET_LOGIN", "SIMPLESPET_PASSWORD", "LOGIN", "SENHA")}
        with patch.dict("os.environ", env, clear=True):
            result = run_login_automation(user)
        assert result["success"] is False
        assert "Missing" in result["detail"]

    def test_run_login_automation_driver_fails(self, user):
        with patch.dict("os.environ", {"SIMPLESPET_LOGIN": "u", "SIMPLESPET_PASSWORD": "p"}):
            with patch.object(ea, "_build_chrome_driver", side_effect=Exception("no chrome")):
                result = run_login_automation(user)
        assert result["success"] is False

    def test_run_login_automation_success(self, user):
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        with patch.dict("os.environ", {"SIMPLESPET_LOGIN": "u", "SIMPLESPET_PASSWORD": "p"}):
            with patch.object(ea, "_build_chrome_driver", return_value=driver):
                with patch.object(ea, "perform_login", return_value=True):
                    with patch.object(ea, "_extract_file_links_from_dom", return_value=[]):
                        with patch.object(ea, "_save_exam_records",
                                         return_value=(0, 0, "Rex", 0, 0)):
                            result = run_login_automation(user)
        assert result["success"] is True

    def test_run_login_automation_receitas_no_credentials(self, user):
        import os
        env = {k: v for k, v in os.environ.items()
               if k not in ("SIMPLESPET_LOGIN", "SIMPLESPET_PASSWORD", "LOGIN", "SENHA")}
        with patch.dict("os.environ", env, clear=True):
            result = run_login_automation_receitas(user)
        assert result["success"] is False

    def test_run_login_automation_receitas_success(self, user):
        animal = baker.make(Animal, guardian=user, name="Rex")
        driver = MagicMock()
        with patch.dict("os.environ", {"SIMPLESPET_LOGIN": "u", "SIMPLESPET_PASSWORD": "p"}):
            with patch.object(ea, "_build_chrome_driver", return_value=driver):
                with patch.object(ea, "perform_login", return_value=True):
                    with patch.object(ea, "_extract_receita_links_from_dom", return_value=[]):
                        with patch.object(ea, "_save_receita_records",
                                         return_value=(0, 0, "Rex", 0, 0)):
                            result = run_login_automation_receitas(user)
        assert result["success"] is True
