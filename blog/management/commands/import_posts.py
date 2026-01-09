"""
Management command to import existing markdown posts from content/posts/ directory.

This command reads markdown files with YAML frontmatter and creates BlogPost entries
in the database. It handles tags, dates, and preserves existing posts based on slug.
"""

from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
import frontmatter

from blog.models import BlogPost, Tag


class Command(BaseCommand):
    help = 'Import markdown posts from content/posts/ directory'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing posts if they already exist (by slug)',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip posts that already exist (by slug)',
        )
        parser.add_argument(
            '--posts-dir',
            type=str,
            default='content/posts',
            help='Directory containing markdown posts (default: content/posts)',
        )

    def handle(self, *args, **options):
        posts_dir = Path(settings.BASE_DIR) / options['posts_dir']
        
        if not posts_dir.exists():
            raise CommandError(f'Posts directory does not exist: {posts_dir}')
        
        if not posts_dir.is_dir():
            raise CommandError(f'Posts path is not a directory: {posts_dir}')

        # Get all markdown files
        markdown_files = list(posts_dir.glob('*.md'))
        
        if not markdown_files:
            self.stdout.write(self.style.WARNING(f'No markdown files found in {posts_dir}'))
            return

        self.stdout.write(f'Found {len(markdown_files)} markdown file(s) to import')

        imported_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        for md_file in markdown_files:
            try:
                result = self.import_post(md_file, options)
                if result == 'imported':
                    imported_count += 1
                elif result == 'updated':
                    updated_count += 1
                elif result == 'skipped':
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Error importing {md_file.name}: {str(e)}')
                )

        # Summary
        self.stdout.write(self.style.SUCCESS('\n=== Import Summary ==='))
        self.stdout.write(f'Imported: {imported_count}')
        self.stdout.write(f'Updated: {updated_count}')
        self.stdout.write(f'Skipped: {skipped_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))

    def import_post(self, md_file, options):
        """Import a single markdown file as a BlogPost."""
        self.stdout.write(f'Processing: {md_file.name}')

        # Read and parse the markdown file
        with open(md_file, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)

        # Extract frontmatter data
        title = post.metadata.get('title', '')
        if not title:
            raise ValueError(f'Missing title in frontmatter for {md_file.name}')

        date_str = post.metadata.get('date', '')
        tags = post.metadata.get('tags', [])
        content = post.content.strip()

        # Parse date
        published_date = None
        if date_str:
            try:
                # Try parsing as YYYY-MM-DD format
                if isinstance(date_str, str):
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    # Make it timezone-aware
                    published_date = timezone.make_aware(
                        datetime.combine(date_obj.date(), datetime.min.time())
                    )
                else:
                    # If it's already a date/datetime object
                    if isinstance(date_str, datetime):
                        published_date = timezone.make_aware(date_str) if timezone.is_naive(date_str) else date_str
            except (ValueError, TypeError) as e:
                self.stdout.write(
                    self.style.WARNING(f'Could not parse date "{date_str}" for {md_file.name}: {e}')
                )

        # Generate slug from title
        slug = slugify(title)

        # Check if post already exists
        existing_post = None
        try:
            existing_post = BlogPost.objects.get(slug=slug)
        except BlogPost.DoesNotExist:
            pass

        # Handle existing posts
        if existing_post:
            if options['skip_existing']:
                self.stdout.write(self.style.WARNING(f'  Skipping existing post: {title}'))
                return 'skipped'
            elif options['update']:
                self.stdout.write(f'  Updating existing post: {title}')
                blog_post = existing_post
            else:
                # Default: skip if exists and no flags set
                self.stdout.write(self.style.WARNING(f'  Post already exists: {title} (use --update to overwrite or --skip-existing to skip)'))
                return 'skipped'
        else:
            blog_post = BlogPost()
            self.stdout.write(f'  Creating new post: {title}')

        # Set post fields
        blog_post.title = title
        blog_post.slug = slug
        blog_post.content = content
        blog_post.published_date = published_date
        blog_post.is_published = True  # Mark imported posts as published
        blog_post.save()

        # Handle tags
        if tags:
            tag_objects = []
            for tag_name in tags:
                if not tag_name:
                    continue
                # Get or create tag
                tag, created = Tag.objects.get_or_create(
                    name=tag_name,
                    defaults={'slug': slugify(tag_name)}
                )
                tag_objects.append(tag)
                if created:
                    self.stdout.write(f'    Created tag: {tag_name}')

            # Set tags (this replaces existing tags)
            blog_post.tags.set(tag_objects)
            self.stdout.write(f'    Added {len(tag_objects)} tag(s)')

        return 'updated' if existing_post else 'imported'
