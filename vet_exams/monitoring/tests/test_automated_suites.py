import pytest
import os
import uuid
from unittest.mock import patch, MagicMock
from django.core.files.base import ContentFile
from datetime import datetime
from django.urls import reverse
from rest_framework import status
from django.utils import timezone
from types import SimpleNamespace

# Import modules for direct patching
import vet_exams.monitoring.exams_automation as ea
import vet_exams.monitoring.views as mv
import vet_exams.monitoring.exams_extraction as ee

from vet_exams.monitoring.exams_automation import (
    _resolve_animal_for_user,
    _save_exam_records,
    _extract_file_name,
    _get_exam_type_label_from_anchor
)
from vet_exams.monitoring.models import (
    AnimalExam, Receita, Animal, WaterBowl, WaterWeightLog, AnimalDiaryEntry
)

@pytest.mark.django_db
class TestCoverageFinal:
    def test_view_actions_hit(self, auth_client, user):
        Animal.objects.all().delete()
        animal = Animal.objects.create(guardian=user, name="Buddy")
        bowl = WaterBowl.objects.create(animal=animal, name="Bowl1")
        
        url = reverse('waterweightlog-bulk-create')
        data = {
            'items': [{'bowl': bowl.id, 'weight': 150}]
        }
        res = auth_client.post(url, data, format='json')
        assert res.status_code == 201

        url_export = reverse('monitoring-export') + f"?animal_id={animal.id}"
        res_exp = auth_client.get(url_export)
        assert res_exp.status_code == 200
        
        with patch.object(mv, '_get_genai_client') as m:
            m.return_value.models.generate_content.return_value = SimpleNamespace(
                text="res", candidates=[]
            )
            auth_client.post(reverse('monitoring-chat'), {'prompt': 'hi', 'animal_id': animal.id}, format='json')

    def test_automation_loop_hit(self, user):
        Animal.objects.all().delete()
        AnimalExam.objects.all().delete()
        
        animal = Animal.objects.create(guardian=user, name="Rex")
        driver = MagicMock()
        driver.find_element.return_value.text = "Rex"
        fname = f"file_{uuid.uuid4().hex}.pdf"
        links = [(f"http://s.com/{fname}", "Lab", datetime.now())]
        
        with patch.object(ea, '_attach_file_to_exam', return_value=True):
            with patch.object(ea, '_download_file_content', return_value=b"data"):
                created, total, name, down, fail = _save_exam_records(user, driver, links)
                assert created == 1

    def test_helpers_logic(self):
        assert _extract_file_name("test.pdf") == "test.pdf"
        assert _extract_file_name("") is None
        anchor = MagicMock()
        anchor.find_element.side_effect = Exception()
        assert _get_exam_type_label_from_anchor(anchor) is None
