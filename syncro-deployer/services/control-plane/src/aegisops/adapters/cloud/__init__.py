"""Multi-cloud adapters exports."""

from aegisops.adapters.cloud.aws_provider import AwsCloudAdapter
from aegisops.adapters.cloud.azure_provider import AzureCloudAdapter
from aegisops.adapters.cloud.cloud_registry import MultiCloudRegistry
from aegisops.adapters.cloud.gcp_provider import GcpCloudAdapter
from aegisops.adapters.cloud.vm_catalog import VM_CATALOG

__all__ = [
    "VM_CATALOG",
    "AwsCloudAdapter",
    "AzureCloudAdapter",
    "GcpCloudAdapter",
    "MultiCloudRegistry",
]
