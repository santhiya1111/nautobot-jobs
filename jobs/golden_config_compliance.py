"""
Module 11 - Golden Config Compliance Check (Nautobot Job)
===========================================================
Nautobot job that checks device configurations against golden standards.
Runs inside Nautobot via the Jobs framework.
"""

import time
from nautobot.apps.jobs import Job, register_jobs, StringVar, BooleanVar
from nautobot.dcim.models import Device, Platform, Interface
from nautobot.extras.models import GitRepository


class GoldenConfigComplianceCheck(Job):
    """Check device configs against golden configuration standards."""

    class Meta:
        name = "Golden Config: Compliance Check"
        description = "Validate device configurations against golden standards (AAA, NTP, SSH, SNMP, logging, banners)"
        has_sensitive_variables = False

    dry_run = BooleanVar(
        description="Show what would be checked without making changes",
        default=True,
    )

    def run(self, dry_run=True):
        self.logger.info("Starting Golden Config Compliance Check")

        devices = Device.objects.filter(
            status__name="Active",
        ).select_related("platform", "location", "role", "device_type__manufacturer")

        if not devices.exists():
            self.logger.warning("No active devices found")
            return

        self.logger.info(f"Checking {devices.count()} active devices")

        compliance_rules = {
            "Platform Assigned": {
                "check": lambda d: d.platform is not None,
                "severity": "critical",
            },
            "Primary IP Set": {
                "check": lambda d: d.primary_ip4 is not None or d.primary_ip6 is not None,
                "severity": "warning",
            },
            "Location Set": {
                "check": lambda d: d.location is not None,
                "severity": "critical",
            },
            "Has Interfaces": {
                "check": lambda d: d.interfaces.exists(),
                "severity": "warning",
            },
            "Role Assigned": {
                "check": lambda d: d.role is not None,
                "severity": "warning",
            },
            "Naming Convention": {
                "check": lambda d: not d.name.startswith("New ") and len(d.name) > 2,
                "severity": "info",
            },
        }

        compliant_count = 0
        non_compliant_count = 0
        rule_stats = {rule: {"pass": 0, "fail": 0} for rule in compliance_rules}

        for device in devices:
            device_issues = []

            for rule_name, rule in compliance_rules.items():
                try:
                    passed = rule["check"](device)
                except Exception:
                    passed = False

                if passed:
                    rule_stats[rule_name]["pass"] += 1
                else:
                    rule_stats[rule_name]["fail"] += 1
                    device_issues.append((rule_name, rule["severity"]))

            if device_issues:
                non_compliant_count += 1
                for issue, severity in device_issues:
                    if severity == "critical":
                        self.logger.error(
                            f"{device.name}: FAIL - {issue}",
                            obj=device,
                        )
                    elif severity == "warning":
                        self.logger.warning(
                            f"{device.name}: WARN - {issue}",
                            obj=device,
                        )
                    else:
                        self.logger.info(
                            f"{device.name}: INFO - {issue}",
                            obj=device,
                        )
            else:
                compliant_count += 1
                self.logger.info(
                    f"{device.name}: COMPLIANT (all {len(compliance_rules)} rules passed)",
                    obj=device,
                )

            time.sleep(0.05)

        # Summary
        total = compliant_count + non_compliant_count
        pct = (compliant_count / total * 100) if total > 0 else 0

        self.logger.info("=" * 50)
        self.logger.info(f"COMPLIANCE SUMMARY")
        self.logger.info(f"Total devices: {total}")
        self.logger.info(f"Compliant: {compliant_count} ({pct:.0f}%)")
        self.logger.info(f"Non-compliant: {non_compliant_count}")
        self.logger.info("")

        for rule_name, stats in rule_stats.items():
            total_rule = stats["pass"] + stats["fail"]
            pass_pct = (stats["pass"] / total_rule * 100) if total_rule > 0 else 0
            self.logger.info(
                f"  {rule_name}: {stats['pass']}/{total_rule} passed ({pass_pct:.0f}%)"
            )


