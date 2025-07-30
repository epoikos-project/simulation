from .base import BaseObservation

from schemas.resource import Resource


class ResourceObservation(BaseObservation):

    resource: Resource

    def __str__(self) -> str:
        if self.resource.available:
            observation = (
                f"[resource_id: {self.id}; "
                f"type: {self.get_observation_type()}; "
                f"location: {self.location}; "
                f"distance: {self.distance}; "
                f"energy yield: {self.resource.energy_yield}; "
                f"required agents: {self.resource.required_agents}; "
                # f"regrow time: {self.resource.regrow_time}; "
                f"available]"
            )

            if self._check_harvest_possible():
                observation += self._harvest_possible()
            else:
                observation += self._harvest_not_possible()

            return observation
        return ""

    def _check_harvest_possible(self) -> bool:
        """Check if the can be harvested by the agent under current conditions"""
        if self.distance > self.resource.harvesting_area:
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

        if len(self.resource.harvesters) > 0:
            resource_message = f""" This resource is currently harvested by {len(self.resource.harvesters)} agent(s)
                                  and requires only ${self.resource.required_agents - len(self.resource.harvesters)} additional harvester(s)."""
        else:
            if self.resource.required_agents > 1:
                resource_message = f""" This resource is currently not harvested by anybody but requires {self.resource.required_agents} harvester(s)."""
            else:
                resource_message = f""" This resource is directly available for harvesting! You do not need to move any futher to harvest it."""

        return resource_message

    def _harvest_not_possible(self) -> str:
        """Message to be sent to the agent if the resource cannot be harvested"""

        message = ""
        # Resource is not available
        if not self.resource.available:
            return f""" This resource is currently NOT available for harvesting!"""
        # Resource is out of range
        if self.distance > self.resource.harvesting_area:
            message += f""" You have to be within {self.resource.harvesting_area} units to harvest this resource. Move closer to harvest it!"""
        # Resource is not harvested by enough agents
        if len(self.resource.harvesters) == 0 and self.resource.required_agents > 1:
            message = f""" The resource is currently not harvested by anybody but requires {self.resource.required_agents} harvester."""

        return message
