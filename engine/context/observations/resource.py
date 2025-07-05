from .base import BaseObservation
from schemas.resource import Resource


class ResourceObservation(BaseObservation):

    resource: Resource

    def __str__(self) -> str:
        availability = "available" if self.resource.available else "unavailable"
        observation = (
            f"[ID: {self.id}; "
            f"type: {self.get_observation_type()}; "
            f"location: {self.location}; "
            f"distance: {self.distance}; "
            f"energy yield: {self.resource.energy_yield}; "
            f"mining time: {self.resource.mining_time}; "
            f"{availability}]"
        )

        if self._check_harvest_possible():
            observation += self._harvest_possible()
        else:
            observation += self._harvest_not_possible()

        return observation

    def _check_harvest_possible(self) -> bool:
        """Check if the can be harvested by the agent under current conditions"""
        if self.distance > self.resource.harvesting_area:
            return False
        elif (
            self.resource.being_harvested
            and len(self.resource.harvesters) >= self.resource.required_agents
        ):
            return False
        elif len(self.resource.harvesters) == 0 and self.resource.required_agents > 1:
            return False
        elif not self.resource.available:
            return False
        else:
            return True

    def _harvest_possible(self) -> str:
        """Message to be sent to the agent if the resource can be harvested"""
        resource_message = ""

        if self.resource.being_harvested:
            resource_message = f""" This resource is currently harvested by {len(self.resource.harvesters)} agent(s)
                                  and requires only ONE additional harvester."""
        else:
            resource_message = (
                f""" This resource is directly available for harvesting!"""
            )

        return resource_message

    def _harvest_not_possible(self) -> str:
        """Message to be sent to the agent if the resource cannot be harvested"""
        # Resource is not available
        if not self.resource.available:
            return f""" This resource is currently NOT available for harvesting!"""
        # Resource is out of range
        if self.distance > self.resource.harvesting_area:
            return f""" The resource is too far away to harvest! (you have to be within {self.resource.harvesting_area} units)"""
        # Resource is being harvested by enough agents
        if (
            self.resource.being_harvested
            and len(self.resource.harvesters) >= self.resource.required_agents
        ):
            return f""" The resource is currently harvested by {len(self.resource.harvesters)} agent(s)
                        and is therefore not available."""
        if len(self.resource.harvesters) == 0 and self.resource.required_agents > 1:
            return f""" The resource is currently not harvested by anybody
                        but requires {self.resource.required_agents} harvester."""

        return f""" The resource is currently NOT available for harvesting!"""
