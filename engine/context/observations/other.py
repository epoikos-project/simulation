from .base import BaseObservation


class OtherObservation(BaseObservation):
    def __str__(self) -> str:
        return (
            f"[type: {self.type.value}; "
            f"location: {self.location}; "
            f"distance: {self.distance}]"
        )
