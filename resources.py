from collections import Counter


INITIAL_RESOURCES = {
    "Ambulance": 2,
    "Rescue Boat": 1,
    "Fire Truck": 1,
    "Generator": 1,
    "Medical Team": 2,
    "Rescue Team": 2,
}


def get_available_resources(allocations):
    """Calculate remaining resources from current assignments."""

    used = Counter(
        item["resource"]
        for item in allocations
    )

    return {
        resource: max(
            0,
            quantity - used[resource]
        )
        for resource, quantity in INITIAL_RESOURCES.items()
    }


def allocate_resource(
    resource,
    incident,
    allocations
):
    """Allocate one resource unit if available."""

    incident = incident.strip()

    if resource not in INITIAL_RESOURCES:
        return False, "Unknown resource."

    if not incident:
        return False, "Enter an incident or location."

    available = get_available_resources(
        allocations
    )

    if available[resource] <= 0:
        return (
            False,
            f"No {resource} units remain available."
        )

    allocations.append(
        {
            "resource": resource,
            "incident": incident
        }
    )

    return (
        True,
        f"{resource} assigned to {incident}."
    )


def release_resource(
    index,
    allocations
):
    """Release an allocated resource."""

    if 0 <= index < len(allocations):
        return allocations.pop(index)

    return None