"""Platform-wide constants shared across middleware and services."""

ROLE_LEVEL: dict[str, int] = {
    "Admin": 4,
    "EditorInChief": 3,
    "Designer": 2,
    "Editor": 2,
    "User": 1,
}
