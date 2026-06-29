from .device_audit import DeviceAudit
from .bulk_onboard import BulkOnboard
from .interface_standardization import InterfaceStandardization
from .ip_allocation import IPAllocation
from .inventory_validation import InventoryValidation

from nautobot.apps.jobs import register_jobs

register_jobs(DeviceAudit, BulkOnboard, InterfaceStandardization, IPAllocation, InventoryValidation)
