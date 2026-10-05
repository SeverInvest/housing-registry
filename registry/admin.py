from django.contrib import admin

from .models import House, HouseManagement, Organization, Region


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "fias_guid", "sync_enabled", "updated_at")
    list_filter = ("sync_enabled",)
    search_fields = ("code", "name", "fias_guid")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("display_name", "ogrn", "inn", "kpp", "organization_type")
    search_fields = ("full_name", "short_name", "ogrn", "inn", "kpp")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Наименование", ordering="full_name")
    def display_name(self, obj):
        return obj.short_name or obj.full_name


class HouseManagementInline(admin.TabularInline):
    model = HouseManagement
    extra = 0
    autocomplete_fields = ("organization",)
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "organization",
        "management_method",
        "management_basis",
        "date_start",
        "date_finish",
        "is_active",
        "source",
        "created_at",
        "updated_at",
    )


class DetailFetchedFilter(admin.SimpleListFilter):
    title = "Подробная карточка"
    parameter_name = "detail_fetched"

    def lookups(self, request, model_admin):
        return (("yes", "Получена"), ("no", "Не получена"))

    def queryset(self, request, queryset):
        if self.value() in {"yes", "no"}:
            return queryset.filter(detail_fetched_at__isnull=self.value() == "no")
        return queryset


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = (
        "address",
        "region",
        "house_type",
        "cadastre_number",
        "commissioning_year",
        "detail_fetched_at",
    )
    search_fields = ("address", "gis_guid", "fias_guid", "house_uid", "cadastre_number")
    list_filter = ("region", "house_type", "condition", "life_cycle_stage", DetailFetchedFilter)
    autocomplete_fields = ("region",)
    readonly_fields = ("detail_fetched_at", "created_at", "updated_at")
    list_select_related = ("region",)
    inlines = (HouseManagementInline,)


@admin.register(HouseManagement)
class HouseManagementAdmin(admin.ModelAdmin):
    list_display = (
        "house",
        "organization",
        "management_method",
        "management_basis",
        "date_start",
        "date_finish",
        "is_active",
        "source",
    )
    list_filter = ("house__region", "management_method", "management_basis", "is_active", "source")
    search_fields = ("house__address", "organization__full_name", "organization__ogrn")
    autocomplete_fields = ("house", "organization")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("house", "organization")
