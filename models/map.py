import pathfind


class Map:
    """Interface for 2D map objects and finding the shortest
    path for an agent's location and destination."""

    def __init__(self, size_x: int, size_y: int):
        """Initialize the map with the given size."""
        self.size_x = size_x
        self.size_y = size_y

        self.map = [[0 for _ in range(size_x)] for _ in range(size_y)]
        for i in range(size_x):
            for j in range(size_y):
                # Initialize each cell as unwalkable (-1)
                # Map is later updated with field of view of agent
                self.map[i][j] = -1

        self.graph: pathfind.transform.matrix2graph = None

    def set_agent_field_of_view(
        self, agent: tuple[int, int], fov: int, obstacles: list[tuple[int, int]]
    ):
        """Set the field of view of an agent."""
        x, y = agent
        for i in range(max(0, x - fov - 1), min(self.size_x, x + fov)):
            for j in range(max(0, y - fov - 1), min(self.size_y, y + fov)):
                if (i, j) not in obstacles:
                    # All cells in field of view that are not an obstacle are walkable (1)
                    self.map[i][j] = 1

        # Update the graph with the new map
        print(self.map)
        self.graph = pathfind.transform.matrix2graph(self.map, diagonal=False)

    def _convert_coordinate(self, c: str) -> tuple[int, int]:
        """Convert a coordinate-String to a tuple of integers."""
        if not isinstance(c, str):
            raise ValueError("Coordinate must be a string.")
        tmp = c.split(",")
        if len(tmp) != 2:
            raise ValueError("Coordinate must be in the format 'x,y'.")

        x = int(tmp[0].strip())
        y = int(tmp[1].strip())

        return (x, y)

    def _convert_path(self, path: list[str]) -> list[tuple[int, int]]:
        """Convert path of coordinate-Strings to a list of tuples of integers."""
        if not isinstance(path, list):
            raise ValueError("Path must be a list.")
        return [self._convert_coordinate(c) for c in path]

    def get_path(
        self,
        start_str: str = None,
        end_str: str = None,
        start_int: tuple[int, int] = None,
        end_int: tuple[int, int] = None,
    ) -> tuple[list[tuple[int, int]], int]:
        """Get the path from start to end using Jump Point Search (JPS)."""

        try:
            start = start_str if start_str else f"{start_int[0]},{start_int[1]}"
            end = end_str if end_str else f"{end_int[0]},{end_int[1]}"
        except ValueError:
            raise ValueError(
                "Start and End must be either in the format 'x,y' or as tuple [x,y]."
            )

        print(self.graph)
        path = pathfind.find(self.graph, start, end, method="jps")

        return self._convert_path(path), len(path)