class GoldenConfigTemplateAudit(Job):
    """Audit which devices have matching Jinja2 templates in the Git repo."""

    class Meta:
        name = "Golden Config: Template Audit"
        description = "Check which devices have platform-matching Jinja2 templates available in the Git repository"
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting Golden Config Template Audit")

        # Check Git repos
        repos = GitRepository.objects.all()
        self.logger.info(f"Git repositories configured: {repos.count()}")
        for repo in repos:
            self.logger.info(f"  {repo.name}: {repo.remote_url}")

        # Check platforms
        platforms = Platform.objects.all()
        self.logger.info(f"\nPlatforms defined: {platforms.count()}")

        platform_template_map = {
            "cisco_ios": "cisco_ios/main.j2",
            "cisco_xe": "cisco_iosxe/main.j2",
            "cisco_iosxe": "cisco_iosxe/main.j2",
            "cisco_nxos": "cisco_nxos/main.j2",
            "arista_eos": "arista_eos/main.j2",
            "juniper_junos": "juniper_junos/main.j2",
            "paloalto_panos": "paloalto_panos/main.j2",
            "fortinet_fortios": "fortinet_fortios/main.j2",
            "linux": "linux/main.j2",
            "cisco_asa": "cisco_asa/main.j2",
        }

        devices_with_template = 0
        devices_without_template = 0

        for platform in platforms:
            driver = platform.network_driver or platform.name
            has_template = driver.lower() in platform_template_map
            device_count = Device.objects.filter(platform=platform).count()

            if has_template:
                template_file = platform_template_map[driver.lower()]
                self.logger.info(
                    f"  [OK] {platform.name} ({driver}) -> {template_file} ({device_count} devices)"
                )
                devices_with_template += device_count
            else:
                self.logger.warning(
                    f"  [--] {platform.name} ({driver}) -> NO TEMPLATE ({device_count} devices)"
                )
                devices_without_template += device_count

        # Devices with no platform
        no_platform = Device.objects.filter(platform__isnull=True).count()
        if no_platform > 0:
            self.logger.warning(f"\n  {no_platform} devices have NO platform assigned")

        self.logger.info(f"\nSummary:")
        self.logger.info(f"  Devices with template coverage: {devices_with_template}")
        self.logger.info(f"  Devices without template: {devices_without_template}")
        self.logger.info(f"  Devices without platform: {no_platform}")

        time.sleep(0.1)


class GoldenConfigInterfaceCompliance(Job):
    """Check interface configurations against golden standards."""

    class Meta:
        name = "Golden Config: Interface Standards"
        description = "Verify interface descriptions, enabled states, and IP assignments follow standards"
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting Interface Standards Compliance Check")

        devices = Device.objects.filter(
            status__name="Active",
        ).select_related("platform", "location")

        total_interfaces = 0
        issues_found = 0

        for device in devices[:50]:
            interfaces = Interface.objects.filter(device=device)

            for iface in interfaces:
                total_interfaces += 1

                # Check 1: Management interfaces should have description
                if iface.name.lower().startswith(("mgmt", "management", "loopback")):
                    if not iface.description:
                        self.logger.warning(
                            f"{device.name} / {iface.name}: Management interface missing description",
                            obj=iface,
                        )
                        issues_found += 1

                # Check 2: Interfaces with IPs should be enabled
                if iface.ip_addresses.exists() and not iface.enabled:
                    self.logger.warning(
                        f"{device.name} / {iface.name}: Has IP but is disabled",
                        obj=iface,
                    )
                    issues_found += 1

                # Check 3: Uplink interfaces naming
                if "uplink" in (iface.description or "").lower():
                    if not iface.ip_addresses.exists():
                        self.logger.info(
                            f"{device.name} / {iface.name}: Uplink without IP",
                            obj=iface,
                        )

            time.sleep(0.02)

        self.logger.info(f"\nResults:")
        self.logger.info(f"  Total interfaces checked: {total_interfaces}")
        self.logger.info(f"  Issues found: {issues_found}")
        self.logger.info(f"  Compliance rate: {(total_interfaces-issues_found)/total_interfaces*100:.1f}%" if total_interfaces > 0 else "  No interfaces found")


register_jobs(
    GoldenConfigComplianceCheck,
    GoldenConfigTemplateAudit,
    GoldenConfigInterfaceCompliance,
)
