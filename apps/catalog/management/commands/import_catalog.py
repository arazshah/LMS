"""Import courses from an Excel file.

    python manage.py import_catalog catalog.xlsx --covers covers/ [--dry-run] [--replace-covers]

`--covers` is a folder or a .zip of images named by course/bundle code (F2.png) or by the
«تصویر» column. Safe to re-run: existing rows are updated, not duplicated.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.importer import CoverSource, import_workbook


class Command(BaseCommand):
    help = "Import categories/courses/lessons/bundles from an Excel workbook"

    def add_arguments(self, parser):
        parser.add_argument("workbook", help="path to the .xlsx file")
        parser.add_argument("--covers", help="folder or .zip with cover images")
        parser.add_argument("--dry-run", action="store_true", help="validate only, save nothing")
        parser.add_argument("--replace-covers", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["workbook"])
        if not path.is_file():
            raise CommandError(f"فایل پیدا نشد: {path}")
        covers = None
        if options["covers"]:
            source = Path(options["covers"])
            if source.is_dir():
                covers = CoverSource.from_dir(source)
            elif source.is_file():
                with source.open("rb") as handle:
                    covers = CoverSource.from_zip(handle)
            else:
                raise CommandError(f"مسیر تصاویر پیدا نشد: {source}")
        with path.open("rb") as handle:
            report = import_workbook(
                handle,
                covers=covers,
                dry_run=options["dry_run"],
                replace_covers=options["replace_covers"],
            )
        for warning in report.warnings:
            self.stdout.write(self.style.WARNING(f"! {warning}"))
        if not report.ok:
            for error in report.errors:
                self.stderr.write(self.style.ERROR(f"✗ {error}"))
            raise CommandError("ایمپورت انجام نشد.")
        label = "بررسی (ذخیره نشد)" if report.dry_run else "انجام شد"
        self.stdout.write(self.style.SUCCESS(f"ایمپورت {label}:"))
        for line in report.lines():
            self.stdout.write(f"  {line}")
