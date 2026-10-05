from django.db import models
from django.db.models import F, Q


class ManagementMethod(models.TextChoices):
    MANAGEMENT_COMPANY = "management_company", "Управляющая организация"
    HOA_TSN = "hoa_tsn", "ТСЖ или ТСН"
    HOUSING_COOPERATIVE = "housing_cooperative", "ЖСК или ЖК"
    DIRECT = "direct", "Непосредственное управление"
    NOT_SELECTED = "not_selected", "Способ управления не выбран"
    OTHER = "other", "Иной способ"
    UNKNOWN = "unknown", "Не определено"


class ManagementBasis(models.TextChoices):
    OWNERS_DECISION = "owners_decision", "Выбор собственниками"
    DEVELOPER_CONTRACT = "developer_contract", "Договор с застройщиком"
    MUNICIPAL_COMPETITION = "municipal_competition", "Муниципальный конкурс"
    ADMINISTRATIVE_APPOINTMENT = "administrative_appointment", "Назначение администрацией"
    UNKNOWN = "unknown", "Основание не определено"


class ManagementSource(models.TextChoices):
    GIS_SEARCH = "gis_search", "Региональная поисковая выдача ГИС ЖКХ"
    GIS_DETAIL = "gis_detail", "Подробная карточка дома"
    LICENSE_REGISTRY = "license_registry", "Реестр лицензий"
    ADMINISTRATIVE_REGISTRY = "administrative_registry", "Реестр назначений администрации"
    MANUAL = "manual", "Ручное внесение"


