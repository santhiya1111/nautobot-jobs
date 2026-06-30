"""
Module 12 — Celery Worker Scaling Demo Jobs
==============================================
10 jobs designed to demonstrate Celery worker scaling.
Each job does real work + simulated processing to take 15-30 seconds,
making the scaling difference visible when running all 10 in parallel.

Demo:
    1. Run all 10 with 1 worker  → ~3-4 minutes (sequential)
    2. Scale to 3 workers        → docker compose up -d --scale celery_worker=3
    3. Run all 10 with 3 workers → ~1 minute (parallel)
"""

import time
from nautobot.apps.jobs import Job, register_jobs, IntegerVar, BooleanVar
from nautobot.dcim.models import Device, Interface, Location, DeviceType, Cable
from nautobot.ipam.models import IPAddress, Prefix, VLAN
from nautobot.extras.models import Status, Role
from django.db.models import Count, Q


# ─── Job 1: Device Inventory Audit ─────────────────────────────

class Job1DeviceInventoryAudit(Job):
    """Scan every device and audit inventory completeness."""

    class Meta:
        name = "Scale Demo 1 — Device Inventory Audit"
        description = "Checks every device for missing fields: serial, asset_tag, platform, primary IP."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting device inventory audit...")
        devices = Device.objects.all().select_related("device_type", "location", "role")
        total = devices.count()
        issues = {"no_serial": 0, "no_platform": 0, "no_primary_ip": 0, "no_comments": 0}

        for device in devices:
            time.sleep(0.3)
            if not device.serial:
                issues["no_serial"] += 1
            if not device.platform:
                issues["no_platform"] += 1
            if not device.primary_ip4 and not device.primary_ip6:
                issues["no_primary_ip"] += 1
            if not device.comments:
                issues["no_comments"] += 1

        for field, count in issues.items():
            pct = (count / total * 100) if total else 0
            self.logger.info(f"  {field}: {count}/{total} devices ({pct:.0f}%)")

        time.sleep(5)
        summary = f"Audited {total} devices. {sum(issues.values())} total gaps found."
        self.logger.info(summary)
        return summary


# ─── Job 2: Interface Description Compliance ───────────────────

class Job2InterfaceCompliance(Job):
    """Check all interfaces for description compliance."""

    class Meta:
        name = "Scale Demo 2 — Interface Description Compliance"
        description = "Scans all interfaces and reports which have blank or non-standard descriptions."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting interface compliance scan...")
        interfaces = Interface.objects.all().select_related("device")
        total = interfaces.count()
        blank = 0
        short = 0
        compliant = 0

        for iface in interfaces:
            time.sleep(0.1)
            desc = iface.description or ""
            if not desc:
                blank += 1
            elif len(desc) < 5:
                short += 1
            else:
                compliant += 1

        time.sleep(5)
        summary = (
            f"Scanned {total} interfaces: "
            f"{compliant} compliant, {blank} blank, {short} too short"
        )
        self.logger.info(summary)
        return summary


# ─── Job 3: Location Capacity Analysis ─────────────────────────

class Job3LocationCapacity(Job):
    """Analyze device capacity at each location."""

    class Meta:
        name = "Scale Demo 3 — Location Capacity Analysis"
        description = "Counts devices per location and identifies over/under-utilized sites."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting location capacity analysis...")
        locations = Location.objects.annotate(
            device_count=Count("devices")
        ).order_by("-device_count")

        total_locations = locations.count()
        total_devices = 0

        for loc in locations:
            time.sleep(0.5)
            total_devices += loc.device_count
            self.logger.info(f"  {loc.name}: {loc.device_count} devices")

        avg = total_devices / total_locations if total_locations else 0

        time.sleep(5)
        summary = (
            f"Analyzed {total_locations} locations, {total_devices} total devices. "
            f"Average: {avg:.1f} devices/location."
        )
        self.logger.info(summary)
        return summary


# ─── Job 4: IP Address Utilization Report ──────────────────────

