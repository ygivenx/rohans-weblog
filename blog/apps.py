from django.apps import AppConfig


class BlogConfig(AppConfig):
    name = "blog"

    def ready(self):
        from django.core.cache import cache
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from .context_processors import invalidate_all_tags_cache
        from .models import (
            BlogPost,
            DailyBriefing,
            FeedItem,
            ProductUpdate,
            Sponsor,
            TIL,
            Tag,
        )

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

        def invalidate_sponsors(**kwargs):
            cache.delete_many(
                [
                    "blog:sponsor:all",
                    "blog:sponsor:hackerstack",
                    "blog:sponsor:digests",
                ]
            )

        def invalidate_products(**kwargs):
            cache.delete("blog:gumroad_products")

        post_save.connect(
            invalidate_sponsors, sender=Sponsor, dispatch_uid="blog_sponsor_save"
        )
        post_delete.connect(
            invalidate_sponsors, sender=Sponsor, dispatch_uid="blog_sponsor_delete"
        )
        post_save.connect(
            invalidate_products,
            sender=ProductUpdate,
            dispatch_uid="blog_product_save",
        )
        post_delete.connect(
            invalidate_products,
            sender=ProductUpdate,
            dispatch_uid="blog_product_delete",
        )
