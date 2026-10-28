from adminsortable2.admin import SortableAdminMixin


class ParentFilteredSortableAdminMixin(SortableAdminMixin):
    """Sürükle-bırak sıralama yalnız üst kayıt filtresi seçiliyken açık (ör. tek bir kursun bölümleri).

    Sıra alanı her üst kayıt içinde ayrı tutulur; filtresiz listede farklı kursların kayıtları karışacağı için
    sürükleme kapatılır. sort_parent_filter, list_filter'daki üst alanın GET parametresidir (ör. "course__id__exact").
    """

    sort_parent_filter = None

    def get_changelist_instance(self, request):
        changelist = super().get_changelist_instance(request)
        if self.sort_parent_filter and self.sort_parent_filter not in request.GET:
            self.enable_sorting = False
        return changelist
