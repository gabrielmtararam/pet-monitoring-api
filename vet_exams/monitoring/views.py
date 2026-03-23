from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from google import genai
import os
from .exams_extraction import _get_genai_client
from vet_exams.monitoring.exams_automation import run_login_automation, run_login_automation_receitas


from vet_exams.monitoring.exams_extraction import process_first_downloaded_exam
from vet_exams.monitoring.receitas_extraction import process_first_receita
from vet_exams.monitoring.models import (
    AnimalDiaryEntry,
    DailyFoodConsumption,
    DailyWaterConsumption,
    FoodBrand,
    FoodType,
    FoodWeightLog,
    WaterBowl,
    WaterWeightLog,
    recalculate_daily_food_consumption_for_log,
    recalculate_daily_water_consumption_for_log,
)
from vet_exams.monitoring.serializers import (
    AnimalDiaryEntrySerializer,
    DailyFoodConsumptionSerializer,
    DailyWaterConsumptionSerializer,
    FoodBrandSerializer,
    FoodTypeSerializer,
    FoodWeightLogSerializer,
    WaterBowlSerializer,
    WaterWeightLogSerializer,
)


class WaterBowlViewSet(viewsets.ModelViewSet):
    serializer_class = WaterBowlSerializer

    def get_queryset(self):
        return WaterBowl.objects.filter(animal__guardian=self.request.user).order_by('id')


class WaterWeightLogViewSet(viewsets.ModelViewSet):
    serializer_class = WaterWeightLogSerializer

    def get_queryset(self):
        request: Request = self.request
        queryset = WaterWeightLog.objects.filter(bowl__animal__guardian=request.user)

        bowl_id = request.query_params.get('bowl_id')
        if bowl_id:
            queryset = queryset.filter(bowl_id=bowl_id)

        return queryset

    @action(detail=False, methods=['post'])
    def bulk_create(self, request: Request):
        """
        Create multiple weight logs at once, using the same
        entry_type and observed_at for all bowls.
        """
        entry_type = request.data.get('entry_type', 'reading')
        observed_at = request.data.get('observed_at')
        items = request.data.get('items', [])

        if not isinstance(items, list) or not items:
            return Response({'detail': 'Nenhum item informado.'}, status=status.HTTP_400_BAD_REQUEST)

        created_logs = []
        errors = []

        for index, item in enumerate(items):
            data = {
                'bowl': item.get('bowl'),
                'weight': item.get('weight'),
                'entry_type': entry_type,
                'observed_at': observed_at or timezone.now(),
            }

            serializer = self.get_serializer(data=data)
            if serializer.is_valid():
                created_logs.append(serializer)
            else:
                errors.append({'index': index, 'errors': serializer.errors})

        if errors:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        for serializer in created_logs:
            serializer.save()

        return Response([s.data for s in created_logs], status=status.HTTP_201_CREATED)


class FoodWeightLogViewSet(viewsets.ModelViewSet):
    serializer_class = FoodWeightLogSerializer

    def get_queryset(self):
        request: Request = self.request
        return FoodWeightLog.objects.filter(animal__guardian=request.user)


class FoodBrandViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FoodBrandSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FoodBrand.objects.all()


class FoodTypeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FoodTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FoodType.objects.all()


class AnimalDiaryEntryViewSet(viewsets.ModelViewSet):
    serializer_class = AnimalDiaryEntrySerializer

    def get_queryset(self):
        request: Request = self.request
        queryset = AnimalDiaryEntry.objects.filter(animal__guardian=request.user)

        animal_id = request.query_params.get('animal_id')
        if animal_id:
            queryset = queryset.filter(animal_id=animal_id)

        return queryset


class MonitoringExportAPIView(APIView):
    """
    Return consolidated JSON with monitoring data
    (bowls, water logs, food logs, diary and daily aggregates) for an animal.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request):
        animal_id = request.query_params.get('animal_id')
        if not animal_id:
            return Response({'detail': 'Parâmetro animal_id é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            animal_id_int = int(animal_id)
        except (TypeError, ValueError):
            return Response({'detail': 'animal_id inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        bowls_qs = WaterBowl.objects.filter(animal_id=animal_id_int, animal__guardian=request.user)
        if not bowls_qs.exists():
            has_any_data = (
                FoodWeightLog.objects.filter(animal_id=animal_id_int, animal__guardian=request.user).exists()
                or AnimalDiaryEntry.objects.filter(animal_id=animal_id_int, animal__guardian=request.user).exists()
            )
            if not has_any_data:
                return Response({'detail': 'Animal não encontrado ou sem dados para este usuário.'}, status=status.HTTP_404_NOT_FOUND)

        water_logs_all = WaterWeightLog.objects.filter(
            bowl__animal_id=animal_id_int,
            bowl__animal__guardian=request.user,
        ).order_by('observed_at')
        for log in water_logs_all:
            recalculate_daily_water_consumption_for_log(log)

        food_logs_all = FoodWeightLog.objects.filter(
            animal_id=animal_id_int,
            animal__guardian=request.user,
        ).order_by('observed_at')
        for log in food_logs_all:
            recalculate_daily_food_consumption_for_log(log)

        bowls = WaterBowlSerializer(bowls_qs, many=True).data

        water_logs = WaterWeightLogSerializer(water_logs_all, many=True).data

        food_logs = FoodWeightLogSerializer(food_logs_all, many=True).data

        diary_qs = AnimalDiaryEntry.objects.filter(
            animal_id=animal_id_int,
            animal__guardian=request.user,
        ).order_by('observed_at')
        diary_entries = AnimalDiaryEntrySerializer(diary_qs, many=True).data

        daily_water_qs = DailyWaterConsumption.objects.filter(
            animal_id=animal_id_int,
        ).order_by('date')
        daily_water = DailyWaterConsumptionSerializer(daily_water_qs, many=True).data

        daily_food_qs = DailyFoodConsumption.objects.filter(
            animal_id=animal_id_int,
        ).order_by('date')
        daily_food = DailyFoodConsumptionSerializer(daily_food_qs, many=True).data

        payload = {
            'animal_id': animal_id_int,
            'bowls': bowls,
            'water_logs': water_logs,
            'food_logs': food_logs,
            'diary_entries': diary_entries,
            'daily_water_consumptions': daily_water,
            'daily_food_consumptions': daily_food,
        }
        return Response(payload, status=status.HTTP_200_OK)


class ExamsUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request):
        result = run_login_automation(request.user)
        response_status = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=response_status)


class ExamsProcessAPIView(APIView):
    """Process the first downloaded exam with Gemini and persist extracted data."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request):
        result = process_first_downloaded_exam(request.user)
        response_status = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=response_status)


