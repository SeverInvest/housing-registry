from django.contrib import admin
from django.urls import path

admin.site.site_header = "Реестр жилищного фонда"
admin.site.site_title = "Реестр ОЖФ"
admin.site.index_title = "Управление данными"

urlpatterns = [path("admin/", admin.site.urls)]