class Region(models.Model):
    code = models.CharField("Код региона", max_length=3, unique=True)
    name = models.CharField("Наименование", max_length=255, unique=True)
    fias_guid = models.UUIDField("GUID региона по ФИАС", null=True, blank=True)
    sync_enabled = models.BooleanField("Синхронизация включена", default=True, db_index=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Регион"
        verbose_name_plural = "Регионы"
        ordering = ("code",)

    def __str__(self):
        return f"{self.code} — {self.name}"


class House(models.Model):
    region = models.ForeignKey(
        Region, verbose_name="Регион", related_name="houses", on_delete=models.PROTECT
    )
    gis_guid = models.UUIDField("GUID дома в ГИС ЖКХ", unique=True)
    gis_address_guid = models.CharField("Код адреса в ГИС ЖКХ", max_length=128, blank=True)
    fias_guid = models.UUIDField("GUID дома в ФИАС", null=True, blank=True, db_index=True)
    house_uid = models.CharField("Идентификатор объекта", max_length=64, blank=True)
    cadastre_number = models.CharField(
        "Кадастровый номер", max_length=128, blank=True, db_index=True
    )
    postal_code = models.CharField("Почтовый индекс", max_length=12, blank=True)
    district = models.CharField("Район", max_length=255, blank=True)
    city = models.CharField("Город", max_length=255, blank=True)
    settlement = models.CharField("Населённый пункт", max_length=255, blank=True)
    planning_structure_element = models.CharField(
        "Элемент планировочной структуры", max_length=255, blank=True
    )
    street = models.CharField("Улица", max_length=255, blank=True)
    building_number = models.CharField(
        "Номер дома, корпус, литер, строение", max_length=128, blank=True
    )
    address = models.CharField("Полный адрес", max_length=2000, blank=True)
    house_type = models.CharField("Тип дома", max_length=128, blank=True)
    condition = models.CharField("Состояние", max_length=128, blank=True)
    life_cycle_stage = models.CharField("Стадия жизненного цикла", max_length=128, blank=True)
    construction_year = models.PositiveSmallIntegerField("Год постройки", null=True, blank=True)
    commissioning_year = models.PositiveSmallIntegerField("Год ввода", null=True, blank=True)
    reconstruction_year = models.PositiveSmallIntegerField(
        "Год реконструкции", null=True, blank=True
    )
    floors = models.PositiveSmallIntegerField("Количество этажей", null=True, blank=True)
    wall_material = models.CharField("Материал стен", max_length=500, blank=True)
    area_total = models.DecimalField(
        "Общая площадь дома", max_digits=16, decimal_places=4, null=True, blank=True
    )
    area_residential = models.DecimalField(
        "Жилая площадь в доме", max_digits=16, decimal_places=4, null=True, blank=True
    )
    residential_premises_area = models.DecimalField(
        "Площадь жилых помещений", max_digits=16, decimal_places=4, null=True, blank=True
    )
    non_residential_premises_area = models.DecimalField(
        "Площадь нежилых помещений", max_digits=16, decimal_places=4, null=True, blank=True
    )
    residential_premises_count = models.PositiveIntegerField(
        "Жилых помещений", null=True, blank=True
    )
    non_residential_premises_count = models.PositiveIntegerField(
        "Нежилых помещений", null=True, blank=True
    )
    detail_fetched_at = models.DateTimeField(
        "Подробная карточка получена", null=True, blank=True, db_index=True
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Дом"
        verbose_name_plural = "Дома"
        ordering = ("address",)

    def __str__(self):
        return self.address or str(self.gis_guid)


class Organization(models.Model):
    gis_guid = models.UUIDField("GUID организации в ГИС ЖКХ", null=True, blank=True, unique=True)
    full_name = models.CharField("Полное наименование", max_length=2000)
    short_name = models.CharField("Сокращённое наименование", max_length=1000, blank=True)
    ogrn = models.CharField("ОГРН/ОГРНИП", max_length=15, null=True, blank=True, unique=True)
    inn = models.CharField("ИНН", max_length=12, blank=True, db_index=True)
    kpp = models.CharField("КПП", max_length=9, blank=True)
    organization_type = models.CharField("Тип организации", max_length=128, blank=True)
    legal_form = models.CharField("Организационно-правовая форма", max_length=500, blank=True)
    legal_address = models.CharField("Юридический адрес", max_length=2000, blank=True)
    website = models.URLField("Сайт", max_length=500, blank=True)
    phone = models.CharField("Телефон", max_length=128, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ("full_name",)

    def __str__(self):
        return self.short_name or self.full_name


class HouseManagement(models.Model):
    house = models.ForeignKey(
        House, verbose_name="Дом", related_name="management_periods", on_delete=models.PROTECT
    )
    organization = models.ForeignKey(
        Organization,
        verbose_name="Организация",
        related_name="management_periods",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    management_method = models.CharField(
        "Способ управления",
        max_length=32,
        choices=ManagementMethod.choices,
        default=ManagementMethod.UNKNOWN,
    )
    management_basis = models.CharField(
        "Основание управления",
        max_length=32,
        choices=ManagementBasis.choices,
        default=ManagementBasis.UNKNOWN,
    )
    date_start = models.DateField("Начало управления", null=True, blank=True)
    date_finish = models.DateField("Окончание управления", null=True, blank=True)
    is_active = models.BooleanField("Действует", default=True)
    source = models.CharField("Источник", max_length=32, choices=ManagementSource.choices)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Период управления"
        verbose_name_plural = "Периоды управления"
        ordering = ("house", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("house",),
                condition=Q(is_active=True),
                name="one_active_management_per_house",
            ),
            models.CheckConstraint(
                condition=Q(date_start__isnull=True)
                | Q(date_finish__isnull=True)
                | Q(date_finish__gte=F("date_start")),
                name="management_dates_ordered",
            ),
            models.CheckConstraint(
                condition=~Q(management_method=ManagementMethod.DIRECT)
                | Q(organization__isnull=True),
                name="direct_management_no_organization",
            ),
            models.CheckConstraint(
                condition=Q(management_method__in=ManagementMethod.values),
                name="management_method_valid",
            ),
            models.CheckConstraint(
                condition=Q(management_basis__in=ManagementBasis.values),
                name="management_basis_valid",
            ),
            models.CheckConstraint(
                condition=Q(source__in=ManagementSource.values),
                name="management_source_valid",
            ),
        ]

    def __str__(self):
        return f"{self.house} — {self.get_management_method_display()}"
