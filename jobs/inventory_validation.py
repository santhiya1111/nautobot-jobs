"""Inventory Validation Job — cross-check data quality rules.

Module 7, Exercise 1 (Slide 18): Inventory Validation Use Case
Nautobot 40-Hour Training Program (Techademy)
"""

from nautobot.apps.jobs import Job, ObjectVar, BooleanVar, ChoiceVar
from nautobot.dcim.models import Device, Location


class InventoryValidation(Job):
    """Validate device inventory against organizational standards."""

    class Meta:
        name = "Inventory Validation Report"
        description = "Cross-check devices against naming conventions, required fields, and organizational rules"
        has_sensitive_variables = False

    location = ObjectVar(
        model=Location,
        required=False,
        description="Filter by location (leave blank for all)",
    )
    severity = ChoiceVar(
        choices=(
            ("all", "All Issues"),
            ("critical", "Critical Only"),
            ("warning", "Warnings & Critical"),
        ),
        default="all",
        description="Minimum severity to report",
    )
    dry_run = BooleanVar(
        default=True,
        description="Report only — no changes",
    )

    RULES = [
        {
            "name": "Primary IP Required",
            "severity": "critical",
            "check": lambda d: bool(d.primary_ip4 or d.primary_ip6),
            "message": "no primary IP address assigned",
        },
        {
            "name": "Serial Number Required",
            "severity": "warning",
            "check": lambda d: bool(d.serial and d.serial.strip()),
            "message": "serial number is empty",
        },
        {
            "name": "Role Assigned",
            "severity": "critical",
            "check": lambda d: bool(d.role),
            "message": "no device role assigned",
        },
        {
            "name": "Platform Assigned",
            "severity": "warning",
            "check": lambda d: bool(d.platform),
            "message": "no platform assigned (needed for automation)",
        },
        {
            "name": "Device Type Set",
            "severity": "critical",
            "check": lambda d: bool(d.device_type),
            "message": "no device type assigned",
        },
        {
            "name": "Status is Active",
            "severity": "warning",
            "check": lambda d: d.status and d.status.name in ("Active", "Staged", "Planned"),
            "message": lambda d: f"status is '{d.status.name if d.status else 'None'}' - review needed",
        },
    ]

    def run(self, location=None, severity="all", dry_run=True):
        devices = Device.objects.select_related(
            "role", "platform", "device_type", "status", "location",
            "primary_ip4", "primary_ip6",
        ).all()

        if location:
            devices = devices.filter(location=location)
            self.logger.info(f"Validating {devices.count()} devices at {location.name}")
        else:
            self.logger.info(f"Validating ALL {devices.count()} devices")

        severity_order = {"critical": 0, "warning": 1, "all": 2}
        min_severity = severity_order.get(severity, 2)

        results = {"critical": 0, "warning": 0, "pass": 0}
        device_scores = {}

        for device in devices:
            device_issues = []

            for rule in self.RULES:
                rule_severity = rule["severity"]
                if severity_order.get(rule_severity, 2) > min_severity:
                    continue

                passed = rule["check"](device)
                if not passed:
                    msg = rule["message"]
                    if callable(msg):
                        msg = msg(device)

                    device_issues.append({
                        "rule": rule["name"],
                        "severity": rule_severity,
                        "message": msg,
                    })
                    results[rule_severity] = results.get(rule_severity, 0) + 1

            if device_issues:
                for issue in device_issues:
                    log_method = self.logger.failure if issue["severity"] == "critical" else self.logger.warning
                    log_method(
                        f"{device.name}: [{issue['severity'].upper()}] {issue['message']}",
                    )
                device_scores[device.name] = len(device_issues)
            else:
                results["pass"] += 1
                self.logger.success(f"{device.name}: all validation checks passed")
                device_scores[device.name] = 0

        total = devices.count()
        pass_rate = (results["pass"] / total * 100) if total > 0 else 0

        self.logger.info(
            f"Validation complete: {total} devices, "
            f"{results['pass']} passed ({pass_rate:.1f}%), "
            f"{results.get('critical', 0)} critical, "
            f"{results.get('warning', 0)} warnings"
        )

        if results.get("critical", 0) > 0:
            self.logger.failure(
                f"ACTION REQUIRED: {results['critical']} critical issues found"
            )

        worst = sorted(device_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        if worst and worst[0][1] > 0:
            self.logger.info("Top devices needing attention:")
            for name, count in worst:
                if count > 0:
                    self.logger.info(f"  {name}: {count} issue(s)")
