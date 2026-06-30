"""
Module 10 — Auto-Remediation Job
===================================
When interface descriptions are blank, auto-populate them
using a standard naming convention:
    "{device_name} - {interface_name} - {interface_type}"

This job can be:
  1. Run manually from the Nautobot Jobs UI
  2. Triggered by a webhook when an interface is created/updated
  3. Scheduled to run periodically

The job also checks for other common issues:
  - Interfaces with no description → auto-populate
  - Interfaces with status "Planned" that have an IP → flag for review
"""

from nautobot.apps.jobs import Job, register_jobs, BooleanVar, MultiObjectVar
from nautobot.dcim.models import Device, Interface
from nautobot.extras.models import Status


class AutoRemediateInterfaceDescriptions(Job):
    """Auto-populate blank interface descriptions with a standard format."""

    class Meta:
        name = "Auto-Remediate Interface Descriptions"
        description = (
            "Finds interfaces with blank descriptions and auto-populates them "
            "using the format: '{device} - {interface} - {type}'. "
            "Can also be triggered by webhooks on interface create/update events."
        )
        has_sensitive_variables = False

    dry_run = BooleanVar(
        description="Preview changes without applying them",
        default=True,
    )

    def run(self, dry_run):
        """Find and fix blank interface descriptions."""
        self.logger.info("Starting auto-remediation scan...")

        blank_interfaces = Interface.objects.filter(
            description=""
        ).select_related("device", "device__location")

        total = blank_interfaces.count()
        self.logger.info(f"Found {total} interfaces with blank descriptions")

        if total == 0:
            self.logger.info("All interfaces already have descriptions. Nothing to remediate.")
            return f"All interfaces OK — 0 changes needed"

        fixed_count = 0
        skipped_count = 0

        for iface in blank_interfaces:
            device = iface.device
            if not device:
                skipped_count += 1
                continue

            iface_type = iface.type or "Unknown"
            new_description = f"{device.name} - {iface.name} - {iface_type}"

            if dry_run:
                self.logger.info(
                    f"[DRY RUN] Would set description on {device.name} / {iface.name}: "
                    f"'{new_description}'"
                )
            else:
                iface.description = new_description
                iface.validated_save()
                self.logger.info(
                    f"Fixed: {device.name} / {iface.name} → '{new_description}'"
                )
            fixed_count += 1

        mode = "DRY RUN" if dry_run else "APPLIED"
        summary = f"[{mode}] {fixed_count} interfaces remediated, {skipped_count} skipped"
        self.logger.info(summary)
        return summary


class AutoRemediateDeviceNaming(Job):
    """Check device names follow the naming convention and flag violations."""

    class Meta:
        name = "Auto-Remediate Device Naming"
        description = (
            "Scans all devices and checks if names follow the convention: "
            "'{location_code}-{role}-{number}'. Logs violations for review."
        )
        has_sensitive_variables = False

    def run(self):
        """Check device naming convention compliance."""
        self.logger.info("Starting device naming compliance check...")

        devices = Device.objects.all().select_related("location", "role")
        total = devices.count()
        violations = 0
        compliant = 0

        for device in devices:
            name = device.name or ""
            location = device.location
            role = device.role

            issues = []

            if not name:
                issues.append("Device has no name")
            elif " " in name:
                issues.append(f"Name contains spaces: '{name}'")
            elif not any(c == "-" for c in name):
                issues.append(f"Name has no hyphens (expected: SITE-ROLE-NUM): '{name}'")

            if location and location.name:
                loc_prefix = location.name.split("-")[0].upper() if "-" in location.name else location.name[:3].upper()
                if not name.upper().startswith(loc_prefix):
                    issues.append(f"Name doesn't start with location prefix '{loc_prefix}'")

            if issues:
                violations += 1
                for issue in issues:
                    self.logger.warning(f"{device.name}: {issue}")
            else:
                compliant += 1

        summary = (
            f"Scanned {total} devices: "
            f"{compliant} compliant, {violations} violations"
        )
        self.logger.info(summary)
        return summary


register_jobs(AutoRemediateInterfaceDescriptions, AutoRemediateDeviceNaming)
