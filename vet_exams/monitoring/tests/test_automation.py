import pytest
from unittest.mock import patch, MagicMock
from vet_exams.monitoring.exams_automation import (
    _extract_file_name,
    _extract_receita_id_from_url,
    perform_login,
    _resolve_animal_for_user
)
from model_bakery import baker

class TestAutomationUtils:
    def test_extract_file_name(self):
        url = "https://example.com/files/exam1.pdf"
        assert _extract_file_name(url) == "exam1.pdf"
        assert _extract_file_name("") is None

    def test_extract_receita_id(self):
        url = "https://example.com/receitas/12345/"
        assert _extract_receita_id_from_url(url) == "12345"

    @patch('vet_exams.monitoring.exams_automation.WebDriverWait')
    def test_perform_login(self, mock_wait):
        mock_driver = MagicMock()
        # Configure the mock wait to return a mock element
        mock_wait.return_value.until.return_value = MagicMock()
        
        result = perform_login(mock_driver, "user", "pass")
        assert result is True
        mock_driver.get.assert_called()

    @pytest.mark.django_db
    def test_resolve_animal(self, user):
        animal = baker.make('animals.Animal', guardian=user, name="Rex")
        mock_driver = MagicMock()
        mock_driver.find_element.return_value.text = "Rex"
        
        resolved_animal, name = _resolve_animal_for_user(user, mock_driver)
        assert resolved_animal == animal
        assert name == "Rex"

    @pytest.mark.django_db
    def test_resolve_animal_fallback(self, user):
        animal = baker.make('animals.Animal', guardian=user, name="Rex")
        mock_driver = MagicMock()
        mock_driver.find_element.side_effect = Exception("Not found")
        
        resolved_animal, name = _resolve_animal_for_user(user, mock_driver)
        assert resolved_animal == animal
        assert name is None