class Job4IPUtilization(Job):
    """Calculate IP address utilization per prefix."""

    class Meta:
        name = "Scale Demo 4 — IP Address Utilization"
        description = "Calculates used vs available IPs for each prefix and flags high-utilization subnets."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting IP utilization analysis...")
        prefixes = Prefix.objects.all().select_related("namespace")
        total_prefixes = prefixes.count()
        high_util = 0

        for prefix in prefixes:
            time.sleep(0.4)
            ip_count = IPAddress.objects.filter(
                parent__in=Prefix.objects.filter(pk=prefix.pk)
            ).count()

            try:
                import ipaddress
                net = ipaddress.ip_network(str(prefix.prefix), strict=False)
                capacity = net.num_addresses - 2 if net.num_addresses > 2 else net.num_addresses
                utilization = (ip_count / capacity * 100) if capacity > 0 else 0
            except Exception:
                utilization = 0

            if utilization > 80:
                high_util += 1
                self.logger.warning(f"  HIGH: {prefix.prefix} — {utilization:.0f}% used")

        time.sleep(5)
        summary = f"Analyzed {total_prefixes} prefixes. {high_util} at >80% utilization."
        self.logger.info(summary)
        return summary


# ─── Job 5: Device Type Standardization ────────────────────────

class Job5DeviceTypeStandards(Job):
    """Check device type standardization across the fleet."""

    class Meta:
        name = "Scale Demo 5 — Device Type Standardization"
        description = "Identifies device types with few instances (potential consolidation candidates)."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting device type standardization check...")
        device_types = DeviceType.objects.annotate(
            device_count=Count("devices")
        ).order_by("-device_count")

        total_types = device_types.count()
        singleton_types = 0
        popular_types = 0

        for dt in device_types:
            time.sleep(0.4)
            manufacturer = dt.manufacturer.name if dt.manufacturer else "Unknown"
            self.logger.info(f"  {manufacturer} {dt.model}: {dt.device_count} devices")

            if dt.device_count <= 1:
                singleton_types += 1
            elif dt.device_count >= 5:
                popular_types += 1

        time.sleep(5)
        summary = (
            f"Analyzed {total_types} device types. "
            f"{popular_types} popular (5+), {singleton_types} singletons."
        )
        self.logger.info(summary)
        return summary


# ─── Job 6: Cable Audit ────────────────────────────────────────

class Job6CableAudit(Job):
    """Audit all cables for completeness and consistency."""

    class Meta:
        name = "Scale Demo 6 — Cable Audit"
        description = "Checks all cables have both terminations and validates cable types."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting cable audit...")
        cables = Cable.objects.all()
        total = cables.count()
        issues = 0

        for cable in cables:
            time.sleep(0.3)
            a_terms = cable.termination_a_type
            b_terms = cable.termination_b_type

            if not a_terms or not b_terms:
                issues += 1
                self.logger.warning(f"  Cable {cable.id}: missing termination")

            if not cable.status:
                issues += 1
                self.logger.warning(f"  Cable {cable.id}: no status set")

        time.sleep(5)
        summary = f"Audited {total} cables. {issues} issues found."
        self.logger.info(summary)
        return summary


# ─── Job 7: VLAN Consistency Check ─────────────────────────────

class Job7VLANConsistency(Job):
    """Check VLAN assignments for consistency."""

    class Meta:
        name = "Scale Demo 7 — VLAN Consistency Check"
        description = "Validates VLAN IDs, names, and checks for duplicates within the same location."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting VLAN consistency check...")
        vlans = VLAN.objects.all().select_related("vlan_group", "location")
        total = vlans.count()
        duplicates = 0
        no_name = 0
        seen = {}

        for vlan in vlans:
            time.sleep(0.3)
            if not vlan.name:
                no_name += 1

            loc_name = vlan.location.name if vlan.location else "global"
            key = f"{loc_name}-{vlan.vid}"
            if key in seen:
                duplicates += 1
                self.logger.warning(
                    f"  Duplicate VLAN {vlan.vid} at {loc_name}: "
                    f"'{vlan.name}' vs '{seen[key]}'"
                )
            else:
                seen[key] = vlan.name or "(unnamed)"

        time.sleep(5)
        summary = f"Checked {total} VLANs. {duplicates} duplicates, {no_name} unnamed."
        self.logger.info(summary)
        return summary


# ─── Job 8: Role Assignment Audit ──────────────────────────────

