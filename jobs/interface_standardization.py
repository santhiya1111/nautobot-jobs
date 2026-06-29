"""Interface Standardization Job — enforce naming and description standards.

Module 7, Exercise 1 (Slide 16): Interface Standardization Use Case
Nautobot 40-Hour Training Program (Techademy)
"""

import re

from nautobot.apps.jobs import Job, ObjectVar, BooleanVar
from nautobot.dcim.models import Device, Interface, Location


class InterfaceStandardization(Job):
    """Standardize interface descriptions across devices."""

    class Meta:
        name = "Interface Standardization"
        description = "Enforce naming conventions and description standards on device interfaces"
        has_sensitive_variables = False

    location = ObjectVar(
        model=Location,
        required=False,
        description="Filter devices by location (leave blank for all)",
    )
    dry_run = BooleanVar(
        default=True,
        description="Preview changes without saving",
    )

    UPLINK_PATTERN = re.compile(r"^(Ethernet|GigabitEthernet|TenGigE)\d+/\d+/[0-4][0-8]?$", re.IGNORECASE)
    MGMT_PATTERN = re.compile(r"^(Management|mgmt)\d*", re.IGNORECASE)

    def run(self, location=None, dry_run=True):
        devices = Device.objects.all()
        if location:
            devices = devices.filter(location=location)

        self.logger.info(f"Scanning interfaces on {devices.count()} devices")

        updated = 0
        already_compliant = 0
        total_interfaces = 0

        for device in devices:
            interfaces = Interface.objects.filter(device=device)

            for iface in interfaces:
                total_interfaces += 1
                needs_update = False
                new_description = iface.description or ""

                if self.MGMT_PATTERN.match(iface.name):
                    expected = f"MGMT - {device.name}"
                    if iface.description != expected:
                        new_description = expected
                        needs_update = True

                elif iface.name.startswith("Loopback"):
                    expected = f"LOOPBACK - {device.name}"
                    if iface.description != expected:
                        new_description = expected
                        needs_update = True

                elif not iface.description or iface.description.strip() == "":
                    if iface.cable:
                        far_end = iface.cable.termination_b if iface.cable.termination_a == iface else iface.cable.termination_a
                        if far_end and hasattr(far_end, 'device'):
                            new_description = f"TO {far_end.device.name} {far_end.name}"
                            needs_update = True
                    else:
                        new_description = f"UNUSED - {iface.name}"
                        needs_update = True

                if needs_update:
                    if dry_run:
                        self.logger.info(
                            f"[DRY RUN] {device.name}/{iface.name}: "
                            f"'{iface.description}' -> '{new_description}'",
                            obj=iface,
                        )
                    else:
                        iface.description = new_description
                        try:
                            iface.validated_save()
                            self.logger.success(
                                f"{device.name}/{iface.name}: set to '{new_description}'",
                                obj=iface,
                            )
                        except Exception as e:
                            self.logger.failure(f"{device.name}/{iface.name}: {e}", obj=iface)
                    updated += 1
                else:
                    already_compliant += 1

        mode = "DRY RUN" if dry_run else "LIVE"
        self.logger.info(
            f"[{mode}] Complete: {total_interfaces} interfaces scanned, "
            f"{updated} need updates, {already_compliant} already compliant"
        )
