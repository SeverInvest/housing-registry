from django.db import models


class ManagementMethod(models.TextChoices):
    UO = "uo", "Управляющая организация"
    HOA_COOPERATIVE = "hoa_cooperative", "ТСЖ/ТСН/ЖСК/ЖК"
    DIRECT = "direct", "Непосредственное управление"
    UNKNOWN = "unknown", "Не определён"


class UOSelectionMethod(models.TextChoices):
    OWNERS = "owners", "Выбрана собственниками"
    MUNICIPALITY = "municipality", "Назначена муниципалитетом"
    UNKNOWN = "unknown", "Не установлено"


class ImportSource(models.TextChoices):
    GIS_SEARCH = "gis_search", "ГИС ЖКХ — поиск"
    GIS_DETAIL = "gis_detail", "ГИС ЖКХ — карточка"
    LICENSE_REGISTRY = "license_registry", "Реестр лицензий"
    ADMIN_REGISTRY = "admin_registry", "Реестр назначенных УО"
    MANUAL = "manual", "Ручное изменение"


class ImportStatus(models.TextChoices):
    RUNNING = "running", "Выполняется"
    COMPLETED = "completed", "Завершён"
    COMPLETED_WITH_ERRORS = "completed_with_errors", "Завершён с ошибками"
    FAILED = "failed", "Ошибка"


