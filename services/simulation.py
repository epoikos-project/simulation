from sqlmodel import select

from schemas.simulation import Simulation as SimulationModel
from services.base import BaseMilvusService


class SimulationService(BaseMilvusService[SimulationModel]):

    def get_simulations(self) -> list[SimulationModel]:
        """
        Retrieve all simulations from the database.
        """
        statement = select(SimulationModel)
        models = self._db.exec(statement).all()
        return models

    def save_simulation(self, simulation: SimulationModel) -> None:
        """
        Save the simulation to the database.
        """
        self._db.add(simulation)
        self._db.commit()
        self._db.refresh(simulation)
