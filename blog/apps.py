from django.apps import AppConfig


class BlogConfig(AppConfig):
    name = "blog"

    def ready(self):
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from .context_processors import invalidate_all_tags_cache
        from .models import BlogPost, DailyBriefing, FeedItem, TIL, Tag

        for model in (Tag, BlogPost, TIL, FeedItem, DailyBriefing):
            post_save.connect(
                invalidate_all_tags_cache,
                sender=model,
                dispatch_uid=f"blog_tags_save_{model.__name__}",
            )
            post_delete.connect(
                invalidate_all_tags_cache,
                sender=model,
                dispatch_uid=f"blog_tags_delete_{model.__name__}",
            )

        for model in (BlogPost, TIL, FeedItem, DailyBriefing):
            m2m_changed.connect(
                invalidate_all_tags_cache,
                sender=model.tags.through,
                dispatch_uid=f"blog_tags_m2m_{model.__name__}",
            )
