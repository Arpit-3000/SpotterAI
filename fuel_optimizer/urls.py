from django.urls import path
from .views import FuelPlanView

app_name = 'fuel_optimizer'

urlpatterns = [
    path('fuel-plan/', FuelPlanView.as_view(), name='fuel-plan'),
]
