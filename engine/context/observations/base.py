from pydantic import BaseModel


class BaseObservation(BaseModel):
    location: tuple[int, int]
    distance: int
    id: str

    def get_observation_type(self) -> str:
        """Return the type of the observation."""
        return self.__class__.__name__
