from django.apps import AppConfig


class HackerStackConfig(AppConfig):
    name = "hackerstack"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import Resource
        from .views import invalidate_hs_meta_cache

        post_save.connect(
            invalidate_hs_meta_cache,
            sender=Resource,
            dispatch_uid="hs_meta_save_resource",
        )
        post_delete.connect(
            invalidate_hs_meta_cache,
            sender=Resource,
            dispatch_uid="hs_meta_delete_resource",
        )