class Region(models.Model):
    code = models.CharField("Код региона", max_length=3, unique=True)
    name = models.CharField("Наименование", max_length=255, unique=True)
    fias_guid = models.UUIDField("GUID региона по ФИАС", unique=True)
    federal_district = models.CharField("Федеральный округ", max_length=255, blank=True)
    sync_enabled = models.BooleanField("Синхронизация включена", default=True, db_index=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Регион"
        verbose_name_plural = "Регионы"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Organization(models.Model):
    gis_guid = models.UUIDField("GUID организации в ГИС ЖКХ", null=True, blank=True, unique=True)
    registry_root_guid = models.UUIDField("Корневой GUID организации", null=True, blank=True)
    ogrn = models.CharField("ОГРН/ОГРНИП", max_length=15, blank=True, db_index=True)
    inn = models.CharField("ИНН", max_length=12, blank=True, db_index=True)
    full_name = models.TextField("Полное наименование")
    short_name = models.TextField("Краткое наименование", blank=True)
    organization_type = models.CharField("Код типа организации", max_length=32, blank=True)
    okopf_code = models.CharField("Код ОКОПФ", max_length=16, blank=True)
    address = models.TextField("Адрес", blank=True)
    phone = models.CharField("Телефон", max_length=128, blank=True)
    website = models.URLField("Сайт", max_length=500, blank=True)
    source_last_event_date = models.DateField(
        "Дата последнего события организации", null=True, blank=True
    )
    raw_data = models.JSONField("Исходные данные", default=dict, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ("full_name",)
        indexes = [models.Index(fields=("ogrn", "inn"), name="org_ogrn_inn_idx")]

    def __str__(self) -> str:
        suffix = f" ({self.ogrn})" if self.ogrn else ""
        return f"{self.short_name or self.full_name}{suffix}"


class ImportRun(models.Model):
    region = models.ForeignKey(
        Region,
        verbose_name="Регион",
        related_name="import_runs",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    source = models.CharField("Источник", max_length=32, choices=ImportSource.choices)
    status = models.CharField(
        "Статус",
        max_length=32,
        choices=ImportStatus.choices,
        default=ImportStatus.RUNNING,
    )
    parameters = models.JSONField("Параметры", default=dict, blank=True)
    started_at = models.DateTimeField("Начало", auto_now_add=True)
    finished_at = models.DateTimeField("Окончание", null=True, blank=True)
    total_expected = models.PositiveIntegerField("Ожидалось записей", default=0)
    processed = models.PositiveIntegerField("Обработано", default=0)
    created_count = models.PositiveIntegerField("Создано", default=0)
    updated_count = models.PositiveIntegerField("Изменено", default=0)
    unchanged_count = models.PositiveIntegerField("Без изменений", default=0)
    error_count = models.PositiveIntegerField("Ошибок", default=0)
    message = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Запуск импорта"
        verbose_name_plural = "Запуски импорта"
        ordering = ("-started_at",)

    def __str__(self) -> str:
        return f"{self.get_source_display()} — {self.started_at:%d.%m.%Y %H:%M}"


class House(models.Model):
    region = models.ForeignKey(
        Region,
        verbose_name="Регион",
        related_name="houses",
        on_delete=models.PROTECT,
    )
    gis_guid = models.UUIDField("Глобальный GUID объекта ГИС ЖКХ", unique=True)
    gis_address_guid = models.UUIDField(
        "GUID адреса в ГИС ЖКХ", null=True, blank=True, db_index=True
    )
    fias_house_guid = models.UUIDField("GUID дома по ФИАС", null=True, blank=True, db_index=True)
    house_uid = models.CharField(
        "Внутренний номер ГИС ЖКХ", max_length=64, blank=True, db_index=True
    )

    formatted_address = models.TextField("Адрес")
    postal_code = models.CharField("Почтовый индекс", max_length=12, blank=True)
    region_name = models.CharField("Регион", max_length=255, blank=True)
    municipality_name = models.CharField("Муниципальное образование", max_length=255, blank=True)
    locality_name = models.CharField("Населённый пункт", max_length=255, blank=True)
    street_name = models.CharField("Улица", max_length=255, blank=True)
    oktmo = models.CharField("ОКТМО", max_length=16, blank=True, db_index=True)

    house_type_code = models.CharField("Код типа дома", max_length=16, blank=True, db_index=True)
    house_type_name = models.CharField("Тип дома", max_length=128, blank=True, db_index=True)
    management_method = models.CharField(
        "Способ управления",
        max_length=32,
        choices=ManagementMethod.choices,
        default=ManagementMethod.UNKNOWN,
        db_index=True,
    )
    management_method_code = models.CharField("Код способа управления", max_length=16, blank=True)
    management_method_name = models.CharField(
        "Способ управления — источник", max_length=128, blank=True
    )
    management_organization = models.ForeignKey(
        Organization,
        verbose_name="Управляющая организация/ТСЖ/кооператив",
        related_name="managed_houses",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    uo_selection_method = models.CharField(
        "Способ выбора УО",
        max_length=32,
        choices=UOSelectionMethod.choices,
        default=UOSelectionMethod.UNKNOWN,
        db_index=True,
    )
    management_start_date = models.DateField("Дата начала управления", null=True, blank=True)
    management_end_date = models.DateField("Дата окончания управления", null=True, blank=True)

    total_square = models.DecimalField(
        "Общая площадь, м²", max_digits=16, decimal_places=4, null=True, blank=True
    )
    residential_square = models.DecimalField(
        "Жилая площадь, м²", max_digits=16, decimal_places=4, null=True, blank=True
    )
    residential_premise_count = models.PositiveIntegerField(
        "Жилых помещений", null=True, blank=True
    )
    non_residential_premise_count = models.PositiveIntegerField(
        "Нежилых помещений", null=True, blank=True
    )
    min_floor_count = models.PositiveSmallIntegerField("Минимум этажей", null=True, blank=True)
    max_floor_count = models.PositiveSmallIntegerField("Максимум этажей", null=True, blank=True)
    underground_floor_count = models.PositiveSmallIntegerField(
        "Подземных этажей", null=True, blank=True
    )
    building_year = models.PositiveSmallIntegerField("Год постройки", null=True, blank=True)
    operation_year = models.PositiveSmallIntegerField(
        "Год ввода в эксплуатацию", null=True, blank=True
    )
    reconstruction_year = models.PositiveSmallIntegerField(
        "Год реконструкции", null=True, blank=True
    )
    cadastre_number = models.CharField(
        "Кадастровый номер", max_length=128, blank=True, db_index=True
    )
    wall_material = models.TextField("Материал стен", blank=True)
    house_condition = models.CharField("Состояние", max_length=128, blank=True)
    life_cycle_stage = models.CharField("Стадия жизненного цикла", max_length=128, blank=True)
    source_status = models.CharField("Статус в источнике", max_length=32, blank=True)
    approved = models.BooleanField("Утверждён", default=False)
    active = models.BooleanField("Актуален", default=True, db_index=True)
    consecutive_missing_runs = models.PositiveSmallIntegerField(
        "Последовательных пропусков в полном поиске", default=0
    )
    last_missing_at = models.DateTimeField("Последний пропуск в поиске", null=True, blank=True)

    first_seen_at = models.DateTimeField("Впервые обнаружен", auto_now_add=True)
    last_seen_at = models.DateTimeField(
        "Последний раз найден", null=True, blank=True, db_index=True
    )
    detail_fetched_at = models.DateTimeField(
        "Карточка получена", null=True, blank=True, db_index=True
    )
    needs_detail_refresh = models.BooleanField(
        "Нужно обновить карточку", default=True, db_index=True
    )
    search_hash = models.CharField("Хеш поисковой записи", max_length=64, blank=True)
    detail_hash = models.CharField("Хеш карточки", max_length=64, blank=True)
    search_payload = models.JSONField("Последняя поисковая запись", default=dict, blank=True)
    detail_payload = models.JSONField("Последняя карточка", default=dict, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Дом"
        verbose_name_plural = "Дома"
        ordering = ("formatted_address",)
        indexes = [
            models.Index(fields=("region", "active"), name="house_region_active_idx"),
            models.Index(fields=("active", "house_type_code"), name="house_active_type_idx"),
            models.Index(fields=("management_method", "active"), name="house_method_active_idx"),
            models.Index(fields=("oktmo", "active"), name="house_oktmo_active_idx"),
        ]

    def __str__(self) -> str:
        return self.formatted_address


class HouseVersion(models.Model):
    house = models.ForeignKey(
        House, verbose_name="Дом", related_name="versions", on_delete=models.CASCADE
    )
    run = models.ForeignKey(
        ImportRun,
        verbose_name="Запуск импорта",
        related_name="house_versions",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    source = models.CharField("Источник", max_length=32, choices=ImportSource.choices)
    observed_at = models.DateTimeField("Зафиксировано", auto_now_add=True, db_index=True)
    content_hash = models.CharField("Хеш версии", max_length=64, db_index=True)
    changed_fields = models.JSONField("Изменившиеся поля", default=list, blank=True)
    snapshot = models.JSONField("Снимок", default=dict)

    class Meta:
        verbose_name = "Версия дома"
        verbose_name_plural = "История изменений домов"
        ordering = ("-observed_at",)
        indexes = [models.Index(fields=("house", "-observed_at"), name="house_version_time_idx")]

    def __str__(self) -> str:
        return f"{self.house} — {self.observed_at:%d.%m.%Y %H:%M}"


class AdministrativeAppointment(models.Model):
    region = models.ForeignKey(
        Region,
        verbose_name="Регион",
        related_name="administrative_appointments",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    house = models.ForeignKey(
        House,
        verbose_name="Дом",
        related_name="administrative_appointments",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    unresolved_house_guid = models.UUIDField(
        "GUID несопоставленного дома", null=True, blank=True, db_index=True
    )
    organization = models.ForeignKey(
        Organization,
        verbose_name="Назначенная УО",
        related_name="administrative_appointments",
        on_delete=models.PROTECT,
    )
    decision_number = models.CharField("Номер решения", max_length=255, blank=True)
    decision_date = models.DateField("Дата решения", null=True, blank=True)
    starts_on = models.DateField("Начало управления", null=True, blank=True)
    ends_on = models.DateField("Окончание управления", null=True, blank=True)
    active = models.BooleanField("Действует", default=True, db_index=True)
    source_key = models.CharField(
        "Ключ записи источника", max_length=255, blank=True, db_index=True
    )
    raw_data = models.JSONField("Исходные данные", default=dict, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Административное назначение УО"
        verbose_name_plural = "Административные назначения УО"
        ordering = ("-decision_date", "house__formatted_address")

    def __str__(self) -> str:
        house = (
            self.house.formatted_address
            if self.house
            else str(self.unresolved_house_guid or "Дом не сопоставлен")
        )
        return f"{house} — {self.organization}"
