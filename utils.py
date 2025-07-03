def compute_distance(a: tuple[int, int], b: tuple[int, int]):
    """Compute distance between two coordinates in 2D space"""
    # Using Manhattan distance formula
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def compute_distance_raw(
    x_coord_a: int, y_coord_a: int, x_coord_b: int, y_coord_b: int
):
    """Compute distance between two coordinates in 2D space"""
    # Using Manhattan distance formula
    return abs(x_coord_a - x_coord_b) + abs(y_coord_a - y_coord_b)
