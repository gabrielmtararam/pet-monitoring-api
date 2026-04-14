"""
Comprehensive tests for monitoring views.py.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from google.genai import types as genai_types

import vet_exams.monitoring.views as mv

from vet_exams.monitoring.models import (
    Animal, WaterBowl, WaterWeightLog, FoodWeightLog, AnimalDiaryEntry,
    FoodBrand, FoodType, AnimalExam,
)
from model_bakery import baker


@pytest.mark.django_db
class TestWaterBowlViewSet:
    def test_list_own_bowls(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        baker.make(WaterBowl, animal=animal)
        r = auth_client.get(reverse('waterbowl-list'))
        assert r.status_code == 200
        assert len(r.data['results']) >= 1

    def test_list_only_own_bowls_not_others(self, auth_client, user):
        other_animal = baker.make(Animal)
        baker.make(WaterBowl, animal=other_animal)
        r = auth_client.get(reverse('waterbowl-list'))
        assert r.status_code == 200
        for bowl in r.data['results']:
            assert bowl['animal'] != other_animal.id

    def test_create_bowl(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        r = auth_client.post(reverse('waterbowl-list'), {'animal': animal.id, 'name': 'Bowl'}, format='json')
        assert r.status_code in [201, 400]


@pytest.mark.django_db
class TestWaterWeightLogViewSet:
    def test_list_own_logs(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        bowl = baker.make(WaterBowl, animal=animal)
        baker.make(WaterWeightLog, bowl=bowl, weight=100)
        r = auth_client.get(reverse('waterweightlog-list'))
        assert r.status_code == 200
        assert len(r.data['results']) >= 1

    def test_list_with_bowl_filter(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        bowl1 = baker.make(WaterBowl, animal=animal)
        bowl2 = baker.make(WaterBowl, animal=animal)
        baker.make(WaterWeightLog, bowl=bowl1, weight=100)
        baker.make(WaterWeightLog, bowl=bowl2, weight=200)
        r = auth_client.get(reverse('waterweightlog-list') + f"?bowl_id={bowl1.id}")
        assert r.status_code == 200
        bowl_ids = {item['bowl'] for item in r.data['results']}
        assert bowl1.id in bowl_ids
        assert bowl2.id not in bowl_ids

    def test_bulk_create_empty_items(self, auth_client):
        r = auth_client.post(reverse('waterweightlog-bulk-create'), {'items': []}, format='json')
        assert r.status_code == 400

    def test_bulk_create_missing_items_key(self, auth_client):
        r = auth_client.post(reverse('waterweightlog-bulk-create'), {}, format='json')
        assert r.status_code == 400

    def test_bulk_create_invalid_bowl(self, auth_client):
        r = auth_client.post(
            reverse('waterweightlog-bulk-create'),
            {'items': [{'bowl': 99999, 'weight': 100}]},
            format='json',
        )
        assert r.status_code == 400

    def test_bulk_create_success(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        bowl = baker.make(WaterBowl, animal=animal)
        r = auth_client.post(
            reverse('waterweightlog-bulk-create'),
            {'items': [{'bowl': bowl.id, 'weight': 100}]},
            format='json',
        )
        assert r.status_code == 201


@pytest.mark.django_db
class TestFoodAndBrandViewSets:
    def test_food_weight_log_list(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        baker.make(FoodWeightLog, animal=animal, weight=100)
        r = auth_client.get(reverse('foodweightlog-list'))
        assert r.status_code == 200

    def test_food_brand_list(self, auth_client):
        baker.make(FoodBrand, name="Brand1")
        r = auth_client.get(reverse('foodbrand-list'))
        assert r.status_code == 200

    def test_food_type_list(self, auth_client):
        baker.make(FoodType, name="Type1")
        r = auth_client.get(reverse('foodtype-list'))
        assert r.status_code == 200


@pytest.mark.django_db
class TestAnimalDiaryEntryViewSet:
    def test_list_own_entries(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        baker.make(AnimalDiaryEntry, animal=animal, text="Obs")
        r = auth_client.get(reverse('animaldiaryentry-list'))
        assert r.status_code == 200
        assert len(r.data['results']) >= 1

    def test_list_with_animal_filter(self, auth_client, user):
        animal1 = baker.make(Animal, guardian=user)
        animal2 = baker.make(Animal, guardian=user)
        baker.make(AnimalDiaryEntry, animal=animal1, text="A1")
        baker.make(AnimalDiaryEntry, animal=animal2, text="A2")
        r = auth_client.get(reverse('animaldiaryentry-list') + f"?animal_id={animal1.id}")
        assert r.status_code == 200
        animal_ids = {item['animal'] for item in r.data['results']}
        assert animal1.id in animal_ids
        assert animal2.id not in animal_ids


@pytest.mark.django_db
class TestMonitoringExportAPIView:
    def test_missing_animal_id(self, auth_client):
        r = auth_client.get(reverse('monitoring-export'))
        assert r.status_code == 400

    def test_invalid_animal_id(self, auth_client):
        r = auth_client.get(reverse('monitoring-export') + "?animal_id=abc")
        assert r.status_code == 400

    def test_animal_not_found(self, auth_client):
        r = auth_client.get(reverse('monitoring-export') + "?animal_id=99999")
        assert r.status_code == 404

    def test_animal_with_diary(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        baker.make(AnimalDiaryEntry, animal=animal, text="Obs")
        r = auth_client.get(reverse('monitoring-export') + f"?animal_id={animal.id}")
        assert r.status_code == 200

    def test_animal_with_bowls(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        bowl = baker.make(WaterBowl, animal=animal)
        baker.make(WaterWeightLog, bowl=bowl, weight=100)
        r = auth_client.get(reverse('monitoring-export') + f"?animal_id={animal.id}")
        assert r.status_code == 200
        assert 'bowls' in r.data


@pytest.mark.django_db
class TestExamsUpdateAPIView:
    def test_post_no_credentials(self, auth_client):
        import os
        env = {k: v for k, v in os.environ.items()
               if k not in ("SIMPLESPET_LOGIN", "SIMPLESPET_PASSWORD", "LOGIN", "SENHA")}
        with patch.dict("os.environ", env, clear=True):
            r = auth_client.post(reverse('exams-update'), {}, format='json')
        assert r.status_code == 400

    @patch.object(mv, 'run_login_automation', return_value={'success': True, 'detail': 'ok'})
    def test_post_success(self, mock_run, auth_client):
        r = auth_client.post(reverse('exams-update'), {}, format='json')
        assert r.status_code == 200


@pytest.mark.django_db
class TestExamsProcessAPIView:
    def test_post_no_pending(self, auth_client):
        r = auth_client.post(reverse('exams-process'), {}, format='json')
        assert r.status_code == 400

    @patch.object(mv, 'process_first_downloaded_exam', return_value={'success': True, 'detail': 'ok'})
    def test_post_success(self, mock_proc, auth_client):
        r = auth_client.post(reverse('exams-process'), {}, format='json')
        assert r.status_code == 200


@pytest.mark.django_db
class TestExamsUpdateMedicationsAPIView:
    @patch.object(mv, 'run_login_automation_receitas', return_value={'success': False, 'detail': 'fail'})
    def test_post_fail(self, mock_run, auth_client):
        r = auth_client.post(reverse('exams-update-medications'), {}, format='json')
        assert r.status_code == 400

    @patch.object(mv, 'run_login_automation_receitas', return_value={'success': True, 'detail': 'ok'})
    def test_post_success(self, mock_run, auth_client):
        r = auth_client.post(reverse('exams-update-medications'), {}, format='json')
        assert r.status_code == 200


@pytest.mark.django_db
class TestReceitasProcessAPIView:
    def test_post_no_pending(self, auth_client):
        r = auth_client.post(reverse('receitas-process'), {}, format='json')
        assert r.status_code == 400

    @patch.object(mv, 'process_first_receita', return_value={'success': True, 'detail': 'ok'})
    def test_post_success(self, mock_proc, auth_client):
        r = auth_client.post(reverse('receitas-process'), {}, format='json')
        assert r.status_code == 200


@pytest.mark.django_db
class TestChatAPIView:
    def _build_client_mock(self, responses):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = responses
        return mock_client

    def test_post_missing_prompt(self, auth_client):
        r = auth_client.post(reverse('monitoring-chat'), {'animal_id': 1}, format='json')
        assert r.status_code == 400

    def test_post_success_no_function_calls(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        mock_response = MagicMock()
        mock_response.text = "Response text"
        mock_response.function_calls = []
        with patch.object(mv, '_get_genai_client', return_value=self._build_client_mock([mock_response])):
            r = auth_client.post(
                reverse('monitoring-chat'),
                {'prompt': 'How is my pet?', 'animal_id': animal.id},
                format='json',
            )
        assert r.status_code == 200

    def test_post_with_water_function_call(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)
        baker.make(AnimalDiaryEntry, animal=animal, text="Good", observed_at=timezone.now())

        func_call = MagicMock()
        func_call.name = "get_water_consumption"
        func_call.args = {"animal_id": animal.id, "start_date": "2020-01-01", "end_date": "2030-01-01"}

        first_resp = MagicMock()
        first_resp.function_calls = [func_call]
        first_resp.candidates = [MagicMock()]
        first_resp.candidates[0].content = "content"

        final_resp = MagicMock()
        final_resp.text = "Water answer"
        final_resp.function_calls = []

        with patch.object(mv, '_get_genai_client',
                          return_value=self._build_client_mock([first_resp, final_resp])):
            with patch.object(genai_types.Part, 'from_function_response', return_value=MagicMock()):
                r = auth_client.post(
                    reverse('monitoring-chat'),
                    {'prompt': 'Water?', 'animal_id': animal.id},
                    format='json',
                )
        assert r.status_code == 200

    def test_post_with_food_function_call(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)

        func_call = MagicMock()
        func_call.name = "get_food_consumption"
        func_call.args = {"animal_id": animal.id, "start_date": "2020-01-01", "end_date": "2030-01-01"}

        first_resp = MagicMock()
        first_resp.function_calls = [func_call]
        first_resp.candidates = [MagicMock()]
        first_resp.candidates[0].content = "content"

        final_resp = MagicMock()
        final_resp.text = "Food answer"
        final_resp.function_calls = []

        with patch.object(mv, '_get_genai_client',
                          return_value=self._build_client_mock([first_resp, final_resp])):
            with patch.object(genai_types.Part, 'from_function_response', return_value=MagicMock()):
                r = auth_client.post(
                    reverse('monitoring-chat'),
                    {'prompt': 'Food?', 'animal_id': animal.id},
                    format='json',
                )
        assert r.status_code == 200

    def test_post_with_unknown_function_call(self, auth_client, user):
        animal = baker.make(Animal, guardian=user)

        func_call = MagicMock()
        func_call.name = "unknown_fn"
        func_call.args = {}

        first_resp = MagicMock()
        first_resp.function_calls = [func_call]
        first_resp.candidates = [MagicMock()]
        first_resp.candidates[0].content = "content"

        final_resp = MagicMock()
        final_resp.text = "Answer"
        final_resp.function_calls = []

        with patch.object(mv, '_get_genai_client',
                          return_value=self._build_client_mock([first_resp, final_resp])):
            with patch.object(genai_types.Part, 'from_function_response', return_value=MagicMock()):
                r = auth_client.post(
                    reverse('monitoring-chat'),
                    {'prompt': 'something', 'animal_id': animal.id},
                    format='json',
                )
        assert r.status_code == 200

    def test_post_gemini_exception(self, auth_client):
        with patch.object(mv, '_get_genai_client', side_effect=Exception("API error")):
            r = auth_client.post(
                reverse('monitoring-chat'),
                {'prompt': 'Hi', 'animal_id': 1},
                format='json',
            )
        assert r.status_code == 500

    def test_post_no_animal_id(self, auth_client):
        mock_response = MagicMock()
        mock_response.text = "Answer"
        mock_response.function_calls = []
        with patch.object(mv, '_get_genai_client', return_value=self._build_client_mock([mock_response])):
            r = auth_client.post(
                reverse('monitoring-chat'),
                {'prompt': 'General question'},
                format='json',
            )
        assert r.status_code == 200
