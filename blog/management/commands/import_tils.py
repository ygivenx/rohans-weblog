"""
Management command to import TILs from a GitHub-style TIL repository.

Handles both markdown (.md) and Jupyter notebook (.ipynb) files.
Uses directory names as tags.
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from blog.models import TIL, Tag


class Command(BaseCommand):
    help = "Import TILs from a directory (e.g., cloned GitHub TIL repo)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tils-dir",
            type=str,
            default="/tmp/tils-import",
            help="Directory containing TIL files (default: /tmp/tils-import)",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing TILs if they already exist (by slug)",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip TILs that already exist (by slug)",
        )

    def handle(self, *args, **options):
        tils_dir = Path(options["tils_dir"])

        if not tils_dir.exists():
            raise CommandError(f"TILs directory does not exist: {tils_dir}")

        if not tils_dir.is_dir():
            raise CommandError(f"TILs path is not a directory: {tils_dir}")

        # Find all markdown and notebook files (excluding README)
        til_files = []
        for pattern in ["**/*.md", "**/*.ipynb"]:
            for f in tils_dir.glob(pattern):
                if f.name.lower() != "readme.md" and f.parent != tils_dir:
                    til_files.append(f)

        if not til_files:
            self.stdout.write(self.style.WARNING(f"No TIL files found in {tils_dir}"))
            return

        self.stdout.write(f"Found {len(til_files)} TIL file(s) to import")

        imported_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        for til_file in til_files:
            try:
                result = self.import_til(til_file, tils_dir, options)
                if result == "imported":
                    imported_count += 1
                elif result == "updated":
                    updated_count += 1
                elif result == "skipped":
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"Error importing {til_file.name}: {str(e)}")
                )

        # Summary
        self.stdout.write(self.style.SUCCESS("\n=== Import Summary ==="))
        self.stdout.write(f"Imported: {imported_count}")
        self.stdout.write(f"Updated: {updated_count}")
        self.stdout.write(f"Skipped: {skipped_count}")
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))

    def import_til(self, til_file: Path, base_dir: Path, options: dict) -> str:
        """Import a single TIL file."""
        self.stdout.write(f"Processing: {til_file.relative_to(base_dir)}")

        # Get tag from directory name
        tag_name = til_file.parent.name

        # Get title from filename
        title = self.filename_to_title(til_file.stem)

        # Get content based on file type
        if til_file.suffix == ".ipynb":
            content = self.extract_notebook_content(til_file)
        else:
            content = til_file.read_text(encoding="utf-8")

        # Generate slug
        slug = slugify(title)

        # Check if TIL already exists
        existing_til = TIL.objects.filter(slug=slug).first()

        if existing_til:
            if options["skip_existing"]:
                self.stdout.write(self.style.WARNING(f"  Skipping existing: {title}"))
                return "skipped"
            elif options["update"]:
                self.stdout.write(f"  Updating existing: {title}")
                til = existing_til
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Already exists: {title} (use --update or --skip-existing)"
                    )
                )
                return "skipped"
        else:
            til = TIL()
            self.stdout.write(f"  Creating new: {title}")

        # Set TIL fields
        til.title = title
        til.slug = slug
        til.content = content
        til.save()

        # Handle tag
        if tag_name:
            tag, created = Tag.objects.get_or_create(
                name=tag_name, defaults={"slug": slugify(tag_name)}
            )
            til.tags.add(tag)
            if created:
                self.stdout.write(f"    Created tag: {tag_name}")
            else:
                self.stdout.write(f"    Added tag: {tag_name}")

        return "updated" if existing_til else "imported"

    def filename_to_title(self, filename: str) -> str:
        """Convert filename to title (kebab-case to Title Case)."""
        # Replace hyphens and underscores with spaces
        title = filename.replace("-", " ").replace("_", " ")
        # Title case
        return title.title()

    def extract_notebook_content(self, notebook_path: Path) -> str:
        """Extract markdown and code cells from a Jupyter notebook."""
        with open(notebook_path, "r", encoding="utf-8") as f:
            notebook = json.load(f)

        content_parts = []
        cells = notebook.get("cells", [])

        for cell in cells:
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))

            if cell_type == "markdown":
                content_parts.append(source)
            elif cell_type == "code":
                content_parts.append(f"```python\n{source}\n```")

        return "\n\n".join(content_parts)
