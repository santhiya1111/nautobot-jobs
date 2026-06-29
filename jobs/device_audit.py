"""Device Audit Job — checks inventory data quality.

Module 7, Exercise 1: Custom Job Development
Nautobot 40-Hour Training Program (Techademy)
"""

from nautobot.apps.jobs import Job, ObjectVar, BooleanVar
from nautobot.dcim.models import Device, Location


class DeviceAudit(Job):
    """Audit device inventory for missing data and quality issues."""

    class Meta:
        name = "Device Inventory Audit"
        description = "Checks for missing primary IPs, empty serial numbers, and unassigned roles across the device inventory."
        has_sensitive_variables = False

    location = ObjectVar(
        model=Location,
        required=False,
        description="Filter devices by location (leave blank for all locations)",
    )
    dry_run = BooleanVar(
        default=True,
        description="Report issues only — do not make any changes",
    )

    def run(self, location=None, dry_run=True):
        devices = Device.objects.all()
        if location:
            devices = devices.filter(location=location)
            self.logger.info(f"Auditing devices at: {location.name}")
        else:
            self.logger.info(f"Auditing ALL {devices.count()} devices")

        total = devices.count()
        issues = {"no_primary_ip": 0, "no_serial": 0, "no_role": 0}
        clean = 0

        for device in devices:
            device_issues = []

            if not device.primary_ip4 and not device.primary_ip6:
                issues["no_primary_ip"] += 1
                device_issues.append("no primary IP")

            if not device.serial or device.serial.strip() == "":
                issues["no_serial"] += 1
                device_issues.append("empty serial number")

                if not dry_run:
                    device.serial = "PENDING-AUDIT"
                    device.validated_save()
                    self.logger.info("Set serial to PENDING-AUDIT")

            if not device.role:
                issues["no_role"] += 1
                device_issues.append("no role assigned")

            if device_issues:
                self.logger.warning(
                    f"{device.name}: {', '.join(device_issues)}",
                )
            else:
                clean += 1
                self.logger.success(f"{device.name}: all checks passed")

        self.logger.info(
            f"Audit complete: {total} devices scanned, "
            f"{clean} clean, "
            f"{issues['no_primary_ip']} missing IP, "
            f"{issues['no_serial']} missing serial, "
            f"{issues['no_role']} missing role"
        )

        if dry_run:
            self.logger.info("DRY RUN — no changes were made")
        else:
            self.logger.info(
                f"LIVE RUN — {issues['no_serial']} serial numbers updated to PENDING-AUDIT"
            )