class Job8RoleAudit(Job):
    """Audit device role assignments for consistency."""

    class Meta:
        name = "Scale Demo 8 — Role Assignment Audit"
        description = "Checks device role distribution and finds devices without proper role assignment."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting role assignment audit...")
        roles = Role.objects.annotate(
            device_count=Count("devices")
        ).order_by("-device_count")

        total_roles = roles.count()
        empty_roles = 0

        for role in roles:
            time.sleep(0.5)
            self.logger.info(f"  {role.name}: {role.device_count} devices")
            if role.device_count == 0:
                empty_roles += 1

        devices_no_role = Device.objects.filter(role__isnull=True).count()
        if devices_no_role:
            self.logger.warning(f"  {devices_no_role} devices have no role assigned!")

        time.sleep(5)
        summary = (
            f"Checked {total_roles} roles. "
            f"{empty_roles} unused roles, {devices_no_role} devices without role."
        )
        self.logger.info(summary)
        return summary


# ─── Job 9: Naming Convention Validator ────────────────────────

class Job9NamingValidator(Job):
    """Validate naming conventions across all object types."""

    class Meta:
        name = "Scale Demo 9 — Naming Convention Validator"
        description = "Checks devices, interfaces, and locations for naming standard violations."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting naming convention validation...")
        violations = 0
        total_checked = 0

        # Check device names
        for device in Device.objects.all():
            time.sleep(0.2)
            total_checked += 1
            name = device.name or ""
            if " " in name:
                violations += 1
                self.logger.warning(f"  Device '{name}': contains spaces")
            if name != name.strip():
                violations += 1
                self.logger.warning(f"  Device '{name}': leading/trailing whitespace")
            if any(c in name for c in "!@#$%^&*()+=[]{}|;:',<>?"):
                violations += 1
                self.logger.warning(f"  Device '{name}': contains special characters")

        # Check location names
        for location in Location.objects.all():
            time.sleep(0.2)
            total_checked += 1
            name = location.name or ""
            if name != name.strip():
                violations += 1
                self.logger.warning(f"  Location '{name}': whitespace issue")

        time.sleep(5)
        summary = f"Validated {total_checked} object names. {violations} violations found."
        self.logger.info(summary)
        return summary


# ─── Job 10: Full Infrastructure Report ───────────────────────

class Job10InfraReport(Job):
    """Generate a comprehensive infrastructure summary report."""

    class Meta:
        name = "Scale Demo 10 — Full Infrastructure Report"
        description = "Counts all major object types, computes stats, and generates a summary report."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Generating full infrastructure report...")

        time.sleep(2)
        device_count = Device.objects.count()
        self.logger.info(f"  Devices:      {device_count}")

        time.sleep(1)
        iface_count = Interface.objects.count()
        self.logger.info(f"  Interfaces:   {iface_count}")

        time.sleep(1)
        ip_count = IPAddress.objects.count()
        self.logger.info(f"  IP Addresses: {ip_count}")

        time.sleep(1)
        prefix_count = Prefix.objects.count()
        self.logger.info(f"  Prefixes:     {prefix_count}")

        time.sleep(1)
        vlan_count = VLAN.objects.count()
        self.logger.info(f"  VLANs:        {vlan_count}")

        time.sleep(1)
        cable_count = Cable.objects.count()
        self.logger.info(f"  Cables:       {cable_count}")

        time.sleep(1)
        location_count = Location.objects.count()
        self.logger.info(f"  Locations:    {location_count}")

        time.sleep(1)
        dt_count = DeviceType.objects.count()
        self.logger.info(f"  Device Types: {dt_count}")

        # Per-status breakdown
        time.sleep(2)
        self.logger.info("\n  Devices by Status:")
        status_counts = (
            Device.objects.values("status__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        for sc in status_counts:
            self.logger.info(f"    {sc['status__name']}: {sc['count']}")

        time.sleep(3)
        total_objects = (
            device_count + iface_count + ip_count +
            prefix_count + vlan_count + cable_count +
            location_count + dt_count
        )
        summary = (
            f"Infrastructure Report: {total_objects} total objects across 8 categories. "
            f"{device_count} devices, {iface_count} interfaces, {ip_count} IPs."
        )
        self.logger.info(summary)
        return summary


register_jobs(
    Job1DeviceInventoryAudit,
    Job2InterfaceCompliance,
    Job3LocationCapacity,
    Job4IPUtilization,
    Job5DeviceTypeStandards,
    Job6CableAudit,
    Job7VLANConsistency,
    Job8RoleAudit,
    Job9NamingValidator,
    Job10InfraReport,
)
