from django.contrib import admin

from .models import (
    AdministrativeAppointment,
    House,
    HouseVersion,
    ImportRun,
    Organization,
    Region,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "fias_guid", "federal_district", "sync_enabled")
    list_filter = ("sync_enabled", "federal_district")
    search_fields = ("code", "name", "fias_guid")
    ordering = ("code",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "short_name",
        "ogrn",
        "inn",
        "organization_type",
        "source_last_event_date",
    )
    search_fields = ("full_name", "short_name", "ogrn", "inn")
    list_filter = ("organization_type",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("full_name",)


class HouseVersionInline(admin.TabularInline):
    model = HouseVersion
    extra = 0
    can_delete = False
    fields = ("observed_at", "source", "changed_fields", "content_hash")
    readonly_fields = fields
    ordering = ("-observed_at",)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = (
        "formatted_address",
        "region",
        "house_type_name",
        "management_method",
        "management_organization",
        "total_square",
        "oktmo",
        "active",
        "needs_detail_refresh",
        "consecutive_missing_runs",
        "last_missing_at",
    )
    list_filter = (
        "region",
        "active",
        "house_type_name",
        "management_method",
        "uo_selection_method",
        "house_condition",
        "life_cycle_stage",
        "needs_detail_refresh",
    )
    search_fields = (
        "formatted_address",
        "house_uid",
        "gis_guid",
        "gis_address_guid",
        "fias_house_guid",
        "cadastre_number",
        "management_organization__full_name",
        "management_organization__ogrn",
    )
    autocomplete_fields = ("region", "management_organization")
    readonly_fields = (
        "first_seen_at",
        "last_seen_at",
        "detail_fetched_at",
        "search_hash",
        "detail_hash",
        "created_at",
        "updated_at",
        "search_payload",
        "detail_payload",
    )
    list_select_related = ("region", "management_organization")
    inlines = (HouseVersionInline,)
    fieldsets = (
        (
            "Идентификаторы",
            {
                "fields": (
                    "gis_guid",
                    "gis_address_guid",
                    "fias_house_guid",
                    "house_uid",
                    "cadastre_number",
                )
            },
        ),
        (
            "Адрес",
            {
                "fields": (
                    "region",
                    "formatted_address",
                    "postal_code",
                    "region_name",
                    "municipality_name",
                    "locality_name",
                    "street_name",
                    "oktmo",
                )
            },
        ),
        (
            "Управление",
            {
                "fields": (
                    "management_method",
                    "management_method_code",
                    "management_method_name",
                    "management_organization",
                    "uo_selection_method",
                    "management_start_date",
                    "management_end_date",
                )
            },
        ),
        (
            "Характеристики",
            {
                "fields": (
                    "house_type_code",
                    "house_type_name",
                    "total_square",
                    "residential_square",
                    "residential_premise_count",
                    "non_residential_premise_count",
                    "min_floor_count",
                    "max_floor_count",
                    "underground_floor_count",
                    "building_year",
                    "operation_year",
                    "reconstruction_year",
                    "wall_material",
                    "house_condition",
                    "life_cycle_stage",
                )
            },
        ),
        (
            "Синхронизация",
            {
                "fields": (
                    "source_status",
                    "approved",
                    "active",
                    "needs_detail_refresh",
                    "consecutive_missing_runs",
                    "last_missing_at",
                    "first_seen_at",
                    "last_seen_at",
                    "detail_fetched_at",
                    "search_hash",
                    "detail_hash",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            "Исходные JSON",
            {"classes": ("collapse",), "fields": ("search_payload", "detail_payload")},
        ),
    )


@admin.register(HouseVersion)
class HouseVersionAdmin(admin.ModelAdmin):
    list_display = ("house", "observed_at", "source", "changed_fields", "content_hash")
    list_filter = ("source", "observed_at")
    search_fields = ("house__formatted_address", "house__gis_guid", "content_hash")
    readonly_fields = (
        "house",
        "run",
        "source",
        "observed_at",
        "content_hash",
        "changed_fields",
        "snapshot",
    )
    list_select_related = ("house", "run")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = (
        "started_at",
        "region",
        "source",
        "status",
        "processed",
        "created_count",
        "updated_count",
        "unchanged_count",
        "error_count",
    )
    list_filter = ("region", "source", "status")
    readonly_fields = (
        "source",
        "region",
        "status",
        "parameters",
        "started_at",
        "finished_at",
        "total_expected",
        "processed",
        "created_count",
        "updated_count",
        "unchanged_count",
        "error_count",
        "message",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AdministrativeAppointment)
class AdministrativeAppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "house",
        "region",
        "organization",
        "decision_number",
        "decision_date",
        "starts_on",
        "ends_on",
        "active",
    )
    list_filter = ("region", "active", "decision_date")
    search_fields = (
        "house__formatted_address",
        "organization__full_name",
        "organization__ogrn",
        "decision_number",
        "source_key",
    )
    autocomplete_fields = ("region", "house", "organization")
    readonly_fields = ("created_at", "updated_at")
