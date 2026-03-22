from django.urls import include, path
from rest_framework.routers import DefaultRouter

from vet_exams.monitoring.views import (
    AnimalDiaryEntryViewSet,
    ExamsProcessAPIView,
    ExamsUpdateAPIView,
    ExamsUpdateMedicationsAPIView,
    FoodBrandViewSet,
    FoodTypeViewSet,
    MonitoringExportAPIView,
    ReceitasProcessAPIView,
    FoodWeightLogViewSet,
    WaterBowlViewSet,
    WaterWeightLogViewSet,
)

router = DefaultRouter()
router.register(r'bowls', WaterBowlViewSet, basename='waterbowl')
router.register(r'logs', WaterWeightLogViewSet, basename='waterweightlog')
router.register(r'food-logs', FoodWeightLogViewSet, basename='foodweightlog')
router.register(r'food-brands', FoodBrandViewSet, basename='foodbrand')
router.register(r'food-types', FoodTypeViewSet, basename='foodtype')
router.register(r'diary-entries', AnimalDiaryEntryViewSet, basename='animaldiaryentry')

urlpatterns = [
    path('exams/update/', ExamsUpdateAPIView.as_view(), name='exams-update'),
    path('exams/process/', ExamsProcessAPIView.as_view(), name='exams-process'),
    path('exams/update-medications/', ExamsUpdateMedicationsAPIView.as_view(), name='exams-update-medications'),
    path('receitas/process/', ReceitasProcessAPIView.as_view(), name='receitas-process'),
    path('export/', MonitoringExportAPIView.as_view(), name='monitoring-export'),
    path('', include(router.urls)),
]