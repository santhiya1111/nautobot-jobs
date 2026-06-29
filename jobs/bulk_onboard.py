"""Bulk Device Onboarding Job — import devices from CSV.

Module 7, Exercise 1 (Slide 15): Bulk Onboarding Use Case
Nautobot 40-Hour Training Program (Techademy)
"""

import csv
import io

from nautobot.apps.jobs import Job, FileVar, BooleanVar
from nautobot.dcim.models import Device, Location
from nautobot.extras.models import Role, Status


class BulkOnboard(Job):
    """Onboard devices in bulk from a CSV file."""

    class Meta:
        name = "Bulk Device Onboarding"
        description = "Import devices from a CSV file with columns: name, role, location, status"
        has_sensitive_variables = False

    csv_file = FileVar(
        description="CSV file with columns: name, role, location (optional: status)",
    )
    dry_run = BooleanVar(
        default=True,
        description="Preview mode — show what would be created without saving",
    )

    def run(self, csv_file=None, dry_run=True):
        reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8"))
        created_count = 0
        skipped_count = 0
        error_count = 0

        for row_num, row in enumerate(reader, start=2):
            name = row.get("name", "").strip()
            if not name:
                self.logger.warning(f"Row {row_num}: empty name — skipping")
                skipped_count += 1
                continue

            try:
                role_name = row.get("role", "").strip()
                location_name = row.get("location", "").strip()
                status_name = row.get("status", "Planned").strip()

                role = Role.objects.get(name=role_name) if role_name else None
                location = Location.objects.get(name=location_name) if location_name else None
                status = Status.objects.get(name=status_name)

                if Device.objects.filter(name=name).exists():
                    self.logger.info(f"Row {row_num}: '{name}' already exists — skipping")
                    skipped_count += 1
                    continue

                if dry_run:
                    self.logger.success(
                        f"[DRY RUN] Would create: {name} "
                        f"(role={role_name}, location={location_name}, status={status_name})"
                    )
                else:
                    device = Device(
                        name=name,
                        role=role,
                        location=location,
                        status=status,
                    )
                    device.validated_save()
                    self.logger.success(f"Created: {device.name}", obj=device)

                created_count += 1

            except Role.DoesNotExist:
                self.logger.failure(f"Row {row_num}: role '{role_name}' not found", obj=None)
                error_count += 1
            except Location.DoesNotExist:
                self.logger.failure(f"Row {row_num}: location '{location_name}' not found", obj=None)
                error_count += 1
            except Status.DoesNotExist:
                self.logger.failure(f"Row {row_num}: status '{status_name}' not found", obj=None)
                error_count += 1
            except Exception as e:
                self.logger.failure(f"Row {row_num}: {e}")
                error_count += 1

        mode = "DRY RUN" if dry_run else "LIVE"
        self.logger.info(
            f"[{mode}] Complete: {created_count} created, "
            f"{skipped_count} skipped, {error_count} errors"
        )
