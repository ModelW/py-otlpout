"""URL configuration for the pet project."""

from django.urls import path

from petdjango import views

urlpatterns = [
    path("pets/<int:pet_id>/", views.pet_detail, name="pet-detail"),
]
