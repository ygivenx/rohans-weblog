from django.core.management.base import BaseCommand

from blog.product_updates import sync_gumroad_products


class Command(BaseCommand):
    help = "Sync listed Gumroad products into ProductUpdate records."

    def handle(self, *args, **options):
        stats = sync_gumroad_products()
        self.stdout.write(
            self.style.SUCCESS(
                "Gumroad sync complete: "
                f"created={stats['created']} updated={stats['updated']} total={stats['total']}"
            )
        )