class ExamsUpdateMedicationsAPIView(APIView):
    """Login to SimplesPet, extract receita links from the page and save Receita records (and download files)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request):
        result = run_login_automation_receitas(request.user)
        response_status = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=response_status)


class ReceitasProcessAPIView(APIView):
    """Process the first receita with file (no indicacoes yet) using Gemini and persist Remedio/IndicacaoMedicamento."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request):
        result = process_first_receita(request.user)
        response_status = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=response_status)


class ChatAPIView(APIView):
    """
    IA Chatbot endpoint for pet monitoring.
    Receives a prompt and returns a response from Gemini, using Function Calling
    and RAG for AnimalDiaryEntry context.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request):
        prompt = request.data.get('prompt')
        animal_id = request.data.get('animal_id')

        if not prompt:
            return Response({'detail': 'O prompt é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = _get_genai_client()
            from google.genai import types

            def get_water_consumption(animal_id: int, start_date: str, end_date: str) -> dict:
                """Obtém o consumo de água do animal entre as datas de início e fim.
                Args:
                    animal_id: ID do animal.
                    start_date: Data inicial no formato YYYY-MM-DD.
                    end_date: Data final no formato YYYY-MM-DD.
                """
                logs = DailyWaterConsumption.objects.filter(
                    animal_id=animal_id,
                    animal__guardian=request.user,
                    date__gte=start_date,
                    date__lte=end_date
                ).order_by('date')
                if not logs:
                    return {"result": "Nenhum dado de consumo de água encontrado para este período."}
                
                result = "Consumo de Água (líquido em gramas):\n"
                for log in logs:
                    result += f"- {log.date}: {log.net_consumption}g\n"
                return {"result": result}

            def get_food_consumption(animal_id: int, start_date: str, end_date: str) -> dict:
                """Obtém o consumo de ração do animal entre as datas de início e fim.
                Args:
                    animal_id: ID do animal.
                    start_date: Data inicial no formato YYYY-MM-DD.
                    end_date: Data final no formato YYYY-MM-DD.
                """
                logs = DailyFoodConsumption.objects.filter(
                    animal_id=animal_id,
                    animal__guardian=request.user,
                    date__gte=start_date,
                    date__lte=end_date
                ).order_by('date')
                if not logs:
                    return {"result": "Nenhum dado de consumo de ração encontrado para este período."}
                
                result = "Consumo de Ração (total em gramas):\n"
                for log in logs:
                    result += f"- {log.date}: {log.total_consumption}g\n"
                return {"result": result}

            rag_context = ""
            if animal_id:
                diary_entries = AnimalDiaryEntry.objects.filter(
                    animal_id=animal_id,
                    animal__guardian=request.user
                ).order_by('-observed_at')[:20]
                
                if diary_entries:
                    rag_context = "Contexto do diário do animal (observações recentes):\n"
                    for entry in diary_entries:
                        # Exibe a data e texto
                        rag_context += f"- Data {entry.observed_at.strftime('%Y-%m-%d %H:%M')}: {entry.text}\n"

            system_instruction = (
                "Você é um assistente virtual veterinário especializado em monitoramento de pets.\n"
                "Para responder sobre histórico numérico de consumo, SEMPRE use as funções fornecidas.\n"
                "Responda sempre em Português do Brasil.\n"
                f"{rag_context}\n"
                f"Hoje é {timezone.now().strftime('%Y-%m-%d')}.\n"
            )
            
            if animal_id:
                prompt_with_context = f"{system_instruction}\n(O animal atual que o usuário está monitorando tem o ID {animal_id})\nUsuário: {prompt}"
            else:
                prompt_with_context = f"{system_instruction}\nUsuário: {prompt}"

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt_with_context,
                config=types.GenerateContentConfig(
                    tools=[get_water_consumption, get_food_consumption],
                    temperature=0.2,
                ),
            )

            if response.function_calls:
                function_responses = []
                for function_call in response.function_calls:
                    if function_call.name == "get_water_consumption":
                        result = get_water_consumption(**function_call.args)  # type: ignore
                    elif function_call.name == "get_food_consumption":
                        result = get_food_consumption(**function_call.args)  # type: ignore
                    else:
                        result = {"result": "Função desconhecida."}
                    
                    function_responses.append(
                        types.Part.from_function_response(
                            name=function_call.name,
                            response=result
                        )
                    )

                final_response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=[
                        prompt_with_context,
                        response.candidates[0].content,
                    ] + function_responses,
                    config=types.GenerateContentConfig(temperature=0.2)
                )
                return Response({'response': final_response.text}, status=status.HTTP_200_OK)

            return Response({'response': response.text}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)