"""IP Allocation Job — assign primary IPs from a prefix.

Module 7, Exercise 1 (Slide 17): IP Allocation Use Case
Nautobot 40-Hour Training Program (Techademy)
"""

from nautobot.apps.jobs import Job, ObjectVar, BooleanVar
from nautobot.dcim.models import Device, Location, Interface
from nautobot.ipam.models import Prefix, IPAddress
from nautobot.extras.models import Status


class IPAllocation(Job):
    """Allocate primary IP addresses to devices from a management prefix."""

    class Meta:
        name = "IP Address Allocation"
        description = "Assign primary IPv4 addresses to devices without one, pulling from a specified prefix"
        has_sensitive_variables = False

    prefix = ObjectVar(
        model=Prefix,
        required=True,
        description="Management prefix to allocate IPs from (e.g., 10.0.0.0/24)",
    )
    location = ObjectVar(
        model=Location,
        required=False,
        description="Filter devices by location",
    )
    dry_run = BooleanVar(
        default=True,
        description="Preview allocations without saving",
    )

    def run(self, prefix=None, location=None, dry_run=True):
        devices = Device.objects.filter(primary_ip4__isnull=True)
        if location:
            devices = devices.filter(location=location)

        self.logger.info(
            f"Found {devices.count()} devices without primary IPv4 "
            f"(allocating from {prefix.prefix})"
        )

        allocated = 0
        skipped = 0
        errors = 0

        active_status = Status.objects.get(name="Active")

        available_ips = prefix.get_available_ips()
        if not available_ips:
            self.logger.failure(f"No available IPs in {prefix.prefix}")
            return

        for device in devices:
            try:
                mgmt_iface = Interface.objects.filter(
                    device=device,
                    name__iregex=r"^(management|mgmt|loopback)"
                ).first()

                if not mgmt_iface:
                    mgmt_iface = Interface.objects.filter(device=device).first()

                if not mgmt_iface:
                    self.logger.warning(f"{device.name}: no interfaces — skipping", obj=device)
                    skipped += 1
                    continue

                available_ips = prefix.get_available_ips()
                if not available_ips:
                    self.logger.failure(f"Prefix exhausted after {allocated} allocations")
                    break

                next_ip = str(available_ips.iter_cidrs()[0]).split("/")[0]
                prefix_length = str(prefix.prefix).split("/")[1]
                ip_with_mask = f"{next_ip}/{prefix_length}"

                if dry_run:
                    self.logger.success(
                        f"[DRY RUN] {device.name}: would assign {ip_with_mask} "
                        f"to {mgmt_iface.name}",
                        obj=device,
                    )
                else:
                    ip_address = IPAddress(
                        address=ip_with_mask,
                        status=active_status,
                    )
                    ip_address.validated_save()
                    ip_address.interfaces.add(mgmt_iface)

                    device.primary_ip4 = ip_address
                    device.validated_save()

                    self.logger.success(
                        f"{device.name}: assigned {ip_with_mask} to {mgmt_iface.name}",
                        obj=device,
                    )

                allocated += 1

            except Exception as e:
                self.logger.failure(f"{device.name}: {e}", obj=device)
                errors += 1

        mode = "DRY RUN" if dry_run else "LIVE"
        self.logger.info(
            f"[{mode}] Complete: {allocated} allocated, "
            f"{skipped} skipped, {errors} errors"
        )
